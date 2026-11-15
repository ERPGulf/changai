# Building your knowledge pack with Claude: complete walkthrough

This page takes a developer of any Frappe app from nothing to a finished knowledge pack, including its questions and answers, using Claude for the drafting. Every prompt is here to copy. It is long because it is complete; a medium-sized app takes two to three hours, most of it your checking.

If you only want the format, see the [format reference](format-reference.md). If you prefer to write by hand, start at [Before you start](getting-started.md).

## How the work is divided

| Claude does | You do |
| --- | --- |
| Reads fixtures, doctypes, hooks, reports and dashboards | Decide what the app is for and what it is not for |
| Finds every value a status field can take | Say what each value means to the business |
| Lists fields that look like secrets | Confirm that list is complete |
| Copies metric filters from dashboards | Decide which numbers matter and whether the filters are right |
| Describes how each report reads data | Decide whether each report is safe to offer |
| Writes well-formed questions and calls | Supply the words your clients really use |
| Translates wordings | Have a native speaker confirm them |
| Fixes what the checker reports | Test results on a site and sign off |

Claude produces a draft. A pack is used by changAI only after a person has reviewed it and set `status: Reviewed`.

## Before you start

You need:

- your app's repository, with fixtures, `hooks.py`, reports and dashboards;
- a development or test site with the app installed and some test data;
- someone who knows the business, for the review;
- Python with PyYAML, to run the checker.

**Privacy.** Using Claude means your code is sent to it. Check that your company allows this for the repository in question; for confidential code, use a plan and settings your company has approved, or a model running on your own hardware. Whatever you use:

- never paste `site_config.json`, `.env` files, keys, passwords or tokens;
- never paste client records, invoices or exports from a live site;
- remove names, amounts and document numbers from any real user questions before pasting them;
- work against a test site, not production.

## What to give Claude

Claude does not know the knowledge pack format. It is new, and without the reference Claude will invent something plausible and wrong.

| Give Claude | Where to get it | Why |
| --- | --- | --- |
| The format reference | [`format-reference.md`](format-reference.md) in this folder: one file with the whole format | So it follows the format |
| One sample pack | [`examples/`](examples/): the fleet pack for a small app, the zatca_erpgulf or einvoice_erpgulf pack for a larger one | So it sees a finished result |
| Your app's code | Your repository | So every field, status and report it names is real |
| The checker | [`tools/check_pack.py`](tools/check_pack.py) | So mistakes are found by a program, not by eye |

The whole folder is at [github.com/ERPGulf/changai/tree/main/docs/knowledge-packs](https://github.com/ERPGulf/changai/tree/main/docs/knowledge-packs).

## Setting up

### Option A: Claude Code, inside your repository (recommended)

Claude Code can read your files directly and run the checker itself.

1. Copy `format-reference.md`, one sample pack and `tools/check_pack.py` into a folder in your project, for example `changai_guide/`. You can delete it when you finish.
2. Create the folder `changai/` inside your app's module folder (the one that contains `hooks.py`).
3. Start Claude Code in the repository root.
4. Send the opening message below.

### Option B: a chat

Attach files to the conversation. Claude cannot read your repository, so you choose what it sees.

| Attach first | Then, as each stage asks |
| --- | --- |
| `format-reference.md` | Python files the hooks point to |
| One sample pack | Report `.py` and `.js` files |
| `fixtures/custom_field.json` (every one, if there are several) | Dashboard and number card JSON |
| `hooks.py` | Client scripts that set or show statuses |
| Each of your doctype `.json` files | Any file Claude asks for |

In a chat you run the checker yourself and paste its output back.

### The opening message

Send this first, in either option:

```text
I am writing a changAI knowledge pack for my Frappe app.

Read the format reference (format-reference.md) and the sample pack before anything else.
Follow that format exactly. Do not add sections or keys that are not in it.

Rules for the whole job:
- Invent nothing. Every doctype, field, report, function and status value must come
  from my code. If you are not sure, say so and put it in review_notes.
- Copy stored values exactly, including upper and lower case.
- Never include customer data, credentials or real document numbers.
- Work in stages. After each stage, stop and show me the result so I can check it.
- Tell me which files you read for each stage, and ask for any file you need.

The app is: <name>, in <path>. In one or two sentences, it does: <what it does>.
Start by telling me what you have read and what else you need.
```

## Part 1: The knowledge pack

Work through these stages in order. After each one, read what Claude produced, correct it in the conversation, and move on. Do not ask for the whole file at once on a large app: mistakes are much easier to catch one section at a time.

### Stage 1: Inventory

```text
Stage 1. Make an inventory of the app. Do not write the pack yet.

List, as tables:
1. Custom fields the app adds, grouped by doctype (from every fixtures/custom_field.json),
   leaving out Section Break, Column Break, Tab Break, HTML and Button fields.
2. The app's own doctypes, with their fields and which roles can read them.
3. doc_events and scheduler_events from hooks.py: which function runs on which event.
4. Reports: name, type (Report Builder, Script, Query) and roles.
5. Number cards, dashboard charts and dashboard pages.
6. Whitelisted functions, with a guess at whether each one only reads or also writes.
7. Fields that look like statuses: Data or Select fields whose name or label suggests a state.
8. Fields that look like secrets or personal identifiers.
```

**Check:** does the count of fields and doctypes match what you expect? Is any module or country folder missing? Correct it now; everything later builds on this.

### Stage 2: Status values

This is the part an AI cannot guess and most often gets wrong.

```text
Stage 2. For every status-like field from the inventory:

1. Search all Python, JavaScript and JSON files for every place the field is set,
   compared or filtered. List each distinct value exactly as written, with the file
   and line where you found it.
2. Include values that appear only in dashboards, list badges or report filters.
3. Note any value written in different cases in different places.
4. For each value, say what you think it means and how sure you are.
5. Say what the default is.

Then write the status_field section (or status_fields, if there is more than one field),
with values, groups for everyday words such as pending, accepted and failed, and notes.
Give each field a `meaning` line if there are several.
```

**Check:** read each meaning. Correct any that are wrong in business terms. Ask yourself what users call these states and make sure `groups` has those words. If a value means two different things (for example "never sent" and "failed"), say so in `notes`.

### Stage 3: Overview, flow and topics

```text
Stage 3. Write overview, flow, applies_when and topics.

- overview: 3 to 5 sentences. What the app does, which standard doctypes it touches,
  what it does not do. No marketing language.
- flow: follow each doc_event and scheduler job into the function it calls and describe
  what happens, as short steps in order. Include rules a user runs into, such as when
  a document cannot be cancelled or edited.
- applies_when: the conditions under which the app does anything at all.
- topics: 5 to 12 short names covering the areas of the pack. I will ask you to fill in
  their references at the end, once the other sections exist.
```

**Check:** is the order of steps right? Are there exceptions the code handles that the flow leaves out? Would a new colleague understand the overview?

### Stage 4: Field notes

```text
Stage 4. Write the doctypes and app_doctypes sections.

For each field the app adds to a standard doctype, write one line saying what the value
means in business terms. Add, where it applies:
- where the value comes from (fetch_from, set by code, typed by the user);
- a default that looks like data;
- a side effect ("the app skips submission when this is 1").
Do not repeat the label as the description. Do not copy long option lists.
Leave out every field from the secrets list in the inventory.

Add related_standard_fields for standard fields the app relies on.
For each of the app's own doctypes, write use_for, not_for and who can read it.
If a field's purpose is not clear from the code, describe it by its label and add a
review note; do not guess.
```

**Check:** skim for descriptions that only restate the label. Check the `not_for` lines: they prevent the most common wrong answers.

### Stage 5: The never-send list

```text
Stage 5. Write never_send.

Go through every settings doctype and every custom field on Company and on user or party
doctypes, field by field. List every field that holds or may hold:
- a key, certificate, password, token, OTP or client secret;
- a signing hash or counter;
- a stored reply from an outside service that may contain a token;
- a personal identifier (national ID, passport, bank account, salary);
- large file content.
Use exact field names, even if misspelled in the app.
For each field you considered and left out, say why in one line.
```

**Check:** this section must be complete, and only you can be sure it is. Open each settings doctype yourself and compare. If in doubt about a field, list it.

### Stage 6: Words

```text
Stage 6. Write the words section: what users say, mapped to what it means in the data.

Include the app's own terms, the informal words people use for each status group
(stuck, pending, failed, sent), and the terms from my industry.
Suggest wordings in <languages your users type in>, and mark those as suggestions
in review_notes.
```

**Check:** replace Claude's guesses with the words your support staff actually hear. Have a native speaker fix the non-English entries.

### Stage 7: Metrics and reports

```text
Stage 7. Write metrics, metric_defaults and reports.

Metrics: take each number card and dashboard figure and write it as a metric, copying
the filters exactly. Give each a name a user would say. Note in review_notes:
- any card that does not filter docstatus;
- any card that uses a transaction-currency field instead of a base_ field;
- any two cards that define the same thing differently.
Do not invent metrics the app does not show; list ideas for additional ones separately.

Reports: for each report, write use_for, roles, filters (name, type, options, required)
and columns. Set permission_reviewed: false. Then tell me, for each report:
- whether it reads with Report Builder, frappe.get_list, frappe.get_all or frappe.db.sql;
- whether every filter shown on screen is actually used in the query;
- whether it filters by company and by docstatus.
```

**Check:** on your test site, compare each metric with the dashboard card it came from. Read Claude's notes on each report carefully: a report that reads with SQL and ignores its company filter must stay unreviewed until it is fixed.

### Stage 8: Tools, actions and masters

```text
Stage 8. Write tools, actions_not_exposed and masters.

Tools: from the whitelisted functions, propose only those that read data, check the
caller's permissions themselves, take simple inputs and return data. For each, show me
the lines that check permissions. If none qualify, write tools: [].
List every other whitelisted function that writes, sends or calls an outside service
under actions_not_exposed.

Masters: list doctypes whose records users refer to by name. For each give title_field,
fields to index, roles (everyday words), linked_from, and parent or tree if records nest.
For name fields the app adds to standard masters, use extra_fields.
Do not list fields from never_send, phone numbers, addresses or ID numbers.
```

**Check:** be strict about tools. If a function's permission check is not obvious in the lines Claude shows, leave it out.

### Stage 9: Put it together

```text
Stage 9. Assemble the complete knowledge_pack.yaml.

- Header with pack_version: 1, the app name, repository, the current commit,
  today's date, reviewed_by: null and status: Draft.
- All sections in the order of the format reference, with a comment line above each.
- Fill in the topics references so each points to sections that exist.
- End with review_notes: everything you inferred, could not confirm, or found
  inconsistent in the app. Be specific; name the file where it helps.
Save it as <module folder>/changai/knowledge_pack.yaml.
```

### Stage 10: Run the checker

From your app's module folder:

```bash
python changai_guide/check_pack.py changai/knowledge_pack.yaml
```

It checks that the file is valid, that every field named exists in your app, that every topic points to something real, and (later) that every example uses things the pack defines. In Claude Code, ask Claude to run it. In a chat, paste the output:

```text
The checker reported the following. Fix each problem in the pack and tell me what you
changed. Do not change anything else.

<paste the output>
```

Repeat until it prints `OK`.

### Stage 11: Review by a person

Ask Claude to prepare the review:

```text
Turn review_notes into a short list of questions for a functional consultant,
each answerable with yes, no or one line. Group them by section.
```

Give the reviewer the pack, those questions and the [review checklist](review-and-upkeep.md). Apply their answers:

```text
Here are the reviewer's answers. Update the pack accordingly and remove the review
notes that are now settled.

<paste the answers>
```

Do not go on to Part 2 until this is done. The examples are built on the pack; a wrong status meaning or metric here makes every example that uses it wrong.

## Part 2: Questions and answers

The rules for this section are on [Writing questions and answers](questions-and-answers.md). Give that page to Claude as well, or rely on the format reference, which summarises it.

### Stage 12: A first set from the pack

```text
Write the examples section for this pack, 15 to 20 entries.
- Cover: a count, a list, one record, a "why" question, a breakdown, an amount,
  one party, everyday words, a report, returns or special cases, and settings.
- Use every metric and every report at least once, and every status value or group.
- Use only metric names, report names, doctypes and field names that exist in the pack.
  Copy stored values exactly.
- Use slots such as {customer}, {invoice}, {period}. No real names, numbers or dates.
- Prefer get_metric, then run_report, then a registered tool, then query_doctype.
- Add docstatus=1 for submitted documents.
- Add a one-line note where the choice of call is not obvious.
```

### Stage 13: Your clients' real wording

Collect questions from support tickets, chats and demos, and remove names, amounts and document numbers.

```text
Below are questions our users actually asked, one per line.

For each one, find the example that answers it and add the wording under also_asked,
with names and dates replaced by slots. If no example fits, write a new one.
If a question cannot be answered from this pack, list it separately and say what is
missing: a metric, a report, a field note or a word.

<paste the questions>
```

The list of questions that cannot be answered tells you what to add to the pack. Add it, then repeat this stage.

### Stage 14: Other languages

```text
For each example, add two natural <language> wordings under also_asked, written the way
an accountant would type them in a chat, not formal translations. Keep slots unchanged.
Do not translate field names or stored values.
```

Have a native speaker read them.

### Stage 15: Follow-ups, refusals and unclear questions

```text
Add to the examples:
- three follow-up questions using `after`, each changing one thing
  (the period, the status or the party);
- one `expect: refuse` example for every doctype listed under never_send;
- two `expect: ask` examples for questions that are unclear in this app,
  with a `reason` saying what to ask.
```

### Stage 16: Ask Claude to find the gaps

```text
Review the examples against the pack. List:
- metrics, reports, status values and topics that no example uses;
- examples whose call does not match the question;
- examples that use query_doctype where a metric exists;
- any field, metric or report name that is not in the pack.
Then fix them.
```

### Stage 17: Check and test

Run the checker again; it now checks the examples too, and notes any metric or report that no example uses. Fix what it reports.

Then test on your site. For each example, compare the result of its call with what the app's own screen, dashboard or report shows for the same question. Where they differ, either the call or the metric is wrong.

## Part 3: Finish

1. The checker prints `OK`.
2. The reviewer has gone through the [checklist](review-and-upkeep.md).
3. Set `reviewed_by` to the reviewer's name and `status: Reviewed`.
4. Keep `changai/knowledge_pack.yaml` in your repository and release it with the app.
5. Delete the temporary guide folder from your project.

## Keeping the pack current with Claude

When the app changes, update the pack in the same change. Give Claude the differences rather than asking for a rewrite:

```text
The app has changed since the pack was written at commit <old commit>.
Here is the list of changed files (or the diff).

Tell me which parts of the knowledge pack are affected: new, renamed or removed fields;
new status values; changed reports, number cards or whitelisted functions; new settings
fields that may be secrets. Propose the exact edits to the pack. Do not rewrite sections
that are not affected. Update source.commit, and set status back to Draft if any
meaning changed.
```

Run the checker, have the affected parts reviewed, and release.

## Small apps: one prompt

For an app with a handful of custom fields and no reports, the stages can be one request:

```text
Read format-reference.md and the sample pack, then read my whole app.
Write a complete changAI knowledge pack for it, following the format exactly.
Invent nothing; put anything unclear in review_notes. Set status: Draft.
For every status-like field, list every value found anywhere in the code.
List every secret or personal field under never_send.
Then write 15 examples covering the kinds of question in the format reference.
Finally, run tools/check_pack.py on the result and fix what it reports.
```

Review it the same way.

## When things go wrong

| What you see | Likely cause | What to do |
| --- | --- | --- |
| Field names that are not in your app | Claude worked from memory, not your files | The checker lists them. Tell Claude: "These fields do not exist; reread the fixtures and correct." |
| Sections or keys not in the format | The format reference was not read, or was forgotten in a long conversation | Attach it again and say: "Use only sections and keys from the format reference." |
| A status value is missing | It is set in a file Claude did not read (a client script, a country folder, a dashboard) | Ask for the search in Stage 2 again, naming the folders to include |
| Descriptions that repeat the label | The code gave no clue | Supply the meaning yourself, or leave a review note |
| The pack is very long | Long option lists or layout fields were copied | "Remove option lists and layout fields; changAI reads them from the site." |
| In a chat, Claude says it cannot see a file | It was not attached | Attach it. In a chat Claude sees only what you attach |
| The YAML does not load | A colon or quote in a description | The checker shows the line. Ask Claude to quote that value |
| Examples all sound formal | No real questions were supplied | Do Stage 13 with real wording |
| Results on the site differ from the dashboard | A filter was changed while copying, or the dashboard itself is inconsistent | Compare the metric's `fixed_filters` with the card; decide which is right and note it |
| Claude marks a report or tool as reviewed | It should not | Set `permission_reviewed: false`; only a person changes it |
| The conversation has become long and Claude contradicts earlier stages | Too much in one conversation | Start a new one: attach the format reference and the pack so far, and continue from the next stage |

## The whole job on one page

| # | Stage | Who | Done when |
| --- | --- | --- | --- |
| 1 | Inventory | Claude, you check | Counts match the app |
| 2 | Status values | Claude, you correct meanings | Every value listed, with groups |
| 3 | Overview, flow, topics | Claude, you check | A newcomer would understand it |
| 4 | Field notes | Claude, you check | No description repeats its label |
| 5 | Never-send list | Claude, **you confirm** | Every settings field looked at |
| 6 | Words | Claude suggests, you supply | Real client wording is in |
| 7 | Metrics and reports | Claude, you compare on site | Metrics match the dashboard |
| 8 | Tools, actions, masters | Claude, you decide | Only safe read-only tools listed |
| 9 | Assemble | Claude | One file, with review notes |
| 10 | Checker | Program | Prints `OK` |
| 11 | Review | Consultant | Review notes settled |
| 12–16 | Questions and answers | Claude, you supply real questions | Coverage complete |
| 17 | Check and test | Program, then you | `OK`, and results match the app |
| — | Finish | You | `status: Reviewed`, shipped with the app |

[Contents](README.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
