# Step 4: Words, metrics and reports

## Words

Map what users say to what it means in your data. Include the languages your users type in, and the informal words ("stuck", "pending").

```yaml
words:
  "zatca status, e-invoice status, حالة الزكاة":          "Sales Invoice.custom_zatca_status"
  "not submitted, pending zatca, failed, stuck":         "custom_zatca_status in (Not Submitted, 503 Service Unavailable)"
  "b2b, standard invoice, tax invoice, فاتورة ضريبية":   "custom_b2c = 0"
  "b2c, simplified invoice, فاتورة مبسطة":               "custom_b2c = 1"
  "credit note, return, إشعار دائن":                     "is_return = 1"
```

Ask support staff which words clients actually use. Have a native speaker write the non-English terms.

## Metrics

A metric is a business number with fixed rules. The AI picks the metric and the period; the server applies the rules. Start from what your app already shows: number cards and dashboard charts are ready-made definitions.

```yaml
metrics:
  - name: VAT Reported to ZATCA
    value: sum(base_total_taxes_and_charges)
    fixed_filters: [[docstatus, "=", 1], [custom_zatca_status, "in", [CLEARED, REPORTED]]]
  - name: Invoices Not Submitted to ZATCA
    value: count
    fixed_filters: [[docstatus, "=", 1], [custom_zatca_status, "=", "Not Submitted"]]

metric_defaults:
  source: Sales Invoice
  date_field: posting_date
  dimensions: [company, customer, custom_zatca_status, custom_b2c, cost_center]
```

| Rule | Why |
| --- | --- |
| Always decide on `docstatus` | Drafts and cancelled documents change totals |
| Use company-currency fields (`base_...`) for amounts | Totals across currencies are otherwise wrong |
| Give each metric a name a user would say | The AI chooses by name |
| Define close variants as separate metrics (gross, net, reported) | The AI must not choose the rule |
| List `dimensions` users can group or filter by | Anything not listed is refused |

## Reports

List the reports changAI may run, with filters and columns. Script and Query reports define filters in JavaScript, which the server cannot read reliably, so write them here.

```yaml
reports:
  - report: Zatca Status Report
    use_for: "Sales invoices with their ZATCA status for a company and date range."
    roles: [Accounts Manager, Accounts User, Sales User]
    filters:
      company: {type: Link, options: Company, required: true}
      dt_from: {type: Date}
      dt_to:   {type: Date}
      status:  {type: Select, options: [Reported, Cleared, Not Submitted]}
    columns: [name, posting_date, customer_name, grand_total, custom_zatca_status]
    permission_reviewed: false
```

Set `permission_reviewed: true` only after checking how the report reads data:

| Report type | Check |
| --- | --- |
| Report Builder | Uses Frappe's list query; user permissions apply. Safe once described. |
| Script Report using `frappe.get_list` | User permissions apply. Confirm no `ignore_permissions`. |
| Script Report using `frappe.db.sql` or `frappe.get_all` | No user permissions. The code must filter by company and respect user restrictions itself. |
| Query Report | Only what the SQL enforces. Usually needs a company filter added. |

A report that is not reviewed stays in the pack but is not offered to users. Review correctness too: changAI repeats a report's mistakes with confidence.

[Previous: Step 3: The never-send list](step-3-never-send.md) · [Contents](README.md) · [Next: Step 5: Tools, actions, masters and examples](step-5-tools-masters-examples.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
