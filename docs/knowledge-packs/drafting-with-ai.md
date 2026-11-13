# Drafting with an AI tool

An AI coding tool with access to your repository can write most of the first draft in minutes; your job becomes checking it. This works for public and private apps: for a private app, run the tool on your own machine against the local code.

A prompt that works:

```text
Read this Frappe app and write a changAI knowledge pack (YAML, pack_version 1)
following the attached guide.

1. From fixtures and doctype JSON: list every custom field and doctype.
2. From hooks.py: describe what happens on submit, cancel and on schedule.
3. For every status-like Data or Select field: grep the code for each value that
   is set or compared, and list all values with their meaning.
4. From number cards, dashboard charts and reports: derive metrics and reports,
   copying filters exactly.
5. For every report: say whether it reads with frappe.get_list or frappe.db.sql.
6. List every field holding a key, certificate, token, password or OTP under never_send.
7. List whitelisted functions; mark which only read and which write.
8. Do not invent anything. Every field name must exist in the app.
   Put anything unclear under review_notes.
Set status: Draft.
```

What an AI draft usually gets right: field lists, hooks, report filters, metric filters copied from dashboards.

What you must check yourself:

| Check | Why |
| --- | --- |
| Every status value and its meaning | The tool finds the values; only you know what each means to the business |
| `never_send` is complete | A tool can miss a secret with an unusual name |
| Report permission review | Deciding whether a report is safe needs judgement |
| `words`, especially non-English | Must be the terms your clients use |
| Flow | Order and exceptions are easy to get subtly wrong |
| Nothing invented | Run the check below |

A quick script confirms every field named in the pack exists in your fixtures and doctype files:

```python
import glob, json, yaml

pack = yaml.safe_load(open("changai/knowledge_pack.yaml"))
have = {(f["dt"], f["fieldname"]) for f in json.load(open("fixtures/custom_field.json"))}
for path in glob.glob("**/doctype/*/*.json", recursive=True):
    d = json.load(open(path))
    have |= {(d["name"], f["fieldname"]) for f in d.get("fields", [])}

named = [(dt, fn) for dt, v in pack.get("doctypes", {}).items() for fn in v.get("fields", {})]
named += [(dt, fn) for dt, fields in pack.get("never_send", {}).items() for fn in fields]
print("Not found in the app:", [x for x in named if x not in have] or "none")
```

If your code is confidential, use a tool and settings your company allows for that code, or a model running on your own hardware.

[Previous: Step 5: Tools, actions, masters and examples](step-5-tools-masters-examples.md) · [Contents](README.md) · [Next: Review and upkeep](review-and-upkeep.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
