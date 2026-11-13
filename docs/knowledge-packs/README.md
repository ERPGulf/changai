# Writing a changAI knowledge pack for your Frappe app

A knowledge pack is one YAML file in your Frappe app that tells changAI what your app means: what its fields and statuses stand for, how its documents flow, which numbers and reports matter, and what must never be shown. With it, users can ask questions about your app's data in plain language and get correct answers.

**Why it is needed.** An AI model knows standard ERPNext reasonably well. It does not know your app. It cannot know that a text field holds one of six status values, that "pending" means two of them, or that a field holds a private key. Without a pack it guesses, and guesses look convincing.

**What changAI does with it.** The pack is loaded into the site when your app is installed or migrated. changAI never sends the whole file to the AI. For each question it sends a short menu of what your app covers, and only the notes that question needs. Metric rules and the secrets list are applied by the server and are not sent at all.

**Who writes it.** The app's developer drafts it; someone who knows the business reviews it. An AI coding tool can do most of the first draft (see [Drafting with an AI tool](drafting-with-ai.md)).

**Status of this guide.** This is a draft specification (pack version 1) for changAI v3, which is under development. Key names may change before release; packs written to this draft will need only small edits. Questions and suggestions: support@erpgulf.com.

## Contents

| Page | What it covers |
| --- | --- |
| [The sample app: zatca_erpgulf](sample-app-zatca-erpgulf.md) | The open-source app used for every example |
| [Before you start, and file structure](getting-started.md) | What you need; where the file goes; all sections at a glance |
| [Step 1: Overview, flow and topics](step-1-overview-flow-topics.md) | What the AI sees first |
| [Step 2: Status values, fields and doctypes](step-2-status-fields-doctypes.md) | Meanings that exist only in your code |
| [Step 3: The never-send list](step-3-never-send.md) | Secrets that must not leave the server |
| [Step 4: Words, metrics and reports](step-4-words-metrics-reports.md) | How users speak; business numbers; reports |
| [Step 5: Tools, actions, masters and examples](step-5-tools-masters-examples.md) | Functions, name lookup, sample questions |
| [Drafting with an AI tool](drafting-with-ai.md) | A prompt that works, and what to check |
| [Review and upkeep](review-and-upkeep.md) | Checklist; keeping the pack current |
| [Common mistakes](common-mistakes.md) | What goes wrong, and the fix |
| [A complete minimal pack](minimal-pack.md) | A whole file in one view |
| [Sample pack: zatca_erpgulf](sample-pack-zatca-erpgulf.md) | The full draft pack for the sample app |

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
