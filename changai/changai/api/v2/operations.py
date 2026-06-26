import frappe
import json
import re
from typing import Any, Dict, List, Tuple, Optional

CHANGAI_GUIDE_LINK="https://app.erpgulf.com/en/articles/chang-ai-quick-start-guide"

@frappe.whitelist(allow_guest=False)
def execute_insert(payload: dict) -> Any:
    from changai.changai.api.v2.auto_gen_api import update_masterdata
    try:
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        operation = payload.get("operation")
        if not operation:
            return {"error": "No operation provided"}

        if operation == "insert_main":
            frappe.has_permission(payload["doctype"], "create", throw=True)
            _validate_linked_fields(payload["doctype"], payload["data"])

            doc = frappe.get_doc({
                "doctype": payload["doctype"],
                **payload["data"]
            })

            # Handle child_rows if present
            child_rows = payload.get("child_rows") or {}
            for child_table, rows in child_rows.items():
                if isinstance(rows, list):
                    for row in rows:
                        doc.append(child_table, row)

            doc.insert(ignore_permissions=False)
            

            result = {
                "success": True,
                "operation": "insert_main",
                "doctype": doc.doctype,
                "name": doc.name,
                "message": f"{doc.doctype} '{doc.name}' created successfully."
            }

            # ✅ Handle after_insert if present
            after_insert = payload.get("after_insert")
            if after_insert:
                after_insert["doctype"] = payload["doctype"]
                after_insert["filters"] = {"name": doc.name}
                after_result = execute_insert(after_insert)
                result["after_insert_result"] = after_result
                if after_result.get("error"):
                    result["after_insert_warning"] = f"Main doc created but linked doc failed: {after_result['error']}"
                else:
                    result["message"] = (
                        f"{doc.doctype} '{doc.name}' created successfully "
                        f"with linked {after_insert.get('linked_doctype', '')}."
                    )
            update_masterdata()

            return result
        # ─── CASE 2: INSERT CHILD ROW ─────────────────────────
        elif operation == "insert_child":
            frappe.has_permission(payload["doctype"], "write", throw=True)

            parent_name = frappe.db.get_value(
                payload["doctype"], payload["filters"], "name"
            )
            if not parent_name:
                return {"error": f"No {payload['doctype']} found for given filters"}

            doc = frappe.get_doc(payload["doctype"], parent_name)
            doc.append(payload["child_table"], payload["data"])
            doc.save(ignore_permissions=False)
            update_masterdata()
            return {
                "success": True,
                "operation": "insert_child",
                "parent": parent_name,
                "child_table": payload["child_table"],
                "message": f"Row added to '{payload['child_table']}' in '{parent_name}' successfully."
            }

        # ─── CASE 3: INSERT LINKED DOC + LINK ─────────────────
        elif operation == "insert_linked":
            frappe.has_permission(payload["linked_doctype"], "create", throw=True)

            # Get parent
            parent_name = frappe.db.get_value(
                payload["doctype"], payload["filters"], "name"
            )
            if not parent_name:
                return {"error": f"No {payload['doctype']} found for given filters"}

            # Create linked doc
            linked_doc = frappe.get_doc({
                "doctype": payload["linked_doctype"],
                **payload["data"]
            })

            # Auto append Dynamic Link
            linked_doc.append("links", {
                "link_doctype": payload["doctype"],
                "link_name": parent_name
            })

            linked_doc.insert(ignore_permissions=False)

            # Update link field on parent if specified
            if payload.get("link_via"):
                parent_doc = frappe.get_doc(payload["doctype"], parent_name)
                parent_doc.set(payload["link_via"], linked_doc.name)
                parent_doc.save(ignore_permissions=False)
            update_masterdata()
            
            return {
                "success": True,
                "operation": "insert_linked",
                "linked_name": linked_doc.name,
                "parent": parent_name,
                "message": f"{payload['linked_doctype']} '{linked_doc.name}' created and linked to '{parent_name}' successfully."
            }

        # ─── CASE 4: INSERT LINKED DOC WITH CHILD ROWS ────────
        elif operation == "insert_linked_child":
            frappe.has_permission(payload["linked_doctype"], "create", throw=True)

            # Get parent
            parent_name = frappe.db.get_value(
                payload["doctype"], payload["filters"], "name"
            )
            if not parent_name:
                return {"error": f"No {payload['doctype']} found for given filters"}

            # Create linked doc
            linked_doc = frappe.get_doc({
                "doctype": payload["linked_doctype"],
                **payload["data"]
            })

            # Auto append Dynamic Link
            linked_doc.append("links", {
                "link_doctype": payload["doctype"],
                "link_name": parent_name
            })

            # Append all child rows
            for child_table, rows in payload.get("child_rows", {}).items():
                for row in rows:
                    linked_doc.append(child_table, row)

            linked_doc.insert(ignore_permissions=False)

            # Update link field on parent if specified
            if payload.get("link_via"):
                parent_doc = frappe.get_doc(payload["doctype"], parent_name)
                parent_doc.set(payload["link_via"], linked_doc.name)
                parent_doc.save(ignore_permissions=False)
            update_masterdata()
            
            return {
                "success": True,
                "operation": "insert_linked_child",
                "linked_name": linked_doc.name,
                "parent": parent_name,
                "message": f"{payload['linked_doctype']} '{linked_doc.name}' created with child rows and linked to '{parent_name}' successfully."
            }

        # ─── CASE 5: INSERT BULK MAIN DOCS ────────────────────
        elif operation == "insert_bulk":
            frappe.has_permission(payload["doctype"], "create", throw=True)

            if len(payload["records"]) > 50:
                return {
                    "error": f"Too many records ({len(payload['records'])}). Maximum allowed is 50 records per bulk insert."
                }

            inserted = []
            failed = []

            for record in payload["records"]:
                try:
                    _validate_linked_fields(payload["doctype"], record)
                    doc = frappe.get_doc({
                        "doctype": payload["doctype"],
                        **record
                    })
                    doc.insert(ignore_permissions=False)
                    inserted.append(doc.name)
                except Exception as e:
                    failed.append({
                        "record": record,
                        "error": str(e)
                    })
            update_masterdata()
            return {
                "success": True,
                "operation": "insert_bulk",
                "inserted": len(inserted),
                "inserted_names": inserted,
                "failed": len(failed),
                "failed_records": failed,
                "message": f"{len(inserted)} record(s) inserted successfully. {len(failed)} failed."
            }

        # ─── CASE 6: INSERT IF NOT EXISTS ─────────────────────
        elif operation == "insert_if_not_exists":
            frappe.has_permission(payload["doctype"], "create", throw=True)

            # Check if already exists
            exists = frappe.db.exists(payload["doctype"], payload["filters"])
            if exists:
                return {
                    "success": False,
                    "operation": "insert_if_not_exists",
                    "name": exists,
                    "message": f"{payload['doctype']} already exists with name '{exists}'. No record created."
                }

            _validate_linked_fields(payload["doctype"], payload["data"])
            doc = frappe.get_doc({
                "doctype": payload["doctype"],
                **payload["data"]
            })
            doc.insert(ignore_permissions=False)
            update_masterdata()
            return {
                "success": True,
                "operation": "insert_if_not_exists",
                "name": doc.name,
                "message": f"{doc.doctype} '{doc.name}' created successfully."
            }

        else:
            return {"error": f"Unknown insert operation: '{operation}'"}

    except frappe.PermissionError:
        return {
            "error": f"User {frappe.session.user} does not have permission to create {payload.get('doctype')}. Please contact your administrator."
        }

    except frappe.exceptions.ValidationError as e:
        import re
        clean_msg = re.sub(r'<[^>]+>', '', str(e))
        return {"error": clean_msg}

    except frappe.exceptions.DuplicateEntryError as e:
        return {"error": f"Record already exists: {str(e)}"}

    except frappe.exceptions.DoesNotExistError as e:
        return {"error": f"Record not found: {str(e)}"}

    except PermissionError:
        return {
            "error": f"User {frappe.session.user} does not have permission to create {payload.get('doctype')}."
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "execute_insert Failed")
        return {"error": f"Insert Failed: {str(e)}\n Check Quick Start Guide Here 👇:\n {CHANGAI_GUIDE_LINK}"}

def _validate_linked_fields(doctype: str, data: dict):
    """Validate all Link fields exist before insert"""
    meta = frappe.get_meta(doctype)
    for field in meta.fields:
        if field.fieldtype == "Link" and field.fieldname in data:
            value = data[field.fieldname]
            if value and not frappe.db.exists(field.options, value):
                frappe.throw(
                    f"'{value}' does not exist in {field.options}. Please create it first."
                )

def _auto_create_linked(payload: dict, parent_name: str, parent_doc) -> dict:
    try:
        frappe.has_permission(payload["linked_doctype"], "create", throw=True)

        linked_doc = frappe.new_doc(payload["linked_doctype"])

        # ✅ Get child table fieldnames from meta
        meta = frappe.get_meta(payload["linked_doctype"])
        child_fieldnames = {
            f.fieldname for f in meta.fields
            if f.fieldtype in ("Table", "Table MultiSelect")
        }

        # ✅ Set direct fields on linked doc
        for field, value in payload.get("data", {}).items():
            if field not in child_fieldnames:
                linked_doc.set(field, value)

        # ✅ Append child table rows from payload child_rows
        for child_table, rows in payload.get("child_rows", {}).items():
            for row in rows:
                linked_doc.append(child_table, row)

        # ✅ Try to set minimum required name fields from parent
        if hasattr(linked_doc, "first_name") and not linked_doc.first_name:
            name_parts = parent_name.strip().split(" ", 1)
            linked_doc.first_name = name_parts[0]
            if hasattr(linked_doc, "last_name"):
                linked_doc.last_name = name_parts[1] if len(name_parts) > 1 else ""

        if hasattr(linked_doc, "address_title") and not linked_doc.address_title:
            linked_doc.address_title = parent_name

        linked_doc.append("links", {
            "link_doctype": payload["doctype"],
            "link_name": parent_name
        })

        linked_doc.insert(ignore_permissions=False)

        # ✅ Update link field on parent
        if payload.get("link_via"):
            parent_doc.set(payload["link_via"], linked_doc.name)
            parent_doc.save(ignore_permissions=False)

        return {
            "success": True,
            "linked_name": linked_doc.name,
            "auto_created": True
        }

    except frappe.exceptions.ValidationError as e:
        clean_msg = re.sub(r'<[^>]+>', '', str(e))
        return {"error": f"Could not auto create {payload['linked_doctype']}. {clean_msg}"}

    except Exception as e:
        return {"error": f"Could not auto create {payload['linked_doctype']} for {parent_name}: {str(e)}"}


def _resolve_child_filters(doc, child_table: str, child_filters: dict, data: dict) -> dict:
    """
    If child_filters only contains primary flags (value=1),
    find the current primary row and return its name as stable filter.
    If child_filters is empty, return empty dict (will append new row).
    """
    if not child_filters:
        return {}

    existing_rows = doc.get(child_table) or []
    if not existing_rows:
        return child_filters

    # ✅ Check if ALL filter values are primary-style (== 1)
    all_primary_flags = all(
        frappe.utils.cint(v) == 1
        for v in child_filters.values()
    )

    if not all_primary_flags:
        return child_filters

    # ✅ Find matching row NOW before unsetting
    for row in existing_rows:
        if all(
            frappe.utils.cint(getattr(row, k, 0)) == frappe.utils.cint(v)
            for k, v in child_filters.items()
        ):
            return {"name": row.name}

    # No match found — return original
    return child_filters


def _unset_primary_flags(doc, child_table: str, data: dict):
    """
    Dynamically detects and unsets primary flags before setting new primary.
    Works for ANY doctype, ANY child table, ANY primary flag.
    """
    if not data:
        return

    existing_rows = doc.get(child_table) or []
    if not existing_rows:
        return

    flags_to_unset = set()
    for field, value in data.items():
        if frappe.utils.cint(value) == 1:
            for row in existing_rows:
                if hasattr(row, field):
                    current_val = getattr(row, field, None)
                    if current_val is not None and str(current_val) in ("0", "1", "True", "False"):
                        flags_to_unset.add(field)
                        break

    if not flags_to_unset:
        return

    for row in existing_rows:
        for flag in flags_to_unset:
            if hasattr(row, flag):
                row.set(flag, 0)

@frappe.whitelist(allow_guest=False)
def execute_update(payload: dict):
    from changai.changai.api.v2.auto_gen_api import update_masterdata
    try:
        if isinstance(payload, str):
            payload = json.loads(payload)

        operation = payload.get("operation")

        # ─── MULTI PAYLOAD ─────────────────────────────────
        if operation == "multi_payload":
            results = []
            for sub_payload in payload.get("payloads", []):
                result = execute_update(sub_payload)
                results.append(result)

            failed = [r for r in results if r.get("error")]
            success = [r for r in results if r.get("success")]
            update_masterdata()
            return {
                "success": len(failed) == 0,
                "operation": "multi_payload",
                "total": len(results),
                "succeeded": len(success),
                "failed": len(failed),
                "results": results,
                "message": f"{len(success)} operation(s) succeeded. {len(failed)} failed."
            }

        # ─── UPDATE MAIN DOC ───────────────────────────────
        elif operation == "update":
            frappe.has_permission(payload["doctype"], "write", throw=True)

            filters = payload.get("filters", {})
            if not filters:
                return {"error": "Filters are required. Cannot update all records."}

            if not payload.get("data"):
                return {"error": "No data provided for update."}

            if payload.get("cross_filters"):
                cf = payload["cross_filters"]
                linked = frappe.get_all(
                    cf["doctype"],
                    filters=cf["filters"],
                    fields=["name"]
                )
                if not linked:
                    return {"error": f"No {cf['doctype']} records found"}
                filters[cf["link_field"]] = ["in", [d.name for d in linked]]

            records = frappe.get_all(
                payload["doctype"],
                filters=filters,
                fields=["name"]
            )

            if not records:
                return {"error": "No records found for given filters"}

            if len(records) > 50:
                return {"error": f"Too many records ({len(records)}) matched. Maximum allowed is 50."}

            for record in records:
                doc = frappe.get_doc(payload["doctype"], record.name)
                for field, value in payload["data"].items():
                    doc.set(field, value)
                doc.save(ignore_permissions=False)
            update_masterdata()
            return {
                "success": True,
                "operation": "update",
                "updated_count": len(records),
                "records": [r.name for r in records],
                "message": f"{len(records)} record(s) updated successfully."
            }

        # ─── UPDATE CHILD ──────────────────────────────────
        elif operation == "update_child":
            frappe.has_permission(payload["doctype"], "write", throw=True)

            if not payload.get("name"):
                return {"error": "Parent document name is required for update_child."}
            if not payload.get("child_table"):
                return {"error": "child_table is required for update_child."}
            if not payload.get("data"):
                return {"error": "No data provided for update_child."}

            if not frappe.db.exists(payload["doctype"], payload["name"]):
                return {"error": f"No {payload['doctype']} found with name '{payload['name']}'"}

            doc = frappe.get_doc(payload["doctype"], payload["name"])

            # ✅ Validate child_table exists via meta
            meta = frappe.get_meta(payload["doctype"])
            child_fields = [
                f.fieldname for f in meta.fields
                if f.fieldtype in ("Table", "Table MultiSelect")
            ]
            if payload["child_table"] not in child_fields:
                return {
                    "error": f"Child table '{payload['child_table']}' does not exist on {payload['doctype']}."
                }

            child_filters = payload.get("child_filters") or {}

            resolved_filters = _resolve_child_filters(
                doc,
                payload["child_table"],
                child_filters,
                payload["data"]
            )

            _unset_primary_flags(doc, payload["child_table"], payload["data"])

            updated = 0
            if resolved_filters:
                for row in doc.get(payload["child_table"]) or []:
                    if all(
                        getattr(row, k, None) == v
                        for k, v in resolved_filters.items()
                    ):
                        for field, value in payload["data"].items():
                            row.set(field, value)
                        updated += 1

            if updated == 0:
                doc.append(payload["child_table"], payload["data"])

            doc.save(ignore_permissions=False)
            update_masterdata()

            return {
                "success": True,
                "operation": "update_child",
                "updated_count": updated,
                "message": f"{updated} child row(s) updated successfully."
                    if updated > 0
                    else "No matching row found — new row added."
            }

        # ─── UPDATE LINKED / UPDATE LINKED CHILD ───────────
        elif operation in ("update_linked", "update_linked_child"):

            frappe.has_permission(payload["doctype"], "write", throw=True)

            if not payload.get("filters"):
                return {"error": "Filters are required for update_linked."}
            if not payload.get("linked_doctype"):
                return {"error": "linked_doctype is required for update_linked."}
            if operation == "update_linked" and not payload.get("data"):
                return {"error": "No data provided for update_linked."}
            if operation == "update_linked_child":
                frappe.has_permission(payload["linked_doctype"], "write", throw=True)
                if not payload.get("child_table"):
                    return {"error": "child_table is required for update_linked_child."}
                if not payload.get("data"):
                    return {"error": "No data provided for update_linked_child."}

            # ✅ Step 1 — Find parent
            parent_name = frappe.db.get_value(
                payload["doctype"],
                payload["filters"],
                "name"
            )
            if not parent_name:
                return {"error": f"No {payload['doctype']} found for given filters"}

            parent_doc = frappe.get_doc(payload["doctype"], parent_name)

            # ✅ Step 2 — Find linked doc via direct link field
            linked_name = None
            auto_created = False

            if payload.get("link_via"):
                linked_name = getattr(parent_doc, payload["link_via"], None)

            # ✅ Step 3 — Fallback to Dynamic Link
            if not linked_name:
                linked_name = frappe.db.get_value(
                    "Dynamic Link",
                    {
                        "link_doctype": payload["doctype"],
                        "link_name": parent_name,
                        "parenttype": payload["linked_doctype"]
                    },
                    "parent"
                )

            # ✅ Step 4 — Auto create if not found
            if not linked_name:
                auto_result = _auto_create_linked(payload, parent_name, parent_doc)
                if auto_result.get("error"):
                    return auto_result
                linked_name = auto_result.get("linked_name")
                auto_created = auto_result.get("auto_created", False)

            # ✅ Step 5 — Load linked doc
            linked_doc = frappe.get_doc(payload["linked_doctype"], linked_name)

            # ─── UPDATE LINKED CHILD ───────────────────────
            if operation == "update_linked_child":

                # ✅ Validate child_table via meta
                meta = frappe.get_meta(payload["linked_doctype"])
                child_fields = [
                    f.fieldname for f in meta.fields
                    if f.fieldtype in ("Table", "Table MultiSelect")
                ]
                if payload["child_table"] not in child_fields:
                    return {
                        "error": f"Child table '{payload['child_table']}' does not exist on {payload['linked_doctype']}."
                    }

                child_filters = payload.get("child_filters") or {}

                resolved_filters = _resolve_child_filters(
                    linked_doc,
                    payload["child_table"],
                    child_filters,
                    payload["data"]
                )

                _unset_primary_flags(
                    linked_doc,
                    payload["child_table"],
                    payload["data"]
                )

                updated = 0
                if resolved_filters:
                    for row in linked_doc.get(payload["child_table"]) or []:
                        if all(
                            getattr(row, k, None) == v
                            for k, v in resolved_filters.items()
                        ):
                            for field, value in payload["data"].items():
                                row.set(field, value)
                            updated += 1

                if updated == 0:
                    linked_doc.append(payload["child_table"], payload["data"])

                linked_doc.save(ignore_permissions=False)
                update_masterdata()

                return {
                    "success": True,
                    "operation": operation,
                    "linked_doc": linked_name,
                    "auto_created": auto_created,
                    "message": f"{payload['linked_doctype']} updated successfully."
                        if updated > 0
                        else f"No matching row — new row added to {payload['child_table']}."
                }

            # ─── UPDATE LINKED DIRECT FIELD ───────────────
            else:
                frappe.has_permission(payload["linked_doctype"], "write", throw=True)
                for field, value in payload["data"].items():
                    linked_doc.set(field, value)
                linked_doc.save(ignore_permissions=False)
                update_masterdata()

                return {
                    "success": True,
                    "operation": operation,
                    "linked_doc": linked_name,
                    "auto_created": auto_created,
                    "message": f"{payload['linked_doctype']} updated successfully."
                }

        return {"error": f"Unsupported update operation: {operation}"}

    except frappe.PermissionError:
        return {
            "error": f"User {frappe.session.user} does not have permission to update {payload.get('doctype')}. Please contact your administrator."
        }

    except frappe.exceptions.ValidationError as e:
        clean_msg = re.sub(r'<[^>]+>', '', str(e))
        return {"error": clean_msg}

    except frappe.exceptions.DuplicateEntryError as e:
        return {"error": f"Record already exists: {str(e)}"}

    except frappe.exceptions.DoesNotExistError as e:
        return {"error": f"Record not found: {str(e)}"}

    except PermissionError:
        return {
            "error": f"User {frappe.session.user} does not have permission to update {payload.get('doctype')}."
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "execute_update Failed")
        return {"error": f"Update Failed: {str(e)}\n Check Quick Start Guide Here 👇:\n {CHANGAI_GUIDE_LINK}"}

        
@frappe.whitelist(allow_guest=False)
def execute_delete(payload:dict):
    from changai.changai.api.v2.auto_gen_api import update_masterdata
    try:
        if isinstance(payload, str):
            payload = json.loads(payload)

        operation = payload.get("operation")

        # ─── DELETE MAIN DOC ───────────────────────────────
        if operation == "delete":
            frappe.has_permission(
                payload["doctype"],
                "delete",
                throw=True
            )

            records = frappe.get_all(
                payload["doctype"],
                filters=payload["filters"],
                fields=["name"]
            )

            if not records:
                return {"error": "No records found"}

            if len(records) > 50:
                return {
                    "error": f"Too many records ({len(records)}) matched. Maximum allowed is 50."
                }

            deleted = []

            for record in records:
                frappe.delete_doc(
                    payload["doctype"],
                    record.name,
                    ignore_permissions=False
                )
                deleted.append(record.name)

            
            update_masterdata()
            
            return {
                "success": True,
                "operation": "delete",
                "deleted_count": len(deleted),
                "records": deleted,
                "message": f"{len(deleted)} record(s) deleted successfully."
            }

        # ─── DELETE CHILD ROW ──────────────────────────────
        elif operation == "delete_child":
            frappe.has_permission(payload["doctype"], "delete", throw=True)
            frappe.has_permission(
                payload["doctype"],
                "write",
                throw=True
            )

            doc = frappe.get_doc(
                payload["doctype"],
                payload["name"]
            )

            before = len(doc.get(payload["child_table"]))

            doc.set(
                payload["child_table"],
                [
                    row for row in doc.get(payload["child_table"])
                    if not all(
                        getattr(row, k) == v
                        for k, v in payload["child_filters"].items()
                    )
                ]
            )

            deleted = before - len(doc.get(payload["child_table"]))

            doc.save(ignore_permissions=False)
            update_masterdata()
            return {
                "success": True,
                "operation": "delete_child",
                "deleted_count": deleted,
                "message": f"{deleted} child row(s) deleted successfully."
            }

        # ─── DELETE LINKED / LINKED CHILD ──────────────────
        elif operation in ("delete_linked", "delete_linked_child"):
            frappe.has_permission(payload["doctype"], "delete", throw=True)

            parent_name = frappe.db.get_value(
                payload["doctype"],
                payload["filters"],
                "name"
            )

            if not parent_name:
                return {
                    "error": f"No {payload['doctype']} found"
                }

            parent_doc = frappe.get_doc(
                payload["doctype"],
                parent_name
            )

            linked_name = None

            if payload.get("link_via"):
                linked_name = getattr(
                    parent_doc,
                    payload["link_via"],
                    None
                )

            if not linked_name:
                linked_name = frappe.db.get_value(
                    "Dynamic Link",
                    {
                        "link_doctype": payload["doctype"],
                        "link_name": parent_name,
                        "parenttype": payload["linked_doctype"]
                    },
                    "parent"
                )

            if not linked_name:
                return {
                    "error": f"No linked {payload['linked_doctype']} found"
                }
            required_perm = "delete" if operation == "delete_linked" else "write"
            frappe.has_permission(payload["linked_doctype"], required_perm, throw=True)
            linked_doc = frappe.get_doc(
                payload["linked_doctype"],
                linked_name
            )

            # delete_linked_child
            if operation == "delete_linked_child":

                before = len(
                    linked_doc.get(payload["child_table"])
                )

                linked_doc.set(
                    payload["child_table"],
                    [
                        row for row in linked_doc.get(payload["child_table"])
                        if not all(
                            getattr(row, k) == v
                            for k, v in payload["child_filters"].items()
                        )
                    ]
                )

                deleted = (
                    before -
                    len(linked_doc.get(payload["child_table"]))
                )

                linked_doc.save(ignore_permissions=False)
                update_masterdata()
                return {
                    "success": True,
                    "operation": "delete_linked_child",
                    "linked_doc": linked_name,
                    "deleted_count": deleted,
                    "message": f"{deleted} linked child row(s) deleted successfully."
                }

            # delete_linked
            if payload.get("link_via"):
                parent_doc.set(payload["link_via"], None)
                parent_doc.save(ignore_permissions=False)

            frappe.delete_doc(
                payload["linked_doctype"],
                linked_name,
                ignore_permissions=False
            )

            
            update_masterdata()
            return {
                "success": True,
                "operation": "delete_linked",
                "linked_doc": linked_name,
                "message": f"{payload['linked_doctype']} '{linked_name}' deleted successfully."
            }

        return {
            "error": f"Unsupported delete operation: {operation}"
        }
    except frappe.PermissionError:
        return {"error": f"User {frappe.session.user} does not have permission to perform this action on {payload.get('doctype')}."}

    except frappe.exceptions.ValidationError as e:
        clean_msg = re.sub(r'<[^>]+>', '', str(e))
        return {"error": clean_msg}

    except frappe.exceptions.DuplicateEntryError as e:
        return {"error": f"Record already exists: {str(e)}"}

    except frappe.exceptions.DoesNotExistError as e:
        return {"error": f"Record not found: {str(e)}"}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "execute Failed")
        return {"error": str(e)}