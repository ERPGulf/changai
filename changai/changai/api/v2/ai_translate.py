import os
import anthropic
import frappe
from frappe import _
from anthropic import Anthropic

def get_meta(doc:str):
    return frappe.get_meta(doc) 
def get_doctype(doc:str,docname: str):
    return frappe.get_doc(doc, docname)
def get_settings():
    return frappe.get_single("ChangAI Settings")


_CLAUDE_CLIENT = None
_CLAUDE_API_KEY = None

def get_claude_client():
    global _CLAUDE_CLIENT, _CLAUDE_API_KEY

    settings = get_settings()
    api_key = (getattr(settings, "claude_api_key", None) or "").strip()

    if not api_key:
        api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()

    if not api_key:
        frappe.throw(
            _("Claude API key is not configured."),
            title=_("Missing Claude API Key")
        )

    if _CLAUDE_CLIENT is None or _CLAUDE_API_KEY != api_key:
        _CLAUDE_CLIENT = Anthropic(api_key=api_key)
        _CLAUDE_API_KEY = api_key

    return _CLAUDE_CLIENT


@frappe.whitelist(allow_guest=False)
def translate_and_store(docname: str, doctype: str, from_field: str, to_field: str, text: str, to_language: str):
    """
    Translates text and stores it in a dynamically created field
    """
    meta = get_meta(doctype)
    field_meta = meta.get_field(to_field)

    if field_meta and field_meta.fieldtype == "Link":
        frappe.throw(
            f"Field '{to_field}' is a Link field and cannot be translated in place."
        )
    if not text:
        frappe.throw(_("No text to translate"))
    settings = get_settings()
    try:
        api_key = settings.claude_api_key
    except Exception:
        api_key = None
    if not api_key:
        api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        frappe.throw(
            _(
                "Claude API key is not configured.<br><br>"
                "Please go to <b>Remote Tab in ChangAI Settings</b> and enter your <b>Claude API Key</b>.<br><br>"
                "Get your API key from "
                "<a href='https://console.anthropic.com/account/keys' target='_blank'>Anthropic Console</a>."
            ),
            title=_("Missing Claude API Key")
        )
    try:
        client = get_claude_client()
        prompt = f"""
        Translate the following text into {to_language}.
        Return ONLY the translated text.
        Text:
        {text}
        """
        response = client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=1024,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        translated_text = response.content[0].text.strip()
    except anthropic.AuthenticationError:
        frappe.throw(
            _(
                "Claude API key is invalid.<br><br>"
                "Please go to <b>ChangAI Settings</b> and enter a valid <b>Claude API Key</b>."
            ),
            title=_("Invalid Claude API Key")
        )
    except anthropic.RateLimitError:
        frappe.throw(
            _(
                "Claude API rate limit exceeded.<br><br>"
                "Please wait a moment and try again, or upgrade your Anthropic plan."
            ),
            title=_("Claude Rate Limit Exceeded")
        )
    except anthropic.APIConnectionError:
        frappe.throw(
            _(
                "Could not connect to Claude API.<br><br>"
                "Please check your internet connection and try again."
            ),
            title=_("Claude Connection Error")
        )
    except anthropic.APIStatusError as e:
        frappe.throw(
            _(
                "Claude API error (status {0}): {1}"
            ).format(e.status_code, str(e)),
            title=_("Claude API Error")
        )
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Claude Translate Unexpected Error")
        frappe.throw(
            _("Translation failed: {0}").format(str(e)),
            title=_("Translation Error")
        )
    frappe.clear_cache(doctype=doctype)
    doc = get_doctype(doctype,docname)
    if not hasattr(doc, to_field):
        frappe.throw(f"Field '{to_field}' does not exist on Item")
    doc.set(to_field, translated_text)
    doc.save(ignore_permissions=False)
    return to_field
