"""
This module provides API endpoints for processing user questions.
It supports conversational handling and integrates with ERP data via dynamic query generation.
"""
import datetime
import re
import os
import random
import json
import requests
import frappe
import spacy
import jinja2
from typing import Any, Dict, Optional
from symspellpy.symspellpy import SymSpell, Verbosity
# from changai.changai.api.v2.text2sql_pipeline import get_settings

pleasantry_file_path = frappe.get_app_path("changai", "changai", "api", "pleasantry.json")
business_keywords_file = frappe.get_app_path("changai", "changai", "api", "business_keywords.json")
custom_dictionary = frappe.get_app_path("changai", "changai", "api", "erp_dictionary.txt")
nlp = spacy.load("en_core_web_sm", disable=["tagger", "parser"])
sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
sym_spell.load_dictionary(custom_dictionary, term_index=0, count_index=1)
with open(pleasantry_file_path, "r", encoding="utf-8") as f:  # nosemgrep: frappe-security-file-traversal - path is constructed via frappe.get_app_path, guaranteed to be within the app directory
    PLEASANTRIES = sorted(json.load(f).items(), key=lambda x: len(x[0]), reverse=True)
COMPILED_PLEASANTRIES = [
    (re.compile(pattern, re.IGNORECASE), response)
    for pattern, response in PLEASANTRIES
]
STOP_WORDS = {
    "tell","as","a","all",
    "i", "me", "my", "mine", "myself",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    "it", "its", "itself",
    "we", "us", "our", "ours", "ourselves",
    "they", "them", "their", "theirs", "themselves",
    "a", "an", "the", "this", "that", "these", "those", "such",
    "is", "am", "are", "was", "were", "be", "being", "been",
    "do", "does", "did", "doing",
    "have", "has", "had", "having",
    "will", "would", "shall", "should", "can", "could", "may", "might", "must",
    "and", "or", "but", "if", "because", "while", "although", "though", "unless", 
    "until", "since", "so", "yet",
    "in", "on", "at", "by", "for", "with", "about", "against", 
    "between", "into", "through", "during", "before", "after",
    "above", "below", "to", "from", "up", "down", "out", "off", "over", "under","of",
    "what", "which", "who", "whom", "whose", 
    "when", "where", "why", "how",
    "than", "more", "most", "much", "many", "few", "less", "least", "enough",
    "ok", "okay", "well", "like", "just", "really", "very", "also", "too", "still",
    "what's", "that's", "it's", "there's", "here's", "let's", "who's", "where's", 
    "how's", "i'm", "you're", "he's", "she's", "we're", "they're",
    "i've", "you've", "we've", "they've",
    "i'll", "you'll", "he'll", "she'll", "we'll", "they'll",
    "i'd", "you'd", "he'd", "she'd", "we'd", "they'd","did"
}

stop_words=list(STOP_WORDS)
stop_word_pattern = r'^(?:' + '|'.join(re.escape(word) for word in stop_words) + r')$'
stop_word_regex = re.compile(stop_word_pattern, re.IGNORECASE)
def is_stopword(token):
    return bool(stop_word_regex.match(token))

conversational_template = """
{#- MACRO to format a single record conversationally -#}
{%- macro format_record(record, doctype=None, concise=False) -%}
    {%- if record is mapping -%}

        {# Case: has name and status #}
        {%- if 'name' in record and 'status' in record -%}
            {%- if concise -%}
{{ record.status }}
            {%- else -%}
The {{ doctype or 'record' }} '{{ record.name }}' is currently marked as '{{ record.status }}'.
            {%- endif -%}

        {# Case: has name, description, and multiple fields #}
        {%- elif 'name' in record and record|length > 2 and 'description' in record -%}
            {%- if concise -%}
{{ record.description }}
            {%- else -%}
Here are the details for {{ doctype or 'record' }} '{{ record.name }}': {{ record.description }}
            {%- endif -%}

        {# Case: has subject #}
        {%- elif 'subject' in record -%}
            {%- if concise -%}
{{ record.subject }}
            {%- else -%}
Take a look at the details for '{{ record.subject }}'.
            {%- endif -%}

        {# Case: has title #}
        {%- elif 'title' in record -%}
            {%- if concise -%}
{{ record.title }}
            {%- else -%}
Here’s what I found for '{{ record.title }}'.
            {%- endif -%}

        {# Case: has only name #}
        {%- elif 'name' in record -%}
            {%- if concise -%}
{{ record.name }}
            {%- else -%}
The {{ doctype or 'record' }} is '{{ record.name }}'.
            {%- endif -%}

        {# Default case: show first value or fallback #}
        {%- else -%}
            {{ record.values()|first or 'Information not available' }}

        {%- endif -%}

    {# If not a mapping, just display it #}
    {%- else -%}
        {{ record or 'Information not available' }}
    {%- endif -%}
{%- endmacro -%}


{#- MAIN RESPONSE TEMPLATE -#}

{# Case 1: Error string detection (check first) #}
{%- if data is string and ('DoesNotExistError' in data or 'not found' in data or 'OperationalError' in data) -%}
    I encountered an error. The system returned this message: {{ data }}

{# Case 2: Sequence of results #}
{%- elif data is sequence and data is not mapping and data is not string -%}
    {%- set display_count = 5 -%}

    {# Case: multiple results #}
    {%- if data|length > 1 -%}
I found {{ data|length }} results.

Here are the first few:
{% for item in data[:display_count] %}
{{ loop.index }}. {{ format_record(item, doctype, concise=True) }}
{% endfor %}
{%- if data|length > display_count -%}
...and {{ data|length - display_count }} more not shown.
{%- endif -%}

    {# Case: single item in list #}
    {%- elif data|length == 1 -%}

        {# If it’s a dictionary with a numeric value (count) #}
        {%- if data[0] is mapping and (data[0].values()|first is number) -%}
            {%- set record = data[0] -%}
            {%- set key = record.keys()|list|first -%}
I found {{ record[key] }} {{ "record" if record[key] == 1 else "records" }}.
        {# Otherwise use normal formatting #}
        {%- else -%}
Result found:
{{ format_record(data[0], doctype) | trim }}
        {%- endif -%}

    {%- else -%}
I couldn’t find any records for {{ doctype or 'your query' }}.
    {%- endif -%}

{# Case 3: Single dictionary result #}
{%- elif data is mapping -%}
    {{ format_record(data, doctype) | trim }}

{# Case 4: Simple value #}
{%- else -%}
    The result for your query is {{ data if data is not none and data != '' else 'Information not available' }}.
{%- endif -%}
"""


# Load business keywords once
with open(business_keywords_file, "r", encoding="utf-8") as f:  # nosemgrep: frappe-security-file-traversal - path is constructed via frappe.get_app_path, guaranteed to be within the app directory
    BUSINESS_KEYWORDS = {kw.lower() for kw in json.load(f)["business_keywords"]}

non_erp_responses = [
    "I'm here to assist with ERP-related queries such as sales, purchases, and inventory.",
    "Please ask a question related to business data or reports.",
    "I'm focused on business operations—try asking about invoices, customers, or stock.",
    "My scope is limited to ERP functions. Let me know how I can help with business data.",
    "I'm designed to handle ERP queries. Could you rephrase that in a business context?"
]

@frappe.whitelist(allow_guest=False)
def correct_sentence(text: str):
    doc = nlp(text)
    entities = [(ent.text, ent.start_char, ent.end_char) for ent in doc.ents]
    text_to_correct = text
    placeholder_map = {}
    for i, (ent_text, _, _) in enumerate(entities):
        placeholder = f"__ENTITY{i}__"
        text_to_correct = text_to_correct.replace(ent_text, placeholder)
        placeholder_map[placeholder] = ent_text

    tokens = re.findall(r"\b[\w\-']+\b|[^\w\s]", text_to_correct)
    corrected_tokens = []

    for token in tokens:
        token_lower = token.lower()
        if (token_lower in BUSINESS_KEYWORDS or token_lower in PLEASANTRIES or is_stopword(token_lower) or token.isdigit() or not re.match(r"[\w\-']+", token)):
            corrected_tokens.append(token)
            continue
        # Lookup
        suggestions = sym_spell.lookup(token.lower(), Verbosity.CLOSEST, max_edit_distance=2)
        corrected = suggestions[0].term if suggestions else token

        if token.istitle():
            corrected = corrected.capitalize()
        elif token.isupper():
            corrected = corrected.upper()
        corrected_tokens.append(corrected)
    corrected_text = " ".join(corrected_tokens)
    # --- STEP 3: Restore entities ---
    for placeholder, ent_text in placeholder_map.items():
        corrected_text = corrected_text.replace(placeholder, ent_text)
    return corrected_text


@frappe.whitelist(allow_guest=False)
def run_query(query:str):
    """Run a query."""
    try:
        if not query:
            return {"error": "Query not provided."}
        result = json.loads(query)
        return {"success": True, "response": result}

    except Exception as e:
        return {"success": False, "response": str(e)}


# To convert the Python Date Objects into an ISO format.
@frappe.whitelist(allow_guest=False)
def sanitize_dates(obj: Any) -> Any:
    if isinstance(obj, list):
        return [sanitize_dates(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: sanitize_dates(v) for k, v in obj.items()}
    elif isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    else:
        return obj


@frappe.whitelist(allow_guest=False)
def fetch_data_from_server(qstn: str) -> dict:
    """
    Handles a user question by detecting greetings or sending it to a prediction API.
    Returns either a greeting response, ERP query results, or an error message.
    """
    response_msg = fuzzy_intent_router(qstn)
    if response_msg["type"] in ("Greeting", "Other"):
        return {"query_data": response_msg["response"]}
    try:
        token = frappe.db.get_single_value("Settings", "token")
        api_url = frappe.db.get_single_value("Settings", "prediction_url")
        version_id = frappe.db.get_single_value("Settings", "version_id")

        headers = {
            "Content-Type": "application/json",
            "Prefer": "wait",
            "Authorization": f"Bearer {token}",
        }
        data = {
            "version": version_id,
            "input": {"user_input": response_msg["corrected"]},
        }
        response = requests.post(api_url, headers=headers, json=data)
        response.raise_for_status()

        response_data = response.json()
        query = response_data["output"]["frappe_query"].replace("[BT]", "`")
        query_result = run_query(query)
        query_result["response"] = sanitize_dates(query_result["response"])
        doc = response_data["output"]["predicted_doctype"]
        user_template = format_data_conversationally(query_result["response"], doc)
        frappe.get_doc(
            {
                "doctype": "ChangAI Query Log",
                "question": response_msg["corrected"],
                "doc": doc,
                "query": query,
                "top_fields": json.dumps(response_data["output"]["top_fields"]),
                "fields": json.dumps(response_data["output"]["selected_fields"]),
                "response": json.dumps(query_result["response"]),
                "jinja2_template_form":user_template
            
            }
        ).insert(ignore_permissions=True)
        return {
            "corrcetd_qstn": response_msg["corrected"],
            "query": query,
            "doctype": doc,
            "top_fields": response_data["output"]["top_fields"],
            "fields": response_data["output"]["selected_fields"],
            "query_data": user_template,
            "data": query_result["response"],
        }
    except Exception as e:
        return {"error": str(e)}


@frappe.whitelist(allow_guest=False)
def fuzzy_intent_router(text: str) -> Dict[str, Any]:
    """Responds to a user question with a fuzzy match"""
    corrected_text = correct_sentence(text)
    corrected_text_lower = corrected_text.lower()
    corrected_words = set(re.findall(r"\b\w+\b", corrected_text_lower))
    if BUSINESS_KEYWORDS & corrected_words:
        return {"type": "ERP", "response": 0, "corrected": corrected_text}
    safe_text = re.sub(r"[^\w\s]", "", corrected_text_lower) 
    for pattern, response in COMPILED_PLEASANTRIES:
        if re.search(pattern, safe_text):
            return {"type": "Greeting", "response": response, "corrected": corrected_text}
    return {
        "type": "Other",
        "response": random.choice(non_erp_responses),
        "corrected": corrected_text,
    }


from jinja2.sandbox import SandboxedEnvironment
from markupsafe import escape

def format_data_conversationally(user_data: Any, doctype: Optional[str] = None) -> str:
    """
    Formats system-controlled user data using a sandboxed Jinja template.
    """

    if isinstance(user_data, dict) and user_data.get("success") is False:
        return f":x: Error: {escape(user_data.get('error', 'Unknown error'))}"

    env = SandboxedEnvironment(
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
        extensions=["jinja2.ext.do"],
    )

    template = env.from_string(conversational_template)

    return template.render(
        data=user_data,
        doctype=doctype
    )