# Before you start, and file structure

## Before you start

You need four things:

- **The app's code**, including fixtures, `hooks.py`, reports and dashboards.
- **A development site with the app installed**, so you can check field names and try queries.
- **Someone who knows the business**: a functional consultant or the product owner, for the review.
- **About half a day** for a medium app, most of it reading and checking.

A pack describes structure and meaning. It never contains customer data, credentials or sample records.

## File location and structure

Put the file in your app at `<app>/changai/knowledge_pack.yaml`, so it is versioned and released with the code it describes.

```text
zatca_erpgulf/
  zatca_erpgulf/
    changai/
      knowledge_pack.yaml
    hooks.py
    fixtures/
```

The file has a header and up to fifteen sections. Only the first four are required; add the others when your app has something to say there.

| Section | Required | What it holds | Sent to the AI |
| --- | --- | --- | --- |
| Header | Yes | App name, source commit, status | No |
| `overview` | Yes | What the app does, in 3 to 5 sentences | Always |
| `flow` | Yes | How documents move, as short steps | On request |
| `topics` | Yes | Short names for the areas the pack covers | Always (as a menu) |
| `status_field` | If you have one | Values of a status field and what they mean | When relevant |
| `doctypes` | If you add fields | Notes on fields you add to standard doctypes | When relevant |
| `app_doctypes` | If you add doctypes | What each of your doctypes is for | When relevant |
| `never_send` | If any secrets | Fields that must never leave the server | Never; enforced by the server |
| `words` | Recommended | How users say things, mapped to fields | Never; used by the server |
| `metrics` | Recommended | Business numbers with fixed rules | Names only |
| `reports` | If you have reports | Reports changAI may run | Names and purpose |
| `tools` | Optional | Read-only functions changAI may call | As tool definitions |
| `actions_not_exposed` | Optional | Functions that write data; listed so they are not exposed | No |
| `masters` | If you add masters | Records users refer to by name | No; used for name lookup |
| `examples` | Recommended | Sample questions and the expected call | Best matches only |
| `review_notes` | Recommended | Open points for the reviewer | No |

Header:

```yaml
pack_version: 1
app: zatca_erpgulf
app_title: ZATCA ERPGulf
source:
  repository: https://github.com/ERPGulf/zatca_erpgulf
  commit: ba0a088
drafted_on: 2026-11-13
reviewed_by: null
status: Draft          # Draft | Reviewed
```

changAI uses a pack only when `status` is `Reviewed`.

[Previous: The sample app: zatca_erpgulf](sample-app-zatca-erpgulf.md) · [Contents](README.md) · [Next: Step 1: Overview, flow and topics](step-1-overview-flow-topics.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
