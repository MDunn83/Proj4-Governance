#!/usr/bin/env python3
"""
Validation script for proj4_governance_workflow.json
Checks:
  a. JSON is valid and parseable
  b. All node names referenced in connections exist in nodes array
  c. All $('NodeName') cross-node references in parameters exist as node names
  d. All Code nodes have 'mode' set
  e. HTTP Request nodes use typeVersion 4.2
  f. No node uses a 'system' role in messages arrays (body strings)
"""

import json
import re
import sys

WORKFLOW_FILE = "/home/user/Proj4-Governance/proj4_governance_workflow.json"

results = {
    "pass": [],
    "fail": [],
    "info": [],
}


def ok(msg):
    results["pass"].append(msg)


def fail(msg):
    results["fail"].append(msg)


def info(msg):
    results["info"].append(msg)


# ---------------------------------------------------------------------------
# CHECK A: JSON validity
# ---------------------------------------------------------------------------
try:
    with open(WORKFLOW_FILE, "r", encoding="utf-8") as f:
        workflow = json.load(f)
    ok("CHECK A: JSON is valid and parseable")
except json.JSONDecodeError as e:
    fail(f"CHECK A: JSON parse error: {e}")
    sys.exit(1)
except FileNotFoundError:
    fail(f"CHECK A: File not found: {WORKFLOW_FILE}")
    sys.exit(1)

nodes = workflow.get("nodes", [])
connections = workflow.get("connections", {})

# Build a set of all node names that actually exist
node_names = {n["name"] for n in nodes}
info(f"  Node names found: {sorted(node_names)}")

# ---------------------------------------------------------------------------
# CHECK B: All connection source/target names exist in nodes array
# ---------------------------------------------------------------------------
b_pass = True

# Source keys in connections must be valid node names
for source_name in connections:
    if source_name not in node_names:
        fail(f"CHECK B: Connection source '{source_name}' not found in nodes array")
        b_pass = False

# Target node names inside each connection must also be valid
for source_name, outputs in connections.items():
    for output_group in outputs.get("main", []):
        for edge in output_group:
            target = edge.get("node")
            if target not in node_names:
                fail(
                    f"CHECK B: Connection target '{target}' (from '{source_name}') "
                    f"not found in nodes array"
                )
                b_pass = False

if b_pass:
    ok("CHECK B: All connection source/target names exist in nodes array")

# ---------------------------------------------------------------------------
# Helpers to recursively extract all string values from a dict/list
# ---------------------------------------------------------------------------

def iter_strings(obj):
    """Yield all string leaf values from a nested dict/list structure."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from iter_strings(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from iter_strings(item)


# ---------------------------------------------------------------------------
# CHECK C: $('NodeName') cross-node references all resolve
# ---------------------------------------------------------------------------
# Pattern: $('NodeName') or $("NodeName")
node_ref_pattern = re.compile(r"""\$\(\s*['"]([^'"]+)['"]\s*\)""")

c_pass = True
c_issues = []

for node in nodes:
    node_name = node["name"]
    params = node.get("parameters", {})
    for s in iter_strings(params):
        for match in node_ref_pattern.finditer(s):
            ref = match.group(1)
            if ref not in node_names:
                msg = (
                    f"CHECK C: Node '{node_name}' references unknown node "
                    f"$(''{ref}'') in parameters"
                )
                c_issues.append(msg)
                fail(msg)
                c_pass = False

if c_pass:
    ok("CHECK C: All $('NodeName') cross-node references resolve to existing nodes")
else:
    # Also list valid refs for context
    all_refs = set()
    for node in nodes:
        for s in iter_strings(node.get("parameters", {})):
            for match in node_ref_pattern.finditer(s):
                all_refs.add((node["name"], match.group(1)))
    info(f"  Cross-node references found: {sorted(all_refs)}")

# ---------------------------------------------------------------------------
# CHECK D: All Code nodes have 'mode' set
# ---------------------------------------------------------------------------
d_pass = True

for node in nodes:
    if node.get("type") == "n8n-nodes-base.code":
        mode = node.get("parameters", {}).get("mode")
        if not mode:
            fail(
                f"CHECK D: Code node '{node['name']}' is missing 'mode' "
                f"in parameters"
            )
            d_pass = False
        else:
            valid_modes = {"runOnceForEachItem", "runOnceForAllItems"}
            if mode not in valid_modes:
                fail(
                    f"CHECK D: Code node '{node['name']}' has unrecognised mode "
                    f"'{mode}' (expected one of {valid_modes})"
                )
                d_pass = False
            else:
                info(f"  Code node '{node['name']}' mode = '{mode}'")

if d_pass:
    ok("CHECK D: All Code nodes have a valid 'mode' set")

# ---------------------------------------------------------------------------
# CHECK E: HTTP Request nodes use typeVersion 4.2
# ---------------------------------------------------------------------------
e_pass = True

for node in nodes:
    if node.get("type") == "n8n-nodes-base.httpRequest":
        tv = node.get("typeVersion")
        if tv != 4.2:
            fail(
                f"CHECK E: HTTP Request node '{node['name']}' has typeVersion "
                f"{tv!r} (expected 4.2)"
            )
            e_pass = False
        else:
            info(f"  HTTP Request node '{node['name']}' typeVersion = {tv}")

if e_pass:
    ok("CHECK E: All HTTP Request nodes use typeVersion 4.2")

# ---------------------------------------------------------------------------
# CHECK F: No 'system' role in messages arrays inside body strings
# ---------------------------------------------------------------------------
# We look for patterns like:
#   "role": "system"    (JSON inside body string)
#   role: 'system'      (JS object literal)
#   role: "system"      (JS object literal)
system_role_pattern = re.compile(
    r"""['"]?role['"]?\s*:\s*['"]system['"]""",
    re.IGNORECASE,
)

f_pass = True

for node in nodes:
    params = node.get("parameters", {})
    for s in iter_strings(params):
        if system_role_pattern.search(s):
            fail(
                f"CHECK F: Node '{node['name']}' contains a 'system' role in a "
                f"messages/body string — Groq qwen3 does not reliably support "
                f"the system role"
            )
            f_pass = False

if f_pass:
    ok("CHECK F: No 'system' role found in any node's body/messages strings")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print("VALIDATION RESULTS")
print("=" * 60)

print(f"\nPASSED ({len(results['pass'])}):")
for m in results["pass"]:
    print(f"  PASS  {m}")

if results["fail"]:
    print(f"\nFAILED ({len(results['fail'])}):")
    for m in results["fail"]:
        print(f"  FAIL  {m}")
else:
    print("\nFAILED (0): none")

print(f"\nINFO ({len(results['info'])}):")
for m in results["info"]:
    print(f"  INFO  {m}")

print("\n" + "=" * 60)
if results["fail"]:
    print(f"OVERALL: {len(results['fail'])} check(s) FAILED")
    sys.exit(1)
else:
    print("OVERALL: ALL CHECKS PASSED")
    sys.exit(0)
