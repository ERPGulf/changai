# Writing questions and answers

The `examples` section of a knowledge pack is a list of questions users ask, each paired with the call that answers it. This page explains how to write them well. It expands the short "Examples" part of [Step 5](step-5-tools-masters-examples.md).

## What an example is

An example pairs **a question** with **the way to answer it**. It does not store the answer itself.

```yaml
- question: "How many invoices are not submitted to ZATCA this month?"
  tool: "get_metric(Invoices Not Submitted to ZATCA, period=this_month)"
```

The number changes every day, so writing "42" would be wrong tomorrow. The call stays right: changAI runs it fresh each time, with the user's own permissions.

changAI uses your examples in three ways:

| Use | What happens |
|---|---|
| Guidance | When a user asks something similar, the closest examples are shown to the AI as "answer it like this" |
| Testing | Each example becomes a test case: does changAI choose the same call for that question? |
| Review | A consultant reading the examples sees quickly whether the pack understands the app |

## The parts of an example

| Key | Required | Purpose |
|---|---|---|
| `question` | Yes | The question, in the words a user would type |
| `tool` | Yes, unless `expect` is `refuse` or `ask` | The call that answers it |
| `also_asked` | No | Other ways of asking the same thing |
| `note` | No | One line on why this call is the right one; passed to the AI with the example |
| `after` | No | The earlier question this one follows up on |
| `expect` | No | `refuse` or `ask`, for questions that must not be answered directly |
| `reason` | With `expect` | Why it is refused, or what to ask |

A fuller example:

```yaml
- question: "Which invoices are stuck with ZATCA?"
  also_asked:
    - "pending zatca invoices"
    - "invoices not sent to zatca"
    - "الفواتير التي لم ترسل إلى الزكاة"
  tool: "query_doctype(Sales Invoice, filters: docstatus=1, custom_zatca_status in [Not Submitted, 503 Service Unavailable], fields: name, customer_name, posting_date, custom_zatca_status)"
  note: "'Stuck' and 'pending' mean both Not Submitted and 503 Service Unavailable."
```

## Slots: leave out the specifics

Replace anything that changes from one question to the next with a slot in braces. One example then covers every customer, invoice and period.

| Write | Not |
|---|---|
| `"ZATCA status of invoice {invoice}"` | `"ZATCA status of invoice ACC-SINV-2026-00412"` |
| `"Sales to {customer} {period}"` | `"Sales to Al Noor Trading in October"` |

Common slot names:

| Slot | Stands for |
|---|---|
| `{customer}`, `{supplier}`, `{employee}`, `{item}` | A record found by name |
| `{invoice}`, `{order}` | A document number |
| `{company}`, `{warehouse}`, `{territory}`, `{cost_center}` | A standard master |
| `{period}` | Any time range |
| Your own masters | Use the role name from your `masters` section, for example `{unit}` or `{vehicle}` |

Use a fixed period only when the question is really about that period ("this month", "today"). Fixed periods are written as: `today`, `yesterday`, `this_week`, `last_week`, `this_month`, `last_month`, `this_quarter`, `last_quarter`, `this_year`, `last_year`.

Never put real customer names, amounts or document numbers in a pack.

## Writing the call

There are four kinds of call. Choose the first one in this list that fits the question:

| Order | Call | Use when | Form |
|---|---|---|---|
| 1 | `get_metric` | The question asks for one of your defined numbers | `get_metric(Metric Name, period=…, group_by=…, filters: …)` |
| 2 | `run_report` | One of your reports already answers it | `run_report(Report Name, filter=…, filter=…)` |
| 3 | A registered tool | Your app has a function for it | `function_name(input=…)` |
| 4 | `query_doctype` | A list, a count or a single record | `query_doctype(DocType, filters: …, fields: …, aggregate: …, group_by: …)` |

Rules for the call:

- **Use only names that exist in your pack**: metric names, report names, doctypes and fields, spelled exactly.
- **Write stored values exactly**, including case: `CLEARED`, not `Cleared`; `reported`, not `Reported`.
- **Include `docstatus=1`** in `query_doctype` calls on submittable documents, unless the question is about drafts or cancelled documents.
- **Ask only for the fields the answer needs.** Never a field from `never_send`.
- **Group words become value lists.** If "pending" means two values, write both: `custom_zatca_status in [Not Submitted, 503 Service Unavailable]`.

## Which questions to write

Aim for 10 to 20 examples that between them cover each row of this table. The examples here are from the two sample packs.

| Kind of question | Example | Call |
|---|---|---|
| A count | "How many sales invoices were reported {period}?" | `get_metric(Sales Invoices Reported, period={period})` |
| A list | "Show invoices still pending with the tax authority" | `query_doctype(Sales Invoice, filters: docstatus=1, custom_reporting_status=pending)` |
| One record | "What is the e-invoice status of {invoice}?" | `query_doctype(Sales Invoice, filters: name={invoice}, fields: custom_einvoice_status, custom_reporting_status)` |
| Why | "Why did {invoice} fail?" | `query_doctype(Sales Invoice, filters: name={invoice}, fields: custom_reporting_status, custom_submit_response)` |
| A breakdown | "Sales invoices by reporting status {period}" | `query_doctype(Sales Invoice, filters: docstatus=1, posting_date in {period}, aggregate: count, group_by: custom_reporting_status)` |
| An amount | "VAT reported to ZATCA {period}" | `get_metric(VAT Reported to ZATCA, period={period})` |
| For one party | "Invoices cleared for {customer} {period}" | `query_doctype(Sales Invoice, filters: customer={customer}, custom_zatca_status=CLEARED, posting_date in {period})` |
| Everyday words | "Which invoices are stuck?" | The value list behind "stuck", as in the fuller example above |
| A report | "Which invoices had ZATCA warnings {period}?" | `run_report(ZATCA Sales Invoices with warnings, from_date, to_date)` |
| Returns and special cases | "Credit notes reported {period}" | `query_doctype(Sales Invoice, filters: is_return=1, docstatus=1, custom_reporting_status=reported, posting_date in {period})` |
| Settings | "Which provider does {company} use for e-invoicing?" | `query_doctype(Company, filters: name={company}, fields: custom_einvoice_enabled, custom_einvoice_provider)` |
| Another language | "كم فاتورة لم ترسل إلى الزكاة هذا الشهر؟" | `get_metric(Invoices Not Submitted to ZATCA, period=this_month)` |

Also make sure that:

- every metric and every reviewed report appears in at least one example;
- every status value, or its group, appears in at least one example;
- each language your users type in has at least two examples.

## Where to find real questions

Invented questions sound like documentation. Real ones sound like "any zatca pending?". Collect them from:

- support tickets and WhatsApp or email requests from clients;
- what people ask during demos and training;
- the reports and dashboard cards users open most, turned into questions;
- your consultants: ask each for the five questions they hear most.

Keep the user's wording in `question` or `also_asked`, including short and informal forms.

## Several ways to ask the same thing

Put the clearest wording in `question` and the others in `also_asked`. Write a separate example only when the call differs.

```yaml
- question: "How many invoices were reported to ZATCA {period}?"
  also_asked:
    - "zatca reported count {period}"
    - "how many went to zatca {period}"
    - "كم فاتورة تم إرسالها إلى الزكاة {period}"
  tool: "get_metric(Invoices Reported, period={period})"
```

## Follow-up questions

Users rarely repeat themselves: after one answer they type "and last month?" or "only the failed ones". Show a few of these with `after`, so the AI learns what carries over.

```yaml
- question: "and last month?"
  after: "How many sales invoices were reported this month?"
  tool: "get_metric(Sales Invoices Reported, period=last_month)"
  note: "Same metric; only the period changes."

- question: "show me the failed ones"
  after: "How many sales invoices were reported this month?"
  tool: "query_doctype(Sales Invoice, filters: docstatus=1, custom_reporting_status in [failed, rejected], posting_date in this_month)"
  note: "Same period; the status changes and a list is wanted."
```

Two or three follow-ups per pack are enough.

## Questions that must not be answered directly

Some questions should be refused, and some need a question back. Writing these down makes them test cases too.

```yaml
- question: "Show the private key for {company}"
  expect: refuse
  reason: "Secrets are listed under never_send."

- question: "What is the status of the last invoice?"
  expect: ask
  reason: "Unclear which status is meant: E-Invoice Status or Reporting Status. Ask, or show both."
```

Include at least one `refuse` example for each doctype that appears in `never_send`.

## Using Claude to write them

Claude can draft most of this section for you in a few minutes. It is good at turning a pack into well-formed examples, rewording questions, and translating. It cannot know which words your clients really use, so the result is a first draft for you to correct.

**What Claude needs from you.** Claude does not know the knowledge pack format; it is new. Give it these three things:

| Give Claude | Where to get it | Why |
| --- | --- | --- |
| The [format reference](format-reference.md) and one sample pack | This folder, and `examples/` | So it follows the format instead of inventing one |
| Your app's code | Your own repository | So every field, status and report it names is real |
| Your knowledge pack | `changai/knowledge_pack.yaml` in your app | So the examples use the metrics, reports and values your pack defines |

**Write and review the rest of the pack first.** The examples are built from the pack, so its metrics, reports, field notes and status values must exist and be correct before you start. If you do not have a pack yet, follow [Building your pack with Claude](using-claude.md), which covers the pack and then these same steps.

Work either in Claude Code inside your app's repository, where it can read the pack and the code directly, or in a chat with the format reference, a sample pack and your `knowledge_pack.yaml` attached.

**Step 1: a first set from the pack**

```text
Here is my changAI knowledge pack and the guide page "Writing questions and answers".

Write the `examples` section for this pack, 15 to 20 entries.
- Cover every row of the "Which questions to write" table.
- Use every metric and every report at least once, and every status value or group.
- Use only metric names, report names, doctypes and field names that exist in the pack.
  Copy stored values exactly, including upper and lower case.
- Use slots such as {customer}, {invoice}, {period}. No real names, numbers or dates.
- Prefer get_metric, then run_report, then a registered tool, then query_doctype.
- Add docstatus=1 for submitted documents.
- Add a one-line `note` where the choice of call is not obvious.
Return YAML only.
```

**Step 2: your clients' real wording**

Collect questions from support tickets, chats and demos. Remove customer names, amounts and document numbers before pasting them, or use a model running on your own hardware.

```text
Below are questions our users actually asked, one per line.

For each one, find the example in my pack that answers it and add the wording
under `also_asked`, with names and dates replaced by slots.
If no example fits, write a new one.
If a question cannot be answered from this pack, list it separately and say what
is missing: a metric, a report, a field note or a word.

<paste the questions>
```

The list of questions that cannot be answered is as useful as the examples: it shows what to add to the pack.

**Step 3: other languages**

```text
For each example, add two natural Arabic wordings under `also_asked`, written the way
an accountant in Saudi Arabia or the UAE would type them in a chat, not formal
translations. Keep slots unchanged. Do not translate field names or stored values.
```

Have a native speaker read the result. Do the same for any other language your users type in.

**Step 4: follow-ups, refusals and unclear questions**

```text
Add to the examples:
- three follow-up questions using `after`, each changing one thing
  (the period, the status, or the party);
- one `expect: refuse` example for every doctype listed under never_send;
- two `expect: ask` examples for questions that are unclear in this app,
  with a `reason` saying what to ask.
```

**Step 5: ask Claude to find the gaps**

```text
Review the examples against the pack. List:
- metrics, reports, status values and topics that no example uses;
- examples whose call does not match the question;
- examples that use query_doctype where a metric exists;
- any field, metric or report name that is not in the pack.
```

**Step 6: check, then fix**

Run the script in the next section. If it reports problems, paste its output back to Claude and ask it to correct those entries. Then test the calls on a site, as described there.

What to check yourself, whatever Claude produces:

| Check | Why |
| --- | --- |
| Every name exists in the pack | An AI can write a plausible field or metric that is not there; the script catches this |
| The wording is what clients say | Claude writes clear questions; users write short, informal ones |
| Each call gives the right result on a test site | A well-formed call can still answer a different question |
| Non-English wordings | Natural phrasing needs a native speaker |
| No private data came in with pasted questions | Names and numbers must not end up in the pack |

## Check your examples

Run this small script on your pack. It confirms that every metric, report and doctype named in an example exists in the pack. A fuller checker, which also checks fields, topics and the never-send list, is at [`tools/check_pack.py`](tools/check_pack.py).

```python
import re, sys, yaml

pack = yaml.safe_load(open(sys.argv[1]))
metrics = {m["name"] for m in pack.get("metrics", [])}
reports = {r["report"] for r in pack.get("reports", [])}
tools = {t["function"].split(".")[-1] for t in pack.get("tools", [])}
known_doctypes = set(pack.get("doctypes", {})) | set(pack.get("app_doctypes", {}))
problems = []

for ex in pack.get("examples", []):
    if ex.get("expect") in ("refuse", "ask"):
        continue
    call = ex.get("tool", "")
    m = re.match(r"(\w+)\((.*)\)\s*$", call)
    if not m:
        problems.append((ex["question"], "tool is not written as name(...)"))
        continue
    name, args = m.group(1), m.group(2)
    first = args.split(",")[0].strip()
    if name == "get_metric" and first not in metrics:
        problems.append((ex["question"], f"unknown metric: {first}"))
    elif name == "run_report" and first not in reports:
        problems.append((ex["question"], f"unknown report: {first}"))
    elif name == "query_doctype" and first not in known_doctypes:
        problems.append((ex["question"], f"doctype not described in the pack: {first}"))
    elif name not in ("get_metric", "run_report", "query_doctype") and name not in tools:
        problems.append((ex["question"], f"unknown tool: {name}"))

print(f"{len(pack.get('examples', []))} examples checked")
for q, why in problems:
    print(" -", q, "->", why)
print("All good" if not problems else f"{len(problems)} to fix")
```

```bash
python check_examples.py changai/knowledge_pack.yaml
```

Then check the answers themselves on a test site: for each example, compare the result of the call with what the app's own screen, dashboard or report shows for the same question. If they differ, either the call or the metric definition is wrong.

## Common mistakes

| Mistake | Result | Do this |
|---|---|---|
| Writing the answer ("There are 42") | Wrong the next day | Write the call |
| Real names or numbers in the question | Private data in the pack; the example fits one case only | Use slots |
| A status written in the wrong case | The filter matches nothing | Copy the stored value |
| Using `query_doctype` where a metric exists | Totals differ from the dashboard | Prefer `get_metric` |
| Twenty variations of one question | Other question types are not covered | One example, with `also_asked` |
| Only tidy, formal wording | Everyday questions are missed | Use the words clients type |
| Only English | Other languages are untested | At least two examples per language |
| No "why" question | Users cannot find out what went wrong | Add one that returns the response field |
| Forgetting `docstatus=1` | Drafts and cancelled documents counted | Add it to calls on submittable documents |
| No refuse or ask examples | Secrets and unclear questions are untested | Add at least one of each |

## A worked set

A short, complete set for an e-invoicing app, covering most of the table above:

```yaml
examples:
  - question: "How many sales invoices were reported {period}?"
    also_asked: ["reported invoices count {period}", "كم فاتورة تم الإبلاغ عنها {period}"]
    tool: "get_metric(Sales Invoices Reported, period={period})"

  - question: "Which invoices failed e-invoicing {period}?"
    also_asked: ["rejected invoices {period}", "any failures {period}?"]
    tool: "query_doctype(Sales Invoice, filters: docstatus=1, custom_reporting_status in [failed, rejected], posting_date in {period}, fields: name, customer_name, grand_total, custom_reporting_status)"
    note: "'Failed' includes both failed and rejected."

  - question: "What is the e-invoice status of {invoice}?"
    tool: "query_doctype(Sales Invoice, filters: name={invoice}, fields: custom_einvoice_status, custom_reporting_status, custom_document_id)"
    note: "Show both statuses; they answer different questions."

  - question: "Why did {invoice} fail?"
    tool: "query_doctype(Sales Invoice, filters: name={invoice}, fields: custom_reporting_status, custom_submit_response, custom_document_status_response)"

  - question: "Sales invoices by reporting status {period}"
    tool: "query_doctype(Sales Invoice, filters: docstatus=1, posting_date in {period}, aggregate: count, group_by: custom_reporting_status)"

  - question: "E-invoice status of invoices for {customer} {period}"
    tool: "query_doctype(Sales Invoice, filters: customer={customer}, docstatus=1, posting_date in {period}, fields: name, posting_date, grand_total, custom_einvoice_status, custom_reporting_status)"

  - question: "and the purchase side?"
    after: "How many sales invoices were reported this month?"
    tool: "get_metric(Purchase Invoices Reported, period=this_month)"

  - question: "Show the API secret for our provider"
    expect: refuse
    reason: "Credentials are listed under never_send."
```

[Previous: Step 5: Tools, actions, masters and examples](step-5-tools-masters-examples.md) · [Contents](README.md) · [Next: Drafting with an AI tool](drafting-with-ai.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
