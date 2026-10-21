import frappe
from frappe.utils.password import set_encrypted_password

SETTINGS = "ChangAI Settings"
FIELDS = ["api_token", "openai_api_key", "claude_api_key", "gemini_api_key", "aws_secret_access_key"]


def execute():
    # These fields changed from Data to Password; move existing plain-text values into __Auth
    for fieldname in FIELDS:
        value = frappe.db.get_single_value(SETTINGS, fieldname, cache=False)
        if not value or set(value) == {"*"}:
            continue
        set_encrypted_password(SETTINGS, SETTINGS, value, fieldname)
        frappe.db.set_single_value(SETTINGS, fieldname, "*" * len(value), update_modified=False)
    frappe.clear_document_cache(SETTINGS, SETTINGS)
