import json
import re
from collections import OrderedDict, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import frappe
import sqlglot
import yaml
from frappe import _
from frappe.utils import getdate
from sqlglot import exp, optimizer
from sqlglot.errors import ParseError, OptimizeError
from sqlglot.optimizer.qualify import qualify
from sqlglot.schema import MappingSchema
import jellyfish
from rapidfuzz import fuzz, process
_VALUE_TO_FIELD = {}
CHANGAI_GUIDE_LINK="https://app.erpgulf.com/en/articles/chang-ai-quick-start-guide"
ERPGULF_LINK = "https://app.erpgulf.com/en/products/chang-ai-an-ai-agent"
settingsUrl = frappe.utils.get_url(
    "/app/changai-settings/ChangAI%20Settings"
)
CHANGAI_SETTINGS = "ChangAI Settings"
_ASSETS_DIR = Path(frappe.get_app_path("changai", "changai", "api", "v2", "assets")).resolve()
_PROMPTS_DIR = Path(frappe.get_app_path("changai", "changai", "prompts")).resolve()
_PHONETIC_BUCKETS = defaultdict(list)
_ALLOWED_EXT = {".json", ".yaml",".j2", ".yml", ".txt", ".md"}
RAG_FOLDER = "Home/RAG Sources"
JSON_EXT = ".json"
YAML_EXT = ".yaml"

def get_report_filter_fields(report_name: str):
    try:
        script = get_script(report_name).get("script") or ""
    except Exception:
        return []
    fieldnames = re.findall(
        r'fieldname\s*:\s*["\']([^"\']+)["\']',
        script
    )
    return "|".join(dict.fromkeys(fieldnames))

def match_report_intent(report_intent: str):
    choices = list(REPORT_INTENT_MAP.keys())
    match = process.extractOne(
        report_intent.lower(),
        choices,
        scorer=fuzz.WRatio,
        score_cutoff=75
    )
    if not match:
        return ""
    matched_intent = match[0]
    return REPORT_INTENT_MAP[matched_intent]

def phonetic_bucket():
    global _PHONETIC_BUCKETS, _VALUE_TO_FIELD
    from changai.changai.api.v2.auto_gen_api import _read_filedoctype
    master_data_content = _read_filedoctype("master_data.yaml")
    master_items = master_data_content["data"]
    for item in master_items:
        table = item["entity_type"]
        field = item["filters"]["field"]
        value = item["filters"]["value"]
        _VALUE_TO_FIELD[value] = f"{table}.{field}:{value}"
        first_word = value.split()[0]
        key = jellyfish.metaphone(first_word)
        _PHONETIC_BUCKETS[key].append(value)


@frappe.whitelist(allow_guest=False)
def phonetic_match(isreport: bool, word: str, threshold: int = 60):
    global _PHONETIC_BUCKETS, _VALUE_TO_FIELD
    original_word = word
    candidates = []
    seen = set()
    phonetic_bucket()
    for token in original_word.split():
        if len(token) <= 2:
            continue
        key = jellyfish.metaphone(token)
        for value in _PHONETIC_BUCKETS.get(key, []):
            if value not in seen:
                seen.add(value)
                candidates.append(value)
    if not candidates:
        return {
            "entity_labels": [],
            "reason": "no phonetic candidates found"
        }
    result = process.extract(
        original_word,
        candidates,
        scorer=fuzz.WRatio,
        limit=5,
        score_cutoff=threshold
    )
    results = []
    for match, score, _ in result:
        label = _VALUE_TO_FIELD.get(match)
        if label:
            results.append(label)
    return {
        "entity_labels": results,
        "reason": "phonetic match found"
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


def _load_mapping_data() -> dict:
    return read_asset("metaschema_clean_v2.json")

@frappe.whitelist()
def validate_sql_schema(sql: str, dialect: str = "mysql") -> dict:
    try:
        mapping_data, schema = get_mapping_schema(dialect)

        ast = sqlglot.parse_one(sql, read=dialect)
        used_tables = {table.name for table in ast.find_all(exp.Table)}
        small_mapping = {
            table: mapping_data[table]
            for table in used_tables
            if table in mapping_data
        }

        for table in ast.find_all(exp.Table):
            if table.name and table.name not in mapping_data:
                return {
                    "ok": False,
                    "error": f"Table '{table.name}' does not exist in schema"
                }

        qualified = optimizer.qualify.qualify(
            ast,
            schema=small_mapping,
            dialect=dialect,
            identify=False,
        )

        return {
            "ok": True,
            "qualified_sql": qualified.sql()
        }

    except sqlglot.errors.OptimizeError as e:
        return {"ok": False, "error": str(e)}
    except sqlglot.errors.ParseError as e:
        return {"ok": False, "error": str(e)}

from frappe.utils import add_to_date, today, date_diff, days_diff
MASTER_DOCTYPES = [
    "Customer",
    "Supplier",
    "Item",
    "Warehouse",
    "Company",
    "Account"
]


def is_doctype_schema_changed(doc, last_sync):
    from frappe.utils import get_datetime

    doctype_modified = frappe.db.get_value("DocType", doc, "modified")

    custom_field_modified = frappe.db.sql(
        "SELECT MAX(modified) FROM `tabCustom Field` WHERE dt = %s",
        doc
    )[0][0]

    property_setter_modified = frappe.db.sql(
        "SELECT MAX(modified) FROM `tabProperty Setter` WHERE doc_type = %s",
        doc
    )[0][0]

    candidates = [
        get_datetime(d) for d in [
            doctype_modified,
            custom_field_modified,
            property_setter_modified
        ] if d
    ]

    latest = max(candidates, default=None)
    return bool(latest and last_sync and latest > get_datetime(last_sync))

def is_master_data_changed(last_sync, stored_data: list):
    for doc in MASTER_DOCTYPES:
        meta = frappe.get_meta(doc)
        title_field = meta.title_field or "name"
        entity_type = f"tab{doc}"

        # ✅ Only compare rows matching title_field
        allowed_fields = [f.fieldname for f in meta.fields] + ["name"]
        if title_field not in allowed_fields:
            frappe.log_error(f"Invalid title_field: {title_field}", "is_master_data_changed")
            continue

        live_records = frappe.get_all(
            doc,
            fields=[title_field],
            limit_page_length=0
        )
        live_titles = set()
        for rec in live_records:
            if rec.get(title_field):
                live_titles.add(rec.get(title_field))

        if stored_titles != live_titles:
            return True

    return False

@frappe.whitelist(allow_guest=False)
def check_file_updates(file_name: str):
    RAG_FOLDER = "Home/RAG Sources"
    from changai.changai.api.v2.build_cards_faiss_index_v2 import _read_file_doc
    settings = frappe.get_single("ChangAI Settings")

    if file_name == "master_data.yaml":
        last_sync = settings.last_masterdata_sync
    elif file_name == "schema.yaml":
        last_sync = settings.last_schema_sync
    else:
        frappe.throw(_("Invalid file_name"))

    if not last_sync:
        return {
            "is_stale": False,
            "data": False,
            "days": 0,
            "last_sync": None
        }

    changed = False

    if file_name == "schema.yaml":
        doctypes = frappe.db.get_all("DocType", {"istable": 0}, pluck="name")
        for doc in doctypes:
            if is_doctype_schema_changed(doc, last_sync):
                changed = True
                break

    elif file_name == "master_data.yaml":
        raw_content = _read_file_doc("master_data.yaml", RAG_FOLDER)

        # ✅ Extract data list from content
        if isinstance(raw_content, dict):
            stored_data = raw_content.get("data", [])
        elif isinstance(raw_content, str):
            import yaml
            parsed = yaml.safe_load(raw_content)
            stored_data = parsed.get("data", []) if isinstance(parsed, dict) else []
        else:
            stored_data = []

        if is_master_data_changed(last_sync, stored_data):
            changed = True

    days = days_diff(today(), getdate(last_sync))

    return {
        "is_stale": changed,
        "data": True,
        "days": days,
        "last_sync": last_sync
    }


@frappe.whitelist()
def reload_mapping_schema_cache():
    global _MAPPING_DATA, _MAPPING_SCHEMA
    _MAPPING_DATA = None
    _MAPPING_SCHEMA = None
    get_mapping_schema()
    return {"ok": True}


_MAPPING_DATA = None
_MAPPING_SCHEMA = None


def get_mapping_schema(dialect="mysql"):
    global _MAPPING_DATA, _MAPPING_SCHEMA

    if _MAPPING_DATA is None:
        mapping_data = _load_mapping_data()
        _MAPPING_DATA = {
            table: columns
            for table, columns in mapping_data.items()
            if table and table.strip() and columns
        }

    if _MAPPING_SCHEMA is None:
        _MAPPING_SCHEMA = MappingSchema(_MAPPING_DATA, dialect=dialect)

    return _MAPPING_DATA, _MAPPING_SCHEMA

@frappe.whitelist()
def convert_yaml_schema_to_sqlglot_meta() -> dict:
    try:
        FRAPPE_GENERIC_FIELDS = {
            "name": "TEXT",
            "owner": "TEXT",
            "creation": "TEXT",
            "modified": "TEXT",
            "modified_by": "TEXT",
            "docstatus": "INT",
            "idx": "INT",
            "parent": "TEXT",
            "parentfield": "TEXT",
            "parenttype": "TEXT",
        }
        data = _read_filedoctype("schema.yaml")
        meta = {}
        for table_entry in data.get("tables", []):
            table_name = table_entry.get("table")
            fields = table_entry.get("fields", [])
            if table_name and fields:
                meta[table_name] = {
                    field["name"]: "TEXT"
                    for field in fields
                    if field.get("name")
                }
                meta[table_name].update(FRAPPE_GENERIC_FIELDS)

        output_path = _ASSETS_DIR / "metaschema_clean_v2.json"
        output_path.write_text(
            json.dumps(meta, indent=2),
            encoding="utf-8"
        )
        reload_mapping_schema_cache()

        return {
            "ok": True,
            "message": "Successfully updated MetaSchema for Validation"
        }
    except Exception as e:
        return {
            "ok": False,
            "message": str(e)
        }


@lru_cache(maxsize=512)
def is_child_table(table: str) -> bool:
    doctype = table.replace("tab", "", 1) if table.startswith("tab") else table

    try:
        meta = frappe.get_meta(doctype, cached=True)
        return bool(getattr(meta, "istable", 0))
    except Exception:
        return False

CHILD_GENERIC_FIELDS = ["parent", "parenttype", "parentfield", "idx"]
MAIN_GENERIC_FIELDS = ["name", "docstatus"]
def enrich_fields_for_sql_context(table: str, fields: list[str]) -> list[str]:
    out = list(fields)

    if is_child_table(table):
        for f in reversed(CHILD_GENERIC_FIELDS):
            if f not in out:
                out.insert(0, f)
    else:
        for f in reversed(MAIN_GENERIC_FIELDS):
            if f not in out:
                out.insert(0, f)

    return out


def publish_pipeline_update(request_id, stage, message, data=None, done=False, error=False):
    if not request_id:
        return
    payload = {
        "request_id": request_id,
        "stage": stage,
        "message": message,
        "data": data or {},
        "done": done,
        "error": error,
        "timestamp": frappe.utils.now_datetime().isoformat(),
    }
    frappe.publish_realtime(
        event=f"debug_{request_id}",
        message=payload,
        user=frappe.session.user,
    )


def format_schema_context(grouped: dict) -> str:
    parts = []

    for table, table_data in grouped.items():
        if isinstance(table_data, dict):
            raw_fields = table_data.get("fields", [])
            is_table_value = table_data.get("is_table")

            if is_table_value is None:
                child = is_child_table(table)
            else:
                child = bool(is_table_value)
        else:
            raw_fields = table_data
            child = is_child_table(table)

        fields = enrich_fields_for_sql_context(table, raw_fields)

        parts.append(f"TABLE: {table}")
        parts.append(f"TYPE: {'Child Table' if child else 'Main Table'}")

        if child:
            parts.append("JOIN RULES:")
            parts.append("- parent = parent document name")
            parts.append("- parenttype = parent DocType")
            parts.append("- parentfield = child table fieldname")

        parts.append("FIELDS:")
        for field in fields:
            parts.append(f"- {field}")

        parts.append("")

    return "\n".join(parts)


def _safe_join(base: Path, rel: str) -> Path:
    """
    Prevent path traversal. Only allow reading inside base directory.
    """
    p = (base / rel).resolve()
    if base != p and base not in p.parents:
        frappe.throw(_("Unsafe path: {0}\n"
                       "Check Quick Start Guide Here 👇:\n {1}").format(rel,CHANGAI_GUIDE_LINK))
    return p


def read_asset(file_name: str, base: str = "assets") -> Any:
    """
    base:
      - "assets"  -> changai/changai/api/v2/assets
      - "prompts" -> changai/changai/prompts
    """
    file_name = (file_name or "").strip()
    if not file_name:
        frappe.throw(_("file_name is required\n"
                       "Check Quick Start Guide Here 👇:\n {0}").format(CHANGAI_GUIDE_LINK))
    ext = Path(file_name).suffix.lower()
    if ext not in _ALLOWED_EXT:
        frappe.throw(_("Unsupported file type: {0}\n"
                       "Check Quick Start Guide Here 👇:\n {1}").format(ext, CHANGAI_GUIDE_LINK))

    if base == "assets":
        root = _ASSETS_DIR
    elif base == "prompts":
        root = _PROMPTS_DIR
    else:
        root = None
    if root is None:
        frappe.throw(_("Invalid base: {0}\n"
                       "Check Quick Start Guide Here 👇:\n {1}").format(base, CHANGAI_GUIDE_LINK))
    # nosemgrep: frappe-semgrep-rules.rules.security.frappe-security-file-traversal
    path = _safe_join(root, file_name)
    if not path.is_file():
        frappe.throw(_("File not found: {0}\n"
                       "Check Quick Start Guide Here 👇:\n {1}").format(str(path), CHANGAI_GUIDE_LINK))
    content = path.read_text(encoding="utf-8", errors="replace")
    if ext == ".json":
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            frappe.throw(_("Invalid JSON in {0}: {1}"
                           "Check Quick Start Guide Here 👇:\n {2}").format(str(path), str(e), CHANGAI_GUIDE_LINK))
    if ext == ".yaml" or ext == ".yml":
        try:
            return yaml.safe_load(content)
        except yaml.YAMLError as e:
            frappe.throw(_("Invalid YAML in {0}: {1}"
                           "Check Quick Start Guide Here 👇:\n {2}").format(str(path), str(e), CHANGAI_GUIDE_LINK))
    return content

REPORT_INTENT_MAP  = read_asset("report_intent_map.json",base="assets")

class ChangAIConfig:
    @classmethod
    def get(cls):
        if not hasattr(frappe.local, "_changai_config"):
            frappe.clear_document_cache(CHANGAI_SETTINGS)
            frappe.local._changai_config = get_settings()
        return frappe.local._changai_config


def _build_frontend_settings_config() -> Dict[str, Any]:
    settings = frappe.get_single(CHANGAI_SETTINGS)
    aws_access_key_id = (getattr(settings, "aws_access_key_id", None) or "").strip()
    aws_secret_access_key = (getattr(settings, "aws_secret_access_key", None) or "").strip()
    aws_region = (
        getattr(settings, "aws_region", None)
        or getattr(settings, "aws_default_region", None)
        or "us-east-1"
    )

    return {
        "RETAIN_MEM": settings.retain_memory,
        "LLM_VERSION_ID": settings.llm_version_id,
        "EMBED_VERSION_ID": settings.embedder_version_id,
        "REMOTE": bool(settings.remote),
        "deploy_url": settings.deploy_url,
        "entity_retriever": settings.entity_retriever,
        "support_api_url": settings.support_url,
        "get_ticket_details_url": settings.get_ticket_details_url,
        "llm": settings.llm,
        "location": settings.gemini_location,
        "retriever_structure": settings.retriever_structure,
        "gemini_project_id": settings.gemini_project_id,
        "gemini_json_content": settings.gemini_json_content,
        "enable_voice_chat": bool(settings.enable_voice_chat),
        "aws_region": aws_region,
        "polly_voice_id": "Zayd",
        "polly_enabled": bool(settings.enable_voice_chat and aws_access_key_id and aws_secret_access_key),
        "enable_changai": bool(settings.enable_changai)
    }


@frappe.whitelist(allow_guest=False)
def get_settings() -> Dict[str, Any]:
    settings = frappe.get_single(CHANGAI_SETTINGS)
    config = {
        "RETAIN_MEM": settings.retain_memory,
        "LLM_VERSION_ID": settings.llm_version_id,
        "EMBED_VERSION_ID": settings.embedder_version_id,
        "API_TOKEN": settings.api_token,
        "REMOTE": bool(settings.remote),
        "deploy_url": settings.deploy_url,
        "entity_retriever": settings.entity_retriever,
        "support_api_url": settings.support_url,
        "get_ticket_details_url": settings.get_ticket_details_url,
        "llm": settings.llm,
        "location": settings.gemini_location,
        "retriever_structure": settings.retriever_structure,
        "gemini_project_id": settings.gemini_project_id,
        "gemini_json_content": settings.gemini_json_content,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
        "enable_voice_chat": settings.enable_voice_chat,
    }
    return config


@frappe.whitelist(allow_guest=False)
def get_frontend_settings() -> Dict[str, Any]:
    return _build_frontend_settings_config()

def clean_sql(s: Any) -> str:
    if isinstance(s, dict):
        s = s.get("output") or s.get("sql") or s.get("text") or json.dumps(s, ensure_ascii=False, default=str)
    elif isinstance(s, list):
        s = "\n".join(str(x) for x in s)
    else:
        s = "" if s is None else str(s)
    s = s.strip()
    if s.startswith("```"):
        first_newline = s.find("\n")
        if first_newline != -1:
            header = s[:first_newline].strip().lower()
            if header in {"```", "```sql"}:
                s = s[first_newline + 1 :].lstrip()
    stripped = s.rstrip()
    if stripped.endswith("```"):
        stripped = stripped[:-3].rstrip()
    s = stripped
    if s[:3].lower() == "sql" and (len(s) == 3 or s[3].isspace()):
        s = s[3:].lstrip()
    return s.strip()

def _parse_sql_ast(sql_text: str, dialect: str):
    try:
        return sqlglot.parse_one(sql_text, read=dialect), None
    except Exception as e:
        return None, str(e)


def _extract_tables(ast) -> Tuple[List[str], Dict[str, str]]:
    base_tables = []
    alias_to_table = {}
    for t in ast.find_all(exp.Table):
        if not t.name:
            continue
        base_tables.append(t.name)
        a = t.args.get("alias")
        if a and a.name:
            alias_to_table[a.name] = t.name
    return list(dict.fromkeys(base_tables)), alias_to_table


def _extract_derived_aliases(ast) -> Set[str]:
    derived = set()
    for sq in ast.find_all(exp.Subquery):
        a = sq.args.get("alias")
        if a and a.name:
            derived.add(a.name)
    for cte in ast.find_all(exp.CTE):
        a = cte.args.get("alias")
        if a and a.name:
            derived.add(a.name)
    return derived


def _extract_select_aliases(ast) -> Set[str]:
    aliases = set()
    for sel in ast.find_all(exp.Select):
        for proj in sel.expressions:
            if isinstance(proj, exp.Alias) and proj.alias:
                aliases.add(proj.alias)
    return aliases


def _validate_qualified_col(col_name: str, qual: str, mapping: Dict,
                              alias_to_table: Dict, derived_aliases: Set) -> Optional[Tuple]:
    if col_name == "*" or qual in derived_aliases:
        return None
    if qual in mapping:
        if col_name not in mapping[qual]:
            return (f"{qual}.{col_name}", qual)
        return None
    if qual in alias_to_table:
        real = alias_to_table[qual]
        if real in mapping and col_name not in mapping[real]:
            return (f"{qual}.{col_name}", real)
        return None
    return (f"{qual}.{col_name}", None)


def _validate_unqualified_col(col_name: str, base_tables_set: Set,
                               mapping: Dict, select_aliases: Set,
                               unknown_cols: List, ambiguous: Set):
    if col_name in select_aliases:
        return
    candidates = [t for t in base_tables_set if col_name in mapping.get(t, [])]
    if len(candidates) == 0:
        unknown_cols.append((col_name, None))
    elif len(candidates) > 1:
        ambiguous.add(col_name)


def _validate_columns(ast, mapping: Dict, alias_to_table: Dict,
                       derived_aliases: Set, select_aliases: Set,
                       base_tables_set: Set) -> Tuple[List, Set]:
    unknown_cols: List[Tuple[str, str]] = []
    ambiguous: Set[str] = set()
    for col in ast.find_all(exp.Column):
        if not col.name:
            continue
        if col.table:
            result = _validate_qualified_col(
                col.name, str(col.table), mapping, alias_to_table, derived_aliases
            )
            if result:
                unknown_cols.append(result)
        else:
            _validate_unqualified_col(
                col.name, base_tables_set, mapping, select_aliases, unknown_cols, ambiguous
            )
    return unknown_cols, ambiguous


def validate_sql_against_mapping(
    sql_text: str,
    mapping: Dict[str, List[str]],
    dialect: str = "mysql"
) -> Dict[str, Any]:
    result = {
        "ok": True,
        "unknown_tables": [],
        "unknown_columns": [],
        "ambiguous_columns": [],
        "details": {"from_tables": [], "alias_to_table": {}, "derived_aliases": [], "select_aliases": []},
    }
    ast, parse_error = _parse_sql_ast(sql_text, dialect)
    if parse_error:
        result["ok"] = False
        result["details"]["parse_error"] = parse_error
        return result
    base_tables, alias_to_table = _extract_tables(ast)
    derived_aliases = _extract_derived_aliases(ast)
    select_aliases = _extract_select_aliases(ast)
    result["details"]["from_tables"] = base_tables
    result["details"]["alias_to_table"] = alias_to_table
    result["details"]["derived_aliases"] = sorted(derived_aliases)
    result["details"]["select_aliases"] = sorted(select_aliases)
    unknown_tables = [t for t in base_tables if t not in mapping]
    if unknown_tables:
        result["ok"] = False
        result["unknown_tables"] = unknown_tables

    unknown_cols, ambiguous = _validate_columns(
        ast, mapping, alias_to_table, derived_aliases, select_aliases, set(base_tables)
    )
    if unknown_cols or ambiguous:
        result["ok"] = False
        result["unknown_columns"] = unknown_cols
        result["ambiguous_columns"] = sorted(ambiguous)

    return result
def _collect_docs(hits: Union[List[Any], Dict, str]) -> List[Tuple[str, Dict]]:
    def _to_txt_md(doc: Any) -> Tuple[str, Dict]:
        if isinstance(doc, dict):
            return doc.get("text", "") or "", doc.get("metadata", {}) or {}
        if isinstance(doc, str):
            return doc, {}
        return "", {}
    if isinstance(hits, dict) and "message" in hits and isinstance(hits["message"], list):
        hits = hits["message"]
    if isinstance(hits, (dict, str)) or hasattr(hits, "page_content"):
        return [_to_txt_md(hits)]
    return [_to_txt_md(d) for d in (hits or [])]


def _parse_tag(txt: str, tag: str) -> str:
    m = re.search(rf"\[{re.escape(tag)}\]\s*(.+?)(?:\s*\||\s*$)", txt or "")
    return m.group(1).strip() if m else ""

def _infer_type(txt: str) -> str:
    if not (txt or "").startswith("["):
        return ""
    order = [
        ("TABLE", "table"), ("FIELD", "field"), ("JOIN", "join"),
        ("METRIC", "metric"), ("ENUM", "enum"), ("PERIOD", "period"),
        ("CURRENCY", "currency"), ("ENTITY", "entity")
    ]
    for tg, tp in order:
        if txt.startswith(f"[{tg}]"):
            return tp
    return ""

class _SchemaAccumulator:
    def __init__(self):
        self.tables: List[str] = []
        self.fields_by_table: Dict[str, List[str]] = OrderedDict()
        self.joins: List[str] = []
        self.metrics: List[Tuple[str, str, str]] = []
        self.periods: List[str] = []
        self.currencies: List[str] = []
        self.enums: OrderedDict = OrderedDict()
        self.entities: List[Tuple[str, Dict]] = []

    def add_table(self, t: str):
        if t and t not in self.tables:
            self.tables.append(t)
            if t not in self.fields_by_table:
                self.fields_by_table[t] = []

    def add_field(self, tbl: str, fld: str):
        if tbl and fld:
            self.add_table(tbl)
            fq = f"{tbl}.{fld}"
            if fq not in self.fields_by_table[tbl]:
                self.fields_by_table[tbl].append(fq)

    def add_join(self, on: str):
        if on and on not in self.joins:
            self.joins.append(on)

    def add_metric(self, mname: str, mexpr: str, mtbl: str):
        if mtbl:
            self.add_table(mtbl)
        if mname:
            tup = (mname, mexpr or "", mtbl or "")
            if tup not in self.metrics:
                self.metrics.append(tup)

    def add_period(self, pname: str):
        if pname and pname not in self.periods:
            self.periods.append(pname)

    def add_currency(self, code: str):
        if code and code not in self.currencies:
            self.currencies.append(code)

    def add_enum(self, tbl: str, fld: str, vals: Any):
        if tbl:
            self.add_table(tbl)
        if tbl and fld:
            key = f"{tbl}.{fld}"
            if isinstance(vals, (list, tuple)):
                vals = ", ".join([str(v) for v in vals])
            if key not in self.enums:
                self.enums[key] = vals or ""
            self.add_field(tbl, fld)

    def add_entity(self, ent_name: str, filt: Dict):
        self.entities.append((ent_name, filt or {}))

    def sort(self):
        self.tables.sort()
        for t in self.fields_by_table:
            if t not in self.tables:
                self.tables.append(t)
        for t in self.fields_by_table:
            self.fields_by_table[t] = sorted(
                self.fields_by_table[t], key=lambda s: s.split(".", 1)[1]
            )
        self.joins.sort()
        self.metrics.sort(key=lambda x: x[0])
        self.periods.sort()
        self.currencies.sort()
        self.enums = OrderedDict(sorted(self.enums.items(), key=lambda kv: kv[0]))

def _process_enum(txt: str, md: Dict, acc: _SchemaAccumulator):
    tbl = md.get("table") or _parse_tag(txt, "TABLE")
    fld = md.get("field")
    if not fld:
        ef = _parse_tag(txt, "ENUM")
        if "." in ef:
            tbl = tbl or ef.split(".", 1)[0].strip()
            fld = ef.split(".", 1)[1].strip()
    vals = md.get("values")
    if vals is None:
        vals = _parse_tag(txt, "VALUES")
    acc.add_enum(tbl, fld, vals)

def _process_entity(txt: str, md: Dict, acc: _SchemaAccumulator):
    ent_name = md.get("entity") or _parse_tag(txt, "ENTITY") or "Entity"
    filt = md.get("filters")
    if filt is None:
        filt_txt = _parse_tag(txt, "FILTERS")
        filt = {}
        if filt_txt:
            for part in [p.strip() for p in filt_txt.split(";") if p.strip()]:
                if "=" in part:
                    k, v = part.split("=", 1)
                    filt[k.strip()] = [x.strip() for x in v.split(",") if x.strip()]
    acc.add_entity(ent_name, filt)

def _get_table_name(txt: str, md: Dict) -> str:
    return md.get("table") or _parse_tag(txt, "TABLE")

def _get_field_name(txt: str, md: Dict) -> str:
    return md.get("field") or _parse_tag(txt, "FIELD").split(" (", 1)[0]

def _process_table_doc(txt: str, md: Dict, acc: _SchemaAccumulator) -> None:
    acc.add_table(_get_table_name(txt, md))

def _process_field_doc(txt: str, md: Dict, acc: _SchemaAccumulator) -> None:
    acc.add_field(_get_table_name(txt, md), _get_field_name(txt, md))

def _process_join_doc(txt: str, md: Dict, acc: _SchemaAccumulator) -> None:
    acc.add_join(md.get("on") or _parse_tag(txt, "ON"))

def _process_metric_doc(txt: str, md: Dict, acc: _SchemaAccumulator) -> None:
    acc.add_metric(
        md.get("name") or _parse_tag(txt, "METRIC"),
        md.get("expression") or _parse_tag(txt, "EXPR"),
        _get_table_name(txt, md),
    )

def _process_period_doc(txt: str, md: Dict, acc: _SchemaAccumulator) -> None:
    acc.add_period(md.get("name") or _parse_tag(txt, "PERIOD"))

def _process_currency_doc(txt: str, md: Dict, acc: _SchemaAccumulator) -> None:
    acc.add_currency(md.get("code") or _parse_tag(txt, "CURRENCY"))

_DOC_PROCESSORS = {
    "table": _process_table_doc,
    "field": _process_field_doc,
    "join": _process_join_doc,
    "metric": _process_metric_doc,
    "period": _process_period_doc,
    "currency": _process_currency_doc,
    "enum": _process_enum,
    "entity": _process_entity,
}

def _process_doc(txt: str, md: Dict, acc: _SchemaAccumulator) -> None:
    dtype = md.get("type") or _infer_type(txt)
    processor = _DOC_PROCESSORS.get(dtype)
    if processor:
        processor(txt, md, acc)


def _append_table_lines(
    lines: List[str],
    acc: _SchemaAccumulator,
    max_fields_per_table: int,
) -> None:
    for tbl in acc.tables:
        lines.append(f"Table: {tbl}")
        lines.append("Fields:")
        fields = acc.fields_by_table.get(tbl, [])
        if not fields:
            lines.append("  -")
            lines.append("")
            continue
        lines.extend(f"  - {field}" for field in fields[:max_fields_per_table])
        extra_count = len(fields) - max_fields_per_table
        if extra_count > 0:
            lines.append(f"  # +{extra_count} more")
        lines.append("")


def _append_simple_section(lines: List[str], title: str, items: List[str]) -> None:
    if not items:
        return
    lines.append(f"{title}:")
    lines.extend(f"  - {item}" for item in items)
    lines.append("")


def _append_metric_lines(lines: List[str], acc: _SchemaAccumulator) -> None:
    if not acc.metrics:
        return
    lines.append("Metrics:")
    for metric_name, metric_expr, metric_table in acc.metrics:
        suffix = f"  # table: {metric_table}" if metric_table else ""
        line = f"  - {metric_name}: {metric_expr}{suffix}" if metric_expr else f"  - {metric_name}{suffix}"
        lines.append(line)
    lines.append("")

def _append_enum_lines(lines: List[str], acc: _SchemaAccumulator) -> None:
    if not acc.enums:
        return
    lines.append("Enums:")
    for key, values in acc.enums.items():
        lines.append(f"  - {key}: {values}" if values else f"  - {key}")
    lines.append("")

def _format_filter_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return str(value)

def _append_entity_lines(
    lines: List[str],
    acc: _SchemaAccumulator,
    show_entity_filters_yaml: bool,
) -> None:
    if not acc.entities:
        return
    lines.append("Entities:")
    for entity, filters in acc.entities:
        if show_entity_filters_yaml and isinstance(filters, dict) and filters:
            lines.append(f"  - Entity: {entity}")
            lines.append("    Filters:")
            for key, value in filters.items():
                lines.append(f"      {key}: {_format_filter_value(value)}")
            continue

        lines.append(f"  - Entity: {entity}, Filters: {filters if filters else '{}'}")

def _trim_trailing_blank_lines(lines: List[str]) -> None:
    while lines and not lines[-1].strip():
        lines.pop()

def _build_context_lines(
    acc: _SchemaAccumulator,
    title: str,
    max_fields_per_table: int,
    show_entity_filters_yaml: bool,
) -> List[str]:
    lines: List[str] = [title]

    _append_table_lines(lines, acc, max_fields_per_table)

    if acc.joins:
        lines.append("Join:")
        lines.extend(f"  {join}" for join in acc.joins)
        lines.append("")

    _append_metric_lines(lines, acc)
    _append_simple_section(lines, "Periods", acc.periods)
    _append_simple_section(lines, "Currencies", acc.currencies)
    _append_enum_lines(lines, acc)
    _append_entity_lines(lines, acc, show_entity_filters_yaml)

    _trim_trailing_blank_lines(lines)
    return lines

def hits_to_schema_context(
    hits: Union[List[Any], Dict, str],
    title: str = "SCHEMA CONTEXT",
    max_fields_per_table: int = 20,
    sort_sections: bool = True,
    show_entity_filters_yaml: bool = True
) -> str:
    acc = _SchemaAccumulator()
    for txt, md in _collect_docs(hits):
        _process_doc(txt, md, acc)
    if sort_sections:
        acc.sort()
    lines = _build_context_lines(acc, title, max_fields_per_table, show_entity_filters_yaml)
    return "\n".join(lines)


