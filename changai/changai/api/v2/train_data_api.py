from __future__ import annotations
from pathlib import Path
import os, json, math, re, time, random, traceback
from typing import Any, Dict, List, Tuple,Union
import frappe
from google.oauth2 import service_account
from frappe import _
from google.genai import types
from google import genai
from changai.changai.api.v2.build_cards_faiss_index_v2 import _ensure_folder_exists
import openai
from vertexai.generative_models import GenerativeModel, GenerationConfig
from google.cloud import aiplatform
from google.api_core import exceptions as google_exceptions
import anthropic
import secrets


MAX_RETRIES = 5
BASE_BACKOFF = 2.0
MAX_BACKOFF = 60.0
REQUEST_DELAY = 30
BATCH_SIZE = 25
TABLE_TAG = "[TABLE]"
FIELD_TAG = "[FIELD]"
LINK_TAG = "[LINK]"
CHANGAI_SETTINGS = "ChangAI Settings"
VALID_OUTPUT_MESSAGE = "You must output ONLY a valid JSON array."
GEMINI_JSON_PARSE_FAIL = "Gemini JSON parse failed"

SYSTEM_FIELDS = {
    "name", "owner", "creation", "modified", "modified_by",
    "docstatus", "idx", "doctype", "parent", "parenttype",
    "parentfield", "amended_from"
}

_table_cache: Dict[str, bool] = {}
_field_cache: Dict[str, set] = {}


def _get_claude_client():
    settings = frappe.get_single(CHANGAI_SETTINGS)
    try:
        api_key = settings.claude_api_key
    except Exception:
        api_key = None

    if not api_key:
        frappe.throw(
            _(
                "Claude API key is not configured.<br><br>"
                "Please go to <b>ChangAI Settings</b> and enter your <b>Claude API Key</b>.<br><br>"
                "Get your API key from "
                "<a href='https://console.anthropic.com/account/keys' target='_blank'>Anthropic Console</a>."
            ),
            title=_("Missing Claude API Key")
        )

    # Build client kwargs — base URL + optional extra headers
    # default_base_url is "" so the official SDK uses its built-in default
    # (https://api.anthropic.com). When the operator sets a custom URL,
    # it is passed through unchanged.
    client_kwargs = {"api_key": api_key}

    base_url = ""
    try:
        base_url = (settings.anthropic_base_url or "").strip()
    except Exception:
        base_url = ""
    if base_url:
        client_kwargs["base_url"] = base_url

    extra_headers_raw = ""
    try:
        extra_headers_raw = (settings.claude_extra_headers or "").strip()
    except Exception:
        extra_headers_raw = ""
    if extra_headers_raw:
        try:
            parsed_headers = json.loads(extra_headers_raw)
            if isinstance(parsed_headers, dict) and parsed_headers:
                client_kwargs["default_headers"] = parsed_headers
        except (ValueError, TypeError):
            frappe.log_error(
                title="ChangAI: invalid Claude extra headers JSON",
                message=(
                    "claude_extra_headers must be a valid JSON object "
                    "of HTTP headers. Ignoring the value."
                ),
            )

    return anthropic.Anthropic(**client_kwargs)


def _get_claude_model() -> str:
    """Return the Claude model name from ChangAI Settings, falling back to the
    historical hard-coded default if the field is missing or unset.

    Operators pointing ChangAI at a non-Anthropic backend (e.g. a self-hosted
    Anthropic-compatible router) can override this via the
    ``claude_model`` field on ChangAI Settings.
    """
    try:
        settings = frappe.get_single(CHANGAI_SETTINGS)
        model = (getattr(settings, "claude_model", None) or "").strip()
        if model:
            return model
    except Exception:
        pass
    return "claude-sonnet-4-6"


def _get_openai_client():
    settings = frappe.get_single(CHANGAI_SETTINGS)
    try:
        api_key = settings.openai_api_key
    except Exception:
        api_key = None

    if not api_key:
        frappe.throw(
            _(
                "OpenAI API key is not configured.<br><br>"
                "Please go to <b>Remote Tab in ChangAI Settings</b> and enter your <b>OpenAI API Key</b>.<br><br>"
                "Get your API key from "
                "<a href='https://platform.openai.com/api-keys' target='_blank'>OpenAI Platform</a>."
            ),
            title=_("Missing OpenAI API Key")
        )

    return openai.OpenAI(api_key=api_key)


def _sleep_backoff(attempt: int, base: float = BASE_BACKOFF, cap: float = MAX_BACKOFF):
    delay = min(cap, base * (2 ** attempt))
    delay = delay * (0.7 + secrets.randbelow(1000) / 1000 * 0.6)
    time.sleep(delay)


def _get_abs_path(module_name: str, folder_path: str,suffix: str = "") -> str:
    relative = folder_path.replace("Home/", "", 1)
    site_path = frappe.get_site_path("private", "files")
    target_dir = os.path.join(site_path, relative)
    os.makedirs(target_dir, exist_ok=True)
    return os.path.join(target_dir, f"{module_name}_batch8_{suffix}.jsonl")


def _seed_seen_from_disk(abs_path: str) -> Tuple[set, int]:
    """Return (seen_anchors, existing_count_lines)."""
    seen = set()
    count = 0
    if not os.path.exists(abs_path):
        return seen, count

    with open(abs_path, "r", encoding="utf-8") as f:  # nosemgrep: security.frappe-security-file-traversal - abs_path is constructed via frappe.get_site_path with a sanitized module name, not directly user-controlled
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    continue
                anchor = (obj.get("anchor") or "").strip()
                if anchor:
                    seen.add(anchor)
                    count += 1
            except Exception:
                # ignore malformed lines
                continue

    return seen, count


def _append_to_disk(abs_path: str, records: List[dict]):
    if not records:
        return

    # Ensure folder exists
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    # Append JSONL safely
    file_exists = os.path.exists(abs_path)
    with open(abs_path, "a", encoding="utf-8") as f:  # nosemgrep: security.frappe-security-file-traversal - abs_path is constructed via frappe.get_site_path with a sanitized module name, not directly user-controlled
        if file_exists and os.path.getsize(abs_path) > 0:
            f.write("\n")
        f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in records))
        f.write("\n")


def _sync_frappe_file_doc(module_name: str, abs_path: str, folder_path: str, suffix: str = ""):
    """
    Create/Update File doc that points to the on-disk file.
    """
    relative = folder_path.replace("Home/", "", 1)
    out_file_name = f"{module_name}_batch8_{suffix}.jsonl"
    file_url = f"/private/files/{relative}/{out_file_name}"
    existing = frappe.db.get_value(
        "File",
        {"file_name": out_file_name, "folder": folder_path},
        "name",
    )
    size = os.path.getsize(abs_path) if os.path.exists(abs_path) else 0

    if existing:
        file_doc = frappe.get_doc("File", existing)
        file_doc.file_url = file_url
        file_doc.file_size = size
        file_doc.is_private = 1
        file_doc.folder = folder_path
        file_doc.save(ignore_permissions=True)
    else:
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": out_file_name,
            "file_url": file_url,
            "is_private": 1,
            "file_size": size,
            "folder": folder_path,
            "file_type": "JSONL"
        }).insert(ignore_permissions=True)
    # nosemgrep: frappe-manual-commit - explicit commit required to persist File DocType record immediately after disk write during training data sync
    frappe.db.commit()
    return file_doc


def _validate_table(doctype: str) -> bool:
    if doctype not in _table_cache:
        _table_cache[doctype] = bool(frappe.db.exists("DocType", doctype))
    return _table_cache[doctype]

def _get_fieldnames_set(doctype: str) -> set:
    if doctype in _field_cache:
        return _field_cache[doctype]

    try:
        meta = frappe.get_meta(doctype)
        field_names = {f.fieldname for f in meta.fields if f.fieldname}
        # include system-ish implicit ones you might allow
        field_names |= set(SYSTEM_FIELDS)
        _field_cache[doctype] = field_names
    except Exception:
        _field_cache[doctype] = set()

    return _field_cache[doctype]


def _validate_field(doctype: str, fieldname: str) -> bool:
    if fieldname in SYSTEM_FIELDS:
        return True
    return fieldname in _get_fieldnames_set(doctype)


def _parse_table_tag(positive: str):
    match = re.match(
        r"^\[TABLE\]\s+([^|\]>]{1,200})(?:\s*\|.*)?$",
        positive
    )
    if not match:
        return False, "Could not parse [TABLE] format"
    table = match.group(1).strip()
    doctype = table[3:] if table.startswith("tab") else table
    if not _validate_table(doctype):
        return False, f"DocType '{doctype}' does not exist"
    return True, None


def _parse_field_tag(positive: str):
    match = re.match(
        r"^\[FIELD\]\s+(\w{1,100})\s+\|\s+\[TABLE\]\s+([^|\]>]{1,200})(?:\s*\|.*)?$",
        positive
    )
    if not match:
        return False, "Could not parse [FIELD] format"
    field = match.group(1).strip()
    table = match.group(2).strip()
    doctype = table[3:] if table.startswith("tab") else table
    if not _validate_table(doctype):
        return False, f"DocType '{doctype}' does not exist"
    if not _validate_field(doctype, field):
        return False, f"Field '{field}' does not exist in '{doctype}'"
    return True, None


def _parse_link_tag(positive: str):
    match = re.match(
        r"^\[LINK\]\s+([^|\]>]{1,200})\s+-->\s+([^|\]>]{1,200})\s+ON\s+(\w{1,100})(?:\s*\|.*)?$",
        positive
    )
    if not match:
        return False, "Could not parse [LINK] format"
    table_a = match.group(1).strip()
    table_b = match.group(2).strip()
    field = match.group(3).strip()
    doctype_a = table_a[3:] if table_a.startswith("tab") else table_a
    doctype_b = table_b[3:] if table_b.startswith("tab") else table_b
    if not _validate_table(doctype_a):
        return False, f"[LINK] DocType '{doctype_a}' does not exist"
    if not _validate_table(doctype_b):
        return False, f"[LINK] DocType '{doctype_b}' does not exist"
    if not _validate_field(doctype_a, field):
        return False, f"[LINK] Field '{field}' does not exist in '{doctype_a}'"
    return True, None


_TAG_PARSERS = {
    TABLE_TAG: _parse_table_tag,
    FIELD_TAG: _parse_field_tag,
    LINK_TAG:  _parse_link_tag,
}


def _is_positive_valid(positive: str):
    for tag, parser in _TAG_PARSERS.items():
        if positive.startswith(tag):
            return parser(positive)
    return False, "Positive must start with [TABLE], [FIELD], or [LINK]"



def _validate_records(raw_records: List[dict]):
    validated_records = []
    total_removed_positives = 0

    for record in raw_records:
        valid_positives = []
        invalid_positives = []

        for positive in record.get("positives", []):
            is_valid, reason = _is_positive_valid(positive)
            if is_valid:
                valid_positives.append(positive)
            else:
                invalid_positives.append((positive, reason))
                total_removed_positives += 1

        if not valid_positives:
            frappe.log_error(
                f"anchor: {record.get('anchor')}\nreasons: {[r for _, r in invalid_positives]}",
                "Validation: Record dropped"
            )
            continue

        validated_records.append({
            "anchor": record["anchor"],
            "positives": valid_positives
        })

    return validated_records, total_removed_positives


def _assign_qids(validated_records: List[dict], module_name: str, existing_count: int):
    final_records = []
    for i, record in enumerate(validated_records):
        qid = f"{module_name}_{str(existing_count + i + 1).zfill(3)}"
        final_records.append({
            "qid": qid,
            "anchor": record["anchor"],
            "positives": record["positives"]
        })
    return final_records

def _build_claude_messages(module_name, module_description) -> List[dict]:
    schema = get_module_schema_str(module_name)
    return [
        {
            "role": "user",
            "content": _val_prompt(schema,module_name, module_description, BATCH_SIZE),
        }
    ]


def _call_claude_batch_once(client, messages: List[dict]) -> str:
    try:
        resp = client.messages.create(
            model=_get_claude_model(),
            max_tokens=4096,
            temperature=1.0,
            system=f"{VALID_OUTPUT_MESSAGE}\nStart with '[' and end with ']'. No markdown. No code fences. No explanation.",
            messages=messages,
        )
        return (resp.content[0].text or "").strip()

    except anthropic.RateLimitError as e:
        frappe.log_error(str(e), "Claude Rate Limit (429) - sleeping 10s")
        time.sleep(10)
        raise

    except anthropic.AuthenticationError as e:
        frappe.log_error(str(e), "Claude Authentication Error")
        raise

    except anthropic.APIConnectionError as e:
        frappe.log_error(str(e), "Claude Connection Error")
        raise

    except anthropic.APIStatusError as e:
        frappe.log_error(
            f"Status {e.status_code}: {str(e)}",
            "Claude API Status Error",
        )
        raise

    except Exception as e:
        frappe.log_error(str(e), "Claude Unexpected Error")
        raise

from typing import Optional

def _call_claude_batch_with_retry(
    client,
    input_raw: Optional[str] = None,
    module_name: Optional[str] = None,
    module_description: Optional[str] = None,
) -> str:
    raw = None

    if input_raw and not module_name and module_description:
       messages = _build_claude_correction_messages(input_raw) 
    else:
       messages = _build_claude_messages(module_name, module_description)
        

    for attempt in range(MAX_RETRIES):
        try:
            raw = _call_claude_batch_once(client, messages)

            if REQUEST_DELAY:
                time.sleep(REQUEST_DELAY)

            break

        except anthropic.AuthenticationError as e:
            frappe.log_error(str(e), "Claude authentication failed")
            return ""

        except Exception as e:
            frappe.log_error(str(e), "Claude call failed (retrying)")
            _sleep_backoff(attempt)

    return raw or ""


def _parse_json_array(raw: str, provider_name: str) -> List[dict]:
    if not raw:
        return []

    cleaned = _strip_code_fence(raw)

    try:
        arr = json.loads(cleaned)
    except Exception:
        frappe.log_error(cleaned[:100], f"{provider_name} output not valid JSON array")
        return []

    if not isinstance(arr, list):
        frappe.log_error(cleaned[:100], f"{provider_name} output not a list")
        return []

    return arr


def _extract_unique_records(arr: List[dict], seen_anchors) -> List[dict]:
    records = []

    for obj in arr:
        if not isinstance(obj, dict):
            continue

        anchor = (obj.get("anchor") or "").strip()
        positives = obj.get("positives")

        if not anchor or not isinstance(positives, list) or not positives:
            continue

        if anchor in seen_anchors:
            continue

        seen_anchors.add(anchor)
        records.append({"anchor": anchor, "positives": positives})

    return records


def _generate_batch_claude(
    client,
    module_name,
    seen_anchors,
    module_description,
    total_count,
    wrong_examples=None,
) -> List[dict]:
    raw = _call_claude_batch_with_retry(
        client=client,
        module_name=module_name,
        module_description=module_description,
    )

    if not raw:
        return []

    arr = _parse_json_array(raw, "Claude")
    return _extract_unique_records(arr, seen_anchors)

def _build_claude_correction_messages(input_raw) -> List[dict]:
    return [
        {
            "role": "system",
            "content": (
                VALID_OUTPUT_MESSAGE +
                "Start with '[' and end with ']'. "
                "No markdown. No code fences. No explanation."
            ),
        },
        {
            "role": "user",
            "content": __correction_prompt(                
                input_raw
            ),
        },
    ]


def _call_openai_batch_once(client, messages: List[dict]) -> str:
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            temperature=1.0,
            messages=messages,
        )
        return (resp.choices[0].message.content or "").strip()

    except openai.RateLimitError as e:
        frappe.log_error(str(e), "OpenAI Rate Limit (429) - sleeping 10s")
        time.sleep(10)
        raise

    except openai.AuthenticationError as e:
        frappe.log_error(str(e), "OpenAI Authentication Error")
        raise

    except openai.APIConnectionError as e:
        frappe.log_error(str(e), "OpenAI Connection Error")
        raise

    except openai.APIStatusError as e:
        frappe.log_error(
            f"Status {e.status_code}: {str(e)}",
            "OpenAI API Status Error",
        )
        raise

    except Exception as e:
        frappe.log_error(str(e), "OpenAI Unexpected Error")
        raise


def _call_openai_batch_with_retry(client,input_raw:None, module_name:None, module_description:None) -> str:
    raw = None
    messages = None
    if input_raw:
        messages = _build_claude_correction_messages(input_raw)
    elif module_name and module_description:
        messages = _build_claude_messages(module_name, module_description)
    else:
        frappe.log_error("No valid input to build messages", "Claude batch skipped")
        return ""

    for attempt in range(MAX_RETRIES):
        try:
            raw = _call_openai_batch_once(client, messages)

            if REQUEST_DELAY:
                time.sleep(REQUEST_DELAY)

            break

        except anthropic.AuthenticationError:
            return ""

        except Exception as e:
            frappe.log_error(str(e)[:2000], "Claude call failed (retrying)")
            _sleep_backoff(attempt)
    if not raw:
        frappe.log_error("All retries exhausted", "Claude batch failed")
    return raw or ""


def _strip_code_fence(raw: str) -> str:
    if raw.startswith("```"):
        raw = raw.split("```", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()
    return raw


def _parse_openai_json_array(raw: str) -> List[dict]:
    if not raw:
        return []

    cleaned = _strip_code_fence(raw)

    try:
        arr = json.loads(cleaned)
    except Exception:
        frappe.log_error(cleaned[:100], "OpenAI output not valid JSON array")
        return []

    if not isinstance(arr, list):
        frappe.log_error(cleaned[:100], "OpenAI output not a list")
        return []

    return arr


def _extract_unique_training_records(arr: List[dict], seen_anchors) -> List[dict]:
    records = []

    for obj in arr:
        if not isinstance(obj, dict):
            continue

        anchor = (obj.get("anchor") or "").strip()
        positives = obj.get("positives")

        if not anchor or not isinstance(positives, list) or not positives:
            continue

        if anchor in seen_anchors:
            continue

        seen_anchors.add(anchor)
        records.append({"anchor": anchor, "positives": positives})

    return records
def _get_gemini_client():
    settings = frappe.get_single(CHANGAI_SETTINGS)
    json_content = (settings.get("gemini_json_content") or "").strip()
    project_id = (settings.get("gemini_project_id") or "").strip()
    location = (settings.get("location") or "us-central1").strip()

    if not json_content:
        frappe.throw(_("Gemini Service Account JSON is missing."), title=_("Missing Gemini Configuration"))
    if not project_id:
        frappe.throw(_("Gemini Project ID is missing."), title=_("Missing Gemini Configuration"))

    try:
        service_account_info = json.loads(json_content)
    except json.JSONDecodeError as e:
        frappe.throw(_("Gemini Service Account JSON is invalid: {0}").format(str(e)), title=_("Invalid Gemini JSON"))

    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    return genai.Client(
        vertexai=True,
        project=project_id,
        location=location,
        credentials=creds,
    )
def _val_prompt(schema:str,module_name, description, batch_size):
    return f"""You are generating ERPNext schema-retrieval TEST data for evaluating a trained retrieval model.
CRITICAL OUTPUT RULE: Return ONLY a valid JSON array. Start with '[' and end with ']'. No markdown, code fences, or explanations.
FORMAT:
[{{"anchor":"query text","positives":["[TABLE] tabX","[FIELD] field_name | [TABLE] tabX"]}}]
ANCHOR RULES:
- Generate a realistic mix of query types: simple (single table), medium (join OR aggregation OR time filter), complex (multi-condition, joins + aggregation + reasoning).
- Do NOT force all queries to be complex.
STYLE VARIATION:
- Include short, natural, business, messy/typo, urgent, and ambiguous queries.
LOGIC COVERAGE:
- Include filters, aggregations, ranking, joins, time-based queries, comparisons, and some complex reasoning.
STRICT RULES:
- NEVER mention table/doctype names in anchor.
- Use realistic business language.
- Ensure anchors are UNIQUE.
POSITIVES RULES:
- Include ALL required tables and fields.
- Include identifier, filter, aggregation, and join fields if needed.
- Do NOT miss required fields or include unrelated ones.
FINAL:
- Generate EXACTLY {batch_size} UNIQUE objects.
- {schema}
Use this Given schema only for produciton grade test data generation.""".strip()



def build_schema_context_for_module(module_name: str) -> str:
    doctypes = frappe.get_all(
        "DocType",
        filters={"module": module_name, "custom": 0},
        pluck="name"
    )
    blocks = []
    for dt in doctypes:
        meta = frappe.get_meta(dt)
        fields = [f"- {f.fieldname}" for f in meta.fields if f.fieldname]

        if fields:
            blocks.append(
                f"TABLE: tab{meta.name}\nFIELDS:\n" + "\n".join(fields)
            )
    return "\n\n".join(blocks)


def testing_file(module_name):
    results = []
    wrong_examples = frappe.get_all("File", filters={"file_name": f"{module_name}.json","folder":"Home/Test Results"}, fields=["name", "file_url"])
    for file in wrong_examples:
        file_doc=frappe.get_doc("File",file.name)
        results.append({
            "name": file.name,
            "file_url": file.file_url,
            "content": file_doc.get_content()
        })
    return results

def _get_generation_backend(use_claude: bool, use_gemini: bool):
    if use_claude:
        return _get_claude_client(), _generate_batch_claude
    if use_gemini:
        return _get_gemini_client(), _generate_batch_gemini

def _normalize_modules(modules):
    if isinstance(modules, str):
        return json.loads(modules)
    return modules or []


def _load_wrong_examples(module_name: str) -> List[dict]:
    wrong_file_name = f"{module_name.lower().replace(' ', '_')}.json"
    file_id = frappe.db.get_value(
        "File",
        {"file_name": wrong_file_name, "folder": "Home/Test Results"},
        "name",
    )

    if not file_id:
        return []

    wrong_file_doc = frappe.get_doc("File", file_id)
    raw_content = wrong_file_doc.get_content()
    wrong_examples = json.loads(raw_content) if raw_content else []

    return wrong_examples if isinstance(wrong_examples, list) else []


def _generate_and_store_module_records(
    client,
    generate_fn,
    module_name: str,
    module_description: str,
    total_count: int,
    abs_path: str,
    wrong_examples: List[dict],
) -> Dict[str, Any]:
    seen_anchors, existing_count = _seed_seen_from_disk(abs_path)

    total_validated = 0
    remaining = total_count
    max_loops = math.ceil(total_count / BATCH_SIZE) * 2

    for _ in range(max_loops):
        if remaining <= 0:
            break

        raw_records = generate_fn(
            client,
            module_name,
            seen_anchors,
            module_description,
            remaining,
            wrong_examples,
        )
        if not raw_records:
            continue
        
        # validated_records, removed = _validate_records(raw_records)
        # if not validated_records:
        # #     continue
        # try:
        #     neg_records = raw_records

        try:
            final_records = _assign_qids(raw_records, module_name, existing_count)
        except Exception as e:
            return {"ok": False, "message": f"Error assigning QIDs: {str(e)}"}

        try:
            _append_to_disk(abs_path, final_records)
        except Exception as e:
            frappe.log_error(str(e), "Error appending to disk")
            return {"ok": False, "message": str(e)}

        existing_count += len(final_records)
        total_validated += len(final_records)
        remaining -= len(final_records)

    return {
        "ok": True,
        "total_validated": total_validated,
    }


def _sync_module_output(module_name: str, abs_path: str, path: str, suffix: str) -> Dict[str, Any]:
    try:
        _sync_frappe_file_doc(module_name, abs_path, path, suffix)
        return {"ok": True}
    except Exception as e:
        frappe.log_error(str(e), "Error syncing frappe file doc")
        return {"ok": False, "message": f"Error {str(e)}"}


@frappe.whitelist(allow_guest=False)
def generate_data(
    modules: Union[str, List[Dict[str, Any]]],
    total_count: int,
    path: str,
    use_claude: bool = False,
    use_gemini: bool = False,
):
    """
    Generates training records and APPENDS to disk JSONL.
    Then syncs/updates a Frappe File doc pointing to that file.
    """
    _ensure_folder_exists(path)

    client, generate_fn = _get_generation_backend(use_claude, use_gemini)
    module_list = _normalize_modules(modules)
    total_count = int(total_count)
    if total_count <= 0:
        return {"ok": False, "message": "total_count must be greater than 0"}
    suffix = "_val" if "Validation" in path else "_train"

    last_module_name = None

    for module_rec in module_list:
        module_name = (module_rec.get("module") or "").strip()
        module_description = (module_rec.get("description") or "").strip()

        if not module_name:
            return {"ok": False, "message": "Each module record must include 'module'."}
        last_module_name = module_name

        wrong_examples = _load_wrong_examples(module_name)
        abs_path = _get_abs_path(module_name, path, suffix)

        result = _generate_and_store_module_records(
            client=client,
            generate_fn=generate_fn,
            module_name=module_name,
            module_description=module_description,
            total_count=total_count,
            abs_path=abs_path,
            wrong_examples=wrong_examples,
        )
        if not result.get("ok"):
            return result

        if result.get("total_validated", 0) <= 0:
            continue

        sync_result = _sync_module_output(module_name, abs_path, path, suffix)
        if not sync_result.get("ok"):
            return sync_result

    return {
        "ok": True,
        "message": f"Generated training data for {last_module_name}" if last_module_name else "No modules processed",
    }


@frappe.whitelist(allow_guest=False)
def start_train(modules: str, total_count: int):
    total_count=int(total_count)
    val_count = max(1, int(int(total_count) * 0.25))

    frappe.enqueue(
        "changai.changai.api.v2.train_data_api.generate_data",
        queue="long",
        timeout=14400,
        modules=modules,
        total_count=total_count,
        path="Home/Training Data/Batch 10",
        use_claude=False,
        use_gemini=True
    )
    # frappe.enqueue(
    #     "changai.changai.api.v2.train_data_api.generate_data",
    #     queue="long",
    #     timeout=14400,
    #     modules=modules,
    #     total_count=val_count,
    #     path="Home/Validation Data/Batch 8",
    #     use_claude=True,                     # <-- Claude
    # )
    return {"ok": True, "message": "Training and validation jobs queued."}

def _build_gemini_system_instruction() -> str:
    return (
        VALID_OUTPUT_MESSAGE +
        "Start with '[' and end with ']'. "
        "No markdown. No code fences. No explanation."
    )


def _build_gemini_contents(module_name: str, module_description, wrong_examples) -> List[dict]:
    try:
        schema=get_module_schema_str(module_name)
        prompt = _training_prompt_1(
            schema,
            BATCH_SIZE,
        )
    except Exception as e:
        frappe.log_error(
            title="Empty prompt",
            message=f"Error building prompt: {str(e)}",
        )
        return []

    return [{"role": "user", "parts": [{"text": prompt}]}]


def _call_gemini_with_retry(client, model_id: str, contents: List[dict], system_instruction: str) -> str:
    raw = None

    for attempt in range(MAX_RETRIES):
        try:
            cfg = types.GenerateContentConfig(
                temperature=0.9,
                max_output_tokens=8192,
                system_instruction=system_instruction,
            )

            response = client.models.generate_content(
                model=model_id,
                contents=contents,
                config=cfg,
            )
            raw = (response.text or "").strip()

            if REQUEST_DELAY:
                time.sleep(REQUEST_DELAY)

            break

        except google_exceptions.ResourceExhausted:
            frappe.log_error(
                "Gemini quota exceeded",
                "Gemini Rate Limit (429) - sleeping 30s",
            )
            time.sleep(30)
            _sleep_backoff(attempt)

        except google_exceptions.Unauthenticated:
            frappe.log_error("Gemini auth failed", "Gemini Authentication Error")
            return ""

        except google_exceptions.GoogleAPIError as e:
            frappe.log_error(str(e), "Gemini API Error")
            _sleep_backoff(attempt)

        except Exception as e:
            frappe.log_error(
                title="Gemini generate_content.test failed",
                message=f"{str(e)}\n\nContents: {json.dumps(contents)[:8000] if contents else 'N/A'}",
            )
            _sleep_backoff(attempt)

    return raw or ""


def _parse_gemini_json_array(raw: str) -> List[dict]:
    if not raw:
        return []

    if raw.startswith("```"):
        raw = raw.split("```", 1)[1].rsplit("```", 1)[0].strip()

    try:
        arr = json.loads(raw)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*([\]}])", r"\1", raw)
        try:
            arr = json.loads(cleaned)
        except Exception:
            frappe.log_error(title=GEMINI_JSON_PARSE_FAIL, message=raw[:3000])
            return []
    except Exception:
        frappe.log_error(title=GEMINI_JSON_PARSE_FAIL, message=raw[:3000])
        return []

    return arr if isinstance(arr, list) else []

def _extract_valid_records(arr: List[dict], seen_anchors: set) -> List[dict]:
    records = []

    for obj in arr:
        if not isinstance(obj, dict):
            continue

        raw_anchor = obj.get("anchors") or obj.get("anchor") or ""

        if isinstance(raw_anchor, list):
            anchors_list = [a.strip() for a in raw_anchor if isinstance(a, str) and a.strip()]
            anchor = anchors_list[0] if anchors_list else ""
        elif isinstance(raw_anchor, str):
            anchor = raw_anchor.strip()
            anchors_list = [anchor]
        else:
            anchor = ""
            anchors_list = []

        positives = obj.get("positives")
        qid = obj.get("qid", "")

        if not anchor or not isinstance(positives, list) or not positives:
            continue

        if any(a in seen_anchors for a in anchors_list):
            continue

        seen_anchors.update(anchors_list)

        # Expand each paraphrase into its own record
        for i, a in enumerate(anchors_list):
            records.append({
                "qid": f"{qid}_p{i}" if i > 0 else qid,  # Stock_026, Stock_026_p1, Stock_026_p2
                "anchor": a,
                "positives": positives
            })

    return records
# def _call_openai_correction(raw:str):
#     try:
#         cleaned_res = json.loads(raw)
#     except Exception as e:
#         frappe.log_error(title="Cleaning failed", message=frappe.get_traceback())
#         return []

    # try:
    #     openai_client=_get_openai_client()

    #     # validate records first
    #     for i, record in enumerate(cleaned_res):
    #         if not isinstance(record, dict):
    #             raise ValueError(f"Record {i} is not a dict")
    #         if not record.get("anchor") or not record.get("positives"):
    #             raise ValueError(f"Record {i} missing anchor or positives")

        # corrected_all = []

        # # process in batches of 5
        # for i in range(0, len(cleaned_res), 5):
        #     batch = cleaned_res[i:i+5]
        #     corrected_raw = _call_openai_batch_with_retry(openai_client, input_raw=batch,module_name=None, module_description=None)

        #     # if OpenAI returns JSONs string
        #     corrected_batch = json.loads(corrected_raw)

        #     if not isinstance(corrected_batch, list):
        #         raise ValueError(f"Corrected batch starting at index {i} is not a list")

        #     corrected_all.extend(corrected_batch)

#     except Exception as e:
#         frappe.log_error(title="Correction failed", message=frappe.get_traceback()[:4000])
#         return []

#     return corrected_all

# import json

def _generate_batch_gemini(
    client,
    module_name: str,
    seen_anchors: set,
    module_description,
    total_count,
    wrong_examples,
) -> list[dict]:
    model_id = "gemini-2.5-flash-lite"
    system_instruction = _build_gemini_system_instruction()

    contents = _build_gemini_contents(
        module_name=module_name,
        module_description=module_description,
        wrong_examples=wrong_examples,
    )
    if not contents:
        return []

    raw = _call_gemini_with_retry(
        client=client,
        model_id=model_id,
        contents=contents,
        system_instruction=system_instruction,
    )
    if not raw:
        return []

    # Step 1: parse Gemini output into valid array
    try:
        arr = raw if isinstance(raw, list) else _parse_gemini_json_array(raw)
    except Exception as e:
        frappe.log_error(
            title=GEMINI_JSON_PARSE_FAIL,
            message=f"{e}\n\nRaw output:\n{str(raw)[:5000]}"
        )
        return []

    if not isinstance(arr, list):
        frappe.log_error(
            title="Gemini output is not a list",
            message=str(arr)[:5000]
        )
        return []

    # Step 2: content correction only after valid JSON exists
    # try:
    #     corrected_raw = _call_openai_correction(
    #         json.dumps(arr, ensure_ascii=False)
    #     )
    #     if corrected_raw:
    #         corrected_arr = (
    #             corrected_raw
    #             if isinstance(corrected_raw, list)
    #             else _parse_gemini_json_array(corrected_raw)
    #         )
    #         if isinstance(corrected_arr, list):
    #             arr = corrected_arr
    # except Exception as e:
    #     frappe.log_error(
    #         title="OpenAI content correction failed",
    #         message=str(e)
    #     )
        # keep original arr

    return _extract_valid_records(arr, seen_anchors)

def _training_prompt(module_name: str, module_description: str, batch_size: int, wrong_examples: list = None) -> str:
    hard_n = (batch_size * 3) // 10
    std_n = batch_size - hard_n 
    return f"""
Act as an ERPNext ERP Architect and Text2SQL dataset designer.

Task:
Generate {batch_size} high-quality training records as a RAW JSON ARRAY only.

Module:
{module_name} ({module_description})

Goal:
Create production-grade Text2SQL training data where each record contains:
- qid
- anchor
- positives

Anchor generation rules:
- Generate only business-style natural language queries.
- Query intent must be one of: SEE, FIND, LIST, CHECK, COUNT.
- Use natural end-user phrasing only.
- Style mix must include:
  - urgent / fast phrasing
  - casual phrasing
  - typo / messy phrasing
- Do not use SQL terms, database terms, schema terms, or technical wording.
- Mix:
  - {std_n} standard queries
  - {hard_n} targeted hard/tricky queries
- Include 1 distractor inspired by another module, but keep the main answer grounded in the current module where logically valid.

Schema rules:
- Use standard ERPNext schema.
- Use parent-child tables whenever required by the query.
- Use only tables and fields that would genuinely be required to generate correct SQL.
- Do not invent tables, fields, joins, or doctypes.
- If a query logically requires a child table, linked table, lookup table, date field, grouping field, filter field, aggregation field, sorting field, or join-relevant field, it must be included in positives.
- If a table or field is not required for correct SQL generation, do not include it.

Critical positives rules:
- positives must be a flat, single-level list of strings only.
- Do not use objects, dictionaries, nested lists, tuples, arrays inside arrays, or any structured item inside positives.
- Every item inside positives must be a string.
- Missing even one critical table or field makes the sample invalid.
- Positives must include every table and field genuinely needed to answer the anchor and generate the SQL correctly.
- This includes, when applicable:
  - root transaction tables
  - child tables
  - lookup/master tables
  - identifier fields
  - output/display fields
  - filter fields
  - date/time fields
  - amount/value fields
  - grouping fields
  - aggregation fields
  - sorting/ranking fields
- Prefer completeness and schema correctness over shortness.

Field/table selection policy:
- Think like a production Text2SQL system, not like a casual annotator.
- For every anchor, determine:
  1. the main entity/table,
  2. all fields needed in SELECT,
  3. all fields needed in WHERE,
  4. all fields needed in GROUP BY,
  5. all fields needed in ORDER BY,
  6. all fields needed for aggregation,
  7. all tables/fields needed for joins.
- Then include all of them in positives.
- Do not omit child tables if the business meaning depends on line items, ledger rows, account rows, stock rows, or detail rows.
- Do not rely on only a parent table when SQL would require a child/detail table.
- Do not return weak positives with only one table unless that is truly sufficient.
CRITICAL SQL REASONING STEP (MANDATORY):

Before constructing positives, explicitly derive the SQL requirements from the anchor:

1. Identify SELECT fields (what needs to be shown).
2. Identify WHERE conditions (filters such as dates, status, names, etc.).
3. Identify GROUP BY fields (if query includes "per", "each", "by").
4. Identify ORDER BY fields (if query includes "top", "highest", "lowest").
5. Identify AGGREGATION fields:
   - "total", "sum", "amount" → numeric fields (e.g., grand_total, paid_amount, debit, credit, amount)
   - "count" → identifier field (e.g., name)
   - "balance" → debit/credit fields from ledger tables (NOT master tables)
6. Identify JOIN requirements:
   - If query references related entity (customer, item, account, warehouse), include linking fields and related tables.
7. Identify TIME filters:
   - "today", "yesterday", "last month", "this year" → 반드시 include correct date field (posting_date, transaction_date, etc.)

MANDATORY RULE:
If any of the above are required by the query, the corresponding fields MUST be included in positives.

Samples missing:
- aggregation field
- grouping field
- numeric field for totals
- ledger fields for balance
- correct date field for time filtering

are INVALID and must be corrected before output.
Validation pass (mandatory before final output):
For each generated record, perform an internal validation pass and correct the sample before returning it.
Check:
- Can correct SQL be generated from these positives alone?
- Is any required table missing?
- Is any required field missing?
- If the query uses time logic, is the correct date field included?
- If the query uses ranking/comparison, is the numeric/sort field included?
- If the query uses grouping like “per customer”, is the grouping field included?
- If the query needs joins, are the linked tables and join-relevant fields included?
- If the query refers to line-level business meaning, is the child table included?
If any answer is no, fix the record before output.

CRITICAL OUTPUT CONSTRAINT:
- Output MUST be a raw JSON array (UTF-8 text).
- DO NOT wrap in ``` or ```json.
- DO NOT include any explanation, notes, or extra text.
- DO NOT include trailing commas.
- DO NOT include comments.
- The first character must be '[' and the last character must be ']'.
- If the format is violated, the response will be discarded.
- Return exactly {batch_size} records.

Each record must follow this structure:
{{
  "qid": "<module_code>_<number>",
  "anchor": "<natural language business query>",
  "positives": [
    "<string>",
    "<string>"
  ]
}}
Do not include Generic fields like creation, modified, owner, parenttype,parentfield, parent, idx, name, docstatus.
Important MUST!!! - Positive string format rules:
- Use only these string formats:
  - "[TABLE] tabDoctype | desc: ..."
  - "[FIELD] fieldname | [TABLE] tabDoctype | desc: ..."
- Keep descriptions short, precise, and business-relevant.
- Descriptions must support retrieval quality, but must not replace required fields/tables.
- Use only tables and fields that eixst in ERPNext"
RULES:
- Format: RAW JSON ARRAY ONLY. No markdown/prose.
Example:
[
  {{
    "qid": "PR_001",
    "anchor": "who authorized the extra items received in the Dammam warehouse yesterday?",
    "positives": [
      "[TABLE] tabPurchase Receipt | desc: Root transaction for received goods.",
      "[FIELD] owner | [TABLE] tabPurchase Receipt | desc: User who created or submitted the receipt.",
      "[FIELD] set_warehouse | [TABLE] tabPurchase Receipt | desc: Header warehouse used to filter location.",
      "[FIELD] posting_date | [TABLE] tabPurchase Receipt | desc: Date used for filtering yesterday.",
      "[TABLE] tabUser | desc: User master used to resolve owner details.",
      "[FIELD] name | [TABLE] tabUser | desc: User identifier used for joining.",
    ]
  }}
]
RULES:
- Use standard ERPNext schema (incl. Parent-Child).do not use custom tables or fields not in ERPNext.
- Format: RAW JSON ARRAY ONLY. No markdown/prose.
OUTPUT: RAW JSON ARRAY [{batch_size} records]. Start '[' end ']'.
Important !!! Format: RAW JSON ARRAY ONLY. No markdown/prose.
Make sure positives' must be a SINGLE-LEVEL list of strings.DO NOT use objects, nested lists, or dictionaries inside 'positives'.
""".strip()

import frappe
@frappe.whitelist(allow_guest=False)
def get_module_schema_str(module_name: str) -> str:

    SKIP_FIELDTYPES = {
        "Section Break", "Column Break", "Tab Break", "HTML",
        "Heading", "Button", "Fold", "Table", "Table MultiSelect",
        "Text Editor", "Small Text", "Read Only", "Attach Image",
        "Attach", "Color", "Signature", "Geolocation", "Code"
    }

    SKIP_FIELDNAMES = {
        "address_display", "contact_display", "other_charges_calculation",
        "base_in_words", "in_words", "scan_barcode", "last_scanned_warehouse",
        "company_address_display", "shipping_address", "dispatch_address",
        "base_rounding_adjustment", "rounding_adjustment", "disable_rounded_total",
        "ignore_pricing_rule", "plc_conversion_rate", "price_list_currency",
        "has_unit_price_items", "group_same_items", "select_print_heading",
        "letter_head", "auto_repeat", "tc_name", "terms", "packed_items",
        "pricing_rules", "payment_schedule", "named_place", "incoterm",
        "reserve_stock", "set_warehouse"
    }

    doctypes = frappe.get_all(
        "DocType",
        filters={"module": module_name, "istable": 0},
        fields=["name"]
    )

    parts = []
    for dt in doctypes:
        try:
            meta = frappe.get_meta(dt["name"])
            fieldnames = []
            for f in meta.fields:
                if f.fieldname in SKIP_FIELDNAMES:
                    continue
                if f.fieldtype in SKIP_FIELDTYPES:
                    continue
                fieldnames.append(f.fieldname)

            if fieldnames:
                parts.append(f"tab{dt['name']}({', '.join(fieldnames)})")

        except Exception:
            continue

    return " | ".join(parts)


def _training_prompt_1(schema: str, batch_size: int) -> str:
    hard_n = (batch_size * 3) // 10
    std_n = batch_size - hard_n
    return f"""
You are a senior ERPNext architect and Text2SQL dataset designer.
Generate exactly {batch_size} COMPLEX training records as RAW JSON ARRAY only.
━━━ COMPLEXITY MANDATE ━━━
Every anchor MUST require at least one of:
  • Multi-table JOIN (2+ tables minimum)
  • Aggregation + GROUP BY (SUM / COUNT / AVG with grouping dimension)
  • Time filter + aggregation combined
  • Comparison / mismatch logic (e.g. expected vs actual, billed vs delivered)
  • Anomaly detection (missing links, zero where non-zero expected, NULL references)
  • Cross-module reasoning (tables from 2+ ERPNext modules)
  • Ranking (TOP N by a computed metric)
DO NOT generate:
  • Single-table queries
  • Simple lookup or filter-only queries
  • "list all X" or "show me X" style queries
Distribution: {hard_n} anomaly/mismatch/cross-module | {std_n} aggregation/trend/ranking
━━━ QUERY GENERATION RULES ━━━
Think deeply about the given schema and its business processes.
For this module, identify:
  • What are the most important business KPIs and metrics?
  • What are common business anomalies or exceptions in this module?
  • What cross-module workflows does this module participate in?
  • What time-based trends matter for this module?
  • What comparisons or mismatches would a business analyst care about?
Then generate anchors that reflect real complex business questions a manager,
analyst, or accountant would ask about the given schema — not a developer.
Style mix:
  • Urgent phrasing ("which ones are at risk", "need to flag immediately")
  • Casual business phrasing ("which customers are we losing money on")
  • Typo/messy phrasing ("custmer with hghest prfit lst mnth")
  • Domain-specific phrasing ("show COGS vs revenue by SKU this quarter")
━━━ SQL REASONING (do internally before building positives) ━━━
For every anchor identify:
  SELECT  → fields to display
  WHERE   → all filter conditions (status, date, amount, flag, type)
  GROUP BY → grouping dimension
  ORDER BY → sort/ranking field
  AGG     → SUM/COUNT/AVG field
  JOIN    → all linking fields + all linked tables
  DATE    → correct date field for this module's time filters
  CHILD   → child/detail table if line-item or ledger rows needed
  ANOMALY → the specific field whose NULL or absence defines the missing link
━━━ DESCRIPTION QUALITY (CRITICAL — this directly affects retrieval) ━━━
Format:
  "[FIELD] fieldname | [TABLE] tabDoctype | desc: ..."
  "[TABLE] tabDoctype | desc: ..."
Do not give simple queries. Give complicated queries that require multiple tables, joins, filters, and aggregations.
Make sure with this dataset i wouldnot get any JSON parse Error.That's important. So please follow the format and rules strictly.
Every field description MUST contain ALL of:
  1. BUSINESS PURPOSE — what this field means in plain business English
     BAD:  "date field"
     GOOD: "date the transaction was recorded in books; used for period filtering and trend analysis"
  2. SYNONYMS — business words that map to this field
     BAD:  "net rate of item"
     GOOD: "selling rate per unit after discounts; synonyms: sale price, unit price, discounted rate"
  3. For COST / VALUATION fields — profit/loss relevance explicitly stated
     GOOD: "cost price at which item was stocked at time of sale; compare with selling rate to calculate
            profit or loss per unit — if this exceeds selling rate, item was sold at a loss;
            synonyms: cost price, buying price, valuation rate, COGS"
  4. For AMOUNT / NUMERIC fields — financial meaning + aggregation purpose
     GOOD: "total net revenue for this line (rate x qty); SUM per customer to get total revenue"
  5. For STATUS fields — list actual ERPNext option values
     GOOD: "payment status; values: Draft, Unpaid, Paid, Partly Paid, Overdue, Cancelled —
            filter Unpaid/Overdue for receivables analysis"
  6. For DATE fields — which business event + filtering use
     GOOD: "date invoice posted to books; use for monthly/quarterly trends and date range filters"
  7. For FK / LINK fields — what it joins + why join is needed
     GOOD: "links to Customer master; required to group by customer or filter by customer segment"
  8. For ANOMALY fields — what NULL or absence means
     GOOD: "reference to originating Sales Order; if NULL on Delivery Note means delivery made
            without a sales order — use to detect unlinked deliveries"
Every table description MUST contain:
  • What business entity/transaction this table represents
  • When it is required (e.g. "required for line-item level analysis")
  • Synonyms if table name doesn't match business language
  BAD:  "child table"
  GOOD: "line-item rows of a sales invoice; contains per-item price, cost, and quantity —
         required for item-level profit, margin, or discount analysis;
         synonyms: invoice lines, sold items, invoice details"
━━━ ANCHOR PARAPHRASES (MANDATORY) ━━━
For every record, generate exactly 3 phrasings of the same question:
  • Original: formal business analyst style
  • Paraphrase 2: casual manager phrasing ("which products are we losing money on")
  • Paraphrase 3: messy/typo style ("itms whr cost exceeds selng pric lst qtr")
Store all 3 in "anchors" list instead of single "anchor" field.
All 3 must map to the SAME positives — same tables, same fields.
━━━ POSITIVES RULES ━━━
  • Flat list of strings only — no objects, dicts, or nested lists
  • Every string MUST follow exactly one of these two formats:
      "[FIELD] fieldname | [TABLE] tabDoctype | desc: ..."
      "[TABLE] tabDoctype | desc: ..."
  • NO raw SQL — do NOT include SUM(), GROUP BY, WHERE, HAVING, JOIN,
    ORDER BY, LIMIT, COUNT(), AVG(), DATE(), Comparison:, or any SQL
    fragment as a standalone string. Encode all logic into field descriptions instead.
    BAD:  "SUM(amount)"
    BAD:  "WHERE purchase_order IS NULL"
    BAD:  "Comparison: valuation_rate > standard_selling_rate"
    GOOD: "[FIELD] amount | [TABLE] tabPurchase Order Item | desc: net amount per line; SUM per supplier to get total spend"
    GOOD: "[FIELD] purchase_order | [TABLE] tabPurchase Receipt | desc: links to originating PO; if NULL, receipt was created without a PO — use to detect unlinked receipts"
  • Include ALL: root tables, child tables, lookup/master tables,
                 SELECT fields, WHERE fields, GROUP BY fields,
                 ORDER BY fields, aggregation fields, JOIN fields
  • Exclude: creation, modified, owner, parenttype, parentfield, idx, docstatus
  • Never invent tables or fields not in standard ERPNext
  • For profit/loss/margin queries: ALWAYS include both cost field AND selling rate field
  • For time queries: ALWAYS include correct date field for this module
  • For anomaly queries: ALWAYS include the field whose NULL defines the missing link
  • For cross-module: ALWAYS include tables and link fields from ALL modules involved
━━━ VALIDATION (run for every record before output) ━━━
  ✓ Is query genuinely complex — multi-table / aggregation / anomaly / cross-module?
  ✓ Can correct SQL be generated from positives alone?
  ✓ For profit/margin/loss: cost field AND selling field both present?
  ✓ For time queries: correct date field present?
  ✓ For aggregation: numeric field AND grouping field present?
  ✓ For anomaly: NULL-defining link field present?
  ✓ For cross-module: tables from ALL modules present?
  ✓ Are descriptions rich enough to match a business query without seeing the field name?
  ✓ Do synonyms bridge business language to technical field names?
  ✓ Does every positive string start with [FIELD] or [TABLE]? If not — fix it.
  ✓ Are there ANY raw SQL fragments in positives? If yes — remove and encode into desc instead.
If any check fails — fix before output.
━━━ OUTPUT FORMAT ━━━
Raw JSON array only. No markdown. No explanation. No trailing commas. No comments.
First char '[' last char ']'. Exactly {batch_size} records.
{{
  "qid": "<module_code>_<number>",
  "anchors": ["<formal phrasing>", "<casual phrasing>", "<messy/typo phrasing>"],
  "positives": ["<string>", "<string>"]
}}
- Format: RAW JSON ARRAY ONLY. No markdown/prose.
Important !!! Format: RAW JSON ARRAY ONLY. No markdown/prose.
Make sure 'positives' must be a SINGLE-LEVEL list of strings. DO NOT use objects, nested lists, or dictionaries inside 'positives'.
IMPORTANT !!!
schema : {schema}
Never ever write the training data with any fields or tables that do not exist in this given schema.
IMPORTANT !!! Use only the above schema to generate training data.
OUTPUT: RAW JSON ARRAY [{batch_size} records]. Start '[' end ']'.
- Do not add explanations, notes, markdown, or extra text like json.
Your entire response must be raw JSON only.
Do NOT include ```json, ```, or any other text before or after the JSON.
Start your response with [ and end with ].
""".strip()


def __correction_prompt(input_raw) -> str:
    return f"""
Act as an ERPNext data validation expert.
Task:
{input_raw}
Review the training records provided above.
For each record, carefully inspect:
1. the anchor
2. the positives list
Your goal is to improve the quality of the dataset for embedding-model training, where the model must retrieve the correct ERPNext tables and fields needed for SQL generation.
Instructions:
- Check whether all required tables and fields needed to answer the anchor are present in positives.
- Add any missing required tables or fields that are semantically necessary to answer the query.
- Remove any wrong, irrelevant, duplicate, or unnecessary tables or fields.
- Keep only the minimum necessary positives required to answer the anchor correctly.
- Do NOT include generic system fields such as: name, docstatus, status, creation, modified, owner, idx — these will be injected automatically later.
- Do NOT include optional or convenience fields unless they are strictly required for the SQL logic.
- Only use standard ERPNext tables and fields that actually exist in standard ERPNext modules.
- Do not invent custom tables or fields.
- Prefer standard ERPNext field names (e.g., use territory instead of region, transaction_date instead of posting_date where appropriate).
- Ensure the final corrected records are high-quality, precise, and minimal for retrieval training.
ADDITIONAL PRODUCTION RULES (STRICT):
* Every query MUST include: entity + metric + filter (time/status/condition).
* Mandatory fields must always be included based on query intent (e.g., sales → amount field, time → date field).
* Remove all noise/irrelevant fields (non-business or system fields).
* Queries must include messy, real-world, and typo variations.
* Cover edge cases: zero/no data, highest/lowest, time ranges, status conditions.
* Ensure records are validation-ready (complete, correct, and usable for SQL generation).
- if the positives are not in this below format.Make it in this below fomat also:
[TABLE] <table_name> | desc: <short table description>
[FIELD] <field_name> | [TABLE] <table_name> | desc: <short field description>
Use only those fields and tables that exist in ERPNext.
Output rules:
- Return the corrected records only.
- Preserve the same JSONL structure (one JSON object per line).
- Do not add explanations, notes, markdown, or extra text like json .
Your entire response must be raw JSON only.
Do NOT include ```json, ```, or any other text before or after the JSON.
Start your response with [ and end with ] .
- Output raw JSON only.
""".strip()