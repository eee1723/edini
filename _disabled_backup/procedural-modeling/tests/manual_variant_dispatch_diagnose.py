"""Diagnostic: pinpoint why Copy to Points 2.0 piece-attribute dispatch
collapses variant instances on real Houdini 21.

SYMPTOM (observed in manual_variant_scatter_test.py on H21.0.440):
  3 variants, 8 scatter points (weighted 0.6/0.3/0.1, seed=42), but Copy to
  Points produced only 2 instances (win_a x1, win_b x1) and win_c vanished.
  Expected ~5 win_a / ~2 win_b / ~1 win_c.

This script builds the EXACT chain (scatter points → pack by name → copy to
points) and inspects each stage's attributes/counts so we can see WHERE the
dispatch collapses. It also probes `targetattribs` (the real H21 attribute-
transfer parm, which replaced the Apply Attributes multiparm).

HOW TO RUN (Houdini 21 Python Shell):
    >>> exec(open('tests/manual_variant_dispatch_diagnose.py').read())

Excluded from pytest/unittest collection (matches manual_* in conftest.py).
"""
import hou

print("=" * 70)
print("VARIANT DISPATCH DIAGNOSTIC — Houdini", hou.applicationVersionString())
print("=" * 70)

_obj = hou.node("/obj")
_geo = _obj.createNode("geo", "edini_dispatch_diag")

# ── 1. Three variant sources, each a box tagged with a Prim `variant` int ──
#   Mirrors _variant_tag_code: variant is a PRIM attribute.
def _make_variant_box(parent, name, variant_idx, tx):
    py = parent.createNode("python", name)
    py.parm("python").set(
        "node = hou.pwd()\n"
        "geo = node.geometry()\n"
        "geo.clear()\n"
        "geo.addAttrib(hou.attribType.Prim, 'variant', 0)\n"
        "geo.addAttrib(hou.attribType.Prim, 'component_id', '')\n"
        # A single-prim "box" (one polygon) so prim count is unambiguous.
        f"import math\n"
        "pts = [geo.createPoint() for _ in range(4)]\n"
        f"for i,p in enumerate(pts):\n"
        f"    p.setPosition(({tx} - 0.5 + (i % 2), 0.0, -0.5 + (i // 2)))\n"
        "poly = geo.createPolygon()\n"
        "for p in pts:\n"
        "    poly.addVertex(p)\n"
        f"poly.setAttribValue('variant', {variant_idx})\n"
        f"poly.setAttribValue('component_id', '{name}')\n"
    )
    py.cook(force=True)
    return py

v0 = _make_variant_box(_geo, "win_a", 0, 0)
v1 = _make_variant_box(_geo, "win_b", 1, 2)
v2 = _make_variant_box(_geo, "win_c", 2, 4)

merge = _geo.createNode("merge", "variants_merge")
merge.setInput(0, v0)
merge.setInput(1, v1)
merge.setInput(2, v2)
merge.cook(force=True)
mg = merge.geometry()
print("\n[MERGE] points:", mg.intrinsicValue("pointcount"),
      "prims:", mg.intrinsicValue("primitivecount"))
# Show variant attribute class/type on the merged geo.
for cls_name, cls in (("Prim", hou.attribType.Prim), ("Point", hou.attribType.Point)):
    a = mg.findPrimAttrib("variant") if cls == hou.attribType.Prim else mg.findPointAttrib("variant")
    if a is not None:
        print(f"  variant attrib present as {cls_name}, dataType={a.dataType()}")

# ── 2. Pack By Name on the `variant` prim attribute ──────────────────────
pack = _geo.createNode("pack", "variants_pack")
pack.setInput(0, merge)
pack.parm("packbyname").set(1)
pack.parm("nameattribute").set("variant")
pack.cook(force=True)
pg = pack.geometry()
print("\n[PACK] packed prims:", pg.intrinsicValue("primitivecount"),
      "points:", pg.intrinsicValue("pointcount"))
# On the packed geo, what class/type is `variant` now?
for cls_name, finder in (("Prim", pg.findPrimAttrib), ("Point", pg.findPointAttrib),
                         ("Detail", pg.findGlobalAttrib)):
    a = finder("variant")
    if a is not None:
        print(f"  variant attrib on packed geo: class={cls_name} dataType={a.dataType()}")
# List each packed prim's variant value (if readable as prim attrib).
print("  per-packed-prim variant values:")
for prim in pg.prims():
    try:
        vv = prim.attribValue("variant")
    except Exception as e:
        vv = f"<unreadable: {e}>"
    print(f"    prim {prim.number()}: variant={vv!r} type={prim.type().name()}")

# ── 3. Scatter points: 8 points with Point `variant` int (weighted) ──────
scatter = _geo.createNode("python", "scatter_points")
import random as _r
_thresholds = [0.6, 0.9, 1.0]
_rng = _r.Random(42)
_scatter_src = (
    "node = hou.pwd()\n"
    "geo = node.geometry()\n"
    "geo.clear()\n"
    "geo.addAttrib(hou.attribType.Point, 'variant', 0)\n"
    "geo.addAttrib(hou.attribType.Point, 'id', 0)\n"
    "import random\n"
    "_thresholds = [0.6, 0.9, 1.0]\n"
    "_rng = random.Random(42)\n"
    "for idx in range(8):\n"
    "    pt = geo.createPoint()\n"
    "    pt.setPosition((idx * 1.0, 0.0, 5.0))\n"
    "    r = _rng.random()\n"
    "    chosen = 2\n"
    "    for ti, thr in enumerate(_thresholds):\n"
    "        if r <= thr:\n"
    "            chosen = ti\n"
    "            break\n"
    "    pt.setAttribValue('variant', chosen)\n"
    "    pt.setAttribValue('id', idx)\n"
)
scatter.parm("python").set(_scatter_src)
scatter.cook(force=True)
sg = scatter.geometry()
print("\n[SCATTER] points:", sg.intrinsicValue("pointcount"))
# Tally the per-point variant values the wrapper assigned.
_tally = {}
for pt in sg.points():
    v = pt.attribValue("variant")
    _tally[v] = _tally.get(v, 0) + 1
print("  per-point variant tally (expected ~5 win_a / ~2 win_b / ~1 win_c):",
      dict(sorted(_tally.items())))

# ── 4. Copy to Points with piece-attribute dispatch ─────────────────────
copy = _geo.createNode("copytopoints::2.0", "copy_dispatch")
copy.setInput(0, pack)       # packed variant library
copy.setInput(1, scatter)    # scatter points
copy.parm("useidattrib").set(1)
copy.parm("idattrib").set("variant")
copy.cook(force=True)
cg = copy.geometry()
print("\n[COPY] points:", cg.intrinsicValue("pointcount"),
      "prims:", cg.intrinsicValue("primitivecount"))
# How many packed instances did Copy produce? (each instance = 1 packed prim)
_n_packed_inst = sum(1 for p in cg.prims() if p.type().name() == "Packed")
print("  packed-primitive instances produced:", _n_packed_inst)
# Variant distribution among produced instances.
_inst_tally = {}
for p in cg.prims():
    if p.type().name() != "Packed":
        continue
    try:
        vv = p.attribValue("variant")
    except Exception:
        vv = "<none>"
    _inst_tally[vv] = _inst_tally.get(vv, 0) + 1
print("  instance variant tally:", dict(sorted(_inst_tally.items())))

# ── 5. targetattribs probe (the real H21 transfer mechanism) ────────────
print("\n[TARGETATTRIBS] the real H21 attribute-transfer parm:")
_ta = copy.parm("targetattribs")
if _ta is not None:
    try:
        _tm = _ta.parmTemplate()
        print("  label:", _tm.label(), "type:", _tm.type().name())
        print("  default:", repr(_tm.defaultValue()))
    except Exception as _e:
        print("  template introspect failed:", _e)
    print("  current eval:", repr(_ta.eval()))
    # Try setting it to transfer `id`.
    try:
        _ta.set("id")
        print("  after set('id'):", repr(_ta.eval()))
    except Exception as _e:
        print("  set('id') failed:", _e)
else:
    print("  targetattribs NOT FOUND")

# ── 6. Re-cook copy WITH targetattribs='id' and check id transfer ───────
if _ta is not None:
    try:
        _ta.set("id")
        copy.cook(force=True)
        cg2 = copy.geometry()
        _ids = set()
        for pt in cg2.points():
            try:
                _ids.add(int(pt.attribValue("id")))
            except Exception:
                pass
        print("\n[COPY+targetattribs=id] unique ids on output points:",
              sorted(_ids))
    except Exception as _e:
        print("  re-cook with targetattribs failed:", _e)

# ── 7. Summary ──────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("DIAGNOSIS POINTS")
print("=" * 70)
print("1. Does pack(packbyname) yield 3 packed prims each carrying a readable")
print("   `variant` prim attrib? (see [PACK] above)")
print("2. Does Copy produce 8 packed instances matching the 8 scatter points?")
print("   If far fewer, piece-attribute dispatch is mismatching — likely the")
print("   packed prim's variant is not where Copy looks.")
print("3. targetattribs: if settable, that's the real id-transfer path.")

try:
    _geo.destroy()
except Exception:
    pass
print("\n(throwaway /obj/edini_dispatch_diag removed)")
