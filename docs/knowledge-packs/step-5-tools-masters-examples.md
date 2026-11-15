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

A master is any record users refer to by name: a unit, a vehicle, a machine, a property. List each one so changAI can find it despite typos, and knows which documents it filters.

```yaml
masters:
  - doctype: Property Unit
    title_field: unit_name                    # the readable name shown to the user
    fields: [unit_name, unit_no]              # what to index for lookup
    roles: [unit, flat, apartment, shop]      # words users use for this kind of record
    parent: {doctype: Building, field: building}   # "units in Tower B"
    active_filter: [[disabled, "=", 0]]
    linked_from:                              # documents that point to this master
      - {doctype: Lease, field: unit}
      - {doctype: Maintenance Request, field: unit}

  - doctype: Location
    title_field: location_name
    fields: [location_name]
    roles: [building, tower, floor]
    tree: true                                # a parent includes its children

  - doctype: Customer
    extra_fields: [zatca_customer_name_in_arabic]   # also index this name field
```

| Key | Purpose | Required |
| --- | --- | --- |
| `doctype` | The master's doctype | Yes |
| `fields` | Name-like fields to index. Codes (unit numbers, plate numbers) are matched exactly | Yes, unless only `extra_fields` |
| `title_field` | The readable name, when the document name is a code such as `UNIT-00123` | Recommended |
| `roles` | Everyday words for this kind of record, in every language users type | Recommended |
| `linked_from` | Documents that point to this master, and through which field. Lets changAI filter those documents by it | Recommended |
| `parent` | The doctype and field a record belongs to, so a parent can stand for its children | If records nest |
| `tree` | `true` for tree doctypes; a node includes its descendants | If a tree |
| `active_filter` | Which records count as current | Optional |
| `extra_fields` | Extra name fields your app adds to a master that is already indexed (for example an Arabic name on Customer) | Optional |

Rules:

- List only name-like fields. Never list fields from `never_send`, phone numbers, addresses or ID numbers.
- A fixed list of values (a Select field such as unit type) is not a master. Describe it in the field notes and under `words`.
- For very large masters, such as serial numbers, index only the code field.
- Records stay in your app's own tables. changAI stores only words and a pointer to each record, in its own index.

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
