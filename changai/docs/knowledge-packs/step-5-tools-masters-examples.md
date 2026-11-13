# Step 5: Tools, actions, masters and examples

## Tools

If your app already has a function that calculates something correctly, register it. changAI calls the function, so the answer matches what your app shows on screen.

```yaml
tools:
  - function: tenant_app.api.get_tenant_balance
    description: "Outstanding balance for a tenant: rent, service charges, penalties; excludes deposit."
    parameters:
      tenant:     {type: Link, options: Customer, required: true}
      unit:       {type: Link, options: Location}
      as_of_date: {type: Date}
    read_only: true
    permission_reviewed: true
```

A function qualifies only if all of these are true:

- It reads and never writes, sends or calls an outside service.
- It checks the caller's permissions itself (`frappe.has_permission`, or it reads through `frappe.get_list`).
- Its inputs are simple values: names, dates, numbers.
- It returns data, not HTML.

If your app has no such function, write `tools: []`.

## Actions not exposed

List whitelisted functions that change data or call outside services. This records that you looked at them and decided they are not available to the AI.

```yaml
actions_not_exposed:
  - zatca_erpgulf.zatca_erpgulf.sign_invoice.resubmit_invoices
  - zatca_erpgulf.zatca_erpgulf.sign_invoice_first.create_csid
```

## Masters

If your app adds records that users refer to by name (units, vehicles, machines, properties), list them so changAI can find them despite typos.

```yaml
masters:
  - doctype: Location
    fields: [location_name]
    roles: [unit, tower, floor, building]     # words users use for this kind of record
    tree: true                                # a parent includes its children
  - doctype: Customer
    extra_fields: [zatca_customer_name_in_arabic]   # also index this name field
```

List only name-like fields. Never list fields from `never_send`, phone numbers or addresses.

## Examples

Write 10 to 20 questions real users would ask, each with the call that answers it. Replace names and periods with slots in braces. These seed changAI's examples and its test set.

```yaml
examples:
  - question: "How many invoices are not submitted to ZATCA this month?"
    tool: "get_metric(Invoices Not Submitted to ZATCA, period=this_month)"
  - question: "What is the ZATCA status of invoice {invoice}?"
    tool: "query_doctype(Sales Invoice, filters: name={invoice}, fields: custom_zatca_status, custom_uuid)"
  - question: "Which invoices had ZATCA warnings {period}?"
    tool: "run_report(ZATCA Sales Invoices with warnings, from_date, to_date)"
  - question: "كم فاتورة لم ترسل إلى الزكاة هذا الشهر؟"
    tool: "get_metric(Invoices Not Submitted to ZATCA, period=this_month)"
```

The calls available are `get_metric`, `run_report`, `query_doctype` and your registered tools. Cover each metric and report at least once, include a "why" question, and include questions in every language your users type.

## Review notes

End with what you were unsure about. A reviewer reads this first.

```yaml
review_notes:
  - "'Not Submitted' is both the default and the value written after a failed attempt."
  - "All five reports read with frappe.db.sql; company is optional in four of them."
```

[Previous: Step 4: Words, metrics and reports](step-4-words-metrics-reports.md) · [Contents](README.md) · [Next: Drafting with an AI tool](drafting-with-ai.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
