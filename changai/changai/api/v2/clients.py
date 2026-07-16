import frappe
import requests
import json
import time
from frappe import _
from typing import Any, Dict, List, Optional, Union
from google import genai
from google.genai import types
from google.oauth2 import service_account
from google.api_core import exceptions as google_exceptions
from openai import OpenAI
from changai.changai.api.v2.schema_utils import (ChangAIConfig, CHANGAI_SETTINGS, CHANGAI_GUIDE_LINK, ERPGULF_LINK, settingsUrl)
_GEMINI_CLIENT = None
_GEMINI_CONFIG = None
_GROK_CLIENT = None
APPLICATION_JSON = "application/json"
MODEL_ID = "gemini-2.5-flash-lite"
GROK_BASE_URL = "https://api.x.ai/v1"
GROK_DEFAULT_MODEL = "grok-3-mini"
STATUS_200 = 200
CLAUDE_DEFAULT_MODEL = "claude-opus-4-8"
CLAUDE_MAX_TOKENS = 8000

# OpenAI-compatible providers reachable through the OpenAI SDK with a custom
# base_url. NOTE: "Groq" (groq.com, free tier) is a different vendor from the
# "Grok" (xAI) provider configured above — do not confuse the two.
OPENAI_COMPATIBLE_PROVIDERS = {
    "Groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_field": "groq_api_key",
        "model_field": "groq_model",
        "default_model": "llama-3.3-70b-versatile",
        "key_url": "https://console.groq.com/keys",
    },
    "OpenAI": {
        "label": "OpenAI",
        "base_url": None,  # native OpenAI endpoint
        "api_key_field": "openai_api_key",
        "model_field": "openai_model",
        "default_model": "gpt-4o-mini",
        "key_url": "https://platform.openai.com/api-keys",
    },
}

# Clients cached by api key so changing the key in settings rebuilds them.
_OPENAI_COMPAT_CLIENTS = {}
_CLAUDE_CLIENT = None
_CLAUDE_CLIENT_KEY = None


def _post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int = 120):
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=timeout)
        ct = (res.headers.get("Content-Type") or "").lower()
        try:
            body = res.json() if APPLICATION_JSON in ct else {"raw_text": res.text}
        except Exception:
            body = {"raw_text": res.text}
        if res.status_code not in (STATUS_200, 201, 202):
            return {"ok": False, "status_code": res.status_code, "body": body}
        return {"ok": True, "status_code": res.status_code, "body": body}
    except requests.exceptions.Timeout:
        return {"ok": False, "status_code": None, "body": {"error": "timeout"}}
    except Exception as e:
        return {"ok": False, "status_code": None, "body": {"error": str(e)}}




def local_llm_request(prompt: str) -> str:
    config = ChangAIConfig.get()
    url = f"{config['URL'].rstrip('/')}/api/generate"
    payload = {"model": config["LOCAL_LLM"], "prompt": prompt, "stream": False}
    resp = _post_json(url, headers={}, payload=payload, timeout=120)
    if not resp.get("ok"):
        return f"Error: local LLM call failed ({resp.get('status_code')}): {resp.get('body')}"
    text = (resp.get("body") or {}).get("response")
    return (text or "").strip() or "Error: Empty response from local LLM."


def _get_gemini_vertex_config(config):
    project_id = (config.get("gemini_project_id") or "").strip()
    credentials_json = (config.get("gemini_json_content") or "").strip()
    location = (config.get("gemini_location") or "").strip()
    return project_id, credentials_json, location


def _throw_missing_vertex_field(project_id: str, location: str, credentials_json: str) -> None:
    if not project_id:
        frappe.throw(
            _("Gemini Project ID is missing.<br><br>Please <b> <a href='{1}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Go to Settings Page</a> </b> and enter your <b>Gemini Project ID</b>.<br>"
            "Check Quick Start Guide 👇:<br><a href='{0}' target='_blank'>Click here</a><br>"
            "<a href='{2}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>ERPGulf.com</a></b>.").format(CHANGAI_GUIDE_LINK,settingsUrl,ERPGULF_LINK),
            title=_("Missing Gemini Project ID"),
        )
    if not location:
        frappe.throw(
            _("Gemini Location is missing.<br><br>Please <b><a href='{1}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Go to Settings Page</a></b> and enter your <b>Gemini Location</b>.<br>"
              "Check Quick Start Guide 👇:<br><a href='{0}' target='_blank'>Click here</a><br>"
              "<a href='{2}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>ERPGulf.com</a></b>.").format(CHANGAI_GUIDE_LINK,settingsUrl,ERPGULF_LINK),
            title=_("Missing Gemini Location"),
        )
    if not credentials_json:
        frappe.throw(
            _("Service Account Credentials are missing.<br><br>Please <b><a href='{1}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Go to Settings Page</a></b> and enter your <b>Service Account Credential</b>.<br>"
            "Check Quick Start Guide 👇:<br><a href='{0}' target='_blank'>Click here</a>"
            "<a href='{2}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>ERPGulf.com</a></b>."
).format(CHANGAI_GUIDE_LINK,settingsUrl,ERPGULF_LINK),
            title=_("Missing Service Account Credentials"),
        )



def _get_api_key_client(config):
    try:
        api_key = config.get("gemini_api_key")
    except Exception:
        api_key = None

    if not api_key:
        frappe.throw(
            _(
                "Gemini API key is not configured.<br><br>"
                "You have two options to authenticate with Gemini:<br><br>"
                "<b>Option 1 (Free / API Key):</b><br>"
                "Go to <b>ChangAI Settings</b> and enter your <b>Gemini API Key</b>.<br>"
                "Get your free API key from "
                "<a href='https://aistudio.google.com/app/apikey' target='_blank'>Google AI Studio</a>.<br><br>"
                "<b>Option 2 (Vertex AI / Service Account):</b><br>"
                "Fill in <b>Gemini Project ID</b>, <b>Gemini Location</b>, "
                "and <b>Service Account Credentials</b> in <b><a href='{1}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Got to Settings Page</a></b>.<br>"
                "ChangAI Quick Start Guide 👇:<br>"
                "<a href='{0}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Click here</a><br>"
                "<a href='{2}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>ERPGulf.com</a></b>."

            ).format(CHANGAI_GUIDE_LINK,settingsUrl,ERPGULF_LINK),
            title=_("Gemini Authentication Not Configured"),
        )

    return genai.Client(api_key=api_key)


def _build_gemini_client(config):
    project_id, credentials_json, location = _get_gemini_vertex_config(config)

    if project_id or credentials_json or location:
        return _build_vertex_gemini_client(project_id, location, credentials_json)

    return _get_api_key_client(config)


def _build_gemini_contents(prompt: str):
    return [
        {
            "role": "user",
            "parts": [{"text": str(prompt)}],
        }
    ]


def _clean_gemini_response_text(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    return text


def _handle_gemini_api_exception(e: Exception) -> None:
    if isinstance(e, google_exceptions.ResourceExhausted):
        frappe.throw(
            _("Gemini API quota exceeded.<br><br>Please wait and try again or upgrade your plan.<br>Check Quick Start Guide 👇:<br>"
            "<a href='{0}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Click here</a><br>"
            "<a href='{1}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>ERPGulf.com</a></b>."
).format(CHANGAI_GUIDE_LINK,ERPGULF_LINK),

            title=_("Gemini Quota Exceeded"),
        )
    if isinstance(e, google_exceptions.Unauthenticated):
        frappe.throw(
            _("Gemini API key is invalid.<br><br>Please go to <b>ChangAI Settings</b> and enter a valid <b>Gemini API Key</b>.<br>"
            "Check ChangAI Quick Start Guide 👇:<br><a href='{0}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Click here</a><br>"
            "<a href='{1}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>ERPGulf.com</a></b>."
).format(CHANGAI_GUIDE_LINK,ERPGULF_LINK),
            title=_("Invalid Gemini API Key"),
        )
    if isinstance(e, google_exceptions.PermissionDenied):
        frappe.throw(
            _("Gemini API permission denied.<br><br>Please check your API key permissions.<br>"
            "Check ChangAI Quick Start Guide 👇:<br><a href='{0}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Click here</a><br>"
            "<a href='{1}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>ERPGulf.com</a></b>."
).format(CHANGAI_GUIDE_LINK,ERPGULF_LINK),
            title=_("Gemini Permission Denied"),
        )
    if isinstance(e, google_exceptions.InvalidArgument):
        frappe.throw(
            _("Invalid request to Gemini API: {0}<br>"
            "Check ChangAI Quick Start Guide 👇:<br>"
            "<a href='{1}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Click here</a><br>"
            "<a href='{2}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>ERPGulf.com</a></b>.").format(str(e),CHANGAI_GUIDE_LINK,ERPGULF_LINK),
            title=_("Gemini Invalid Request"),
        )

    frappe.log_error(frappe.get_traceback(), "Gemini API Unexpected Error")
    frappe.throw(
        _("Gemini API error: {0}<br>"
        "Check ChangAI Quick Start Guide 👇:<br>"
        "<a href='{1}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>Click here</a><br>"
        "<a href='{2}' target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>ERPGulf.com</a></b>.").format(str(e),CHANGAI_GUIDE_LINK,ERPGULF_LINK),
        title=_("Gemini API Error"),
    )


def gemini_client():
    global _GEMINI_CLIENT,_GEMINI_CONFIG
    if _GEMINI_CLIENT is None:
        config = frappe.get_single(CHANGAI_SETTINGS)
        _GEMINI_CONFIG =  config
        _GEMINI_CLIENT = _build_gemini_client(config)
    return _GEMINI_CLIENT


def grok_client():
    global _GROK_CLIENT
    if _GROK_CLIENT is None:
        config = ChangAIConfig.get()
        api_key = (config.get("grok_api_key") or "").strip()
        if not api_key:
            frappe.throw(
                _(
                    "Grok (xAI) API key is not configured.<br><br>"
                    "Go to <b>ChangAI Settings</b> and enter your <b>xAI API Key</b>.<br>"
                    "Get your key from <a href='https://console.x.ai' target='_blank' "
                    "rel='noopener noreferrer' style='color: #1e90ff;'>console.x.ai</a>."
                ),
                title=_("Grok API Key Missing"),
            )
        _GROK_CLIENT = OpenAI(
            api_key=api_key,
            base_url=GROK_BASE_URL,
        )
    return _GROK_CLIENT


def reset_grok_client():
    """Reset cached Grok client — call after changing the xAI API key in settings."""
    global _GROK_CLIENT
    _GROK_CLIENT = None



def _build_input_payload(task: str, prompt: str, question: Optional[str],
                          db_result_json: Optional[str], user_message: Optional[str]) -> Dict[str, Any]:
    if task == "format_db":
        return {"task": "format_db", "question": question or "", "db_result_json": db_result_json or "{}"}
    if task == "helpdesk_task":
        return {"task": "helpdesk_task", "user_message": user_message or prompt or ""}
    return {"task": "llm", "user_input": prompt}


def _poll_until_done(get_url: str, headers: Dict) -> Any:
    terminal = {"succeeded", "failed", "canceled"}
    deadline = time.time() + 300
    last = None
    while time.time() < deadline:
        try:
            poll = requests.get(get_url, headers=headers, timeout=120).json()
        except Exception as e:
            poll = {"raw_text": str(e)}
        last = poll
        status = poll.get("status")
        if status in terminal:
            if status == "succeeded":
                return poll.get("output")
            return {"Error": f"Model ended with status {status}", "details": poll}
        time.sleep(2)
    return {"Error": "Polling timed out", "details": last}


def _build_vertex_gemini_client(project_id: str, location: str, credentials_json: str):
    _throw_missing_vertex_field(project_id, location, credentials_json)

    service_account_info = json.loads(credentials_json)
    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    return genai.Client(
        vertexai=True,
        project=project_id,
        location=location,
        credentials=creds,
    )



def remote_llm_request_deploy_test(
    prompt: str = "",
    task: str = "llm",
    question: Optional[str] = None,
    db_result_json: Optional[str] = None,
    user_message: Optional[str] = None,
) -> Any:
    config = ChangAIConfig.get()
    headers = {
        "Content-Type": APPLICATION_JSON,
        "Prefer": "wait",
        "Authorization": f"Bearer {config['API_TOKEN']}",
    }
    input_payload = _build_input_payload(task, prompt, question, db_result_json, user_message)
    create = _post_json(config["deploy_url"], headers=headers, payload={"input": input_payload}, timeout=120)

    if not create.get("ok"):
        return {"Error": "Create prediction failed", "status_code": create.get("status_code"), "details": create.get("body")}

    get_url = ((create.get("body") or {}).get("urls") or {}).get("get")
    if not get_url:
        return {"Error": "Missing get URL from deploy response", "details": create.get("body")}

    return _poll_until_done(get_url, headers)


def remote_embedder_request(formatted_q: str) -> Union[List[Any], str]:
    config = ChangAIConfig.get()
    payload = {"version": config["EMBED_VERSION_ID"], "input": {"user_input": formatted_q}}
    headers = {
        "Content-Type": APPLICATION_JSON,
        "Prefer": "wait",
        "Authorization": f"Bearer {config['API_TOKEN']}",
    }
    response = _post_json(config["URL"], headers, payload)
    try:
        if response:
            return response["body"]["output"]
    except Exception as e:
        return "Error: " + str(e)


def call_model(prompt: str, task: str = "llm", sys_prompt: str = "") -> Any:
    config = ChangAIConfig.get()
    llm = config["llm"]
    if config["REMOTE"] and llm == "QWEN3":
        return remote_llm_request_deploy_test(prompt=prompt, task=task)
    if llm == "Grok":
        return call_grok(prompt, sys_prompt)
    if llm == "Claude":
        return call_claude(prompt, sys_prompt)
    if llm in OPENAI_COMPATIBLE_PROVIDERS:
        return call_openai_compatible(llm, prompt, sys_prompt)
    return call_gemini(prompt, sys_prompt)


def call_gemini(prompt: str,sys_prompt: str) -> Union[str, Dict[str, Any]]:
    try:
        # frappe.clear_document_cache(CHANGAI_SETTINGS)
        client = gemini_client()

        gemini_config = types.GenerateContentConfig(
            system_instruction=sys_prompt,
        )
        response = client.models.generate_content(
            model=MODEL_ID,
            config=gemini_config,
            contents=_build_gemini_contents(prompt),
        )
        return _clean_gemini_response_text(response.text)

    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        _handle_gemini_api_exception(e)


def call_grok(prompt: str, sys_prompt: str = "") -> str:
    try:
        config = ChangAIConfig.get()
        model = (config.get("grok_model") or GROK_DEFAULT_MODEL).strip()
        client = grok_client()

        messages = []
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.append({"role": "user", "content": str(prompt)})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
        )
        text = (response.choices[0].message.content or "").strip()
        if text.startswith("```"):
            text = text.replace("```json", "").replace("```", "").strip()
        return text

    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Grok API Error")
        frappe.throw(
            _(
                "Grok API error: {0}<br><br>"
                "Please check your <b>xAI API Key</b> and <b>Grok Model</b> in ChangAI Settings."
            ).format(str(e)),
            title=_("Grok API Error"),
        )


def _strip_code_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    return text


def openai_compatible_client(provider: str):
    """Return a cached OpenAI SDK client for an OpenAI-compatible provider."""
    spec = OPENAI_COMPATIBLE_PROVIDERS[provider]
    config = ChangAIConfig.get()
    api_key = (config.get(spec["api_key_field"]) or "").strip()
    if not api_key:
        frappe.throw(
            _(
                "{0} API key is not configured.<br><br>"
                "Go to <b>ChangAI Settings</b> and enter your <b>{0} API Key</b>.<br>"
                "Get your key from <a href='{1}' target='_blank' "
                "rel='noopener noreferrer' style='color: #1e90ff;'>{1}</a>."
            ).format(spec["label"], spec["key_url"]),
            title=_("{0} API Key Missing").format(spec["label"]),
        )
    cached = _OPENAI_COMPAT_CLIENTS.get(provider)
    if cached and cached[0] == api_key:
        return cached[1]
    kwargs = {"api_key": api_key}
    if spec["base_url"]:
        kwargs["base_url"] = spec["base_url"]
    client = OpenAI(**kwargs)
    _OPENAI_COMPAT_CLIENTS[provider] = (api_key, client)
    return client


def call_openai_compatible(provider: str, prompt: str, sys_prompt: str = "") -> str:
    spec = OPENAI_COMPATIBLE_PROVIDERS[provider]
    try:
        config = ChangAIConfig.get()
        model = (config.get(spec["model_field"]) or spec["default_model"]).strip()
        client = openai_compatible_client(provider)

        messages = []
        if sys_prompt:
            messages.append({"role": "system", "content": sys_prompt})
        messages.append({"role": "user", "content": str(prompt)})

        response = client.chat.completions.create(model=model, messages=messages)
        text = (response.choices[0].message.content or "").strip()
        return _strip_code_fences(text)

    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"{spec['label']} API Error")
        frappe.throw(
            _(
                "{0} API error: {1}<br><br>"
                "Please check your <b>{0} API Key</b> and <b>{0} Model</b> in ChangAI Settings."
            ).format(spec["label"], str(e)),
            title=_("{0} API Error").format(spec["label"]),
        )


def claude_client():
    """Return a cached Anthropic client, rebuilt when the API key changes."""
    global _CLAUDE_CLIENT, _CLAUDE_CLIENT_KEY
    config = ChangAIConfig.get()
    api_key = (config.get("claude_api_key") or "").strip()
    if not api_key:
        frappe.throw(
            _(
                "Claude (Anthropic) API key is not configured.<br><br>"
                "Go to <b>ChangAI Settings</b> and enter your <b>Claude API Key</b>.<br>"
                "Get your key from <a href='https://console.anthropic.com/settings/keys' "
                "target='_blank' rel='noopener noreferrer' style='color: #1e90ff;'>"
                "console.anthropic.com</a>."
            ),
            title=_("Claude API Key Missing"),
        )
    if _CLAUDE_CLIENT is not None and _CLAUDE_CLIENT_KEY == api_key:
        return _CLAUDE_CLIENT
    try:
        import anthropic
    except ImportError:
        frappe.throw(
            _(
                "The <b>anthropic</b> Python package is not installed.<br><br>"
                "Install it in your bench environment:<br>"
                "<code>./env/bin/pip install anthropic</code>"
            ),
            title=_("Anthropic SDK Not Installed"),
        )
    _CLAUDE_CLIENT = anthropic.Anthropic(api_key=api_key)
    _CLAUDE_CLIENT_KEY = api_key
    return _CLAUDE_CLIENT


def call_claude(prompt: str, sys_prompt: str = "") -> str:
    try:
        config = ChangAIConfig.get()
        model = (config.get("claude_model") or CLAUDE_DEFAULT_MODEL).strip()
        client = claude_client()

        kwargs = {
            "model": model,
            "max_tokens": CLAUDE_MAX_TOKENS,
            "messages": [{"role": "user", "content": str(prompt)}],
        }
        if sys_prompt:
            kwargs["system"] = sys_prompt
        # Adaptive thinking keeps reasoning in separate blocks so the text blocks
        # stay clean. Haiku does not support it, so only enable for other models.
        if not model.lower().startswith("claude-haiku"):
            kwargs["thinking"] = {"type": "adaptive"}

        response = client.messages.create(**kwargs)
        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        return _strip_code_fences(text)

    except frappe.exceptions.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Claude API Error")
        frappe.throw(
            _(
                "Claude API error: {0}<br><br>"
                "Please check your <b>Claude API Key</b> and <b>Claude Model</b> in ChangAI Settings."
            ).format(str(e)),
            title=_("Claude API Error"),
        )


def reset_llm_clients():
    """Reset all cached provider clients — call after changing any API key."""
    global _GROK_CLIENT, _CLAUDE_CLIENT, _CLAUDE_CLIENT_KEY
    _GROK_CLIENT = None
    _CLAUDE_CLIENT = None
    _CLAUDE_CLIENT_KEY = None
    _OPENAI_COMPAT_CLIENTS.clear()