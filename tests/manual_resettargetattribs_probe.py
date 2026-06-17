"""Diagnostic: capture what `resettargetattribs` button does to the Copy to
Points 2.0 `targetattribs` Folder multiparm on real Houdini 21.

USER INSIGHT: creating copytopoints then pressing the `resettargetattribs`
button auto-populates the whole targetattribs parameter set. This script
captures EXACTLY what parms appear after the press, so the harness can
replicate it programmatically.

HOW TO RUN (Houdini 21 Python Shell):
    >>> exec(open('tests/manual_resettargetattribs_probe.py').read())

Excluded from pytest/unittest collection (matches manual_* in conftest.py).
"""
import hou

print("=" * 70)
print("RESETTARGETATTRIBS PROBE — Houdini", hou.applicationVersionString())
print("=" * 70)

_obj = hou.node("/obj")
_geo = _obj.createNode("geo", "edini_reset_probe")
copy = _geo.createNode("copytopoints::2.0", "copy")

def _dump(label):
    print(f"\n{'─' * 70}\n{label}\n{'─' * 70}")
    parms = copy.parms()
    # Show all targetattribs-related + apply-related parms.
    related = []
    for p in parms:
        pn = p.name()
        if ("targetattrib" in pn.lower() or "apply" in pn.lower()
                or pn.lower().startswith("num")):
            related.append(p)
    print(f"({len(related)} targetattrib/apply/num parms)")
    for p in related:
        try:
            ttype = p.parmTemplate().type().name()
        except Exception:
            ttype = "?"
        try:
            val = p.eval()
        except Exception:
            val = "<unevaluated>"
        # For multiparm instance parms, show the value.
        print(f"  {p.name():30s} type={ttype:10s} value={val!r}")

# ── 1. BEFORE pressing the button ────────────────────────────────────────
_dump("BEFORE resettargetattribs press")

# ── 2. Press the button ──────────────────────────────────────────────────
print("\n>>> pressing resettargetattribs...")
reset = copy.parm("resettargetattribs")
if reset is None:
    print("  resettargetattribs parm NOT FOUND — aborting")
else:
    try:
        reset.pressButton()
        print("  pressButton() returned OK")
    except Exception as e:
        print(f"  pressButton() FAILED: {e}")

# ── 3. AFTER pressing the button ─────────────────────────────────────────
_dump("AFTER resettargetattribs press")

# ── 4. Is targetattribs now a multiparm with instances? ─────────────────
ta = copy.parm("targetattribs")
if ta is not None:
    print("\n[targetattribs] multiparm introspection:")
    for attr in ("isMultiparm", "numInstances", "multiParmStartLength"):
        fn = getattr(ta, attr, None)
        if callable(fn):
            try:
                print(f"  {attr}() = {fn()}")
            except Exception as e:
                print(f"  {attr}() raised: {e}")
        else:
            print(f"  {attr}: <not available>")

# ── 5. Raw dump of ALL parms after press (to catch any new ones) ─────────
print("\n[ALL PARMS AFTER PRESS] (name : value)")
for p in copy.parms():
    try:
        val = p.eval()
    except Exception:
        val = "?"
    # Skip noisy transform/group parms; show the structural ones.
    pn = p.name()
    if any(k in pn.lower() for k in ("targetattrib", "apply", "num", "piece", "idattrib")):
        print(f"  {pn}: {val!r}")

print("\n" + "=" * 70)
print("WHAT WE NEED TO KNOW:")
print("1. After press, what is targetattribs's multiparm instance count?")
print("2. What are the per-instance parm names (e.g. useapply1/applyattribs1)?")
print("3. Can we set applyattribs1='id' (or equivalent) to transfer id?")
print("=" * 70)

try:
    _geo.destroy()
except Exception:
    pass
print("\n(throwaway /obj/edini_reset_probe removed)")
