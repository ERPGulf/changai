# Knowledge pack format: complete reference

This page holds the whole knowledge pack format in one place. Give this single file to an AI assistant so that it follows the format instead of inventing one. People writing a pack by hand will find the step-by-step pages easier; start at the [contents](README.md).

Format version: `pack_version: 1` (draft, for changAI v3).

## What a knowledge pack is

One YAML file inside a Frappe app, at `<app>/changai/knowledge_pack.yaml`. It tells changAI what the app's data means so that users can ask questions in plain language. changAI loads it when the app is installed or migrated. It never sends the whole file to an AI model: it sends a short menu, and only the notes a question needs. Metric rules and the secrets list are applied by the server.

A pack describes structure and meaning only. It must never contain customer data, sample records, credentials or real document numbers.

## Rules that apply to the whole file

1. **Invent nothing.** Every doctype, field, report, function and status value must exist in the app. If something is unclear, put it under `review_notes`; do not guess.
2. **Copy stored values exactly**, including upper and lower case and spaces.
3. **Describe meaning, not mechanics.** Say what a value means to the business and where it comes from, not how the code computes it line by line.
4. **Skip layout fields**: Section Break, Column Break, Tab Break, HTML, Button.
5. **Do not copy long option lists.** changAI reads field types and options from the site.
6. **Anything secret goes under `never_send`** and nowhere else.
7. **Write for someone who has never seen the app.**
8. **New packs start with `status: Draft`.** Only a person sets `Reviewed`.

## Sections

| Section | Required | Sent to the AI |
| --- | --- | --- |
| Header | Yes | No |
| `overview` | Yes | Always |
| `flow`, `applies_when` | Yes | On request |
| `topics` | Yes | Always, as a menu |
| `status_field` or `status_fields` | If the app has status-like fields | When relevant |
| `doctypes` | If the app adds fields to standard doctypes | When relevant |
| `app_doctypes` | If the app has its own doctypes | When relevant |
| `never_send` | If any field is secret or personal | Never; enforced by the server |
| `words` | Recommended | Never; used by the server |
| `metrics`, `metric_defaults` | Recommended | Names only |
| `reports` | If the app has reports | Names and purpose |
| `tools` | Optional | As tool definitions |
| `actions_not_exposed` | Optional | No |
| `masters` | If users refer to the app's records by name | No; used for name lookup |
| `examples` | Recommended | Best matches only |
| `review_notes` | Recommended | No |

### Header

```yaml
pack_version: 1
app: my_app                     # the app's folder name
app_title: My App
source:
  repository: https://github.com/example/my_app
  commit: 1a2b3c4               # the commit the pack was written from
drafted_on: 2026-11-15
reviewed_by: null               # a person's name, once reviewed
status: Draft                   # Draft | Reviewed
```

### overview

Three to five sentences: what the app does, which standard doctypes it touches, what it does not do. No marketing.

```yaml
overview: >
  Vehicle fleet management for ERPNext. Each Vehicle has Trips and Service Records.
  A trip is planned, started and completed by a driver (Employee). The app does not
  handle fuel purchases; those are Purchase Invoices.
```

### flow and applies_when

`flow` is the life of a document as short steps, in order. Take it from `doc_events` and `scheduler_events` in `hooks.py` and the functions they call. Include rules users run into, such as when a document cannot be cancelled. `applies_when` says when the app is active at all.

```yaml
flow:
  - "Trip is created with status Planned."
  - "Driver starts the trip: status In Transit."
  - "Driver completes it: status Completed, and distance_km is filled."
applies_when: "Fleet Settings.enabled = 1."
```

### topics

Short names (one or two plain words) for the areas the pack covers, each listing the pack sections it returns. Five to twelve topics. A reference is a section name, `doctypes.<DocType>`, `doctypes.<DocType>.<field>`, or `app_doctypes.<DocType>`. Every reference must exist in the pack.

```yaml
topics:
  trip status:  [status_field]
  vehicles:     [app_doctypes.Vehicle]
  flow:         [flow, applies_when]
```

### status_field / status_fields

For every field that holds a status-like value. When the field is Data type, its values are not in the field definition: find every value that is set or compared anywhere in Python, JavaScript, dashboards and report filters.

Use `status_field` for one field. Use `status_fields` (a list) for several, and give each a `meaning` line so they can be told apart.

| Key | Purpose |
| --- | --- |
| `doctypes` | Doctypes that carry the field |
| `fieldname` | Exact field name |
| `meaning` | One line: what question this field answers (needed when there are several) |
| `default` | Default value, or `null` |
| `values` | Each stored value, exactly as stored, with its meaning |
| `groups` | Everyday words mapped to value lists: pending, accepted, failed |
| `notes` | Anything a user would trip over: case, where to find the reason for a failure |

```yaml
status_field:
  doctypes: [Trip]
  fieldname: status
  default: "Planned"
  values:
    "Planned": "Created, not started."
    "In Transit": "Started by the driver, not finished."
    "Completed": "Finished; distance recorded."
  groups:
    open: ["Planned", "In Transit"]
  notes:
    - "Completed trips always have distance_km filled."
```

### doctypes

Fields the app adds to standard doctypes (from `fixtures/custom_field.json`). One line per field that a new team member would need.

| Key | Purpose |
| --- | --- |
| `use_for` | What questions this doctype answers in this app |
| `fields` | `fieldname: "meaning"`; where the value comes from (copied, set by code, typed); defaults that look like data; side effects |
| `related_standard_fields` | Standard fields the app relies on, such as `is_return`, `docstatus`, `base_net_total` |
| `notes` | Optional list |

```yaml
doctypes:
  Sales Invoice:
    use_for: "Trip charges billed to customers."
    fields:
      custom_trip: "The Trip this invoice bills. Set when the invoice is created from a trip."
    related_standard_fields:
      base_net_total: "Amount before tax, company currency."
```

### app_doctypes

The app's own doctypes.

```yaml
app_doctypes:
  Service Record:
    use_for: "Maintenance done on a vehicle, with cost and date."
    not_for: "Fuel (use Purchase Invoice)."
    permissions: "Fleet Manager and System Manager."
```

`not_for` matters: it stops a log or settings doctype being used when the answer is on the main document.

### never_send

Fields whose values must never be sent to an AI model or returned to a user: keys, certificates, passwords, tokens, OTPs, signing hashes, stored API replies that may contain tokens, personal identifiers (national ID, passport, bank account), and large file content. Use exact field names. When unsure, list the field and add a review note.

```yaml
never_send:
  Fleet Settings:
    - gps_api_key
    - gps_api_secret
```

### words

What users say, mapped to what it means in the data. Include informal words and every language users type in.

```yaml
words:
  "trip, journey, delivery run, رحلة":   "Trip"
  "on the road, in transit, running":   "Trip.status = In Transit"
```

### metrics and metric_defaults

A metric is a business number with fixed rules. Take definitions from the app's number cards and dashboard charts, copying filters exactly.

| Key | Purpose |
| --- | --- |
| `name` | A name a user would say; unique in the pack |
| `value` | `count`, or `sum(field)`, `avg(field)`, `min(field)`, `max(field)` |
| `fixed_filters` | Filters always applied: `[[field, operator, value], …]` |
| `source` | Doctype, if different from `metric_defaults.source` |
| `date_field` | Date field, if different from the default |

```yaml
metrics:
  - name: Distance Travelled
    value: sum(distance_km)
    fixed_filters: [[status, "=", "Completed"]]
  - name: Service Cost
    source: Service Record
    value: sum(cost)
    date_field: service_date
    fixed_filters: [[docstatus, "=", 1]]
metric_defaults:
  source: Trip
  date_field: start_date
  dimensions: [vehicle, driver, company]
```

Rules: always decide on `docstatus`; use company-currency fields (`base_…`) for amounts; define close variants (gross, net) as separate metrics; a dimension that does not exist on a metric's doctype is ignored for that metric.

### reports

Reports changAI may run. Write filters and columns here, because Script and Query reports define them in JavaScript.

```yaml
reports:
  - report: Vehicle Utilisation
    use_for: "Trips, distance and idle days per vehicle for a date range."
    roles: [Fleet Manager]
    filters:
      company: {type: Link, options: Company, required: true}
      from_date: {type: Date}
      to_date: {type: Date}
    columns: [vehicle, trips, distance_km, idle_days]
    permission_reviewed: false
```

An AI assistant always writes `permission_reviewed: false`, and adds a review note saying how the report reads data: Report Builder; `frappe.get_list`; or `frappe.db.sql` / `frappe.get_all` (no user permissions applied), and whether each filter shown on screen is used in the query.

### tools and actions_not_exposed

`tools`: existing functions that only read, check the caller's permissions themselves, take simple inputs and return data. If there are none, write `tools: []`.

```yaml
tools:
  - function: fleet_app.api.get_vehicle_cost
    description: "Total running cost of a vehicle for a period: service and fuel."
    parameters:
      vehicle:   {type: Link, options: Vehicle, required: true}
      from_date: {type: Date}
      to_date:   {type: Date}
    read_only: true
    permission_reviewed: false
```

`actions_not_exposed`: whitelisted functions that write data, send something, or call an outside service, listed by full path.

### masters

Records users refer to by name.

| Key | Purpose |
| --- | --- |
| `doctype` | The master's doctype |
| `fields` | Name-like fields to index; codes are matched exactly |
| `title_field` | The readable name, when the document name is a code |
| `roles` | Everyday words for this kind of record, in every language users type |
| `linked_from` | `[{doctype, field}]`: documents that point to this master |
| `parent` | `{doctype, field}`: what a record belongs to |
| `tree` | `true` for tree doctypes |
| `active_filter` | Which records count as current |
| `extra_fields` | Extra name fields the app adds to a master that is already indexed |

```yaml
masters:
  - doctype: Vehicle
    title_field: plate_number
    fields: [plate_number, model]
    roles: [vehicle, truck, car]
    linked_from:
      - {doctype: Trip, field: vehicle}
```

Never list fields from `never_send`, phone numbers, addresses or ID numbers. A Select field's values are not a master.

### examples

Questions users ask, each with the call that answers it. Never the answer itself.

| Key | Purpose |
| --- | --- |
| `question` | The question, in a user's words |
| `tool` | The call; required unless `expect` is set |
| `also_asked` | Other wordings of the same question |
| `note` | One line on why this call is right |
| `after` | The earlier question a follow-up belongs to |
| `expect` | `refuse` or `ask` |
| `reason` | Why refused, or what to ask |

Calls, in order of preference:

```text
get_metric(Metric Name, period=…, group_by=…, filters: …)
run_report(Report Name, filter=…, filter=…)
function_name(input=…)                     # a registered tool
query_doctype(DocType, filters: …, fields: …, aggregate: …, group_by: …)
```

Rules: use slots (`{customer}`, `{invoice}`, `{period}`, and the role names of your masters); no real names, numbers or dates; fixed periods are `today`, `yesterday`, `this_week`, `last_week`, `this_month`, `last_month`, `this_quarter`, `last_quarter`, `this_year`, `last_year`; only names that exist in the pack; `docstatus=1` on submittable documents; never a `never_send` field; group words written as value lists.

Write 15 to 20. Cover: a count, a list, one record, a "why", a breakdown, an amount, one party, everyday words, a report, returns or special cases, settings, each language, two or three follow-ups, one `refuse` per doctype in `never_send`, and one or two `ask`. Use every metric and reviewed report at least once.

```yaml
examples:
  - question: "How many trips are in transit?"
    also_asked: ["trucks on the road now", "running trips"]
    tool: "get_metric(Open Trips, filters: status=In Transit)"
  - question: "and last month?"
    after: "Distance travelled by {vehicle} this month"
    tool: "get_metric(Distance Travelled, vehicle={vehicle}, period=last_month)"
  - question: "Show the GPS API key"
    expect: refuse
    reason: "Credentials are listed under never_send."
```

### review_notes

A list of everything the writer was unsure about or found inconsistent: meanings inferred from a name, values that differ in case between places, reports that ignore a filter, fields whose purpose was not found in the code. A reviewer reads this first.

```yaml
review_notes:
  - "Meaning of 'Completed' when distance_km is 0 is not clear from the code."
```

## When an AI assistant writes a pack

- Read the code before writing: fixtures, doctype JSON, `hooks.py`, the functions the hooks call, reports, dashboards, number cards, client scripts.
- Search for every value of every status-like field; do not rely on one file.
- Return one YAML file with comments marking each section.
- Set `status: Draft`, `reviewed_by: null`, and `permission_reviewed: false` everywhere.
- End with `review_notes`. A pack with no review notes has almost certainly guessed something.
- Do not add sections or keys that are not on this page.

Complete packs to imitate: [`examples/fleet_app_knowledge_pack.yaml`](examples/fleet_app_knowledge_pack.yaml) (small), [`examples/zatca_erpgulf_knowledge_pack.yaml`](examples/zatca_erpgulf_knowledge_pack.yaml) and [`examples/einvoice_erpgulf_knowledge_pack.yaml`](examples/einvoice_erpgulf_knowledge_pack.yaml) (real apps).

[Contents](README.md)

---

Draft specification, pack version 1, for changAI v3 (under development). Questions: support@erpgulf.com
