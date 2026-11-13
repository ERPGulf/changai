# Step 2: Status values, fields and doctypes

This is where most of the value is: the meanings that exist only in your code.

## Status values

If a status is stored in a Data field, its values are not in the field definition. Search the code for every place the field is set or compared, and list every value.

```bash
grep -rn "custom_zatca_status" --include=*.py --include=*.js --include=*.json .
```

Check dashboards and report filters too; they sometimes use values the main code path does not.

```yaml
status_field:
  doctypes: [Sales Invoice, POS Invoice]
  fieldname: custom_zatca_status
  default: "Not Submitted"
  values:
    "Not Submitted": "Not yet accepted: not sent, waiting for the background job, or the last attempt failed."
    "REPORTED": "Simplified (B2C) invoice reported to ZATCA successfully."
    "CLEARED": "Standard (B2B) invoice cleared by ZATCA successfully."
    "503 Service Unavailable": "ZATCA's server was unavailable; the scheduler retries these."
    "Intra-company transfer": "Company tax ID equals customer tax ID; not sent to ZATCA."
  groups:
    accepted_by_zatca: ["REPORTED", "CLEARED"]
    pending_or_failed: ["Not Submitted", "503 Service Unavailable"]
  notes:
    - "Values are stored in upper case for REPORTED and CLEARED."
```

`groups` matter: users say "pending" or "sent", not the exact value. Write the value exactly as stored, including case.

## Fields you add to standard doctypes

List fields from your fixtures (`custom_field.json`) or `get_meta`. For each, write one line a new team member would need.

```yaml
doctypes:
  Sales Invoice:
    use_for: "ZATCA status of invoices and credit notes; B2B vs B2C split; tax category."
    fields:
      custom_b2c: "1 = simplified (B2C) invoice, 0 = standard (B2B). Copied from the customer, read-only."
      custom_uuid: "UUID sent to ZATCA. Default text 'Not submitted' until sent."
      custom_zatca_full_response: "Raw response from ZATCA, including warnings and errors."
      custom_zatca_pmm: "1 = Profit Margin Method invoice. The app skips ZATCA submission for these."
    related_standard_fields:
      is_return: "1 = credit note."
      base_net_total: "Sales amount before VAT, company currency."
```

| Describe | Skip |
| --- | --- |
| What the value means in business terms | Section Break, Column Break, HTML and Button fields |
| Where the value comes from (`fetch_from`, set by code, typed by the user) | Field type and options: changAI reads those live |
| Defaults that look like data ("Not submitted") | Long option lists |
| Side effects ("the app skips submission when this is 1") | Fields that only control the form layout |
| Standard fields your app relies on (`related_standard_fields`) | Anything in `never_send` |

## Your own doctypes

Say what each is for, what it is not for, and who can read it.

```yaml
app_doctypes:
  ZATCA ERPGulf Success Log:
    use_for: "One row per invoice accepted by ZATCA: invoice_number, uuid, time, zatca_response."
    not_for: "Counting accepted invoices (use Sales Invoice.custom_zatca_status)."
    permissions: "System Manager only."
```

`not_for` prevents the most common mistake: the AI picking a log or settings doctype when the answer is on the main document.

[Previous: Step 1: Overview, flow and topics](step-1-overview-flow-topics.md) · [Contents](README.md) · [Next: Step 3: The never-send list](step-3-never-send.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
