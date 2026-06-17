"""Manual real-Houdini test for houdini_variant_scatter.

HOW TO RUN (in Houdini 21):
  1. Open Windows > Python Source Editor
  2. Paste the ENTIRE contents of this file
  3. Ctrl+Enter to execute
  4. Watch the textport (Windows > Houdini Textport) for the report
  5. The built asset appears under /obj/edini_sandbox_..._test_scatter

WHAT IT TESTS:
  - 3 window-style variants (cylinder / box / torus) scattered onto 8 points
  - Weighted distribution (60/30/10) with seed=42 (reproducible)
  - The modern packed-primitive + piece-attribute workflow actually dispatches
    DIFFERENT geometry per point (this is the part the mock can't verify)
  - Per-instance component_id is assigned after unpack
  - fuse+clean+normal postprocess runs clean

EXPECTED RESULT:
  - 8 instances total, distributed ~5/2/1 across the 3 styles (with seed 42)
  - Each instance tagged with a unique component_id like win_a_0, win_b_3...
  - No cook errors
"""
import sys
import importlib

# --- make the edini package importable from the Houdini session ---
_EDINI_LIBS = r"E:\edini\python3.11libs"
if _EDINI_LIBS not in sys.path:
    sys.path.insert(0, _EDINI_LIBS)

# --- FORCE-RELOAD: Houdini caches edini.harness from a prior session.
# Without this, you get "module 'edini.harness' has no attribute
# 'build_variant_scatter'" because the old in-memory module is reused.
from edini import harness
importlib.reload(harness)
# Confirm the new function is present (fail loud if reload didn't take).
if not hasattr(harness, "build_variant_scatter"):
    raise RuntimeError(
        "edini.harness still lacks build_variant_scatter after reload. "
        "Either the file on disk wasn't updated, or Houdini is loading "
        "edini from a different path. Check: "
        "print(edini.harness.__file__)")
print("harness.__file__:", harness.__file__)
print("has build_variant_scatter:", hasattr(harness, "build_variant_scatter"))


# ── 3 window-style variants, each emits distinct geometry ──────────────
# Style A: a cylinder (tall narrow window)
WIN_A = (
    "import math\n"
    "node = hou.pwd(); geo = node.geometry(); geo.clear()\n"
    "geo.addAttrib(hou.attribType.Prim, 'component_id', '')\n"
    "geo.addAttrib(hou.attribType.Prim, 'material_zone', '')\n"
    "r, h, seg = 0.15, 1.0, 8\n"
    "pts = []\n"
    "for i in range(seg):\n"
    "    a = 2*math.pi*i/seg\n"
    "    for y in (0.0, h):\n"
    "        p = geo.createPoint(); p.setPosition((r*math.cos(a), y, r*math.sin(a))); pts.append(p)\n"
    "for i in range(seg):\n"
    "    j = (i+1) % seg\n"
    "    poly = geo.createPolygon()\n"
    "    for k in (i, j, j+seg, i+seg): poly.addVertex(pts[k])\n"
    "    poly.setAttribValue('component_id', 'win_a')\n"
    "    poly.setAttribValue('material_zone', 'glass_a')\n"
)

# Style B: a box (square window)
WIN_B = (
    "node = hou.pwd(); geo = node.geometry(); geo.clear()\n"
    "geo.addAttrib(hou.attribType.Prim, 'component_id', '')\n"
    "geo.addAttrib(hou.attribType.Prim, 'material_zone', '')\n"
    "w, h = 0.4, 0.6\n"
    "pts = []\n"
    "for x,y,z in [(-w,-h,0),(w,-h,0),(w,h,0),(-w,h,0),(-w,-h,0.08),(w,-h,0.08),(w,h,0.08),(-w,h,0.08)]:\n"
    "    p = geo.createPoint(); p.setPosition((x,y,z)); pts.append(p)\n"
    "for idx in ([0,3,2,1],[4,5,6,7],[0,1,5,4],[3,7,6,2],[0,4,7,3],[1,2,6,5]):\n"
    "    poly = geo.createPolygon()\n"
    "    for i in idx: poly.addVertex(pts[i])\n"
    "    poly.setAttribValue('component_id', 'win_b')\n"
    "    poly.setAttribValue('material_zone', 'glass_b')\n"
)

# Style C: a flat torus-ish ring (small round window)
WIN_C = (
    "import math\n"
    "node = hou.pwd(); geo = node.geometry(); geo.clear()\n"
    "geo.addAttrib(hou.attribType.Prim, 'component_id', '')\n"
    "geo.addAttrib(hou.attribType.Prim, 'material_zone', '')\n"
    "R, r, seg = 0.25, 0.08, 12\n"
    "pts = []\n"
    "for i in range(seg):\n"
    "    a = 2*math.pi*i/seg\n"
    "    for rr in (R, R-r):\n"
    "        p = geo.createPoint(); p.setPosition((rr*math.cos(a), rr*math.sin(a), 0)); pts.append(p)\n"
    "for i in range(seg):\n"
    "    j = (i+1) % seg\n"
    "    poly = geo.createPolygon()\n"
    "    for k in (2*i, 2*j, 2*j+1, 2*i+1): poly.addVertex(pts[k])\n"
    "    poly.setAttribValue('component_id', 'win_c')\n"
    "    poly.setAttribValue('material_zone', 'glass_c')\n"
)

# ── scatter source: a 2x4 grid of points with orient facing +Z ─────────
SCATTER = (
    "node = hou.pwd(); geo = node.geometry(); geo.clear()\n"
    "geo.addAttrib(hou.attribType.Point, 'orient', (0,0,0,1))\n"
    "geo.addAttrib(hou.attribType.Point, 'pscale', 1.0)\n"
    "for row in range(2):\n"
    "    for col in range(4):\n"
    "        pt = geo.createPoint()\n"
    "        pt.setPosition((col*0.8 - 1.2, row*1.2 + 0.5, 0))\n"
    "        pt.setAttribValue('orient', (0,0,0,1))\n"
    "        pt.setAttribValue('pscale', 1.0)\n"
)

recipe = {
    "asset_name": "test_scatter",
    "variants": [
        {"id": "win_a", "code": WIN_A},
        {"id": "win_b", "code": WIN_B},
        {"id": "win_c", "code": WIN_C},
    ],
    "scatter": {
        "source": SCATTER,
        "seed": 42,
        "weights": {"win_a": 0.6, "win_b": 0.3, "win_c": 0.1},
    },
    "postprocess": [
        {"type": "fuse"},
        {"type": "clean"},
        {"type": "normal", "params": {"cuspangle": 60}},
    ],
}

print("=" * 60)
print("VARIANT SCATTER TEST — 3 styles x 8 points, seed=42")
print("=" * 60)

r = harness.build_variant_scatter(recipe)
print("success:", r["success"])
print("build_mode:", r.get("build_mode"))

if not r["success"]:
    print("ERROR:", r.get("error", "")[:500])
    print("traceback:", r.get("traceback", "")[-800:])
else:
    print("\n── Network built ──")
    print("root:", r["root_path"])
    print("output:", r["output_node"])
    print("variants_built:", r["variants_built"])
    print("weights:", r["weights"])
    print("seed:", r["seed"])
    print("piece_attribute:", r["piece_attribute"])
    root = hou.node(r["root_path"])
    print("nodes:", sorted(c.name() for c in root.children()))

    print("\n── Diagnostics ──")
    diag = r.get("diagnostics", {})
    geo = diag.get("geometry", {})
    print("points:", geo.get("point_count"))
    print("prims:", geo.get("prim_count"))
    print("bounds:", geo.get("bounds", {}).get("size"))

    print("\n── Structure gate ──")
    sa = r.get("structure_advisory", {})
    print("passed:", sa.get("passed"))
    print("is_monolithic:", sa.get("is_monolithic"))
    print("modular_node_count:", sa.get("details", {}).get("modular_node_count"))

    print("\n── component_id check ──")
    print("ok:", r.get("component_id_check", {}).get("ok"))
    print("missing:", r.get("component_id_check", {}).get("missing"))

    if r.get("warnings"):
        print("\n── warnings ──")
        for w in r["warnings"]:
            print("  -", w)

    # ── Verify actual variant distribution on the real geometry ────────
    print("\n── REAL GEOMETRY INSPECTION (the part the mock can't do) ──")
    out = hou.node(r["output_node"])
    out_geo = out.geometry()
    # Count how many instances of each variant landed
    cid_attr = out_geo.findPrimAttrib("component_id")
    if cid_attr is not None:
        from collections import Counter
        cids = [prim.stringAttribValue("component_id") for prim in out_geo.prims()
                if prim.stringAttribValue("component_id")]
        prefixes = Counter(cid.split("_")[0] + "_" + cid.split("_")[1]
                            if "_" in cid else cid for cid in cids)
        # Actually count unique instance ids (each instance shares a prefix)
        instances = set(c.rsplit("_", 1)[0] if "_" in c else c for c in cids)
        inst_by_variant = Counter(i.split("_", 2)[0] + "_" + i.split("_", 2)[1]
                                   if i.count("_") >= 1 else i for i in instances)
        print("unique instance ids:", len(instances))
        print("instances per variant:", dict(inst_by_variant))
        print("(expected ~5 win_a, ~2 win_b, ~1 win_c with seed 42)")

    print("\n── DONE. Inspect the network at:", r["root_path"], "──")
    print("Set /obj display to", r["output_node"], "to see it in the viewport.")
