# The sample app: zatca_erpgulf

Every example in this guide comes from [zatca_erpgulf](https://github.com/ERPGulf/zatca_erpgulf), ERPGulf's open-source app for Saudi e-invoicing (ZATCA Phase 1 and Phase 2) on ERPNext. It is used here as a worked sample: a complete draft pack was written for it, and each step shows the part of that pack it produced.

The app sends submitted Sales Invoices and POS Invoices to ZATCA and records the result on the invoice. It adds no new business documents; it extends standard ones.

| What the app contains | Count | Where it shows up in the pack |
| --- | --- | --- |
| Custom fields on 13 doctypes (Company 55, Sales Invoice 31, POS Invoice 17, Purchase Invoice 10, others) | 155 | `doctypes`, `never_send` |
| Its own doctypes (settings and logs) | 5 | `app_doctypes` |
| Values of the ZATCA status field, found only in the code | 6 | `status_field` |
| Number cards and dashboard charts | 24 + 10 | `metrics` |
| Script reports | 5 | `reports` |
| Scheduler job (every 30 minutes) and submit hooks | 1 + 4 | `flow` |
| Whitelisted functions, all of which write data or call ZATCA | about 20 | `actions_not_exposed` |
| Python code | about 19,000 lines | Read once to write the pack, never sent to an AI |

It is a useful sample because it has the three things an AI cannot work out by itself:

- **Meaning that lives only in code.** The status is a plain text field. Its six values, and the fact that "Not Submitted" also covers failed attempts, appear nowhere in the field definition.
- **Secrets.** Settings hold private keys, certificates, OTPs and auth tokens: more than 30 fields that must never leave the server.
- **Reports that read with SQL.** All five need a permission review before an assistant may run them.

The resulting draft pack has 12 metrics, 5 reports, 13 example questions and 10 notes for the reviewer. It was written from the public repository at commit `ba0a088` (26 October 2026) and is a draft until a consultant reviews it. Your installed version may differ; changAI always checks a pack against the installed app.

The full file is on the [Sample pack: zatca_erpgulf](sample-pack-zatca-erpgulf.md) page.

[Contents](README.md) · [Next: Before you start, and file structure](getting-started.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
