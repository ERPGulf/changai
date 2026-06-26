import frappe
from frappe import _
from werkzeug.wrappers import Response
from typing import Any, Optional, Dict
import json
from changai.changai.api.v2.schema_utils import read_asset
from changai.changai.api.v2.clients import call_gemini

SUPPORT_PROMPT = read_asset("support.txt", base="prompts")
SUPPORT_USER_PROMPT = read_asset("support_user_prompt.txt", base="prompts")
SUPPORT_SYS_PROMPT = read_asset("support_sys_prompt.txt", base="prompts")
@frappe.whitelist()
def create_helpdesk_ticket(subject:str,user:str,email:str,priority:str ="Low", ticket_type: str ="Bug"):
    try:

        doc = frappe.new_doc("ChangAI Help Desk")
        doc.subject = subject
        doc.description = subject
        doc.customer = user
        doc.email = email
        doc.priority = priority
        doc.ticket_type = ticket_type
        doc.status = "Open"

        doc.insert(ignore_permissions=True)
        # nosemgrep: frappe-manual-commit - explicit commit required to persist File DocType record.
        frappe.db.commit()


        return Response(
            json.dumps(
                {
                "kind": "TICKET_CREATED",
                "data": {
                    "ticket_id": doc.name,
                    "subject": doc.subject,
                    "email": doc.email,
                }
            }
            ),
            status=200,
            mimetype="application/json")


    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Create Helpdesk Ticket API")

        return Response(
            json.dumps(
                {
            "message": {
                "kind": "TICKET_CREATION_FAILED",
                "data": {
                    "error": str(e)
                }
            }
            }
            ),
            status=500,
            mimetype="application/json")

@frappe.whitelist()
def get_user_tickets(ticket_id: int =None):
    try:

        filters = {}
        if ticket_id:
            filters["name"] = ticket_id

        tickets = frappe.get_all(
            "ChangAI Help Desk",
            filters=filters,
            fields=[
                "name",
                "subject",
                "status",
                "priority",
                "description",
                "creation",
                "customer",
            ],
            order_by="creation desc"
        )

        if ticket_id and not tickets:
            return Response(
            json.dumps(
                {
                    "kind": "TICKET_DETAILS",
                    "data": {
                        "error": "Ticket not found"
                    }
                }
            ),
            status=500,
            mimetype="application/json")


        formatted = []
        for t in tickets:
            formatted.append({
                "ticket_id": t.name,
                "subject": t.subject,
                "raised_by": t.customer,
                "status": t.status,
                "priority": t.priority,
                "description": t.description,
                "created_on": str(t.creation)
            })

        return Response(
            json.dumps(
                {
                "kind": "TICKET_DETAILS",
                "data": {
                    "tickets": formatted if not ticket_id else formatted[0]
                }
            }
            ),
            status=200,
            mimetype="application/json")



    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Get Ticket Details API")
        return Response(
            json.dumps(
                {
                "kind": "TICKET_DETAILS",
                "data": {
                    "status": 500,
                    "error": str(e)
                }
            }
            ),
            status=500,
            mimetype="application/json")


@frappe.whitelist(allow_guest=False)
def support_bot(message: str) -> Dict[str, Any]:
    user_email = frappe.session.user
    full_name = frappe.get_value("User", frappe.session.user, "full_name")
    prompt = SUPPORT_USER_PROMPT.format(user_message=message)
    raw = call_gemini(prompt, SUPPORT_SYS_PROMPT)
    output = json.loads(raw)
    task_flag = (output.get("task_flag") or "UNKNOWN").strip()
    ticket_id = output.get("ticket_id")

    if isinstance(ticket_id, str) and ticket_id.isdigit():
        ticket_id = int(ticket_id)
    if not isinstance(ticket_id, int):
        ticket_id = None

    if task_flag == "CREATE_TICKET":
        try:
            response = create_helpdesk_ticket(message, full_name, user_email)
            return json.loads(response.get_data(as_text=True))  # ✅ unwrap Response → dict
        except Exception as e:
            return {"error": str(e)}

    if task_flag == "TICKET_DETAILS":
        if not ticket_id:
            return {"kind": "TICKET_DETAILS", "error": "Ticket id missing. Please say like: ticket 29"}
        try:
            response = get_user_tickets(ticket_id)
            return json.loads(response.get_data(as_text=True))  # ✅ unwrap Response → dict
        except Exception as e:
            return {"error": str(e)}

    if task_flag == "GET_USER_TICKETS":
        response = get_user_tickets()
        return json.loads(response.get_data(as_text=True))  
    if task_flag == "TICKET_CREATION_FAILED":
        return {"kind":"TICKET_CREATION_FAILED","message":"Something went wrong. Please try again."}

    return {"kind": "UNKNOWN", "message": "Please describe the issue or provide a ticket number."}

