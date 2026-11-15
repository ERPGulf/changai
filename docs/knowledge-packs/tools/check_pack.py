#!/usr/bin/env python3
"""Check a changAI knowledge pack against the app it describes.

Usage, from your app's module folder (the one that contains hooks.py):

    python check_pack.py changai/knowledge_pack.yaml

It checks that:
  1. the file is valid YAML and has the required sections;
  2. every field named under `doctypes`, `status_field(s)` and `never_send`
     exists in the app's fixtures or doctype files;
  3. every topic points to something that exists in the pack;
  4. every example uses a metric, report, tool or doctype defined in the pack;
  5. no example asks for a field listed under `never_send`.

It reads only local files. Nothing is sent anywhere.
"""
import glob
import json
import re
import sys

import yaml

REQUIRED = ["pack_version", "app", "status", "overview", "flow", "topics"]
BUILT_IN_CALLS = ("get_metric", "run_report", "query_doctype")


def app_fields():
    """(doctype, fieldname) pairs defined by this app: custom fields and its own doctypes."""
    have, own_doctypes = set(), set()
    for path in set(glob.glob("**/fixtures/custom_field.json", recursive=True)):
        for f in json.load(open(path)):
            have.add((f.get("dt"), f.get("fieldname")))
    for path in glob.glob("**/doctype/*/*.json", recursive=True):
        d = json.load(open(path))
        if d.get("doctype") != "DocType":
            continue
        own_doctypes.add(d["name"])
        for f in d.get("fields", []):
            have.add((d["name"], f.get("fieldname")))
    return have, own_doctypes


def status_entries(pack):
    if "status_field" in pack:
        yield pack["status_field"]
    for entry in pack.get("status_fields", []) or []:
        yield entry


def main(path):
    problems, warnings = [], []
    try:
        pack = yaml.safe_load(open(path))
    except yaml.YAMLError as e:
        print("Not valid YAML:", e)
        return 1

    for key in REQUIRED:
        if key not in pack:
            problems.append(f"missing required section: {key}")

    have, own_doctypes = app_fields()
    if not have:
        warnings.append("no fixtures or doctype files found here; run this from your app's module folder")

    # 2. fields
    for dt, entry in (pack.get("doctypes") or {}).items():
        for fn in (entry.get("fields") or {}):
            if (dt, fn) not in have:
                problems.append(f"doctypes: {dt}.{fn} is not a field this app defines")
    for entry in status_entries(pack):
        for dt in entry.get("doctypes", []):
            if (dt, entry.get("fieldname")) not in have:
                problems.append(f"status field: {dt}.{entry.get('fieldname')} is not a field this app defines")
    never = set()
    for dt, fields in (pack.get("never_send") or {}).items():
        for fn in fields:
            never.add(fn)
            if (dt, fn) not in have:
                problems.append(f"never_send: {dt}.{fn} is not a field this app defines")
    for dt in (pack.get("app_doctypes") or {}):
        if own_doctypes and dt not in own_doctypes:
            problems.append(f"app_doctypes: {dt} is not a doctype of this app")

    # 3. topics
    for topic, refs in (pack.get("topics") or {}).items():
        for ref in refs:
            parts = ref.split(".")
            ok = parts[0] in pack
            if ok and parts[0] in ("doctypes", "app_doctypes") and len(parts) > 1:
                ok = parts[1] in pack[parts[0]]
                if ok and parts[0] == "doctypes" and len(parts) > 2:
                    ok = parts[2] in (pack["doctypes"][parts[1]].get("fields") or {})
            if not ok:
                problems.append(f"topics: '{topic}' points to {ref}, which is not in the pack")

    # 4 and 5. examples
    metrics = {m["name"] for m in pack.get("metrics") or []}
    reports = {r["report"] for r in pack.get("reports") or []}
    tools = {t["function"].split(".")[-1] for t in pack.get("tools") or []}
    described = set(pack.get("doctypes") or {}) | set(pack.get("app_doctypes") or {})
    examples = pack.get("examples") or []
    for ex in examples:
        q = ex.get("question", "?")
        if ex.get("expect") in ("refuse", "ask"):
            if not ex.get("reason"):
                warnings.append(f"example '{q}': expect is set but there is no reason")
            continue
        m = re.match(r"(\w+)\((.*)\)\s*$", ex.get("tool", ""), re.S)
        if not m:
            problems.append(f"example '{q}': tool is not written as name(...)")
            continue
        name, args = m.group(1), m.group(2)
        first = args.split(",")[0].strip()
        if name == "get_metric" and first not in metrics:
            problems.append(f"example '{q}': unknown metric '{first}'")
        elif name == "run_report" and first not in reports:
            problems.append(f"example '{q}': unknown report '{first}'")
        elif name == "query_doctype" and first not in described:
            problems.append(f"example '{q}': doctype '{first}' is not described in the pack")
        elif name not in BUILT_IN_CALLS and name not in tools:
            problems.append(f"example '{q}': unknown tool '{name}'")
        for word in re.findall(r"[a-z_][a-z0-9_]+", args):
            if word in never:
                problems.append(f"example '{q}': asks for '{word}', which is under never_send")

    used = " ".join(ex.get("tool", "") for ex in examples)
    for name in sorted(metrics):
        if name not in used:
            warnings.append(f"metric '{name}' is not used in any example")
    for name in sorted(reports):
        if name not in used:
            warnings.append(f"report '{name}' is not used in any example")
    if pack.get("status") == "Reviewed" and not pack.get("reviewed_by"):
        warnings.append("status is Reviewed but reviewed_by is empty")

    print(f"{path}: {len(examples)} examples, {len(metrics)} metrics, {len(reports)} reports")
    for p in problems:
        print("  PROBLEM:", p)
    for w in warnings:
        print("  note:", w)
    print("OK" if not problems else f"{len(problems)} problem(s) to fix")
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
