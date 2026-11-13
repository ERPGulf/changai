# Step 1: Overview, flow and topics

These three sections are what the AI sees first, so write them for someone who has never heard of your app.

**`overview`**: what the app does, which standard doctypes it touches, and what it does not do. Three to five sentences, no marketing.

```yaml
overview: >
  Saudi e-invoicing (ZATCA Phase 1 and Phase 2) for ERPNext. When a Sales Invoice or
  POS Invoice is submitted for a Saudi company, the app builds the e-invoice XML, signs
  it, sends it to ZATCA and stores the result on the invoice. Standard (B2B) invoices are
  cleared by ZATCA; simplified (B2C) invoices are reported. The app adds fields to
  Sales Invoice, POS Invoice, Purchase Invoice, Customer and Company, plus log doctypes.
```

**`flow`**: the life of a document, as short steps in order. Read `doc_events` and `scheduler_events` in `hooks.py`: they show what happens on submit, on cancel and on a schedule.

```yaml
flow:
  - "Customer is marked B2C or not (Customer.custom_b2c). The invoice copies it."
  - "Sales Invoice or POS Invoice is submitted."
  - "The app sends it to ZATCA: immediately, or later by a scheduler every 30 minutes."
  - "ZATCA's answer is written to custom_zatca_status and custom_uuid on the invoice."
  - "Failed or unsent invoices are retried by the scheduler or resubmitted by a user."

applies_when: "Company country is Saudi Arabia and ZATCA is enabled on the Company."
```

**`topics`**: short names for the areas your pack covers. changAI shows these to the AI as a menu; the AI asks for a topic by name when a question needs it. Each topic lists the pack sections it returns.

```yaml
topics:
  status values:   [status_field]
  invoice types:   [doctypes.Sales Invoice.custom_b2c, doctypes.Customer.custom_b2c]
  tax categories:  [doctypes.Sales Invoice.custom_zatca_tax_category, doctypes.Item Tax Template]
  credit notes:    [doctypes.Sales Invoice.custom_credit_note_reasoninstruction_note]
  settings:        [doctypes.Company]
  logs:            [app_doctypes]
  flow:            [flow]
```

Keep topic names to one or two plain words. Five to ten topics is typical.

[Previous: Before you start, and file structure](getting-started.md) · [Contents](README.md) · [Next: Step 2: Status values, fields and doctypes](step-2-status-fields-doctypes.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
