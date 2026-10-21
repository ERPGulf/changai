from __future__ import annotations
from typing import Any, Dict, List, Optional, Set, Tuple
import datetime
import gc
import json
import os
import time
from sentence_transformers import SentenceTransformer
from langchain_community.vectorstores import FAISS
from langchain_core.embeddings import Embeddings
import yaml
import frappe
from frappe import _
from changai.changai.api.v2.build_cards_faiss_index_v2 import build_schema_fvs_job,build_master_data_fvs_job,build_table_fvs_job,_generate_table_description
from frappe.utils import now_datetime, add_to_date
from anthropic import Anthropic
import openai
import math
from pathlib import Path
from changai.changai.api.v2.schema_utils import convert_yaml_schema_to_sqlglot_meta
from frappe.utils.file_manager import get_file
from changai.changai.api.v2.clients import call_model
from changai.changai.api.v2.train_data_api import _get_openai_client
JSON_EXT = ".json"
SCHEMA_YAML = "schema.yaml"
YAML_EXT = ".yaml"
RAG_FOLDER = "Home/RAG Sources"

def ensure_file_folder(folder_path: str, is_private: int = 1) -> str:
    """
    Ensure a File folder path like 'Home/RAG Sources' exists.
    Returns the full folder path.
    """
    if not folder_path:
        return "Home"
    parts = [p.strip() for p in folder_path.split("/") if p.strip()]
    if not parts:
        return "Home"
    current_path = parts[0]
    # Usually Home already exists, but keep this safe.
    if not frappe.db.exists("File", current_path):
        frappe.get_doc({
            "doctype": "File",
            "file_name": parts[0],
            "is_folder": 1,
            "folder": "",
            "is_private": is_private,
        }).insert(ignore_permissions=True)
    for part in parts[1:]:
        next_path = f"{current_path}/{part}"
        if not frappe.db.exists("File", next_path):
            frappe.get_doc({
                "doctype": "File",
                "file_name": part,
                "is_folder": 1,
                "folder": current_path,
                "is_private": is_private,
            }).insert(ignore_permissions=True)
        current_path = next_path
    return current_path


def get_mod(app_names: list[str]):
    if isinstance(app_names, str):
        app_names = frappe.parse_json(app_names)
    return [
        module 
        for app in app_names 
        for module in frappe.get_all("Module Def", filters={"app_name": app}, pluck="name")
    ]

EXCLUDED_FIELDTYPES: Set[str] = {
    # Layout / Structure — no data value
    "Section Break",
    "Column Break",
    "Tab Break",
    "Fold",
    "Heading",
    "HTML",
    "HTML Editor",
    "Markdown Editor",
    "Read Only",
    "Image",
    "Icon",
    "Button",
    "Attach",
    "Attach Image",
    "Signature",
    "Geolocation",
    "Barcode",
    "Color",
}

def _get_file_doc_by_name(file_name: str, folder: str = RAG_FOLDER) -> Optional["frappe.model.document.Document"]:
    file_id = frappe.db.get_value("File", {"file_name": file_name, "folder": folder}, "name")
    if not file_id:
        return None
    return frappe.get_doc("File", file_id)

def _read_filedoctype(file_name: str, folder: str = RAG_FOLDER):
    doc = _get_file_doc_by_name(file_name, folder)
    if not doc:
        if file_name.endswith(JSON_EXT):
            return []
        if file_name.endswith((YAML_EXT, ".yml")):
            return {}
        return ""
    raw = doc.get_content() or ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if file_name.endswith(JSON_EXT):
        return json.loads(raw or "[]")
    if file_name.endswith((YAML_EXT, ".yml")):
        obj = yaml.safe_load(raw) or {}
        return obj if isinstance(obj, dict) else {}
    return raw
def write_filedoctype(
    file_name: str,
    payload: Any,
    folder: str = "Home/RAG Sources",
    is_private: int = 1
):
    folder = ensure_file_folder(folder, is_private=is_private)
    if file_name.endswith(JSON_EXT):
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    elif file_name.endswith((YAML_EXT, ".yml")):
        text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    else:
        text = str(payload)
    content = text.encode("utf-8")
    existing = frappe.db.get_value(
        "File",
        {"file_name": file_name, "folder": folder},
        "name"
    )
    if existing:
        doc = frappe.get_doc("File", existing)
        frappe.logger().info(f"Overwriting {file_name} -> file_url={doc.file_url}")
        doc.save_file(content=content, overwrite=True)
        doc.save(ignore_permissions=True)
        doc.reload()
        return doc
    doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "folder": folder,
        "is_private": is_private,
        "content": content,
    }).insert(ignore_permissions=True)
    return doc
def _tab(dt: str) -> str:
    dt = (dt or "").strip()
    return f"tab{dt}"


def _strip_tab(t: str) -> str:
    t = (t or "").strip()
    return t[3:] if t.startswith("tab") else t


def _normalize_master_data_payload(payload: Any) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not isinstance(payload, dict):
        payload = {}
    meta = payload.get("_meta") or {}
    data = payload.get("data") or []
    if not isinstance(meta, dict):
        meta = {}
    if not isinstance(data, list):
        data = []
    return meta, data


def _build_master_data_row(entity_type: str, entity_id:str,doc_name:str, title_field:str,filter: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "doc_name": doc_name or entity_id,
        "filters": filter or {"field": title_field if title_field else "name", "value": entity_id},
    }

def _clean_schema_fields(by_table: Dict[str, Dict[str, Any]]) -> None:
    for block in by_table.values():
        for field in block.get("fields", []) or []:
            if not isinstance(field, dict):
                continue
            if field.get("fieldtype") != "Select":
                field.pop("options", None)
            if field.get("fieldtype") != "Link":
                field.pop("join_hint", None)
            # ✅ Add this — preserve child_hint only for Table fields
            if field.get("fieldtype") not in ("Table", "Table MultiSelect"):
                field.pop("child_hint", None)


def get_doctypes_changed_since(last_sync: Optional[str],erpnext_modules: Optional[List[str]] = None) -> List[str]:
    if erpnext_modules is None:
        app_names=["erpnext","frappe"]
        erpnext_modules = get_mod(app_names)
    filters = {
    "module": ["in", erpnext_modules],
    "issingle": 0,
    "is_virtual": 0,
}
    if last_sync:
        try:
            since = add_to_date(last_sync, minutes=-2)
            filters["modified"] = [">=", since]  # catches updated tables
        except Exception:
            pass
    results = frappe.get_all("DocType", filters=filters, pluck="name")
    # Also catch newly created DocTypes since last sync
    if last_sync:
        try:
            since = add_to_date(last_sync, minutes=-2)
            new_doctypes = frappe.get_all(
                "DocType",
                filters={
                    "module": ["in", erpnext_modules],
                    "issingle": 0,
                    "is_virtual": 0,
                    "creation": [">=", since],
                },
                pluck="name",
            )
            results = list(set(results) | set(new_doctypes))
        except Exception:
            pass
    return results
TABLES_JSON = "tables.json"
YML_EXTENSIONS = (".yaml", ".yml")
REPORTS_JSON = "reports.json"

def _normalize_schema_payload(payload: Any) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not isinstance(payload, dict):
        return {}, []
    meta = payload.get("_meta") or {}
    tables_blocks = payload.get("tables") or []
    if not isinstance(meta, dict):
        meta = {}
    if not isinstance(tables_blocks, list):
        tables_blocks = []
    return meta, tables_blocks


def _build_table_map(tables_blocks: List[Any]) -> Dict[str, Dict[str, Any]]:
    return {
        block.get("table"): block
        for block in tables_blocks
        if isinstance(block, dict) and block.get("table")
    }


def _get_changed_doctypes(last_sync_raw: Optional[str],erpnext_modules: Optional[List[str]] = None) -> List[str]:
    if not last_sync_raw:
        return []
    return get_doctypes_changed_since(last_sync_raw,erpnext_modules)


def _get_existing_fields_for_table(by_table: Dict[str, Dict[str, Any]], table: str) -> Dict[str, Dict[str, Any]]:
    table_block = by_table.get(table) or {}
    return {
        field.get("name"): field
        for field in table_block.get("fields", [])
        if isinstance(field, dict) and field.get("name")
    }


def _merge_select_options(live_options_raw: str, existing_options: Any) -> List[str]:
    live_options = [opt.strip() for opt in live_options_raw.split("\n") if opt.strip()]
    if isinstance(existing_options, str):
        existing_options = [opt.strip() for opt in existing_options.split("\n") if opt.strip()]
    elif not isinstance(existing_options, list):
        existing_options = []
    return list(dict.fromkeys(live_options + existing_options))


def _build_fields_from_meta(
    meta_dt: Any,
    existing_fields: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    fields: List[Dict[str, Any]] = []
    added_fieldnames = set()
    for field_meta in meta_dt.fields:
        fieldname = (getattr(field_meta, "fieldname", None) or "").strip()
        fieldtype = (getattr(field_meta, "fieldtype", None) or "").strip()
        if not fieldname:
            continue
        if fieldname in added_fieldnames:
            continue
        if fieldtype in EXCLUDED_FIELDTYPES:
            continue
        field_entry = _build_field_entry(field_meta, existing_fields, meta_dt.name)
        if field_entry:
            fields.append(field_entry)
            added_fieldnames.add(field_entry["name"])
    return fields


def _update_or_create_table_block(
    by_table: Dict[str, Dict[str, Any]],
    table: str,
    fields: List[Dict[str, Any]],
) -> None:
    block = by_table.setdefault(table, {})
    block["table"] = table
    block.setdefault("description", "")
    block.setdefault("grain", "")
    block["fields"] = fields
    block["desc_done"] = not _has_pending_descriptions(fields)

def _build_field_entry(
    field_meta: Any,
    existing_fields: Dict[str, Dict[str, Any]],
    source_doctype: str,
) -> Optional[Dict[str, Any]]:
    if isinstance(field_meta, dict):
        fieldname = field_meta.get("fieldname")
        fieldtype = field_meta.get("fieldtype", "Data")
        label = field_meta.get("label") or fieldname
        options = field_meta.get("options")
    else:
        fieldname = getattr(field_meta, "fieldname", None)
        fieldtype = getattr(field_meta, "fieldtype", "Data")
        label = getattr(field_meta, "label", None) or fieldname
        options = getattr(field_meta, "options", None)

    if not fieldname:
        return None

    existing = existing_fields.get(fieldname) or {}
    description = existing.get("description") or ""

    entry = {
        "name": fieldname,
        "fieldtype": fieldtype,
        "label": label,
        "description": description,
    }

    if fieldtype == "Select" and options:
        entry["options"] = _merge_select_options(
            options,
            existing.get("options", []),
        )

    elif fieldtype == "Link" and options:
        entry["join_hint"] = {
            "table": f"tab{options}",
            "on": f"{fieldname} = tab{options}.name"
        }

    elif fieldtype in ("Table", "Table MultiSelect") and options:
        entry["child_hint"] = {
            "child_table": f"tab{options}",
            "fieldname": fieldname,
            "join_rules": {
                "parent": "parent document name",
                "parenttype": "parent DocType",
                "parentfield": fieldname
            }
        }
    if fieldtype != "Select":
        entry.pop("options", None)
    if fieldtype != "Link":
        entry.pop("join_hint", None)
    if fieldtype not in ("Table", "Table MultiSelect"):
        entry.pop("child_hint", None)

    return entry


def _write_schema_outputs(
    meta: Dict[str, Any],
    by_table: Dict[str, Dict[str, Any]],
    table_dict_with_desc: List[Dict[str,Any]],
) -> None:
    reports = []
    current_table_names = [row.get("table") for row in table_dict_with_desc if isinstance(row, dict) and row.get("table")]
    ordered_blocks = [by_table[t] for t in current_table_names if t in by_table]
    reports = frappe.get_all("Report",fields=["name","report_name","ref_doctype"])
    write_filedoctype(
        SCHEMA_YAML,
        {"_meta": meta, "tables": ordered_blocks},
        folder=RAG_FOLDER,
    )
    write_filedoctype(TABLES_JSON, table_dict_with_desc, folder=RAG_FOLDER)  
    write_filedoctype(
        REPORTS_JSON,
        reports,
        folder=RAG_FOLDER,
    )


def _has_pending_descriptions(fields: List[Dict[str, Any]]) -> bool:
    return any(
        not (field.get("description") or "").strip()
        for field in fields
        if isinstance(field, dict) and field.get("name")
    )

def _infer_grain_label(meta_dt: Any, table: str) -> str:

    if meta_dt.istable:
        return f"GRAIN: 1 row per parent document + idx (child table of {table}). Comparison-ready across parent records."
    return f"GRAIN: 1 row per {_strip_tab(table)} document (master/transaction). Use only for single-entity lookups, not cross-record comparison unless fields are per-relationship (e.g. supplier, price_list)."


def _process_schema_table(table: str, by_table: Dict[str, Dict[str, Any]]) -> bool:
	dt = _strip_tab(table)
	if not frappe.db.exists("DocType", dt):
		return False

	frappe.clear_cache(doctype=dt)
	meta_dt = frappe.get_meta(dt)
	block = by_table.setdefault(table, {})
	block.setdefault("table", table)   # ← insert this first, so "table:" is always the leading key
	block["is_table"] = bool(meta_dt.istable)
	block["grain"] = _infer_grain_label(meta_dt, table)
	existing_fields = _get_existing_fields_for_table(by_table, table)
	fields = _build_fields_from_meta(meta_dt, existing_fields)
	_update_or_create_table_block(by_table, table, fields)
	return True



def fill_missing_field_descriptions(
    batch_size: int = 15,
    max_tables: int = 0,
    checkpoint_every_table: int = 10,
) -> Dict[str, Any]:
    payload = _read_filedoctype(SCHEMA_YAML)
    meta = payload.get("_meta") or {}
    tables_blocks = payload.get("tables") or []

    if not isinstance(tables_blocks, list):
        return {"ok": False, "message": _("schema.yaml invalid")}

    # client = _get_claude_client()
    # if not client:
    #     return {"ok": False, "message": _("Claude API key missing")}
    updated_tables = 0
    updated_fields = 0
    processed_updated_tables = 0
    tables_since_last_save = 0
    consecutive_errors = 0

    for block in tables_blocks:
        _reset_frappe_local_cache()

        result = _process_table_for_missing_descriptions(
            # client=client,
            block=block,
            batch_size=batch_size,
        )

        updated_in_table = result["updated_in_table"]
        updated_fields += result["updated_fields"]
        consecutive_errors = result["consecutive_errors"]

        if updated_in_table:
            updated_tables += 1
            processed_updated_tables += 1
            tables_since_last_save += 1

        if tables_since_last_save >= checkpoint_every_table:
            _save_schema_checkpoint(meta, tables_blocks)
            tables_since_last_save = 0
            gc.collect()

        if consecutive_errors > 5:
            frappe.logger().error("Stopping job: Too many consecutive API errors.")
            break

        if max_tables and processed_updated_tables >= max_tables:
            break

    meta["last_desc_sync"] = str(now_datetime())
    _save_schema_checkpoint(meta, tables_blocks)
    return {
        "ok": True,
        "tables_updated": updated_tables,
        "fields_updated": updated_fields,
        "status": "Complete" if consecutive_errors <= 5 else "Partial Failure",
    }
from changai.changai.api.v2.build_cards_faiss_index_v2 import enrich_tables_descriptions

def sync_tables_and_schema_smart() -> Dict[str, Any]:
    payload = _read_filedoctype(SCHEMA_YAML, RAG_FOLDER)
    meta, tables_blocks = _normalize_schema_payload(payload)
    by_table = _build_table_map(tables_blocks)
    last_sync_raw = meta.get("last_sync")
    app_names=["erpnext","frappe"]
    erpnext_modules = get_mod(app_names)
    changed_doctypes = _get_changed_doctypes(last_sync_raw,erpnext_modules)
    current_doctypes = frappe.get_all(
    "DocType",
    filters={
        "module": ["in", erpnext_modules],
        "issingle": 0,
        "is_virtual": 0,
    },
    pluck="name",
)
    current_tables = sorted(_tab(dt) for dt in current_doctypes)

    changed_tables = {_tab(dt) for dt in changed_doctypes}
    missing_from_schema = {t for t in current_tables if t not in by_table}

    tables_to_process = sorted(changed_tables | missing_from_schema)
    table_dict_with_desc = enrich_tables_descriptions(current_tables)

    for table in tables_to_process:
        _process_schema_table(table, by_table)

    valid_doctypes = set(current_doctypes)

    by_table = {
        table: block
        for table, block in by_table.items()
        if _strip_tab(table) in valid_doctypes
    }
    _clean_schema_fields(by_table)
    meta["last_sync"] = str(now_datetime())
    settings = frappe.get_single("ChangAI Settings")
    settings.last_schema_sync = meta["last_sync"]
    settings.save(ignore_permissions=True)

    try:
        _write_schema_outputs(meta, by_table, table_dict_with_desc)
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), str(e))
        return {"ok": False, "error": str(e)}
    return {
        "ok": True,
        "changed_tables": len(changed_tables),
        "missing_added": len(missing_from_schema),
        "total_tables": len(current_tables),
    }
def _get_claude_client() -> Optional[Anthropic]:
    
    settings = frappe.get_single("ChangAI Settings")
    api_key = None
    try:
        api_key = settings.get_password("claude_api_key")
    except Exception:
        api_key = None

    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        frappe.logger().error("Claude API key missing. Set ChangAI Settings claude_api_key or env ANTHROPIC_API_KEY.")
        return None

    return Anthropic(api_key=api_key)


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text or not str(text).strip():
        return None
    text = str(text).strip()

    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            obj = json.loads(candidate)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

    return None

def _get_field_names(fields: List[Dict[str, Any]]) -> List[str]:
    return [
        field.get("name")
        for field in fields
        if isinstance(field, dict) and field.get("name")
    ]


def _build_desc_prompt(table_name: str, field_names: List[str]) -> str:
    return f"""
Generate SHORT, HIGH-SIGNAL ERP field descriptions for embedding retrieval.

Table: {table_name}

Rules:
- Do NOT rename fields.
- 1 sentence per field.
- Focus on WHEN/WHY this field is used in business questions.
- Output ONLY JSON object: {{"field_name": "description"}}

Fields:
{json.dumps(field_names, ensure_ascii=False)}
""".strip()


def _extract_claude_text(msg: Any) -> str:
    text_parts: List[str] = []

    for block in getattr(msg, "content", []) or []:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            text_parts.append(block.text)

    return "\n".join(text_parts).strip()


def _normalize_desc_map(parsed: Any) -> Dict[str, str]:
    if not isinstance(parsed, dict):
        return {}

    out: Dict[str, str] = {}
    for key, value in parsed.items():
        if isinstance(key, str) and isinstance(value, str) and key.strip() and value.strip():
            out[key.strip()] = value.strip()
    return out


def _call_claude_desc_map_once(client: Anthropic, prompt: str) -> Any:
    return client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        temperature=0.2,
        system="Return ONLY a JSON object. No markdown. No extra text.",
        messages=[{"role": "user", "content": prompt}],
        timeout=180,
    )


def _smart_desc_map(client: Optional[Anthropic], table_name: str, fields: List[Dict[str, Any]]) -> Dict[str, str]:
    if not client:
        return {}

    field_names = _get_field_names(fields)
    if not field_names:
        return {}

    prompt = _build_desc_prompt(table_name, field_names)

    for attempt in range(3):
        try:
            msg = _call_claude_desc_map_once(client, prompt)
            text = _extract_claude_text(msg)

            parsed = _extract_json_object(text)
            normalized = _normalize_desc_map(parsed)
            if normalized:
                return normalized

            frappe.logger().warning(
                f"Claude returned non-JSON table={table_name} attempt={attempt+1} preview={text[:200]!r}"
            )
        except Exception as e:
            frappe.logger().error(f"Claude error table={table_name} attempt={attempt+1}: {e}")

        time.sleep(2 * (attempt + 1))

    return {}


def _reset_frappe_local_cache() -> None:
    frappe.local.meta_cache = {}
    if hasattr(frappe.local, "docs"):
        frappe.local.docs = {}


def _get_pending_fields(block: Dict[str, Any]) -> List[Dict[str, Any]]:
    fields = block.get("fields") or []
    return [
        field
        for field in fields
        if isinstance(field, dict)
        and field.get("name")
        and not (field.get("description") or "").strip()
    ]


def _mark_table_desc_done(block: Dict[str, Any]) -> None:
    block["desc_done"] = not any(
        isinstance(field, dict) and not (field.get("description") or "").strip()
        for field in block.get("fields", [])
    )


def _save_schema_checkpoint(meta: Dict[str, Any], tables_blocks: List[Dict[str, Any]]) -> None:
    write_filedoctype(
        SCHEMA_YAML,
        {"_meta": meta, "tables": tables_blocks},
        folder=RAG_FOLDER,
    )



def _process_table_for_missing_descriptions(block: Dict[str, Any], batch_size: int) -> Dict[str, int]:
    if not isinstance(block, dict):
        return {"updated_in_table": 0, "updated_fields": 0, "consecutive_errors": 0, "skipped": 1}
    table = block.get("table")
    pending_fields = _get_pending_fields(block)
    if not pending_fields:
        block["desc_done"] = True
        return {"updated_in_table": 0, "updated_fields": 0, "consecutive_errors": 0, "skipped": 0}
    block["desc_done"] = False
    try:
        result = _process_pending_field_batches(table=table, pending_fields=pending_fields, batch_size=batch_size)   # no client=
    except Exception as e:
        frappe.logger().error(f"Critical error in table {table}: {e}")
        return {"updated_in_table": 0, "updated_fields": 0, "consecutive_errors": 1, "skipped": 0}
    if result["updated_in_table"]:
        _mark_table_desc_done(block)
    result["skipped"] = 0
    return result

def _process_pending_field_batches(table: str, pending_fields: List[Dict[str, Any]], batch_size: int) -> Dict[str, int]:
    updated_in_table = 0
    updated_fields = 0
    consecutive_errors = 0
    for i in range(0, len(pending_fields), batch_size):
        batch = pending_fields[i:i + batch_size]
        desc_map = _smart_desc_map_gemini(table, batch)   # was _smart_desc_map(client, table, batch)
        if not desc_map:
            consecutive_errors += 1
            continue
        consecutive_errors = 0
        for field in batch:
            field_name = field.get("name")
            if field_name in desc_map:
                field["description"] = desc_map[field_name].strip()
                updated_fields += 1
                updated_in_table += 1
    return {"updated_in_table": updated_in_table, "updated_fields": updated_fields, "consecutive_errors": consecutive_errors}
def _smart_desc_map_gemini(table_name: str, fields: List[Dict[str, Any]]) -> Dict[str, str]:
    field_names = _get_field_names(fields)
    if not field_names:
        return {}
    prompt = _build_desc_prompt(table_name, field_names)
    system_prompt = "Return ONLY a valid JSON object. No markdown. No extra text."
    for attempt in range(3):
        try:
            response = call_model(prompt, sys_prompt=system_prompt)
            text = (response or "").strip()
            parsed = _extract_json_object(text)
            normalized = _normalize_desc_map(parsed)
            if normalized:
                return normalized
            frappe.logger().warning(f"Gemini returned non-JSON table={table_name} attempt={attempt+1} preview={text[:200]!r}")
        except Exception as e:
            frappe.logger().error(f"Gemini error table={table_name} attempt={attempt+1}: {e}")
        time.sleep(2 * (attempt + 1))
    return {}
def full_schema_rebuild_job():
    res = sync_tables_and_schema_smart()
    if res and res.get("ok"):
        fill_missing_field_descriptions()
        convert_yaml_schema_to_sqlglot_meta()
        build_table_fvs_job()
        build_schema_fvs_job()

SCHEMA_REBUILD_LOCK_KEY = "changai:schema_full_rebuild_pending"
def _schedule_full_schema_rebuild():
    if frappe.cache().get_value(SCHEMA_REBUILD_LOCK_KEY):
        return
    frappe.cache().set_value(SCHEMA_REBUILD_LOCK_KEY, "1", expires_in_sec=14400 + 60)
    frappe.enqueue(
        "changai.changai.api.v2.auto_gen_api.full_schema_rebuild_job",
        queue="long",
        timeout=14400,
    )

def _call_openai_desc_map_once(client, prompt: str):
    return client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Return ONLY a valid JSON object. No markdown. No extra text."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=800,
        timeout=180,
    )

def _smart_desc_map_openai(client, table_name: str, fields: List[Dict[str, Any]]) -> Dict[str, str]:
    if not client:
        return {}
    field_names = _get_field_names(fields)
    if not field_names:
        return {}
    prompt = _build_desc_prompt(table_name, field_names)
    for attempt in range(3):
        try:
            response = _call_openai_desc_map_once(client, prompt)
            text = (response.choices[0].message.content or "").strip()
            parsed = _extract_json_object(text)
            normalized = _normalize_desc_map(parsed)
            if normalized:
                return normalized
            frappe.logger().warning(
                f"OpenAI returned non-JSON table={table_name} attempt={attempt+1} preview={text[:200]!r}"
            )
        except Exception as e:
            frappe.logger().error(f"OpenAI error table={table_name} attempt={attempt+1}: {e}")
        time.sleep(2 * (attempt + 1))
    return {}


MODULES_TO_SYNC = [ 
    "Customer",
    "Supplier",
    "Item",
    "Warehouse",
    "Company",
    "Account"
]


def sync_master_data_smart() -> Dict[str, Any]:
    file_name = "master_data.yaml"
    payload = _read_filedoctype(file_name, RAG_FOLDER)
    meta, data = _normalize_master_data_payload(payload)
    rebuilt_rows: List[Dict[str, Any]] = []
    for mod in MODULES_TO_SYNC:
        entity_type = f"tab{mod}"
        meta_doc = frappe.get_meta(mod)
        title_field = meta_doc.title_field or "name"
        fields = ["name"]
        if title_field != "name":
            fields.append(title_field)
        live_records = frappe.get_all(mod, fields=fields, limit_page_length=0)
        for rec in live_records:
            if mod == "Item":
                item_code = rec.get("name")
                item_name = rec.get(title_field)
                if item_code:
                    filters = [{"field": "item_code", "value": item_code}]
                    if item_name and item_name != item_code:
                        filters.append({"field": "item_name", "value": item_name})
                    rebuilt_rows.append(
                        _build_master_data_row(entity_type, item_code, rec.get("name"), title_field, filters)
                    )
            else:
                entity_id = rec.get(title_field) if title_field in rec else rec.get("name")
                rebuilt_rows.append(
                    _build_master_data_row(entity_type, entity_id, rec.get("name"), title_field, None)
                )
    final_data = rebuilt_rows
    meta["last_sync"] = str(now_datetime())
    settings = frappe.get_single("ChangAI Settings")
    settings.last_masterdata_sync = meta["last_sync"]
    settings.save(ignore_permissions=True)
    payload_out = {"_meta": meta, "data": final_data}
    write_filedoctype(file_name, payload_out, folder=RAG_FOLDER)


def sync_and_rebuild_masterdata():
    try:
        sync_master_data_smart()
        # call vector api
        build_master_data_fvs_job()
    finally:
        frappe.cache().delete_value(MASTERDATA_FULL_SYNC_LOCK_KEY)


MASTERDATA_FULL_SYNC_LOCK_KEY = "changai:masterdata_full_sync_pending"
def schedule_masterdata_full_sync() -> bool:
    """Enqueue a full master data sync unless one is already queued or running."""
    if frappe.cache().get_value(MASTERDATA_FULL_SYNC_LOCK_KEY):
        return False
    frappe.cache().set_value(MASTERDATA_FULL_SYNC_LOCK_KEY, "1", expires_in_sec=1800 + 60)
    frappe.enqueue(
        "changai.changai.api.v2.auto_gen_api.sync_and_rebuild_masterdata",
        queue="long",
        timeout=1800,
    )
    return True


def daily_full_sync():
    # Scheduler: the only automatic sync for master data and schema (there are no doc hooks).
    schedule_masterdata_full_sync()
    _schedule_full_schema_rebuild()


# Settings buttons: full rebuilds on demand.
@frappe.whitelist()
def sync_masterdata_from_ui() -> Dict[str, Any]:
    frappe.has_permission("ChangAI Settings", "write", throw=True)
    if not schedule_masterdata_full_sync():
        return {"ok": True, "message": _("A master data sync is already running.")}
    return {"ok": True, "message": _("Master data sync started in the background.")}


@frappe.whitelist()
def sync_schema_from_ui() -> Dict[str, Any]:
    frappe.has_permission("ChangAI Settings", "write", throw=True)
    if frappe.cache().get_value(SCHEMA_REBUILD_LOCK_KEY):
        return {"ok": True, "message": _("A schema sync is already running.")}
    _schedule_full_schema_rebuild()
    return {"ok": True, "message": _("Schema sync started in the background.")}


#run after migrate - single full scan call
def rebuild_masterdata_after_migrate(doc: Optional[Document] = None, method: Optional[str] = None) -> None:
    try:
        sync_and_rebuild_masterdata()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ChangAI patch: masterdata rebuild failed")
    try:
        full_schema_rebuild_job()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "ChangAI patch: schema rebuild failed")
