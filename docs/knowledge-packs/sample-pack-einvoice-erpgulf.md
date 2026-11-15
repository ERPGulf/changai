# Sample pack: einvoice_erpgulf

A second complete draft knowledge pack, for [einvoice_erpgulf](https://github.com/ERPGulf/einvoice_erpgulf), ERPGulf's open-source e-invoicing app for countries where invoices reach the tax authority through a provider the taxpayer chooses (United Arab Emirates, Oman, Belgium). It was written from the public repository at commit `6a4d666` (13 November 2026).

**Status: Draft.** It has not yet been reviewed by a consultant; see `review_notes` at the end of the file for the open points.

The file: [`examples/einvoice_erpgulf_knowledge_pack.yaml`](examples/einvoice_erpgulf_knowledge_pack.yaml)

## What this sample shows that the first one does not

| Feature of the app | How the pack handles it |
| --- | --- |
| **Two status fields.** E-Invoice Status says whether the provider accepted the invoice; Reporting Status says what the tax authority answered | `status_fields`, a list, with a `meaning` line and its own `groups` for each field |
| **Both sales and purchases.** Sales Invoices and self-billed Purchase Invoices carry the same fields | One `doctypes` entry for each; metrics with their own `source` |
| **Several countries in one app.** Some fields exist only for Oman or Belgium | Field notes start with "Oman only"; changAI skips fields that are not installed on a site |
| **Credentials in a settings doctype.** Each company has a provider settings record with secrets and tokens | `never_send` lists 17 fields on that doctype, including stored tokens and raw connection replies |
| **A field that can hold personal data.** A party's registration number may be an Emirates ID or passport number | Listed under `never_send`, with a review note on how to relax it |
| **Incoming documents.** Supplier invoices arrive through the provider | An `app_doctypes` entry, a word mapping and an example question |
| **A rule about cancelling.** Reported invoices cannot be cancelled | Written as a step in `flow` and offered as the topic "cancelling" |

## Contents of the pack

| Section | Content |
| --- | --- |
| `topics` | 11 topics, from status values to Oman |
| `status_fields` | 2 fields: 2 values and 5 values, each with groups |
| `doctypes` | Notes on 76 fields across 11 standard doctypes |
| `app_doctypes` | The app's 4 doctypes |
| `never_send` | 24 fields |
| `words` | 14 entries, English and Arabic |
| `metrics` | 8 counts, copied from the app's dashboard cards, for sales and purchases |
| `reports` | 2 script reports, not yet permission-reviewed |
| `examples` | 15 questions with the expected call |
| `review_notes` | 14 open points for the reviewer |

## What the code showed

- Reporting Status is written in lower case (`pending`, `reported`, `failed`), while E-Invoice Status is written as `Success` and `Not Submitted`. The pack copies each exactly.
- "Not Submitted" covers three situations: never sent, rejected by the provider, and provider unreachable.
- The Document ID field holds the text "Not Submitted" until the invoice is sent, so "has a document ID" cannot be tested as "is not empty".
- A scheduler checks pending invoices every five minutes and looks back seven days; webhooks update statuses sooner.

[Previous: Sample pack: zatca_erpgulf](sample-pack-zatca-erpgulf.md) · [Contents](README.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
