import os
import re
import json
import pickle
import shutil
from pathlib import Path
from functools import lru_cache
from typing import Any, Dict, List, Optional, Union
from rapidfuzz import fuzz, process
from changai.changai.api.v2.non_erp_handler import load_non_erp_data
from changai.changai.api.v2.clients import gemini_client
from changai.changai.api.v2.tts import get_polly_client
from changai.changai.api.v2.schema_utils import (
    ChangAIConfig,
    CHANGAI_GUIDE_LINK,
    ERPGULF_LINK,
    settingsUrl,
    format_schema_context,
    publish_pipeline_update,
    _safe_join,
)
from changai.changai.api.v2.non_erp_handler import _safe_open_path


from changai.changai.api.v2.clients import (
    _post_json,
    _GEMINI_CLIENT,
    APPLICATION_JSON,
)
import numpy as np
import frappe
from frappe import _
from huggingface_hub import snapshot_download
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
_KEYWORDS_LIST = None
_KEYWORDS_SET = None
_FIELD_DOCS_CACHE = None
_FIELD_EMBS_CACHE = None
_TABLE_TO_IDX_CACHE = None
_VS_REPORT=None
_VS_TABLE = None
_KEYWORDS_SET=None
_VS_MASTER = None
_EMBEDDER_INSTANCE = None
_FULL_FIELDS_VS = None
_SUB_VS_CACHE = {}
EMBEDDING_ENGINE_NONE_MESSG = f"""
Embedding engine is None. Model not loaded.
Check Quick Start Guide Here 👇:
{CHANGAI_GUIDE_LINK}"""
from changai.changai.api.v2.schema_utils import read_asset
bk = read_asset("business_keywords_v1.json", base="assets")
BUSINESS_KEYWORDS = bk.get("business_keywords", bk)

@frappe.whitelist(allow_guest=False)
def download_model():
    frappe.enqueue(
        "changai.changai.api.v2.retrieve.download_model_from_ui",  # dot-path to the function
        queue="long",           # use "long" queue for heavy tasks
        timeout=3600,           # 1 hour timeout (in seconds)
        is_async=True,          # run in background (default True)
        job_name="download_model",  # optional: helps track/deduplicate jobs
    )
    return {
        "ok":True,"message":"Model Downloading.."
    }


def _get_model_path():
    site_path = frappe.get_site_path("private", "files", "changai_model")
    return site_path


@frappe.whitelist(allow_guest=False)
def download_model_from_ui():
    global _EMBEDDER_INSTANCE

    model_path = _get_model_path()

    try:
        if os.path.exists(model_path):
            shutil.rmtree(model_path)

        os.makedirs(model_path, exist_ok=True)

        snapshot_download(
            repo_id="hyrinmansoor/changAI-nomic-embed-text-v1.5-finetuned",
            local_dir=model_path,
            ignore_patterns=[
        "*.pt",
        "*.pth",
        "*.bin",
        "trainer_*",
        "optimizer*"
    ]
        )
        _EMBEDDER_INSTANCE = None
        return {"status": "success", "message": "Embedding model downloaded successfully."}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Embedding Model Download Failed")
        frappe.throw(_("Model download failed: {0}\n Check Quick Start Guide Here 👇:\n{1} <br>" 
        "<a href='{1}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Download Embedding Model</a></b>.<br>"
        "<a href='{2}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>ERPGulf.com</a></b>."
).format(str(e),CHANGAI_GUIDE_LINK,settingsUrl,ERPGULF_LINK))



def load_field_matrix():
    global _FIELD_DOCS_CACHE, _FIELD_EMBS_CACHE, _TABLE_TO_IDX_CACHE

    if _FIELD_DOCS_CACHE is not None:
        return _FIELD_DOCS_CACHE, _FIELD_EMBS_CACHE, _TABLE_TO_IDX_CACHE

    app_root = Path(frappe.get_app_path("changai")).resolve()
    schema_rel = "changai/api/v2/fvs_stores/erpnext/emb_dir"
    schema_path = _safe_join(app_root, schema_rel)  # already validates traversal

    allowed_dir = str(schema_path)  # all files must live here

    embs_path = schema_path / "field_embs.npy"
    docs_path = schema_path / "field_docs.pkl"
    table_idx_path = schema_path / "table_to_idx.pkl"

    if not embs_path.exists():
        frappe.throw(f"Missing field_embs.npy. Rebuild schema FVS first: {embs_path}")

    safe_docs = _safe_open_path(str(docs_path), allowed_dir)
    docs = pickle.loads(safe_docs.read_bytes())

    safe_table_idx = _safe_open_path(str(table_idx_path), allowed_dir)
    table_to_idx = pickle.loads(safe_table_idx.read_bytes())

    embs = np.load(embs_path, mmap_mode="r")

    _FIELD_DOCS_CACHE = docs
    _FIELD_EMBS_CACHE = embs
    _TABLE_TO_IDX_CACHE = table_to_idx

    return docs, embs, table_to_idx


def get_embedding_engine():
    global _EMBEDDER_INSTANCE
    if _EMBEDDER_INSTANCE is not None:
        return _EMBEDDER_INSTANCE
    
    model_path = _get_model_path()  # check path first, always
    
    if not os.path.exists(model_path):
        _EMBEDDER_INSTANCE = None  # reset if model missing
        frappe.throw(
            _(
                "Go to <b>ChangAI Settings</b> and click"
                "<a href='{1}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Download Embedding Model</a></b>.<br><br>"
                "Check this Quick Start Guide for more detail: "
                "<a href='{0}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Click here</a>"
                "<a href='{2}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>ERPGulf.com</a></b>."

            ).format(CHANGAI_GUIDE_LINK,settingsUrl,ERPGULF_LINK),
            title=_("Embedding Model Required")
        )
    
    if _EMBEDDER_INSTANCE is None:
        _EMBEDDER_INSTANCE = HuggingFaceEmbeddings(
            model_name=model_path,
            model_kwargs={"device": "cpu","trust_remote_code": True,},
            encode_kwargs={
        "normalize_embeddings": True,
    },
        )
    
    return _EMBEDDER_INSTANCE




def get_vs(istable: bool):
    global _VS_TABLE, _VS_REPORT

    emb = get_embedding_engine()
    if emb is None:
        frappe.throw(_(EMBEDDING_ENGINE_NONE_MESSG))

    app_path = frappe.get_app_path("changai")

    if istable:
        if _VS_TABLE is None:
            table_vs_path = os.path.join(
                app_path, "changai", "api", "v2",
                "fvs_stores", "erpnext", "table_fvs"
            )

            if not os.path.exists(table_vs_path):
                frappe.throw(_("FAISS table store not found at {0}").format(table_vs_path))

            _VS_TABLE = FAISS.load_local(
                table_vs_path,
                emb,
                allow_dangerous_deserialization=True
            )

        return _VS_TABLE

    else:
        if _VS_REPORT is None:
            report_vs_path = os.path.join(
                app_path, "changai", "api", "v2",
                "fvs_stores", "erpnext", "report_fvs"
            )

            if not os.path.exists(report_vs_path):
                frappe.throw(_("FAISS report store not found at {0}").format(report_vs_path))

            _VS_REPORT = FAISS.load_local(
                report_vs_path,
                emb,
                allow_dangerous_deserialization=True
            )

        return _VS_REPORT


def get_master_vs():
    global _VS_MASTER
    try:
        if _VS_MASTER is None:
            emb = get_embedding_engine()
            if emb is None:
                frappe.throw(_(EMBEDDING_ENGINE_NONE_MESSG))

            master_vs_path = frappe.get_site_path(
                "private", "changai", "fvs_stores", "erpnext", "masterdata_fvs"
            )
            if not os.path.exists(master_vs_path):
                frappe.throw(_(
                    "FAISS MASTER store not found at {0}.<br><br>"
                    "Please open "
                    "<a href='{1}' target='_blank' rel='noopener noreferrer'>Go to Settings Page</a>"
                    "and click on the <b>Update Master Data</b> button in the Training tab.<br><br>"
                    "Check Quick Start Guide Here 👇<br>"
                    "<a href='{2}' target='_blank' rel='noopener noreferrer' style='color:#1e90ff;'>Click here</a><br><br><br>"
                    "<a href='{3}' target='_blank' rel='noopener noreferrer' style='color:#1e90ff;'>ERPGulf.com</a>"

                ).format(
                    master_vs_path,
                    settingsUrl,
                    CHANGAI_GUIDE_LINK,
                    ERPGULF_LINK
                ))

            _VS_MASTER = FAISS.load_local(
                master_vs_path,
                emb,
                allow_dangerous_deserialization=True
            )
    except Exception as e:
        frappe.log_error(f"Error loading master vector store: {e}", "ChangAI Master VS Load Error")

    return _VS_MASTER
_WARMUP_COUNT=0
def load_on_startup():
    global _WARMUP_COUNT,_EMBEDDER_INSTANCE, _VS_TABLE, _FULL_FIELDS_VS, _VS_MASTER, _FIELD_DOCS_CACHE, _GEMINI_CLIENT
    _WARMUP_COUNT+=1
    frappe.log_error(
        title=f"ChangAI Warmup called | PID {os.getpid()} | Count {_WARMUP_COUNT}",
        message="load_on_startup triggered"
    )
    # If all are already loaded, skip
    if all([
        _EMBEDDER_INSTANCE is not None,
        _VS_TABLE is not None,
        _FULL_FIELDS_VS is not None,
        _VS_MASTER is not None,
        _FIELD_DOCS_CACHE is not None    ]):
        frappe.log_error(
            title=f"ChangAI Warmup skipped | PID {os.getpid()}",
            message="Already loaded in this worker"
        )
        return 
    message=f"PID={os.getpid()} | module={__name__} | file={__file__} | loaded={_EMBEDDER_INSTANCE is not None} | id={id(_EMBEDDER_INSTANCE)}"
    try:
        load_non_erp_data()
        get_embedding_engine()
        get_vs(True)
        load_field_matrix()
        gemini_client()
        get_master_vs()
        _init_keywords()
        config = ChangAIConfig.get()
        get_polly_client(config)
        frappe.log_error(
        title="ChangAI Warmup Completed",
        message=frappe.get_traceback()  # full stack trace
    )
    except Exception as e:
        frappe.log_error(
        title="ChangAI Warmup Failed",
        message=frappe.get_traceback()  # full stack trace
    )
    return message
@lru_cache(maxsize=None)
def _word_is_erp(word: str) -> bool:
    if len(word) <= 3:
        return False
    if word in _KEYWORDS_SET:
        return True
    for kw in _KEYWORDS_SET:
        if word in kw or kw in word:
            return True
    if len(word) >= 4:
        match = process.extractOne(
            word, _KEYWORDS_LIST, scorer=fuzz.ratio, score_cutoff=70
        )
        if match:
            return True
    return False
def _init_keywords():
    global _KEYWORDS_SET, _KEYWORDS_LIST
    if not _KEYWORDS_SET:
        _KEYWORDS_SET = set(kw.lower() for kw in BUSINESS_KEYWORDS)
        _KEYWORDS_LIST = list(_KEYWORDS_SET)
        # ✅ pre-warm cache — run every keyword through _word_is_erp at startup
        for kw in _KEYWORDS_LIST:
            _word_is_erp(kw)  # result gets cached — first real request is instant

def check_memory_status() -> dict:
    return {
        "pid": os.getpid(),
        "module": __name__,
        "file": __file__,
        "globals": {
            "embedding_model": {
                "loaded": _EMBEDDER_INSTANCE is not None,
                "id": id(_EMBEDDER_INSTANCE),
            },
            "table_vs": {
                "loaded": _VS_TABLE is not None,
                "id": id(_VS_TABLE),
            },
            "full_fields_vs": {
                "loaded": _FULL_FIELDS_VS is not None,
                "id": id(_FULL_FIELDS_VS),
            },
            "field_docs": {
                "loaded": _FIELD_DOCS_CACHE is not None,
                "id": id(_FIELD_DOCS_CACHE),
            },
            "field_embs": {
                "loaded": _FIELD_EMBS_CACHE is not None,
                "id": id(_FIELD_EMBS_CACHE),
            },
            "table_to_idx": {
                "loaded": _TABLE_TO_IDX_CACHE is not None,
                "id": id(_TABLE_TO_IDX_CACHE),
            },
            "master_vs": {
                "loaded": _VS_MASTER is not None,
                "id": id(_VS_MASTER),
            },
            "gemini_client": {
                "loaded": _GEMINI_CLIENT is not None,
                "id": id(_GEMINI_CLIENT),
            },
            # "symspell": {
            #     "loaded": sym_spell is not None,
            #     "id": id(sym_spell),
            # },
            # "keywords": {
            #     "loaded": _KEYWORDS_SET is not None,
            #     "id": id(_KEYWORDS_SET),
            # },
        }
    }


@lru_cache(maxsize=512)
def _get_cached_embedding(q: str, request_id: str) -> tuple:
    # vec = get_local_embedding(q)
    emb = get_embedding_engine()

    publish_pipeline_update(
            request_id,
            "embedding_end",
            "get_embedding_engine ended"
    )
    vec = emb.embed_query(q)
    publish_pipeline_update(
            request_id,
            "embedding_query_done",
            "embedding query done"
    )
    return tuple(vec)  # tuple for hashability



def call_fvs_table_search(is_cud,get_table: bool, q: str, request_id: str) -> List[str]:
    # get cached embedding
    top_k=0
    publish_pipeline_update(
            request_id,
            "Inside the Table Search Function",
            _("Inside the Table Search Function")
        )
    q_vec = np.array(_get_cached_embedding(q,request_id), dtype="float32")
    publish_pipeline_update(
            request_id,
            "Completed Embed for Table Search Function",
            _("Completed Embed for Table Search Function")
        )
    
    # use FAISS index directly instead of similarity_search
    publish_pipeline_update(
            request_id,
            "q_vec_ready",
            _("q_vec_ready")
        )
    vs = get_vs(get_table)
    publish_pipeline_update(
            request_id,
            "vs_ready",
            _("vs_ready")
        )
    top_k=30 if is_cud else 20
    scores, indices = vs.index.search(q_vec.reshape(1, -1), k=top_k)
    publish_pipeline_update(
            request_id,
            "index_search_done",
            _("index_search_done")
        )
    
    out, seen = [], set()
    for idx in indices[0]:
        if idx == -1:
            continue
        doc_id = vs.index_to_docstore_id[idx]
        doc = vs.docstore.search(doc_id)
        t = doc.metadata.get("table") if get_table else doc.metadata.get("report_name")
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out

SKIP_FIELDS = {
    "docstatus",
    "owner",
    "creation",
    "modified",
    "modified_by",
    "parent",
    "parenttype",
    "parentfield",
    "idx",
}

def call_fvs_field_search_global_k(
    is_cud:bool,
    user_question: str,
    selected_tables: List[str],
    k_total: int = 40,
    request_id: Optional[str] = None
) -> str:
    if isinstance(selected_tables, str):
        try:
            selected_tables = json.loads(selected_tables)
        except Exception:
            selected_tables = [selected_tables]
    if not user_question or not selected_tables:
        return ""

    docs, embs, table_to_idx = load_field_matrix()

    q_vec = np.array(
        _get_cached_embedding(user_question, request_id),
        dtype="float32"
    )
    q_vec = q_vec / max(np.linalg.norm(q_vec), 1e-12)

    all_idxs = []
    for t in selected_tables:
        t = str(t).strip()
        if not t:
            continue
        candidates = [
            t,
            f"tab{t}" if not t.startswith("tab") else t,
            t.replace("tab", "", 1) if t.startswith("tab") else t,
        ]
        for key in candidates:
            if key in table_to_idx:
                all_idxs.extend(table_to_idx[key])
                break

    if not all_idxs:
        frappe.log_error(
            title="ChangAI Field Search: No Indexes Found",
            message=json.dumps({
                "user_question": user_question,
                "selected_tables": selected_tables,
                "sample_table_to_idx_keys": list(table_to_idx.keys())[:50],
            }, indent=2, default=str)
        )
        return ""

    sub_embs = embs[all_idxs]
    scores = sub_embs @ q_vec
    top_global = np.argsort(-scores)[:k_total]

    grouped = {}
    seen = set()

    for i in top_global:
        doc_i = all_idxs[int(i)]
        d = docs[doc_i]
        meta = getattr(d, "metadata", {}) or {}

        is_table = meta.get("is_table")
        table = meta.get("table")
        field = meta.get("field") or meta.get("name")

        if not table or not field:
            continue
        if is_cud:
            if field in SKIP_FIELDS:
                continue

        key = (table, field)
        if key in seen:
            continue
        seen.add(key)

        name = field
        fieldtype = meta.get("fieldtype", "")

        # ─── Link field → join hint ────────────────────────
        join_hint = meta.get("join_hint")
        if isinstance(join_hint, dict):
            linked_table = join_hint.get("table")
            if linked_table:
                name += f" -> {linked_table}"
        elif isinstance(join_hint, str) and join_hint.strip():
            name += f" -> {join_hint.strip()}"

        # ─── Table field → child hint ──────────────────────
        elif fieldtype in ("Table", "Table MultiSelect"):
            child_hint = meta.get("child_hint")
            if isinstance(child_hint, dict):
                child_table = child_hint.get("child_table")
                if child_table:
                    name += f" (Table) -> {child_table}"
            elif isinstance(child_hint, str) and child_hint.strip():
                name += f" (Table) -> {child_hint.strip()}"

        # ─── Select field → options ────────────────────────
        opts = meta.get("options")
        if opts and fieldtype == "Select":
            if isinstance(opts, list):
                name += " {" + ", ".join(str(o) for o in opts[:5]) + "}"
            else:
                name += " {" + str(opts) + "}"

        grouped.setdefault(table, {
            "is_table": is_table,
            "fields": []
        })
        grouped[table]["fields"].append(name)

    if not grouped:
        frappe.log_error(
            title="ChangAI Field Search: Empty Grouped Result",
            message=json.dumps({
                "user_question": user_question,
                "selected_tables": selected_tables,
                "all_idxs_count": len(all_idxs),
                "top_global_count": len(top_global),
            }, indent=2, default=str)
        )
        return ""

    return format_schema_context(grouped)

def call_retrieve_multi_line(is_cud:bool,user_question: str, request_id: str) -> Dict[str, Any]:
    try:
        top_tables = call_fvs_table_search(is_cud,True, user_question, request_id)
        publish_pipeline_update(
            request_id,
            "table_retrieval_done",
            _("Tables retrieved")
        )
        fields_candidates = call_fvs_field_search_global_k(
            is_cud,
            user_question,
            selected_tables=top_tables,
            k_total= 60 if is_cud else 40,
            request_id=request_id
        )
        publish_pipeline_update(
            request_id,
            "field_retrieval_done",
            "Fields selected"
        )
        return {
            "selected_fields": fields_candidates,
            "selected_tables": top_tables,
            "top_tables": top_tables,
            "top_fields": fields_candidates,
        }
    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        return {"selected_fields": {}, "selected_tables": [], "top_tables": [],"top_fields": [],"error": str(e)}

def debug_entity_retriever(q: str,state:Dict):
    resp = remote_entity_embedder(q)   # this returns {"ok":..., "body":...}
    return {
        "query": q,
        "raw_response": resp,
        "parsed_entity_cards": call_entity_retriever(False, q,state)
    }

def remote_entity_embedder(q: str) -> Union[list, str]:
    config = ChangAIConfig.get()
    payload = {"version": config["entity_retriever"], "input": {"query": q}}
    headers = {
        "Content-Type": APPLICATION_JSON,
        "Prefer": "wait",
        "Authorization": f"Bearer {config['API_TOKEN']}",
    }
    response = _post_json(config["URL"], headers, payload)
    return response



def append_entity_field_to_schema(top_fields: str, table_name: str, field_name: str) -> str:
    """
    Append field_name to the FIELDS section of table_name if missing.
    Example: append customer_name into TABLE: tabCustomer block.
    """

    pattern = rf"(TABLE:\s*{re.escape(table_name)}\n.*?FIELDS:\n)(.*?)(?=\n\nTABLE:|\Z)"

    def replace_block(match):
        header = match.group(1)
        fields_block = match.group(2)

        # already exists
        if re.search(rf"^- {re.escape(field_name)}(\s|$)", fields_block, re.MULTILINE):
            return match.group(0)

        return header + fields_block.rstrip() + f"\n- {field_name}\n"

    return re.sub(pattern, replace_block, top_fields, count=1, flags=re.DOTALL)


def local_entity_embedder(q: str) -> List[Dict[str, Any]]:
    hits = get_master_vs().similarity_search(q, k=20)
    out, seen = [], set()
    for h in hits:
        entity_type = h.metadata.get("entity_type")   # example: tabCustomer
        entity_id = h.metadata.get("entity_id")    # example: customer_name
        entity_label = h.metadata.get("entity_label")
        # if entity_type in state["selected_tables"]:
        #     state["selected_fields"] = append_entity_field_to_schema(
        #         top_fields=state["selected_fields"],
        #         table_name=entity_type,
        #         field_name=entity_id
        #     )

        key = (entity_type, entity_label)
        if key not in seen:
            seen.add(key)
            out.append({"entity_type": entity_type, "entity_id": entity_id, "entity_label": entity_label})
    return out


def call_entity_retriever(isreport: bool, qstn: str, state: Dict) -> Dict[str, Any]:
    config = ChangAIConfig.get()
    if config["REMOTE"] and config["llm"] == "QWEN3":
        response = remote_entity_embedder(qstn)

        if not response.get("ok"):
            frappe.log_error(f"Entity retriever failed: {response.get('body')}", "ChangAI Entity Retriever")
            return {"raw": response, "cards": []}

        body = response.get("body") or {}
        output = body.get("output") or {}
        results = output.get("results") or []

        cards = [r.get("entity_label") for r in results if r.get("entity_label")]

        return {"raw": body, "cards": cards}
    else:
        from changai.changai.api.v2.schema_utils import phonetic_match
        entity_words = state.get("entity_words")
        cards = []
        debug=[]
        if entity_words is None:
            return {"cards":[]}
        for word in entity_words:
            result = phonetic_match(isreport, word)
            labels = result.get("entity_labels") or []
            debug.append({
                "word": word,
                "result": result,
                "labels": labels
    })   
            for label in labels:
                if isreport:
                    try:
                        table_field, _  = label.split(":", 1)
                        table, field = table_field.split(".", 1)
                        doctype = table.removeprefix("tab")
                        state["doc"] =  doctype
                    except Exception:
                        pass
                if label and label not in cards:
                    cards.append(label)
        return {"cards": cards}

