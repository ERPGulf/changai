import json
import yaml
import numpy as np
import faiss
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import frappe
from langchain_core.documents import Document
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from changai.changai.api.v2.retrieve import get_embedding_engine
import os
import pickle
from changai.changai.api.v2.non_erp_handler import _safe_open_path


def get_app_fvs_base():
    return os.path.join(
        frappe.get_app_path("changai"),
        "changai", "api", "v2", "fvs_stores", "erpnext"
    )


def get_private_fvs_base():
    return frappe.get_site_path("private", "changai", "fvs_stores", "erpnext")


def _get_fvs_paths() -> tuple:
    app_base = get_app_fvs_base()
    private_base = get_private_fvs_base()

    table_path = os.path.join(app_base, "table_fvs")
    schema_path = os.path.join(app_base, "schema_fvs")
    schema_emb_path = os.path.join(app_base, "emb_dir")
    master_path = os.path.join(private_base, "masterdata_fvs")
    report_path = os.path.join(app_base, "report_fvs")

    for p in (app_base, private_base, table_path, schema_path, master_path, report_path):
        os.makedirs(p, exist_ok=True)

    return app_base, private_base, table_path, schema_path, master_path, schema_emb_path, report_path

RAG_FOLDER = "Home/RAG Sources"
HNSW_M           = 32
EF_CONSTRUCTION  = 256
EF_SEARCH        = 64


def _ensure_folder_exists(folder: str) -> None:
    """
    Ensure all segments of a Frappe folder path exist.
    Creates any missing folders. Safe to call before reads or writes.
    """
    parts = folder.strip("/").split("/")
    current = parts[0]

    for p in parts[1:]:
        exists = frappe.db.exists("File", {
            "file_name": p,
            "folder": current,
            "is_folder": 1,
        })
        if not exists:
            frappe.logger().info(f"Creating missing folder '{p}' inside '{current}'")
            frappe.get_doc({
                "doctype": "File",
                "file_name": p,
                "is_folder": 1,
                "folder": current,
            }).insert(ignore_permissions=True)

        current = f"{current}/{p}"


def _read_file_doc(file_name: str, folder: str = RAG_FOLDER) -> str:
    """
    Read a file from Frappe File DocType.
    Ensures folder exists first (creates if missing), then looks up the file.
    Raises a clear error if the file itself is not found.
    """
    _ensure_folder_exists(folder)
    file_id = frappe.db.get_value(
        "File",
        {"file_name": file_name, "folder": folder},
        "name",
    )
    if not file_id:
        frappe.throw(
            f"File '{file_name}' not found in folder '{folder}'. "
            f"Please upload it before building the index."
        )

    doc = frappe.get_doc("File", file_id)
    content = doc.get_content() or ""
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    return content


def _load_yaml_from_file_doc(file_name: str) -> Any:
    """Load a YAML file from Frappe File DocType."""
    content = _read_file_doc(file_name)
    return yaml.safe_load(content)


def _load_json_from_file_doc(file_name: str) -> Any:
    """Load a JSON file from Frappe File DocType."""
    content = _read_file_doc(file_name)
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        frappe.throw(f"Invalid JSON in {file_name}: {e}")


def _assert_dir_inside_base(dir_path: str, base_dir: str) -> Path:
    base = Path(base_dir).resolve()
    d = Path(dir_path).resolve()
    if base != d and base not in d.parents:
        raise ValueError(f"Unsafe output dir (outside base): {d}")
    return d

def build_report_docs(report_list: List[Dict[str, Any]]) -> List[Document]:
    """
    Build one Document per report name from reports.json.
    reports.json is a flat list: ["Sales Invoice", "Purchase Order", ...]
    """
    docs = []
    for report in report_list:
        report_name = report.get("report_name")
        ref_doctype = report.get("ref_doctype")
        if not isinstance(report_name, str) or not report_name.strip():
            continue
        docs.append(Document(
            page_content=f"{report_name}",
            metadata={
                "type": "report",
                "report_name": report_name,
                "ref_doctype": ref_doctype,
            }
        ))
    return docs

def build_table_docs(table_list: List[str]) -> List[Document]:
    """
    Build one Document per table name from tables.json.
    tables.json is a flat list: ["tabSales Invoice", "tabPurchase Order", ...]
    """
    docs = []
    for table_name in table_list:
        if not isinstance(table_name, str) or not table_name.strip():
            continue
        docs.append(Document(
            page_content=f"[TABLE] {table_name}",
            metadata={
                "type": "table",
                "table": table_name,
            }
        ))
    return docs

def _is_valid_schema_table(table_block: Any) -> bool:
    return isinstance(table_block, dict) and "table" in table_block


def _build_field_metadata(table_name: str, field_name: str, module: str, join_hint: str, options: Any) -> Dict[str, Any]:
    metadata = {
        "type": "field",
        "table": table_name,
        "field": field_name,
        "module": module,
    }
    if options:
        metadata["options"] = options
    if join_hint:
        metadata["join_hint"] = join_hint
    return metadata


def _build_field_page_content(table_name: str, field_name: str, field_desc: str, join_hint: str, options: Any) -> str:
    page_content = f"[FIELD] {field_name} | [TABLE] {table_name}\n{field_desc}"
    if join_hint:
        page_content += f"\n{join_hint}"
    if options:
        page_content += f"\n{options}"
    return page_content

def _build_field_document(table_name: str, module: str, field_row: Dict[str, Any]) -> Optional[Document]:
    if not isinstance(field_row, dict):
        return None

    field_name = field_row.get("name")
    if not field_name:
        return None

    field_desc = field_row.get("description", "") or ""
    join_hint = field_row.get("join_hint") or ""
    child_hint = field_row.get("child_hint") or ""      # ✅ Add this
    options = field_row.get("options") or ""
    fieldtype = field_row.get("fieldtype") or ""        # ✅ Add this
    is_table_field = fieldtype in ("Table", "Table MultiSelect")  # ✅ Add this

    # Build page content
    page_content = f"[FIELD] {field_name} | [TABLE] {table_name}\n{field_desc}"
    if join_hint:
        page_content += f"\n{join_hint}"
    if child_hint and is_table_field:                   # ✅ Add child hint to content
        if isinstance(child_hint, dict):
            page_content += f"\nChild Table: {child_hint.get('child_table', '')}"
        else:
            page_content += f"\n{child_hint}"
    if options:
        page_content += f"\n{options}"

    # Build metadata
    metadata = {
        "type": "field",
        "table": table_name,
        "field": field_name,
        "fieldtype": fieldtype,                         # ✅ Store fieldtype
        "module": module,
    }
    if options:
        metadata["options"] = options
    if join_hint:
        metadata["join_hint"] = join_hint
    if child_hint and is_table_field:                   # ✅ Store child_hint
        metadata["child_hint"] = child_hint

    return Document(
        page_content=page_content,
        metadata=metadata,
    )
GENERIC_FIELDS = {
    'creation', 'modified', 'owner', 'parenttype','old_parent',
    'parentfield', 'parent', 'idx', 'name', 'docstatus'
}

def clean_schema(schema: Dict[str, Any], output_path: str):

    tables = schema.get("tables", [])
    for table_block in tables:
        fields = table_block.get("fields")
        if isinstance(fields, list):
            table_block["fields"] = [
                field for field in fields
                if field.get("name") not in GENERIC_FIELDS
            ]
    allowed_dir = str(Path(output_path).parent.resolve())
    safe = _safe_open_path(output_path, allowed_dir)
    safe.write_text(yaml.dump(schema, allow_unicode=True, sort_keys=False), encoding="utf-8")


def build_schema_docs(schema: Dict[str, Any]) -> List[Document]:
    """
    Build field-level Documents from schema.yaml.
    One Document per field — same method as the notebook.
    """
    docs: List[Document] = []
    tables = schema.get("tables", [])

    if not isinstance(tables, list):
        return docs

    for table_block in tables:
        if not _is_valid_schema_table(table_block):
            continue

        table_name = table_block.get("table")
        module = table_block.get("module", "")
        fields = table_block.get("fields") or []

        if not isinstance(fields, list):
            continue
        
        for field_row in fields:
            field_name = field_row.get("name")
            if field_name in GENERIC_FIELDS:
                continue
                
            doc = _build_field_document(table_name, module, field_row)
            if doc:
                docs.append(doc)

    return docs


def _build_entity_text(md: Dict[str, Any]) -> str:
    text = (md.get("embedding_text") or "").strip()
    if text:
        return text

    entity_type = (md.get("entity_type") or "entity").strip()
    canonical = (md.get("canonical_name") or md.get("entity_id") or "").strip()
    aliases = md.get("aliases") or []
    misspellings = md.get("misspellings") or []

    parts = []

    if canonical:
        parts.append(f"{entity_type.title()}: {canonical}")
    if aliases:
        parts.append(f"Also known as {', '.join(aliases)}")
    if misspellings:
        parts.append(f"Common misspellings: {', '.join(misspellings)}")

    return ". ".join(parts)


def _build_entity_metadata(md: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": "entity",
        "entity_type": md.get("entity_type"),
        "entity_id": md.get('entity_id'),
        "entity_label": f"{md.get('filters', {}).get('field')}:{md.get('filters', {}).get('value')}"
        # "canonical_name": md.get("canonical_name"),
        # "aliases": md.get("aliases", []),
    }


def build_entity_docs(master_data: Dict[str, Any]) -> List[Document]:
    """
    Build entity Documents from master_data.yaml.
    Uses embedding_text if present, else builds from canonical_name + aliases.
    """
    docs = []

    for md in master_data.get("data", []):
        if not isinstance(md, dict):
            continue

        text = _build_entity_text(md)
        if not text:
            continue

        docs.append(
            Document(
                page_content=f"search_document: {text}",
                metadata=_build_entity_metadata(md),
            )
        )

    return docs


def _build_and_save_faiss(
    docs: List[Document],
    out_path: str,
    label: str,
    base_dir: str,
) -> None:
    if not docs:
        frappe.throw(f"No documents to index for: {label}")

    safe_path = _assert_dir_inside_base(out_path, base_dir)
    safe_path.mkdir(parents=True, exist_ok=True)
    emb = get_embedding_engine()

    doc_texts = [d.page_content for d in docs]
    vectors   = emb.embed_documents(doc_texts)

    dim   = len(vectors[0])
    index = faiss.IndexHNSWFlat(dim, HNSW_M)
    index.hnsw.efConstruction = EF_CONSTRUCTION
    index.hnsw.efSearch       = EF_SEARCH
    index.add(np.array(vectors, dtype="float32"))
    store = FAISS(
        embedding_function=emb,
        index=index,
        docstore=InMemoryDocstore({str(i): docs[i] for i in range(len(docs))}),
        index_to_docstore_id={i: str(i) for i in range(len(docs))},
        normalize_L2=True,
    )
    store.save_local(str(safe_path))
    frappe.logger().info(f"[FVS] {label} — {len(docs)} docs | dim={dim} | path={safe_path}")


@frappe.whitelist(allow_guest=False)
def build_all_fvs() -> Dict[str, Any]:
    """
    Enqueues 3 separate background jobs to build FAISS vector stores.
    """
    frappe.enqueue(
        "changai.changai.api.v2.build_cards_faiss_index_v2.build_table_fvs_job",
        queue="long",
        timeout=1800,
    )
    frappe.enqueue(
        "changai.changai.api.v2.build_cards_faiss_index_v2.build_schema_fvs_job",
        queue="long",
        timeout=1800,
    )
    frappe.enqueue(
        "changai.changai.api.v2.build_cards_faiss_index_v2.build_master_data_fvs_job",
        queue="long",
        timeout=1800,
    )
    return {
        "status": "enqueued",
        "message": "All 3 FVS build jobs have been queued. Check Error Logs for progress.",
    }

@frappe.whitelist(allow_guest=False)
def build_table_fvs_job():
    try:
        app_base, _, table_path, _, _,_, report_path = _get_fvs_paths()
        tables_list = _load_json_from_file_doc("tables.json")
        reports_list = _load_json_from_file_doc("reports.json")
        table_docs = build_table_docs(tables_list)
        try:
            report_docs = build_report_docs(reports_list)
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Build Report FVS Failed")
            raise
        _build_and_save_faiss(table_docs, table_path, "ERPNext Table FVS", app_base)
        _build_and_save_faiss(report_docs, report_path, "ERPNext Report FVS", app_base)
        frappe.logger().info(f"ERPNext Table FVS built: {len(table_docs)} docs")
    except Exception :
        frappe.log_error(frappe.get_traceback(), "Build Table FVS Failed")
        raise


def save_field_matrix(schema_docs, base_dir):
    emb = get_embedding_engine()

    texts = [d.page_content for d in schema_docs]
    vectors = emb.embed_documents(texts)

    embs = np.array(vectors, dtype="float32")
    embs = embs / np.clip(
        np.linalg.norm(embs, axis=1, keepdims=True),
        1e-12,
        None
    )

    table_to_idx = {}
    for i, d in enumerate(schema_docs):
        meta = getattr(d, "metadata", {}) or {}
        table = meta.get("table")
        field = meta.get("field")
        if table and field:
            table_to_idx.setdefault(table, []).append(i)

    safe_dir = _assert_dir_inside_base(base_dir, get_app_fvs_base())  # validates path
    safe_dir.mkdir(parents=True, exist_ok=True)

    np.save(safe_dir / "field_embs.npy", embs)
    allowed_dir = str(safe_dir)
    safe_docs = _safe_open_path(str(safe_dir / "field_docs.pkl"), allowed_dir)
    safe_docs.write_bytes(pickle.dumps(schema_docs))

    safe_idx = _safe_open_path(str(safe_dir / "table_to_idx.pkl"), allowed_dir)
    safe_idx.write_bytes(pickle.dumps(table_to_idx))


def build_schema_fvs_job():
    try:
        schema = _load_yaml_from_file_doc("schema.yaml")
        # schema = clean_schema(schema,schema_path)
        schema_docs = build_schema_docs(schema)
        app_base, _, _, schema_path, _,schema_emb_dir, _ = _get_fvs_paths()
        _build_and_save_faiss(schema_docs, schema_path, "ERPNext Schema FVS", app_base)
        save_field_matrix(schema_docs, schema_emb_dir)
        frappe.logger().info(f"ERPNext Schema FVS built: {len(schema_docs)} docs")
    except Exception :
        frappe.log_error(frappe.get_traceback(), "Build Schema FVS Failed")
        raise


def build_master_data_fvs_job():
    try:
        _, private_base, _, _, master_path,_, _ = _get_fvs_paths()
        master_data = _load_yaml_from_file_doc("master_data.yaml")
        entity_docs = build_entity_docs(master_data)
        _build_and_save_faiss(entity_docs, master_path, "ERPNext Master Data FVS", private_base)
        frappe.logger().info(f"ERPNext Master Data FVS built: {len(entity_docs)} docs")
    except Exception :
        frappe.log_error(frappe.get_traceback(), "Build Master Data FVS Failed")
        raise
