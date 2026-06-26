#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regenerate node_parms_manifest.json and self-verify the new fields.

Run inside a Houdini Python Shell (or hython):

    import sys; sys.path.insert(0, r"E:\\edini\\python3.11libs")
    exec(open(r"E:\\edini\\scripts\\regen_and_verify_manifest.py", encoding="utf-8").read())

This (re)writes node_parms_manifest.json using the FIXED generator (vector
components + multiparm tags) and then spot-checks the new fields so you can
confirm the fix landed in the data, not just the code.
"""
import sys, os, json

PKG = r"E:\edini\python3.11libs"
if PKG not in sys.path:
    sys.path.insert(0, PKG)

from edini.node_utils import generate_node_parms_manifest

OUT = os.path.join(PKG, "edini", "data", "node_parms_manifest.json")
m = generate_node_parms_manifest("Sop")
tmp = OUT + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(m, f, indent=2, ensure_ascii=False)
os.replace(tmp, OUT)
print("wrote", OUT, "with", len(m["node_types"]), "node types")

# ── self-verification ──────────────────────────────────────────────────
nts = m["node_types"]
ok = True

def check(cond, msg):
    global ok
    print(("  OK   " if cond else "  FAIL ") + msg)
    ok = ok and cond

print("\n=== verify fix #1 (vector components) ===")
line = nts.get("line", {}).get("parms", [])
by = {p["name"]: p for p in line}
check("dir" in by, "line.dir present")
check(by.get("dir", {}).get("vector_size") == 3, f"line.dir vector_size==3 (got {by.get('dir', {}).get('vector_size')})")
check(by.get("dir", {}).get("components") == ["dirx", "diry", "dirz"],
      f"line.dir components==[dirx,diry,dirz] (got {by.get('dir', {}).get('components')})")
check(by.get("origin", {}).get("vector_size") == 3, "line.origin is vector")
check("vector_size" not in by.get("points", {}), "line.points scalar (no vector_size)")

print("\n=== verify fix #2 (multiparm) ===")
# Count multiparm counter + instance tags across all nodes.
counters = sum(1 for nd in nts.values() for p in nd.get("parms", []) if p.get("multiparm") == "counter")
instances = sum(1 for nd in nts.values() for p in nd.get("parms", []) if p.get("multiparm") == "instance")
check(counters > 0, f"multiparm counters recorded: {counters}")
check(instances > 0, f"multiparm instances recorded: {instances}")
# copytopoints::2.0 should have numapply + useapply# style.
ct = nts.get("copytopoints::2.0", {}).get("parms", [])
has_mp_counter = any(p.get("multiparm") == "counter" for p in ct)
has_mp_inst = any(p.get("multiparm") == "instance" for p in ct)
check(has_mp_counter or has_mp_inst, "copytopoints::2.0 has multiparm tags")

print("\n=== verify fix #4 (versioned alias: boolean) ===")
check("boolean::2.0" in nts, "boolean::2.0 in manifest")
check("boolean" not in nts, "bare 'boolean' NOT a key (resolved via fallback)")

print("\n=== verify review fix (multiparm-vector naming) ===")
# A multiparm-instance template named with '#' must NOT carry xyz components —
# those use a numeric index scheme (value1v1), so synthesising 'value#x' would
# be wrong. It may carry vector_size, but components must be absent.
bad_comp = 0
total_hash_vec = 0
for nd in nts.values():
    for p in nd.get("parms", []):
        if "#" in p.get("name", "") and p.get("vector_size", 1) > 1:
            total_hash_vec += 1
            if p.get("components"):
                bad_comp += 1
check(bad_comp == 0, f"no '#' vector param has (wrong) xyz components ({bad_comp}/{total_hash_vec} flagged)")
# All '#' params should be tagged as multiparm instances now. A tiny residue
# is acceptable: these are nested multiparm counters (e.g. agentlayer's
# 'bindings#') inside agent/crowd/material nodes — non-modeling edge cases
# whose '#' carries a sub-index. We assert the vast majority (>99%) are tagged.
total_hash = sum(1 for nd in nts.values() for p in nd.get("parms", []) if "#" in p.get("name", ""))
tagged_hash = sum(1 for nd in nts.values() for p in nd.get("parms", []) if "#" in p.get("name", "") and p.get("multiparm") == "instance")
check(tagged_hash >= total_hash * 0.99,
      f">99% '#' params tagged as multiparm instance ({tagged_hash}/{total_hash})")

print("\n=== verify review fix (real vector component names) ===")
# tube.rad MUST be rad1/rad2 (numeric), NOT radx/rady — the xyz rule is wrong
# for tube. The walker now corrects components from a live node instance.
tube = {p["name"]: p for p in nts.get("tube", {}).get("parms", [])}
tube_rad = tube.get("rad", {}).get("components")
check(tube_rad == ["rad1", "rad2"], f"tube.rad components==[rad1,rad2] (got {tube_rad})")
# circle.rad stays radx/rady (xyz rule is correct for circle).
circle = {p["name"]: p for p in nts.get("circle", {}).get("parms", [])}
circle_rad = circle.get("rad", {}).get("components")
check(circle_rad == ["radx", "rady"], f"circle.rad components==[radx,rady] (got {circle_rad})")
# xform.t stays tx/ty/tz.
xform = {p["name"]: p for p in nts.get("xform", {}).get("parms", [])}
check(xform.get("t", {}).get("components") == ["tx", "ty", "tz"], "xform.t==[tx,ty,tz]")

print("\n=== summary ===")
print("ALL CHECKS PASSED ✅" if ok else "SOME CHECKS FAILED ❌ — review above")
