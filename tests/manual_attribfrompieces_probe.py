"""Diagnostic: validate the CORRECT variant-scatter architecture on real H21.

USER CORRECTION (decisive):
  - Do NOT use Pack. Copy to Points `idattrib` dispatches on UNPACKED source
    geometry directly (source prim `variant` attr matches target point
    `variant` attr).
  - The real dispatch failure was that scatter points only carried variant
    0/1 (seed=42, 8 pts) so variant 2 (win_c) was never requested — NOT a
    dispatch mechanism failure.
  - `attribfrompieces` is the right tool to give target points a `variant`
    attribute drawn from the source piece library (pieceattrib=variant,
    mode=random/weighted).

This script builds the corrected chain and confirms:
  1. Copy to Points dispatches correctly on UNPACKED source (no pack node).
  2. attribfrompieces assigns target points a `variant` from the source.
  3. After copy + unpack, prims carry both `variant` and `id`.

HOW TO RUN (Houdini 21 Python Shell):
    >>> exec(open('tests/manual_attribfrompieces_probe.py').read())
"""
import hou

print("=" * 70)
print("CORRECTED ARCHITECTURE PROBE — Houdini", hou.applicationVersionString())
print("=" * 70)

_obj = hou.node("/obj")
_geo = _obj.createNode("geo", "edini_correct_probe")


def _make_variant_geo(parent, name, variant_idx, tx):
    """One polygon per variant, tagged with a PRIM `variant` int."""
    py = parent.createNode("python", name)
    py.parm("python").set(
        "node = hou.pwd()\n"
        "geo = node.geometry()\n"
        "geo.clear()\n"
        "geo.addAttrib(hou.attribType.Prim, 'variant', 0)\n"
        "geo.addAttrib(hou.attribType.Prim, 'component_id', '')\n"
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


v0 = _make_variant_geo(_geo, "win_a", 0, 0)
v1 = _make_variant_geo(_geo, "win_b", 1, 2)
v2 = _make_variant_geo(_geo, "win_c", 2, 4)

# ── Merge the 3 variants (NO pack) ───────────────────────────────────────
merge = _geo.createNode("merge", "variants_merge")
merge.setInput(0, v0)
merge.setInput(1, v1)
merge.setInput(2, v2)
merge.cook(force=True)
mg = merge.geometry()
print("\n[MERGE] prims:", mg.intrinsicValue("primitivecount"),
      "each prim variant:",
      [p.attribValue("variant") for p in mg.prims()])

# ── Scatter points (8 points, NO variant yet) ────────────────────────────
scatter = _geo.createNode("python", "scatter_points")
scatter.parm("python").set(
    "node = hou.pwd()\n"
    "geo = node.geometry()\n"
    "geo.clear()\n"
    "geo.addAttrib(hou.attribType.Point, 'id', 0)\n"
    "for idx in range(8):\n"
    "    pt = geo.createPoint()\n"
    "    pt.setPosition((idx * 1.0, 0.0, 5.0))\n"
    "    pt.setAttribValue('id', idx)\n"
)
scatter.cook(force=True)
sg = scatter.geometry()
print("[SCATTER] points:", sg.intrinsicValue("pointcount"),
      "has variant attr?", sg.findPointAttrib("variant") is not None)

# ── attribfrompieces: give target points a `variant` from the source ─────
print("\n[ATTRIBFROMPIECES] trying to assign variant to scatter points...")
afp = _geo.createNode("attribfrompieces", "afp")
# Input 0 = target points (scatter), input 1 = source piece library (merge).
# (Houdini's AFP convention: first input = points to fill, second = pieces.)
afp.setInput(0, scatter)
afp.setInput(1, merge)
afp.parm("pieceattrib").set("variant")
try:
    afp.parm("mode").set(0)  # try mode 0 first; see AFP docs for the menu
except Exception as e:
    print("  set mode failed:", e)
afp.cook(force=True)
ag = afp.geometry()
print("  AFP errors:", list(afp.errors() or []))
print("  AFP warnings:", list(afp.warnings() or []))
print("  AFP output points:", ag.intrinsicValue("pointcount"))
print("  AFP output has variant attr?", ag.findPointAttrib("variant") is not None)
if ag.findPointAttrib("variant") is not None:
    from collections import Counter as _C
    _tally = _C(pt.attribValue("variant") for pt in ag.points())
    print("  per-point variant tally after AFP:", dict(sorted(_tally.items())))

# ── Copy to Points: dispatch UNPACKED source by `variant` ────────────────
print("\n[COPY] dispatch on UNPACKED source by variant...")
copy = _geo.createNode("copytopoints::2.0", "copy_dispatch")
copy.setInput(0, merge)       # UNPACKED variant library (source)
copy.setInput(1, afp)         # scatter points WITH variant attr (target)
copy.parm("useidattrib").set(1)
copy.parm("idattrib").set("variant")
copy.cook(force=True)
cg = copy.geometry()
print("  COPY errors:", list(copy.errors() or []))
print("  COPY output points:", cg.intrinsicValue("pointcount"),
      "prims:", cg.intrinsicValue("primitivecount"))
if cg.findPrimAttrib("variant") is not None:
    from collections import Counter as _C
    _ptally = _C(p.attribValue("variant") for p in cg.prims())
    print("  per-prim variant tally on COPY output:", dict(sorted(_ptally.items())))
else:
    print("  COPY output has NO variant prim attr")

# ── resettargetattribs to transfer id ────────────────────────────────────
print("\n[COPY+resettargetattribs] press button to init attribute transfer...")
copy.parm("resettargetattribs").pressButton()
copy.cook(force=True)
cg2 = copy.geometry()
print("  targetattribs value:", copy.parm("targetattribs").eval())
print("  useapply1:", copy.parm("useapply1").eval(),
      "applymethod1:", copy.parm("applymethod1").eval())
print("  applyattribs1:", repr(copy.parm("applyattribs1").eval()))
if cg2.findPointAttrib("id") is not None:
    from collections import Counter as _C
    _ids = sorted(set(pt.attribValue("id") for pt in cg2.points()))
    print("  unique ids on COPY output points:", _ids)
else:
    print("  NO id attr on COPY output — transfer did not work")

print("\n" + "=" * 70)
print("DECISION POINTS")
print("=" * 70)
print("1. Did AFP give scatter points a `variant` attr covering 0,1,2?")
print("2. Did Copy dispatch correctly (3 distinct variants present)?")
print("3. After resettargetattribs, is `id` present on output points?")
print("4. Which AFP input order + mode value worked?")

try:
    _geo.destroy()
except Exception:
    pass
print("\n(throwaway /obj/edini_correct_probe removed)")
