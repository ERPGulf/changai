from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict
from typing import Any, Dict, List, Tuple, Optional
import requests
import json
import base64
from changai.changai.api.v2.operations import execute_insert,execute_update,execute_delete
import os
from frappe.utils.jinja import render_template
from changai.changai.api.v2.schema_utils import match_report_intent, get_report_filter_fields
from changai.changai.api.v2.store_chats import get_last_thread_message
from changai.changai.api.v2.retrieve import (
    call_retrieve_multi_line,
    call_fvs_table_search,
    call_entity_retriever,
    check_memory_status,
    remote_entity_embedder,
    get_embedding_engine,
    get_vs,
    load_field_matrix,
    get_master_vs
)
import re
from changai.changai.api.v2.tts import get_polly_client
from rapidfuzz import fuzz, process
from langgraph.checkpoint.memory import MemorySaver
from changai.changai.api.v2.schema_utils import (
    validate_sql_schema,
    check_file_updates,
    read_asset,
    clean_sql,
    validate_sql_against_mapping,
    hits_to_schema_context,
    CHANGAI_GUIDE_LINK,
    ERPGULF_LINK,
    settingsUrl,
    publish_pipeline_update,
    ChangAIConfig
)
from werkzeug.wrappers import Response
from changai.changai.api.v2.helpdesk_api import(
    create_helpdesk_ticket,
    get_user_tickets
)
import frappe
from changai.changai.api.v2.store_chats import (
    save_turn_2,
    inject_prompt,
    save_logs,
    find_similar_log_question,
    _get_sql_error_message,
   _error_response 
)
from changai.changai.api.v2.format_output import (
    format_data
)
from changai.changai.api.v2.clients import call_model,gemini_client
from changai.changai.api.v2.non_erp_handler import non_erp_response
from frappe.desk.reportview import build_match_conditions
from frappe import _
from frappe.desk.query_report import get_script
from changai.changai.api.v2.clients import (
    call_model,
    call_gemini,
    remote_embedder_request,
)
STATUS_200 = 200
APPLICATION_JSON = "application/json"
EMBEDDING_ENGINE_NONE_MESSG = f"""
Embedding engine is None. Model not loaded.
Check Quick Start Guide Here 👇:
{CHANGAI_GUIDE_LINK}"""
REPORT_ACTION_PROMPT = read_asset("report_prompt.txt",base="prompts")
RETRY_LIMIT = 2
bk = read_asset("business_keywords_v1.json", base="assets")
BUSINESS_KEYWORDS = bk.get("business_keywords", bk)
mapping_data = read_asset("metaschema_clean_v2.json", base="assets")
CONVERSATION_TEMPLATE = read_asset("conversation_template_v2.j2", base="assets")
SQL_SYS_PROMPT = read_asset("sql_system_prompt.txt", base="prompts")
SQL_PROMPT = read_asset("sql_user_prompt.txt", base="prompts")
FILTER_TABLES = read_asset("filter_tables.txt", base="prompts")
filter_fields = read_asset("filter_fields.txt", base="prompts")
STOP_WORDS = set(read_asset("stop_words.json", base="assets"))
THREAD_WORDS = set(read_asset("thread_words.json", base="assets"))
SQL_REWRITE_SYS_PROMPT = read_asset("sql_rewrite_sys_prompt.txt", base="prompts")
SQL_REWRITE_USER_PROMPT = read_asset("sql_rewrite_user_prompt.txt", base="prompts")

INSERT_PROMPT = read_asset("insert_prompt.txt", base="prompts")
INSERT_USER_PROMPT = read_asset("insert_user_prompt.txt",base="prompts")
UPDATE_PROMPT = read_asset("update_prompt.txt", base="prompts")
UPDATE_USER_PROMPT = read_asset("update_user_prompt.txt", base="prompts")
DELETE_PROMPT = read_asset("delete_prompt.txt", base="prompts")
DELETE_USER_PROMPT = read_asset("delete_user_prompt.txt", base="prompts")

def get_cud_prompt(cud_type, formatted_q, context):
    if cud_type == "insert":
        return (
            INSERT_PROMPT,
            INSERT_USER_PROMPT.format(
                question=formatted_q,
                context=context
            )
        )

    elif cud_type == "update":
        return (
            UPDATE_PROMPT,
            UPDATE_USER_PROMPT.format(
                question=formatted_q,
                context=context
            )
        )

    elif cud_type == "delete":
        return (
            DELETE_PROMPT,
            DELETE_USER_PROMPT.format(
                question=formatted_q,
                context=context
            )
        )

    raise ValueError(f"Unsupported CUD type: {cud_type}")



@frappe.whitelist(allow_guest=True)  # nosemgrep: security.guest-whitelisted-method - intentional, validates credentials via OAuth client lookup and Frappe password grant before returning a token
def generate_token_secure(api_key: str, api_secret: str, app_key: str):
    try:
        try:
            app_key = base64.b64decode(app_key).decode("utf-8")
        except Exception:
            return Response(
                json.dumps(
                    {"message": "Security Parameters are not valid", "user_count": 0}
                ),
                status=401,
                mimetype=APPLICATION_JSON,
            )
        doc = frappe.db.get_value(
            "OAuth Client",
            {"app_name": app_key},
            ["name", "client_id", "client_secret", "user"],
            as_dict=True
        )
        if not doc:
            frappe.local.response["http_status_code"] = 401
            return {"ok": False, "error": "OAuth client not found / invalid app_key"}
        if doc.client_id is None:
            return Response(
                json.dumps(
                    {"message": "Security Parameters are not valid", "user_count": 0}
                ),
                status=401,
                mimetype=APPLICATION_JSON,
            )
        url = (
            frappe.local.conf.host_name
            + "/api/method/frappe.integrations.oauth2.get_token"
        )
        payload = {
            "username": api_key,
            "password": api_secret,
            "grant_type": "password",
            "client_id": doc.client_id,
            "client_secret": doc.client_secret,
        }
        response = requests.request("POST", url, data=payload)
        if response.status_code == STATUS_200:
            result_data = json.loads(response.text)
            return Response(
                json.dumps({"data": result_data}),
                status=STATUS_200,
                mimetype=APPLICATION_JSON,
            )
        else:
            frappe.local.response.http_status_code = 401
            return json.loads(response.text)
    except Exception as e:
        return Response(
            json.dumps({"message":str(e), "user_count": 0}),
            status=500,
            mimetype=APPLICATION_JSON,
        )

# Api for  checking user name  using token
@frappe.whitelist(allow_guest=False)
def whoami() -> Dict[str, Any]:
    """This function returns the current session user"""
    try:
        response_content = {
            "user": frappe.session.user,
        }
        frappe.local.response = {
            "data": response_content,
            "http_status_code": STATUS_200,
        }
        return Response(
            json.dumps({"data": response_content}),
            status=STATUS_200,
            mimetype=APPLICATION_JSON,
        )
    except ValueError as ve:
        frappe.throw(_("{0}\n Check Quick Start Guide Here 👇:\n {1}").format(str(ve),CHANGAI_GUIDE_LINK))


def extract_tables_from_sql(sql: str) -> List[str]:
    """Extract all table names from a SQL query."""
    if not sql:
        return []
    matches = re.findall(r'`(tab[^`]+)`', sql, re.IGNORECASE)
    seen = set()
    tables = []
    for t in matches:
        if t not in seen:
            seen.add(t)
            tables.append(t)
    return tables

def _safe_strip(v):
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False, default=str)
    return str(v).strip()

# Shared State
class SQLState(TypedDict, total=False):
    payload_res :dict
    is_cud:bool
    cud_type:str
    payload:dict
    filters:str
    entity_type_list:List[str]
    create_entity:bool
    open_report:bool
    report_name:str
    entity_name:str
    doc:str
    reports_filter_before_call:list
    entity_type:str
    final_prompt:str
    request_id: str
    sendNonErptoAI:bool
    session_id: str
    question: str
    contains_values: bool
    entity_words:List[str]
    formatted_q: str
    hits: List[Any]
    context: str
    sql: str
    orm: str
    validation: Dict[str, Any]
    error: Optional[str]
    tries: int
    query_type: str
    sql_prompt: str
    formatting_prompt: str
    non_erp_res: str
    entity_cards: List[str]
    entity_raw: Any
    retrieval_mode: str
    top_tables: List[str]
    selected_tables: List[str]
    top_fields: Dict[str, Any]
    selected_fields: str
    message:str
    stop_followup:bool


def route_action(state: SQLState) -> str:
    if state.get("stop_followup"):
        return "STOP_FOLLOW"
    if state.get("create_entity"):
        return "CREATE_ENTITY"
    if state.get("open_report"):
        return "OPEN_REPORT"
    return "CONTINUE"


def cud_router_node(state: SQLState):
    return state

def fill_sql_prompt(question: str, context: str) -> str:
    return SQL_PROMPT.format(question=question, context=context)

def tokenize_mixed(text):
    return re.findall(r'[\u0600-\u06FF]+|[a-zA-Z0-9]+', text.lower())

def is_erp_query(master_match:bool, q: str, words_list: list,cut_off_perc:int) -> bool:
    if master_match:
        match = process.extract(
            q.strip().lower(),
            [v.strip().lower() for v in words_list],
            scorer=fuzz.WRatio,
            limit=5        )
        # matched_value = match[
        return {
            "matched_value": match,
        }
    words = tokenize_mixed(q)
    for word in words:
        if words_list != THREAD_WORDS:
            if word in STOP_WORDS:
                continue
            if len(word) <= 2:
                continue
        match = process.extractOne(
            word,
            words_list,
            scorer=fuzz.ratio,
            score_cutoff=cut_off_perc
        )

        if match:
            return True
    return False


def guardrail_router(state: SQLState) -> SQLState:
    request_id = state.get("request_id")
    chat_id = state.get("session_id")
    raw_q = state.get("question") or ""
    try:
        is_erp= is_erp_query(False,raw_q,BUSINESS_KEYWORDS,98)
        if is_erp:
            query_type = "ERP"
        elif is_thread_erp(raw_q, chat_id):
            query_type = "ERP"
        else:
            query_type = "NON_ERP"
    except Exception as e:
        query_type = "NON_ERP"
        frappe.log_error(frappe.get_traceback(), "Guardrail Router Error")
        return {**state, "query_type": query_type, "error": f"Error in guardrail router: {str(e)}"}
    state["query_type"] = query_type
    publish_pipeline_update(
            request_id,
            "question_classify_done",
            "Query classified as " + query_type,
            data={"query_type": query_type}
        )
    return state

def _parse_rewrite_response(raw: Any, user_qstn: str) -> Tuple[str, bool]:
    standalone = ""
    contains_values = False
    obj = None
    doc = None
    entity_words = []
    stop_followup =False
    entity_name = None
    report_name = None
    open_report = False
    create_entity = False
    report_intent = None
    message=None
    is_cud=None
    cud_type=None
    if isinstance(raw, dict):
        obj = raw
    elif isinstance(raw, str):
        try:
            obj = json.loads(raw.strip())
        except Exception:
            standalone = raw.strip()
    else:
        standalone = str(raw).strip()
    if isinstance(obj, dict):
        standalone = (obj.get("standalone_question") or "").strip() or standalone
        contains_values = bool(obj.get("contains_values"))
        entity_words = obj.get("entity_words") or [] if contains_values else []
        create_entity = bool(obj.get("create_entity"))
        create_entity = obj.get("create_entity") if create_entity else False
        if create_entity :
            doc = obj.get("doctype")
            entity_name = obj.get("entity_name")
        open_report = bool(obj.get("open_report"))
        if open_report:
            report_name = obj.get("report_name")
            report_intent = obj.get("report_intent")
        stop_followup = bool(obj.get("stop_followup"))
        if stop_followup:
            message = obj.get("message")
        is_cud = bool(obj.get("is_cud"))
        if is_cud:
            cud_type = obj.get("cud_type")
    elif isinstance(obj, list) and not standalone:
        standalone = json.dumps(obj)
    return standalone or user_qstn.strip(), contains_values, entity_words,create_entity, doc,entity_name,report_name,open_report,report_intent,stop_followup,message,is_cud,cud_type

def rewrite_question(state: SQLState) -> SQLState:
    report_intent = None
    request_id = state.get("request_id")
    user_qstn = state.get("question") or ""
    session_id = state.get("session_id")
    entity_words = []
    sys_prompt = SQL_REWRITE_SYS_PROMPT
    prompt = inject_prompt(user_qstn, session_id)
    report_name_new=None
    try:
        raw = call_model(prompt, "llm",sys_prompt)
        standalone, contains_values,entity_words,create_entity, doc,entity_name,report_name,open_report,report_intent,stop_followup,message,is_cud,cud_type = _parse_rewrite_response(raw, user_qstn)
        if report_intent:
            report_name_new = match_report_intent(report_intent)
        publish_pipeline_update(
            request_id,
            "question_rewrite_done",
            "Question rewritten",
            data={"formatted_q": standalone}
        )
        return {
            **state,
            "payload":{},
            "payload_res":None,
            "report_name":report_name_new or report_name or "",
            "report_intent": report_intent,
            "open_report":open_report,
            "create_entity":create_entity,
            "entity_name":entity_name if create_entity else None,
            "doc":doc if create_entity else None,
            "formatted_q": standalone,
            "contains_values": contains_values,
            "entity_words": entity_words,
            "formatting_prompt": prompt,
            "error": None,
            "message":message if stop_followup else None,
            "stop_followup": stop_followup,
            "is_cud":is_cud,
            "cud_type":cud_type
        }
    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        publish_pipeline_update(
            request_id,
            "failed",
            str(e),
            error=True,
            done=True
        )
        return {**state, "error": str(e)}


ENTITY_CREATION_PROMPT = read_asset("create_entity_prompt.txt", base="prompts")
def create_entity(state:SQLState):
    request_id = state.get("request_id")
    res = call_fvs_table_search(True, state.get("formatted_q"), state.get("request_id"))
    prompt =ENTITY_CREATION_PROMPT.format(question=state.get("formatted_q"),candidate_doctypes=res[:10])
    publish_pipeline_update(
    request_id,
    "Detecting doctype for creation",
    "Detecting doctype for creation",
    done=True)
    res = call_gemini(prompt,"")
    try:
        if isinstance(res, str):
            res = res.replace("```json", "").replace("```", "").strip()
            result = json.loads(res)
            doctype = result.get("doctype", "")
        return {**state,"doc": doctype}
    except json.JSONDecodeError as e:
        return {**state,"error":str(e)}

def _parse_json_list(raw: str) -> List[Any]:
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def get_payload(prompt:str,user_prompt:str,state:SQLState):
    payload={}
    response=call_model(prompt,"llm",user_prompt)
    response = re.sub(r"^```(?:json)?\s*", "", response)
    response = re.sub(r"\s*```$", "", response)
    if not response:
        return {**state, "error": "Empty response from LLM", "sql_prompt": prompt}
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except json.JSONDecodeError:
            return {}
    return response.get("payload", {})



def check_update(res:dict):
    if not res.get("data"):
        frappe.throw(_(
            "Master Data does not exist. Because of this, results may not be accurate. "
            "For better accuracy, please open "
            "<a href='{0}' target='_blank' rel='noopener noreferrer' style='color:#1e90ff;'>Go to Settings Page</a> "
            "and click on the <b>Update Master Data</b> button in the Training tab.<br><br>"
            "Check Quick Start Guide Here 👇:<br>"
            "<a href='{1}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Click here</a><br>"
            "<a href='{2}' target='_blank' rel='noopener noreferrer' style='color:#1e90ff;'>ERPGulf.com</a>"
        ).format(settingsUrl, CHANGAI_GUIDE_LINK, ERPGULF_LINK))

    if res.get("is_stale"):
        frappe.throw(_(
            "Master Data not updated."
            "Because of this, results may not be accurate. "
            "For better accuracy, please open "
            "<a href='{1}' target='_blank' rel='noopener noreferrer' style='color:#1e90ff;'>Go to Settings Page</a> "
            "and click on the <b>Update Master Data</b> button in the Training tab.<br><br>"
            "Check Quick Start Guide Here 👇:<br>"
            "<a href='{2}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Click here</a><br>"
            "<a href='{3}' target='_blank' rel='noopener noreferrer' style='color:#1e90ff;'>ERPGulf.com</a>"
        ).format(res.get("days"), settingsUrl, CHANGAI_GUIDE_LINK, ERPGULF_LINK))

def generate_orm(state: SQLState) -> SQLState:
    from changai.changai.api.v2.auto_gen_api import update_masterdata
    attempt  = 0
    MAX_TRIES = 4
    payload = {}
    request_id = state.get("request_id")
    cud_type = state.get("cud_type")
    fields = _safe_strip(state.get("selected_fields") or "")
    entity_cards = state.get("entity_cards") or []
    entity_block = ""
    config = ChangAIConfig.get()
    formatted_q = state.get("formatted_q")
    prompt = None
    if not formatted_q:
        return {**state, "sql": "", "orm": "", "error": "No question to generate SQL for", "sql_prompt": ""}
    if entity_cards:
        entity_block = "\n\nENTITY_CARDS:\n" + "\n".join(str(c) for c in entity_cards)
    if config["retriever_structure"]=="multi line":
        context = fields + (entity_block or "")
        context = re.sub(
            r'\btab([A-Za-z0-9_ ]+)',
            r'\1',
            context
        )
        try:
            prompt, user_prompt = get_cud_prompt(cud_type,formatted_q,context)
        except ValueError as e:
            return {
                **state,
                "error": str(e)
            }
    try:
        while(attempt < MAX_TRIES):
            payload = get_payload(prompt, user_prompt,state)
            if payload and payload!={}:
                break
            attempt += 1
            frappe.log_error(f"Empty payload received. Retrying... attempt {attempt}/{MAX_TRIES}")
        if not payload or payload == {}:
            frappe.log_error(f"Empty payload received. After all {MAX_TRIES} Tries.")
            return {"error":f"Failed to generate the payload for {cud_type}"}
        publish_pipeline_update(
            request_id,
            "Payload_generated",
            "Payload  generated"
        )
        if cud_type == "insert":
            response = execute_insert(payload)  
            return {**state,"sql":"","final_prompt":prompt,"payload":payload, "payload_res": response}
        elif cud_type == "update":
            response = execute_update(payload)
            return {**state,"sql":"","final_prompt":prompt,"payload":payload, "payload_res": response}
        elif cud_type == "delete":
            response = execute_delete(payload)
            return {**state,"sql":"","final_prompt":prompt,"payload":payload, "payload_res": response}
        else:
            return {
                **state,
                "error": f"Unsupported CUD type: {cud_type}"
            }
    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        return {**state,"error": f"LLM call failed: {e}","sql_prompt":prompt}



# Node 1: Retrive with Fiass Vector Store.
def schema_retriever(state: SQLState) -> SQLState:
    config = ChangAIConfig.get()
    try:
        if config["REMOTE"]:
            hits = remote_embedder_request(state.get("formatted_q", "") or state.get("question", ""))
            return {**state, "hits": hits}
        else:
            out = call_retrieve_multi_line(state.get("is_cud"),state.get("formatted_q") or state.get("question") or "",state.get("request_id"),)
            return {
                **state,
                "retrieval_mode": "multi",
                "top_tables": out.get("top_tables", []),
                "top_fields": out.get("top_fields", {}),
                "selected_fields": out.get("selected_fields", ""),
                "selected_tables": out.get("selected_tables", []),
            }
    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        return {**state, "error": f"Schema retrieval failed: {e}"}


# # Node 2: Build schema context from hits - for SQL Prompt
def hits_to_prompt_context(state:SQLState) -> SQLState:
    ctx=hits_to_schema_context(state["hits"],title="SCHEMA CONTEXT",max_fields_per_table=25)
    entity_context=state.get("entity_cards", [])
    full_context = ctx
    if entity_context:
        full_context += "\n\nENTITY_CARDS:\n"
        full_context += "\n".join(entity_context)
    return {
        **state,
        "context": full_context
    }


# # Node 3:Generate the SQL Prompt and call LLM(Ollama Http)
def generate_sql(state:SQLState) -> SQLState:
    # if state.get("context") == "" or state.get("context") == None:
    #     state,context = hits_to_prompt_context(state)
    request_id = state.get("request_id")
    fields = _safe_strip(state.get("selected_fields") or "")
    entity_cards = state.get("entity_cards") or []
    entity_block = ""
    config = ChangAIConfig.get()
    formatted_q = state.get("formatted_q")
    if not formatted_q:
        return {**state,"payload":{},"payload_res":None, "sql": "", "orm": "", "error": "No question to generate SQL for", "sql_prompt": ""}
    if entity_cards:
        entity_block = "\n\nENTITY_CARDS:\n" + "\n".join(str(c) for c in entity_cards)
    if config["retriever_structure"]=="multi line":
        context = fields + (entity_block or "")
        prompt = SQL_PROMPT.format(question=formatted_q, context=context)
        state["final_prompt"] = prompt
    else:
        prompt=fill_sql_prompt(formatted_q,state["context"])
    try:
        response=call_model(prompt,"llm",SQL_SYS_PROMPT)
        if not response:
            return {**state, "error": "Empty response from LLM", "sql_prompt": prompt}
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                return {
                    **state,
                    "error": "Invalid JSON returned by LLM"
                }
        sql = response.get("sql", "")
        payload = response.get("payload", {})
        publish_pipeline_update(
            request_id,
            "sql_generated",
            "SQL generated"
        )
        return {**state,"sql_prompt":prompt,"sql":sql,"payload":payload,"error":None,"payload_res": None}
    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        return {**state,"error": f"LLM call failed: {e}","sql_prompt":prompt}
# # Node 4:Validate the SQL Generate with meta schema mapping using SQLGlot
def validate_sql(state: SQLState) -> SQLState:
    sql = clean_sql(state.get("sql") or "")
    if not sql:
        return {
            **state,
            "validation": {
                "ok": False,
                "unknown_tables": [],
                "unknown_columns": [],
                "ambiguous_columns": [],
                "details": {
                    "parse_error": sql or "Empty SQL from LLM"
                },
            },
        }

    val = validate_sql_against_mapping(sql, mapping_data, dialect="mysql")
    return {**state, "validation": val}


def route_is_cud(state:SQLState):
    if state.get("is_cud"):
        return "IS_CUD"
    else:
        return "NOT_CUD"


# # Node 5:Repair Loop :Simple prompt for one more try.
def repair_sqlquery(state: SQLState) -> SQLState:
    hints: List[str] = []
    tries = int(state.get("tries") or 0) + 1
    val = state.get("validation", {})
    unknown_tables = val.get("unknown_tables", [])
    unknown_cols = val.get("unknown_columns", [])
    ambiguous = val.get("ambiguous_columns", [])

    if unknown_tables:
        hints.append(f"Unknown tables:{unknown_tables}.Use only tables in context")
    if unknown_cols:
        hints.append(f"Unknown Columns:{unknown_cols}.Use only fields listed for each tables from the context")
    if ambiguous:
        hints.append(f"Ambiguous columns(qualify them):{ambiguous}")
    sql_prompt = state.get("sql_prompt")
    if not sql_prompt:
        return {**state, "tries": tries, "error": "No SQL prompt to repair from"}
    patched_prompt =sql_prompt + "\n\n#VALIDATION HINTS\n" + "\n".join(f"-{h}" for h in hints)

    try:
        response = call_model(patched_prompt,"llm",SQL_SYS_PROMPT)
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except json.JSONDecodeError:
                return {**state, "tries": tries, "error": f"{response[:200]}"}

        if not response or not isinstance(response, dict):
            return {**state, "tries": tries, "error": "Repair: empty or invalid response from LLM"}

        sql = response.get("sql", "")
        return {**state, "sql": sql, "tries": tries, "error": None}
    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        return {**state, "tries": tries, "error": f"Repair call failed {e}"}


def detect_specific_entities(state: SQLState) -> SQLState:
    if not state.get("contains_values"):
        return {**state, "entity_cards": [], "entity_raw": None}
    
    q = (state.get("formatted_q") or "").strip()
    if not q:
        return {**state, "entity_cards": [], "entity_raw": None}
    if state.get("is_cud") and state.get("cud_type") == "insert":
        return {
            **state,
            "entity_cards": [],
            # "entity_raw": out.get("raw"),
        }

    try:
        res = check_file_updates("master_data.yaml")
        check_update(res)
        out = call_entity_retriever(False, q, state)
        return {
            **state,
            "entity_cards": out.get("cards") or [],
            # "entity_raw": out.get("raw"),
        }
    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(f"Entity retriever failed: {e}", "ChangAI Entity Gate")
        return {**state, "entity_cards": [], "entity_raw": {"error": str(e)}}



def routeNonErpToAI(state: SQLState):
    question= state["question"]
    sys_prompt = """You are ChangAI, an intelligent assistant powered by ERPGulf. 
The user has asked a general question that is not related to ERP. 
Answer the question clearly and helpfully.
Always mention that you are ChangAI by ERPGulf when introducing yourself."""
    if frappe.utils.cint(state.get("sendNonErptoAI", 0)) == 1 or state.get("sendNonErptoAI") == "true":
        try:
            res = call_gemini(question,sys_prompt)
            return {**state, "non_erp_res": res}
        # except ValidationError as ve:
        #     return {**state,"error":str(ve)}
        except frappe.exceptions.ValidationError:
            raise
        except Exception as e:
            return {**state, "non_erp_res": "Model Calling Failed .Please try Again","error":str(e)}
    else:
        res= send_non_erp_request(state)
        return res


def send_non_erp_request(state: SQLState) -> SQLState:
    qstn =state.get("question")
    if not qstn:
        return {**state, "non_erp_res": "", "error": "No question provided"}
    try:
        # response = handle_non_erp_query(qstn)
        response = non_erp_response(qstn)
        # response = call_model(prompt, "llm")
        if not response or not response.get("data"):
            return {**state,"non_erp_res": "", "error": str(response)}
        return {**state,"non_erp_res": response["data"], "error": None}
    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        return {**state, "non_erp_res": "", "error": f"NON-ERP call failed: {e}"}
 
def route_after_entities(state: SQLState) -> str:
    config = ChangAIConfig.get()
    return "DIRECT" if config.get("retriever_structure") == "multi line" else "CONTEXT"


def route_guardrail(state: SQLState) -> str:
    return "ERP" if state.get("query_type") == "ERP" else "NON_ERP"


# # Router to decide next stage:
def router(state:SQLState) -> str:
    if state.get("error"):
        return "end"
    val=state.get("validation",{})
    if val.get("ok"):
        return "end"
    tries=int(state.get("tries") or 0)
    if tries < RETRY_LIMIT:
        return "repair"
    return "end"

def prepare_report_action(state: SQLState) -> SQLState:
    report_name = None
    q = state.get("formatted_q") or state.get("question") or ""
    request_id = state.get("request_id")
    report_name = state.get("report_name")
    cards = call_entity_retriever(True, q, state) if state.get("contains_values") else {"cards": []}
    # reports_listed = call_fvs_table_search(False, q, request_id)
    doctype = state.get("doc") if state.get("doc") else None
    result = []
    result.append({"report":report_name,"filters": get_report_filter_fields(report_name)})
    prompt = REPORT_ACTION_PROMPT.format(
    question=q,
    doctype=doctype or "",
    available_reports=json.dumps(result, ensure_ascii=False, default=str),
    entity_cards=json.dumps(cards, ensure_ascii=False, default=str))
    response = call_model(prompt, "llm", "")
    raw_response = str(response or "").strip()
    raw_response = raw_response.replace("```json", "").replace("```", "").strip()
    if not raw_response:
        response = {"report_name": "", "filters": {}}
    else:
        try:
            response = json.loads(raw_response)
        except json.JSONDecodeError:
            frappe.log_error(
                f"Invalid JSON from prepare_report_action:\n{raw_response}",
                "prepare_report_action JSON Error"
            )
            response = {"report_name": "", "filters": {}}
    if not isinstance(response, dict):
        response = {"report_name": "", "filters": {}}
    publish_pipeline_update(
        request_id,
        "Detected Report name & filters",
        "Detected Report name & filters",
        data={"report_name": response.get("report_name"),"filters":response.get("filters")},
        done=True
    )
    return {
        **state,
        "report_name": response.get("report_name") or "",
        "filters": response.get("filters") or {},
        "reports_filter_before_call":result[:30],
        "entity_cards": cards.get("cards") or [],
        "entity_raw": cards,
        "error": None,
    }
# Building the Workflow Graph
workflow=StateGraph(SQLState)
workflow.add_node("rewrite_question",rewrite_question)
workflow.add_node("guardrail_router",guardrail_router)
workflow.add_node("retrieve",schema_retriever)
workflow.add_node("detect_entities", detect_specific_entities)
workflow.add_node("build_context",hits_to_prompt_context)
workflow.add_node("generate_sql",generate_sql)
workflow.add_node("validate_sql",validate_sql)
workflow.add_node("repair_sql",repair_sqlquery)
workflow.add_node("send_non_erp_request",send_non_erp_request)
workflow.add_node("routeNonErpToAI",routeNonErpToAI)
workflow.add_node("prepare_report_action", prepare_report_action)
workflow.add_node("create_entity", create_entity)
workflow.set_entry_point("guardrail_router")
workflow.add_node("generate_orm", generate_orm)
workflow.add_node("cud_router_node", cud_router_node)
workflow.add_conditional_edges("guardrail_router",route_guardrail,{"ERP":"rewrite_question","NON_ERP":"routeNonErpToAI"})
workflow.add_edge("routeNonErpToAI", END)
workflow.add_conditional_edges(
    "rewrite_question",
    route_action,
    {
        "CREATE_ENTITY": "create_entity",
        "OPEN_REPORT": "prepare_report_action",
        "STOP_FOLLOW":END,
        "CONTINUE": "retrieve"
    }
)
workflow.add_edge("prepare_report_action", END)
workflow.add_edge("create_entity", END)
workflow.add_edge("retrieve","detect_entities")
workflow.add_conditional_edges("detect_entities", route_after_entities, {"CONTEXT":"build_context","DIRECT":"cud_router_node"})
workflow.add_edge("build_context", "cud_router_node")
workflow.add_conditional_edges("cud_router_node", route_is_cud, {"IS_CUD":"generate_orm","NOT_CUD":"generate_sql"})
workflow.add_edge("generate_sql",END)
workflow.add_edge("generate_orm",END)
checkpointer=MemorySaver()
app=workflow.compile(checkpointer=checkpointer)
def _build_match_conditions(doctypes: List[str]) -> str:
    conditions = []
    for t in doctypes:
        doctype = t[3:] if t.startswith("tab") else t
        cond = build_match_conditions(doctype)
        if cond:
            conditions.append(cond)
    return " AND ".join(conditions) if conditions else ""


def _append_conditions(sql: str, combined: str) -> str:
    if "where" in sql.lower():
        return sql + f" AND {combined}"
    return sql + f" WHERE {combined}"


def execute_query(sql: str, doctypes: List[str]) -> Any:
    try:
        if not sql:
            return []
        # if not str(sql).lower().strip().startswith("select"):
        #     frappe.throw(_("Only SELECT queries are allowed."
        #                    "Check Quick Start Guide Here 👇:\n {0}").format(CHANGAI_GUIDE_LINK))
        sql = sql.rstrip().rstrip(';')
        combined = _build_match_conditions(doctypes)
        if combined:
            sql = _append_conditions(sql, combined)
        return frappe.db.sql(sql, as_dict=True)
    except frappe.PermissionError:
        return {
            "error": _("You do not have permission to access this data. Check the Quick Start Guide here 👇: {0}").format(
                f'<a href="{CHANGAI_GUIDE_LINK}" target="_blank">Click here</a><br><br><a href="{ERPGULF_LINK}" target="_blank">ERPGulf.com</a>'
            )        }
    except Exception as e:
        return {"error": f"SQL Execution Failed: {e}\n Check Quick Start Guide Here 👇:\n {CHANGAI_GUIDE_LINK}"}


def _invoke_pipeline(user_question: str, chat_id: str, request_id: str,sendNonErptoAI: bool = False):
    initial_state: SQLState = {
        "question": user_question or "",
        "session_id": chat_id,
        "request_id": request_id,
        "sendNonErptoAI":sendNonErptoAI
    }
    config = {
        "configurable": {"thread_id": chat_id},
        "run_name": "changai_text2sql_graph",
        "run_type": "graph",
        "tags": ["changai", "rag", "sql"],
        "metadata": {"tenant": "demo"},
    }
    try:
        return app.invoke(initial_state, config=config), None
    except frappe.exceptions.ValidationError as e:
        # clean_msg = re.sub(r'<[^>]+>', '', str(e))
        return None, {"Bot": str(e), "error": str(e)}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "ChangAI Pipeline Invoke Error")
        return None, {"Bot": "⚠️ An unexpected error occurred. Please try again.", "error": str(e)}


def _handle_non_erp_(non_erp_res,formatted_q,err,user_question: str,request_id:str, chat_id: str) -> Dict:
    if not non_erp_res:
        if err:
            frappe.log_error(err, "ChangAI NON_ERP Error")
            save_logs(user_question=user_question, formatted_q="Not formatted as its NONERP",err=err, result=non_erp_res,type_="NonERP")
        return {
            "Question": user_question,
            "Formatted-Question": formatted_q,
            "Bot": err if err else "⚠️ Could not get a response. Please try again.",
        }

    if not err and non_erp_res:
        try:
            publish_pipeline_update(request_id, "mapped to non-erp", "Mapped as NON-ERP")
            save_turn_2(session_id=chat_id, user_text=formatted_q or user_question, bot_text=non_erp_res,type_="non_erp")
            save_logs(user_question=user_question, formatted_q="Not formatted as its NONERP",err="None", result=non_erp_res,type_="NonERP")
        except Exception as e:
            frappe.log_error(f"Failed to save NON_ERP logs: {e}", "ChangAI Logs")
            save_logs(user_question=user_question, formatted_q="Not formatted as its NONERP",err=str(e), result=non_erp_res,type_="NonERP")
    return {"Question": user_question, "Formatted-Question": formatted_q, "Bot": non_erp_res}


def _handle_sql_result(
    memory_status: Dict,
    request_id: str,
    sql_prompt: Optional[str],
    final: Optional[Dict],
    sql: str,
    formatted_q: Optional[str],
    fields: Optional[str],
    selected_tables: Optional[List],
    val: Optional[Dict],
    entity_debug: Optional[Dict],
    user_question: str,
    chat_id: str
) -> Dict:
    final = final or {}
    val = val or {}
    entity_debug = entity_debug or {}
    selected_tables = selected_tables or []
    fields = fields or ""
    formatted_q = formatted_q or user_question
    sql_result=[]
    extracted_tables=[]
    formatted_result =""
    payload = {}
    try:
        request_id = request_id or final.get("request_id")
        org_sql = final.get("sql") or sql
        payload = final.get("payload") or {}
        payload_res = final.get("payload_res")
        if org_sql:
            extracted_tables = extract_tables_from_sql(org_sql)
        try:
            if sql:
                sql_result = execute_query(sql, extracted_tables)
        except Exception as e:
            # err = str(e)
            final["error"] = str(e)
        publish_pipeline_update(request_id, "sql_executed", "Query executed")
        entity_words = final.get("entity_words") or []
    except Exception as e:
        final["error"] = str(e)
        return {"ok": False, "error": f"SQL Execution Failed: {e}"}
    context = (final.get("context") or final.get("selected_fields") or fields or "")[:800]
    contains_values = final.get("contains_values") or entity_debug.get("contains_values") or ""
    err = final.get("error")

    payload_res = final.get("payload_res")

    if payload_res:
        # ✅ Check if it's an error response
        if payload_res.get("error") and not payload_res.get("success"):
            error_msg = payload_res.get("error", "Unknown error occurred")
            # Clean HTML tags if any
            clean_msg = re.sub(r'<[^>]+>', '', error_msg)
            publish_pipeline_update(
                request_id,
                "format_data_completed",
                "Completed Formatting Result",
                done=True
            )
            save_turn_2(
                session_id=chat_id,
                user_text=formatted_q,
                bot_text=f"❌ {clean_msg}",
                type_="erp"
            )
            save_logs(
                user_question=user_question,
                formatted_q=formatted_q,
                context=context,
                payload=payload,
                sql=sql,
                val=val,
                err=clean_msg,
                result=[],
                formatted_result=f"❌ {clean_msg}",
                tables=selected_tables,
                fields=fields,
                entity_debug=entity_debug,
                type_="ERP"
            )
            return {
                "Model returned SQL": "",
                "context": context,
                "payload": payload,
                "entity_words": [],
                "Question": user_question,
                "payload_res": payload_res,
                "Formated Question": formatted_q,
                "Cleaned SQL": "",
                "Tables": selected_tables,
                "Fields": fields,
                "Entity Values present ?": "",
                "Validation": {},
                "Error": clean_msg,
                "result": [],
                "EntityDebug": entity_debug,
                "Bot": {
                    "answer": f"❌ {clean_msg}"
                }
            }

        # ✅ Normal success case
        formatted_result = format_data(user_question, payload_res)
    elif sql:
        formatted_result = format_data(
            user_question,
            sql_result
        )
    publish_pipeline_update(
        request_id,
        "format_data_completed",
        "Completed Formatting Result",
        done=True
    )
    if not err:
        try:
            save_turn_2(
                session_id=chat_id,
                user_text=formatted_q,
                bot_text=formatted_result,
                type_="erp"
            )
        except Exception as e:
            save_logs(
                user_question=user_question,
                payload=payload,
                formatted_q=formatted_q,
                context=context,
                sql=sql,
                val=val,
                err=str(e),
                result=sql_result,
                formatted_result=formatted_result,
                tables=selected_tables,
                fields=fields,
                entity_debug=entity_debug,
                type_="ERP"
            )
            return {"ok": False, "error": str(e)}
    save_logs(
                user_question=user_question,
                formatted_q=formatted_q,
                context=context,
                payload=payload,
                sql=sql,
                val=val,
                err=err if err else "",
                result=sql_result,
                formatted_result=formatted_result,
                tables=selected_tables,
                fields=fields,
                entity_debug=entity_debug,
                type_="ERP"
            )
    return {
        "Model returned SQL": org_sql,
        "context": context,
        "payload":payload,
        "entity_words": entity_words,
        "Question": user_question,
        "payload_res":final.get("payload_res"),
        "Formated Question": formatted_q,
        "Cleaned SQL": sql,
        "Tables": selected_tables,
        "Fields": fields,
        "Entity Values present ?": contains_values,
        "Validation": val,
        "Error": err,
        "result": sql_result,
        "EntityDebug": entity_debug if entity_debug.get("contains_values") else None,
        "Bot": formatted_result
    }
RETRY_PROMPT = read_asset("retry_sys_prompt.txt",base="prompts")
RETRY_USER_PROMPT = read_asset("retry_user_prompt.txt",base="prompts")
def retry_sql(sql, error, formatted_q, sql_prompt):
    retry_prompt = SQL_SYS_PROMPT + RETRY_PROMPT
    user_prompt = sql_prompt + RETRY_USER_PROMPT.format(sql=sql,error=error,formatted_q=formatted_q)
    try:
        rewritten = call_gemini(user_prompt, sys_prompt=retry_prompt)
        rewritten_json = json.loads(rewritten)
        retried_sql = clean_sql(rewritten_json.get("sql") or "")
        retried_orm = clean_sql(rewritten_json.get("orm") or "")
    except Exception:
        return "",{"ok": False, "error": "Retry failed to parse response"}
    if not retried_sql:
        return "",{"ok": False, "error": "Retry returned empty SQL"}
    val_res = validate_sql_schema(retried_sql)
    return retried_sql, val_res

def is_thread_erp(q:str,chat_id:str):
    msg_type = get_last_thread_message(chat_id)
    if msg_type == "erp" and is_erp_query(False,q, THREAD_WORDS,98):
        return True
    else:
        return False

@frappe.whitelist(allow_guest=False)
def run_text2sql_pipeline(
    user_question: str,
    chat_id: str,
    request_id: str,
    sendNonErptoAI: bool = False
) -> Dict:

    memory_status = check_memory_status()

    # --------------------------------------------------
    # CACHE
    # --------------------------------------------------
    logs = find_similar_log_question(user_question)

    if logs.get("matched"):
        publish_pipeline_update(
            request_id,
            "cache_hit",
            "Using cached result"
        )

        formatted_q = logs.get("rewritten_question")
        sql = logs.get("sql")

        tables = json.loads(logs.get("tables") or "[]")
        fields = logs.get("fields") or ""
        entity_debug = json.loads(logs.get("entity_debug") or "{}")

        return _handle_sql_result(
            memory_status,
            request_id,
            None,
            {},
            sql,
            formatted_q,
            fields,
            tables,
            {"ok": True, "from_cache": True},
            entity_debug,
            user_question,
            chat_id
        )

    # --------------------------------------------------
    # PIPELINE INVOCATION
    # --------------------------------------------------
    final, err_response = _invoke_pipeline(
        user_question,
        chat_id,
        request_id,
        sendNonErptoAI
    )
    if err_response:
        return err_response

    if not final:
        return {
            "error": "Pipeline returned empty state"
        }
    if (final.get("query_type") or "NON_ERP") == "NON_ERP":

        non_erp_res = _safe_strip(final.get("non_erp_res", ""))
        formatted_q = _safe_strip(final.get("formatted_q", ""))
        err = final.get("error")

        return _handle_non_erp_(
            non_erp_res,
            formatted_q,
            err,
            user_question,
            request_id,
            chat_id
        )

    if final.get("create_entity") is True:
        return {
            "create_entity": True,
            "doc": final.get("doc"),
            "entity_name": final.get("entity_name")
        }

    if final.get("open_report") is True:
        return {
            "open_report": True,
            "report_name": final.get("report_name"),
            "filters": final.get("filters") or {},
            "reports_filter_before_call": final.get("reports_filter_before_call"),
            "entity_raw": final.get("entity_raw"),
            "question_rewritten": _safe_strip(final.get("formatted_q") or "")
        }

    if final.get("stop_followup"):

        save_turn_2(
            session_id=chat_id,
            user_text=user_question,
            bot_text=final.get("message"),
            type_="non_erp"
        )

        save_logs(
            user_question=user_question,
            formatted_q="",
            context=None,
            payload=final.get("payload") or None,
            sql=None,
            val=None,
            err=final.get("error") or "",
            result=None,
            formatted_result=final.get("message"),
            tables=None,
            fields=None,
            entity_debug=None,
            type_="NonERP"
        )

        publish_pipeline_update(
            request_id,
            "Stop follow-up detected",
            "Stop follow-up detected",
            data={"message": final.get("message")},
            done=True
        )

        return {
            "Model returned SQL": None,
            "context": None,
            "entity_words": None,
            "Question": user_question,
            "Formated Question": _safe_strip(final.get("formatted_q") or ""),
            "Cleaned SQL": None,
            "stop_followup": True,
            "ORM": None,
            "Tables": None,
            "Fields": None,
            "Entity Values present ?": None,
            "Validation": None,
            "Error": final.get("error"),
            "result": None,
            "EntityDebug": None,
            "Bot": final.get("message"),
        }
    payload = final.get("payload") or {}
    payload_res = final.get("payload_res")
    sql = clean_sql(final.get("sql")) or ""
    formatted_q = _safe_strip(final.get("formatted_q") or "")
    context = final.get("context") or ""
    selected_tables = final.get("selected_tables") or []
    fields = _safe_strip(final.get("selected_fields") or "")
    sql_prompt = _safe_strip(final.get("sql_prompt") or "")
    entity_debug = {
        "contains_values": final.get("contains_values"),
        "entity_cards": final.get("entity_cards") or [],
    }
    err = final.get("error")
    res = {}
    if payload_res:
        return _handle_sql_result(
            memory_status,
            request_id,
            sql_prompt,
            final,
            sql,
            formatted_q,
            fields,
            selected_tables,
            res,
            entity_debug,
            user_question,
            chat_id
        )
    if sql:
        res = validate_sql_schema(sql)
        publish_pipeline_update(
            request_id,
            "sql_validated",
            _("SQL validation Completed")
        )
        if res.get("ok"):
            return _handle_sql_result(
                memory_status,
                request_id,
                sql_prompt,
                final,
                sql,
                formatted_q,
                fields,
                selected_tables,
                res,
                entity_debug,
                user_question,
                chat_id
            )

        retried_sql2, retry2_val_res = retry_sql(
            sql,
            res.get("error"),
            formatted_q,
            sql_prompt
        )

        if retry2_val_res.get("ok"):
            return _handle_sql_result(
                memory_status,
                request_id,
                sql_prompt,
                final,
                retried_sql2,
                formatted_q,
                fields,
                selected_tables,
                retry2_val_res,
                entity_debug,
                user_question,
                chat_id
            )

        retried_sql3, retry3_val_res = retry_sql(
            retried_sql2,
            retry2_val_res.get("error"),
            formatted_q,
            sql_prompt
        )

        if retry3_val_res.get("ok"):
            return _handle_sql_result(
                memory_status,
                request_id,
                sql_prompt,
                final,
                retried_sql3,
                formatted_q,
                fields,
                selected_tables,
                retry3_val_res,
                entity_debug,
                user_question,
                chat_id
            )

        final_error = (
            retry3_val_res.get("error")
            or retry2_val_res.get("error")
            or res.get("error")
            or "SQL not valid or missing"
        )
        return _error_response(
            memory_status,
            user_question,
            formatted_q,
            context,
            selected_tables,
            fields,
            retried_sql3 or retried_sql2 or sql,
            retry3_val_res,
            entity_debug,
            2,
            final_error,
            err
        )
    return _error_response(
        memory_status,
        user_question,
        formatted_q,
        context,
        selected_tables,
        fields,
        sql,
        {},
        entity_debug,
        1,
        "No SQL or Payload generated",
        err
    )



@frappe.whitelist(allow_guest=False)
def guardrail_router_test(
    question: str,
    chat_id: str = None,
    request_id: str = "test_001"
):
    try:
        is_erp = is_erp_query(False, question, BUSINESS_KEYWORDS, 98)
        if is_erp:
            query_type = "ERP"
        elif chat_id and is_thread_erp(question, chat_id):
            query_type = "ERP"
        else:
            query_type = "NON_ERP"

        return {
            "success": True,
            "question": question,
            "query_type": query_type,
            "is_erp_match": bool(is_erp),
            "is_thread_erp": bool(chat_id and is_thread_erp(question, chat_id))
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Guardrail Router Test Error")
        return {
            "success": False,
            "question": question,
            "query_type": "NON_ERP",
            "error": str(e)
        }