import json
import frappe
from typing import Any, Optional, Dict
from rapidfuzz import fuzz
CHANGAI_CHAT_HIST_DOC = "ChangAI Chat History"

def save_logs(
    user_question: Optional[str] = None,
    formatted_q: Optional[str] = None,
    context: Optional[str] = None,
    payload: Optional[dict]=None,
    sql: Optional[str] = None,
    val: Any = None,
    result: Any = None,
    tries: Optional[int] = None,
    err: Any = None,
    formatted_result: Any = None,
    tables:Any=None,
    fields:Any=None,
    entity_debug:Any=None,
    type_=None
) -> str:
    def to_json_if_needed(v: Any) -> Any:
        if isinstance(v, (dict, list)):
            return json.dumps(v, default=str, ensure_ascii=False)
        return v
    
    MAX_LOG_LEN = 140
    doc = frappe.new_doc("ChangAI Logs")
    doc.user_question = user_question
    doc.payload = json.dumps(payload) if payload else None
    safe_question=(formatted_q[:137] + "..." if formatted_q and len(formatted_q) > MAX_LOG_LEN else formatted_q or "")
    doc.rewritten_question = safe_question
    doc.schema_retrieved = to_json_if_needed(context)
    doc.sql_generated = to_json_if_needed(sql)
    doc.validation = to_json_if_needed(val)
    doc.tries = tries
    doc.error = to_json_if_needed(err)
    doc.result = to_json_if_needed(result)
    doc.formatted_result = to_json_if_needed(formatted_result)
    doc.tables = to_json_if_needed(tables)
    doc.fields = to_json_if_needed(fields)
    doc.entity = to_json_if_needed(entity_debug)
    doc.type = type_
    doc.insert(ignore_permissions=True)
    return doc.name


def save_message_doc(session_id:str,message_type:str,content:str):

    doc=frappe.get_doc({
        "doctype":CHANGAI_CHAT_HIST_DOC,
        "session_id": session_id,
        "message_type": message_type,
        "content": content or ""
    })
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist(allow_guest=False)
def save_turn_2(session_id: str, user_text: str=None, bot_text: Any = None,type_:str=None):
    # find existing document
    doc_name = frappe.db.exists(CHANGAI_CHAT_HIST_DOC, {"session_id": session_id})
    history = []
    if doc_name:
        raw = frappe.db.get_value(CHANGAI_CHAT_HIST_DOC, doc_name, "content")
        if raw:
            try:
                history = json.loads(raw)
            except Exception:
                history = []

    if user_text:
        history.append({"human": user_text,"type":type_})
    if bot_text:
        history.append({"ai": bot_text})
    new_content = json.dumps(history, ensure_ascii=False, indent=2)

    if doc_name:
        frappe.db.set_value(
            CHANGAI_CHAT_HIST_DOC,
            doc_name,
            "content",
            new_content,
            update_modified=True
        )
        return doc_name

    else:
        doc = frappe.get_doc({
            "doctype": CHANGAI_CHAT_HIST_DOC,
            "session_id": session_id,
            "content": new_content
        })
        doc.insert(ignore_permissions=True)
        return doc.name


@frappe.whitelist(allow_guest=False)
def get_chat_history(session_id: str) -> list:
    doc_name = frappe.db.exists(CHANGAI_CHAT_HIST_DOC, {"session_id": session_id})
    if not doc_name:
        return []

    raw = frappe.db.get_value(
        CHANGAI_CHAT_HIST_DOC,
        doc_name,
        "content"
    )

    if not raw:
        return []

    try:
        history = json.loads(raw)
    except Exception:
        return []

    return history[-5:]

@frappe.whitelist(allow_guest=False)
def respond_from_cache(user_question:str):
    if user_question:
        doc=frappe.db.get_value("ChangAI Logs",{"user_question":user_question},["sql_generated","result"],as_dict=False)
        return doc

PROMPT_FOLLOWUP = """You are an ERP query rewriter and entity detector.
Return ONLY valid JSON:
{{"standalone_question":"...","contains_values":true/false}}
TASK 1 — FOLLOW-UP
- If the query depends on previous messages, rewrite it as a complete standalone question.
- Otherwise keep it unchanged.
TASK 2 — ENTITY DETECTION
contains_values = TRUE Any noun that refers to a specific named master record 
(item name, customer name, supplier name, warehouse name, employee name) 
if not sure then also contains_values = TRUE otherwise contains_values = FALSE
Eg:
TASK 3 — ERP CONTEXTUAL REWRITE
1. Normalize:
- Fix typos, clear English
- Do NOT change entity values
2.complete intent
Never change the question's intent — only fix grammar and map ERP terms.
3. ERP mapping:
- Map generic terms to standard ERPNext concepts based on intent
- Avoid vague words if clearer business terms exist
- Do NOT invent documents or use report names.
Examples:
stock → Bin / Stock Ledger Entry
production → Work Order
finance/profit → GL Entry
4. Field hints (max 1–2):
Use natural phrasing ("based on", "using")
sales → grand_total
qty → qty
stock → actual_qty
production → produced_qty
finance → debit / credit
status → status
5. Time fields:
Sales/Stock/Finance → posting_date
Work Order → actual_start_date / actual_end_date
Timesheet → start_date / end_date
Timesheet Detail → from_time / to_time
- NEVER use posting_date for Timesheet
- NEVER use creation unless asked
6. Relationships:
- Include linked entities if required
STYLE:
- Natural business language
- No SQL, no tab* names
EXAMPLES:
"total sales amount last month"
→ What is the total sales amount from Sales Invoices last month based on grand_total and posting_date?
"stock in warehouse a"
→ What is the stock quantity in Warehouse A based on actual_qty from Bin?
"who worked today"
→ Which employees logged time today based on Timesheet start_date or Timesheet Detail from_time?
If the query mentions Draft, Submitted, or Cancelled, explicitly include docstatus in the rewritten question.
- Do not add a specific document type unless it is clearly implied by the user query or required by standard ERPNext business meaning.
- For vague money questions, clarify the business meaning as actual, ordered, quoted, paid, or outstanding, but do not guess the document type incorrectly.
- If the user says "spend", treat it as actual purchase/expense, not quotation or order commitment, unless the user explicitly mentions order, quotation, or planned purchase.
- Preserve all filter conditions, status values, and keywords from the original question — never drop them during rewriting.
- Do NOT add dates, filters, entities, statuses, or assumptions unless explicitly present in the user question or clearly inferred from conversation memory.
Use chat history only when the current query clearly implies continuation or follow-up context. Never assume dates, filters, entities, or conditions from previous messages unless strongly indicated.
Chat history:
{rows}
User:
{qstn}
Use only the most relevant tables and fields required for the user query.
Use only valid tables and fields from the provided schema context, regardless of retrieval ranking order. Choose fields based on business meaning and user intent, not rank position. Never invent schema elements. Always return any one clear user-readable business fields, not only technical IDs, unless explicitly requested. If the query is ambiguous, ask for clarification and set "clarify": true.
"""
USER_PROMPT = """Chat History:
{rows}

User Question:
{qstn}"""
def find_similar_log_question(new_question: str, threshold: int = 98):
    logs = frappe.get_all(
        "ChangAI Logs",
        fields=[
            "name",
            "user_question",
            "sql_generated",
            "rewritten_question",
            "fields",
            "tables",
            "error",
            "entity",
            "result",
            "type",
            "payload"
        ],
        limit_page_length=500
    )

    best_match = None
    best_score = 0

    for log in logs:

        # Skip Non-ERP
        if log.type == "NonERP":
            continue

        # Skip CUD operations
        if log.payload:
            continue

        # Skip logs with errors
        if log.error:
            continue

        # Skip logs without SQL
        if not log.sql_generated:
            continue

        result = frappe.parse_json(log.result or "{}")

        # Skip SQL execution failures
        if isinstance(result, dict) and result.get("error"):
            continue

        score = fuzz.token_set_ratio(
            new_question,
            log.user_question
        )

        if score > best_score:
            best_score = score
            best_match = log

    if best_match and best_score >= threshold:
        return {
            "matched": True,
            "payload": best_match.payload,
            "score": best_score,
            "log_name": best_match.name,
            "question": best_match.user_question,
            "sql": best_match.sql_generated,
            "rewritten_question": best_match.rewritten_question,
            "fields": best_match.fields,
            "tables": best_match.tables,
            "entity_debug": best_match.entity,
            "result": best_match.result,
            "error": best_match.error,
            "type":best_match.type
        }

    return {
        "matched": False,
        "score": best_score
    }

def _error_response(memory_status, user_question, formatted_q, context,
                    selected_tables, fields, sql, validation,
                    entity_debug, tries, error, err):
    return {
        "Memory Status": memory_status,
        "Question": user_question,
        "Formatted_Question": formatted_q,
        "Context": (context or "")[:800],
        "Tables": selected_tables,
        "Fields": fields,
        "SQL": sql,
        "Validation": validation,
        "EntityDebug": entity_debug,
        "Tries": tries,
        "Error": error,
        "Result": [],
        "Bot": _get_sql_error_message(error, validation),
    }

def _get_sql_error_message(err: Any, val: Dict) -> str:
    # if err:
    #     frappe.log_error(err, "ChangAI SQL Pipeline Error")
    #     return "⚠️ The model encountered an error generating your query. Please try the same Question again."

    error_text = (val.get("error") or "").strip()

    if not error_text:
        return "⚠️ Could nprocess your request. Please try rephrasing."

    if "Empty SQL from LLM" in error_text:
        return "⚠️ The model could not generate a SQL query for your question. Please try rephrasing."

    if "does not exist in schema" in error_text:
        return f"⚠️ The model generated an invalid table reference. {error_text}"

    if "could not be resolved" in error_text:
        return f"⚠️ The model generated an invalid field reference. {error_text}"

    if "parse" in error_text.lower() or "syntax" in error_text.lower() or "expected" in error_text.lower():
        return "⚠️ The model generated invalid SQL syntax. Please try rephrasing."

    return f"⚠️ The model generated an invalid query. {error_text}"

def get_last_thread_message(chat_id: str):
    data = frappe.get_all(
        "ChangAI Chat History",
        filters={"session_id": chat_id},
        fields=["content"],
        order_by="creation asc"
    )
    for row in reversed(data):
        try:
            msg = json.loads(row["content"])
            # human_msg = msg[-2]["human"]
            msg_type = msg[-2]["type"]
            return msg_type
        except Exception:
            pass
    return ""
@frappe.whitelist(allow_guest=False)
def inject_prompt(user_qstn: str, session_id: str) -> str:
    rows=get_chat_history(session_id)
    prompt=USER_PROMPT.format(rows=rows,qstn=user_qstn)
    return prompt


def normalize(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return value
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return value
