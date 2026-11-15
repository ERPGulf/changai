# The sample app: einvoice_erpgulf

The second sample is [einvoice_erpgulf](https://github.com/ERPGulf/einvoice_erpgulf), ERPGulf's open-source e-invoicing app for countries where invoices reach the tax authority through a provider the taxpayer chooses: a Peppol access point or an accredited service provider. The United Arab Emirates, Oman and Belgium are included. A complete draft pack was written for it too.

The app sends submitted Sales Invoices and self-billed Purchase Invoices to the Company's provider, records the result on the invoice, and receives supplier invoices arriving through the same channel. Like the first sample, it adds no new business documents; it extends standard ones.

| What the app contains | Count | Where it shows up in the pack |
| --- | --- | --- |
| Custom fields on 12 doctypes (Sales Invoice 27, Purchase Invoice 25, Company 8, Customer 6, Supplier 6, others) | 91 | `doctypes`, `never_send` |
| Its own doctypes (provider settings, two logs, incoming invoices) | 4 | `app_doctypes`, `never_send` |
| Status fields, with values found only in the code | 2 fields, 2 + 5 values | `status_fields` |
| Dashboard cards, for sales and for purchases | 5 + 5 | `metrics` |
| Script reports | 2 | `reports` |
| Scheduler jobs (every minute and every 5 minutes) and document hooks | 2 + 7 | `flow` |
| Countries, and providers across them | 3 and 6 | `overview`, field notes marked "Oman only" |
| Whitelisted functions, all of which write data, call the provider or receive webhooks | about 30 | `actions_not_exposed` |
| Python code | about 12,000 lines | Read once to write the pack, never sent to an AI |

It is a useful second sample because it needs things the first one does not:

| Feature of the app | How the pack handles it |
| --- | --- |
| **Two status fields.** E-Invoice Status says whether the provider accepted the invoice; Reporting Status says what the tax authority answered | `status_fields`, a list, with a `meaning` line and its own `groups` for each field |
| **Both sales and purchases.** Sales Invoices and self-billed Purchase Invoices carry the same fields | One `doctypes` entry for each; metrics with their own `source` |
| **Several countries in one app.** Some fields exist only for Oman or Belgium | Field notes start with "Oman only"; changAI skips fields that are not installed on a site |
| **Credentials in a settings doctype.** Each company has a provider settings record with secrets and tokens | `never_send` lists 17 fields on that doctype, including stored tokens and raw connection replies |
| **A field that can hold personal data.** A party's registration number may be an Emirates ID or passport number | Listed under `never_send`, with a review note on how to relax it |
| **Incoming documents.** Supplier invoices arrive through the provider | An `app_doctypes` entry, a word mapping and an example question |
| **A rule about cancelling.** Reported invoices cannot be cancelled | Written as a step in `flow` and offered as the topic "cancelling" |

What reading the code showed:

- Reporting Status is written in lower case (`pending`, `reported`, `failed`), while E-Invoice Status is written as `Success` and `Not Submitted`. The pack copies each exactly.
- "Not Submitted" covers three situations: never sent, rejected by the provider, and provider unreachable.
- The Document ID field holds the text "Not Submitted" until the invoice is sent, so "has a document ID" cannot be tested as "is not empty".
- A scheduler checks pending invoices every five minutes and looks back seven days; webhooks update statuses sooner.

The resulting draft pack has 8 metrics, 2 reports, 15 example questions and 14 notes for the reviewer. It was written from the public repository at commit `6a4d666` (13 November 2026) and is a draft until a consultant reviews it. Your installed version may differ; changAI always checks a pack against the installed app.

The full file is on the [Sample pack: einvoice_erpgulf](sample-pack-einvoice-erpgulf.md) page.

[Previous: Sample pack: zatca_erpgulf](sample-pack-zatca-erpgulf.md) · [Contents](README.md) · [Next: Sample pack: einvoice_erpgulf](sample-pack-einvoice-erpgulf.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
