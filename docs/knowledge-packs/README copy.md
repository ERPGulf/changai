# Writing a changAI knowledge pack for your Frappe app

A knowledge pack is one YAML file in your Frappe app that tells changAI what your app means: what its fields and statuses stand for, how its documents flow, which numbers and reports matter, and what must never be shown. With it, users can ask questions about your app's data in plain language and get correct answers.

**Why it is needed.** An AI model knows standard ERPNext reasonably well. It does not know your app. It cannot know that a text field holds one of six status values, that "pending" means two of them, or that a field holds a private key. Without a pack it guesses, and guesses look convincing.

**What changAI does with it.** The pack is loaded into the site when your app is installed or migrated. changAI never sends the whole file to the AI. For each question it sends a short menu of what your app covers, and only the notes that question needs. Metric rules and the secrets list are applied by the server and are not sent at all.

**Who writes it.** The app's developer drafts it; someone who knows the business reviews it. An AI coding tool can do most of the first draft (see [Drafting with an AI tool](drafting-with-ai.md)).

**Status of this guide.** This is a draft specification (pack version 1) for changAI v3, which is under development. Key names may change before release; packs written to this draft will need only small edits. Questions and suggestions: support@erpgulf.com.

## Contents

**The guide**

| Page | What it covers |
| --- | --- |
| [Before you start, and file structure](getting-started.md) | What you need; where the file goes; all sections at a glance |
| [Step 1: Overview, flow and topics](step-1-overview-flow-topics.md) | What the AI sees first |
| [Step 2: Status values, fields and doctypes](step-2-status-fields-doctypes.md) | Meanings that exist only in your code |
| [Step 3: The never-send list](step-3-never-send.md) | Secrets that must not leave the server |
| [Step 4: Words, metrics and reports](step-4-words-metrics-reports.md) | How users speak; business numbers; reports |
| [Step 5: Tools, actions, masters and examples](step-5-tools-masters-examples.md) | Functions, name lookup, sample questions |
| [Writing questions and answers](questions-and-answers.md) | How to write the `examples` section: slots, calls, coverage, follow-ups, refusals |
| [Drafting with an AI tool](drafting-with-ai.md) | A short prompt for a first draft, and what to check |
| [Building your pack with Claude: complete walkthrough](using-claude.md) | Every stage, with every prompt: what to give Claude, the pack, the questions and answers, checking, upkeep |
| [Format reference](format-reference.md) | The whole format in one file, to hand to an AI assistant |
| [Review and upkeep](review-and-upkeep.md) | Checklist; keeping the pack current |
| [Common mistakes](common-mistakes.md) | What goes wrong, and the fix |
| [A complete minimal pack](minimal-pack.md) | A whole file in one view, for a small fictional app |

**Tool**

[`tools/check_pack.py`](tools/check_pack.py) checks a pack against your app: valid YAML, every field exists, topics and examples refer to things the pack defines. Run it from your app's module folder: `python check_pack.py changai/knowledge_pack.yaml`.

**Samples from real apps**

Each sample has two pages: the app (what it contains and why it is a useful example) and the pack written for it.

| Sample | The app | The pack |
| --- | --- | --- |
| **zatca_erpgulf**: Saudi e-invoicing. One status field, many secrets, five SQL reports. Used for the examples throughout the guide | [The sample app: zatca_erpgulf](sample-app-zatca-erpgulf.md) | [Sample pack: zatca_erpgulf](sample-pack-zatca-erpgulf.md) |
| **einvoice_erpgulf**: e-invoicing for the UAE, Oman and Belgium. Two status fields, sales and purchases, several countries | [The sample app: einvoice_erpgulf](sample-app-einvoice-erpgulf.md) | [Sample pack: einvoice_erpgulf](sample-pack-einvoice-erpgulf.md) |

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
