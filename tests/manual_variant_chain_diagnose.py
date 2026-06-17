"""Manual real-Houdini diagnostic: builds the variant-scatter chain NODE BY
NODE so you can inspect exactly where it works / breaks. This bypasses the
harness wrapper entirely — every node is created explicitly so you can click
through them in the network editor and see the geometry at each stage.

HOW TO RUN: paste into Windows > Python Source Editor, Ctrl+Enter.
The network is built under /obj/variant_diag — open it in the network editor
and click through each node in order to watch the variant dispatch happen.
"""
import hou

obj = hou.node("/obj")
# Clean slate: if a previous run left variant_diag behind, remove it first.
old = hou.node("/obj/variant_diag")
if old is not None:
    old.destroy()
geo = obj.createNode("geo", "variant_diag")

# ════════════════════════════════════════════════════════════════════════
# STAGE 1 — Two distinct variant geometries (a box + a sphere)
# ════════════════════════════════════════════════════════════════════════
va = geo.createNode("python", "variant_a")
va.parm("python").set(
    "node = hou.pwd(); geo = node.geometry(); geo.clear()\n"
    "geo.addAttrib(hou.attribType.Prim, 'variant', 0)\n"
    "geo.addAttrib(hou.attribType.Prim, 'component_id', '')\n"
    "# a box (variant 0)\n"
    "pts = []\n"
    "for x,y,z in [(-0.5,-0.5,-0.5),(0.5,-0.5,-0.5),(0.5,0.5,-0.5),(-0.5,0.5,-0.5),(-0.5,-0.5,0.5),(0.5,-0.5,0.5),(0.5,0.5,0.5),(-0.5,0.5,0.5)]:\n"
    "    p = geo.createPoint(); p.setPosition((x,y,z)); pts.append(p)\n"
    "for idx in ([0,3,2,1],[4,5,6,7],[0,1,5,4],[3,7,6,2],[0,4,7,3],[1,2,6,5]):\n"
    "    poly = geo.createPolygon()\n"
    "    for i in idx: poly.addVertex(pts[i])\n"
    "    poly.setAttribValue('variant', 0)\n"
    "    poly.setAttribValue('component_id', 'box')\n"
)

vb = geo.createNode("python", "variant_b")
vb.parm("python").set(
    "node = hou.pwd(); geo = node.geometry(); geo.clear()\n"
    "geo.addAttrib(hou.attribType.Prim, 'variant', 0)\n"
    "geo.addAttrib(hou.attribType.Prim, 'component_id', '')\n"
    "# a sphere (variant 1)\n"
    "import math\n"
    "seg, hseg = 8, 6\n"
    "pts = []\n"
    "for j in range(hseg+1):\n"
    "    phi = math.pi * j / hseg\n"
    "    for i in range(seg):\n"
    "        theta = 2*math.pi*i/seg\n"
    "        x = 0.4*math.sin(phi)*math.cos(theta)\n"
    "        y = 0.4*math.cos(phi)\n"
    "        z = 0.4*math.sin(phi)*math.sin(theta)\n"
    "        p = geo.createPoint(); p.setPosition((x,y,z)); pts.append(p)\n"
    "for j in range(hseg):\n"
    "    for i in range(seg):\n"
    "        k = j*seg + i\n"
    "        k2 = j*seg + (i+1)%seg\n"
    "        poly = geo.createPolygon()\n"
    "        for v in (k, k2, k2+seg, k+seg): poly.addVertex(pts[v])\n"
    "        poly.setAttribValue('variant', 1)\n"
    "        poly.setAttribValue('component_id', 'sphere')\n"
)

# ════════════════════════════════════════════════════════════════════════
# STAGE 2 — Merge → Pack (one packed prim per connected piece)
# ════════════════════════════════════════════════════════════════════════
merge = geo.createNode("merge", "merge_variants")
merge.setInput(0, va)
merge.setInput(1, vb)

# ════════════════════════════════════════════════════════════════════════
# STAGE 2b — Pack BY NAME on the integer `variant` attribute.
# Each variant's prims carry i@variant (0 for box, 1 for sphere).
# Pack's default "Packed Fragments" mode MERGES overlapping geometry into a
# single prim (observed prims=1) — so we MUST use Pack By Name to get one
# packed prim per variant.
# ════════════════════════════════════════════════════════════════════════
pack = geo.createNode("pack", "pack_variants")
pack.setInput(0, merge)
pack.parm("packbyname").set(1)             # enable Pack By Name
pack.parm("nameattribute").set("variant")  # group by the integer variant attr

# ════════════════════════════════════════════════════════════════════════
# STAGE 3 — Scatter points with an integer `variant` attribute per point.
# (Attribute from Pieces is NOT used — it needs TWO inputs and does its own
#  assignment. We assign `variant` here deterministically, then Copy to Points
#  dispatches by matching point.variant == packed-source.variant.)
# ════════════════════════════════════════════════════════════════════════
scatter = geo.createNode("python", "scatter_points")
scatter.parm("python").set(
    "import random\n"
    "node = hou.pwd(); geo = node.geometry(); geo.clear()\n"
    "geo.addAttrib(hou.attribType.Point, 'variant', 0)\n"
    "geo.addAttrib(hou.attribType.Point, 'orient', (0,0,0,1))\n"
    "geo.addAttrib(hou.attribType.Point, 'pscale', 1.0)\n"
    "geo.addAttrib(hou.attribType.Point, 'edini_scatter_ptnum', 0)\n"
    "rng = random.Random(42)\n"
    "for i in range(6):\n"
    "    pt = geo.createPoint()\n"
    "    pt.setPosition((i*0.8, 0, 0))\n"
    "    r = rng.random()\n"
    "    v = 0 if r < 0.6 else 1   # 60% box, 40% sphere\n"
    "    pt.setAttribValue('variant', v)\n"
    "    pt.setAttribValue('edini_scatter_ptnum', i)\n"
)

# ════════════════════════════════════════════════════════════════════════
# STAGE 4 — Copy to Points 2.0 with Piece Attribute dispatch.
# Source = packed variants (each carries i@variant). Target = scatter points
# (each carries i@variant). Copy matches them 1:1.
# ════════════════════════════════════════════════════════════════════════
copy = geo.createNode("copytopoints::2.0", "copy_dispatch")
copy.setInput(0, pack)        # the packed variant library (source)
copy.setInput(1, scatter)     # the target points (each has @variant)
# THE CRITICAL PARMS (H21 names — verified against manifest):
#   useidattrib = "Piece Attribute" toggle (enable dispatch)
#   idattrib    = the attribute NAME to match on
copy.parm("useidattrib").set(1)
copy.parm("idattrib").set("variant")

# ════════════════════════════════════════════════════════════════════════
# STAGE 5 — Unpack → Connectivity → per-instance component_id
# ════════════════════════════════════════════════════════════════════════
unpack = geo.createNode("unpack", "unpack")
unpack.setInput(0, copy)

# Connectivity: each connected instance gets a unique integer `piece`.
# This is how we distinguish instances (Copy to Points does NOT transfer
# target-point attributes like edini_scatter_ptnum onto instances).
connect = geo.createNode("connectivity", "connect")
connect.setInput(0, unpack)
# Connectivity's default attr name is `class`; set it to `piece`.
connect.parm("attribname").set("piece")

# idfix: read prim `variant` (which shape) + point `piece` (which instance).
idfix = geo.createNode("python", "idfix")
idfix.setInput(0, connect)
idfix.parm("python").set(
    "node = hou.pwd(); geo = node.geometry()\n"
    "variant_ids = ['box', 'sphere']\n"
    "if geo.findPrimAttrib('component_id') is None:\n"
    "    geo.addAttrib(hou.attribType.Prim, 'component_id', '')\n"
    "for prim in geo.prims():\n"
    "    vidx = 0\n"
    "    try: vidx = int(prim.attribValue('variant'))\n"
    "    except Exception: vidx = 0\n"
    "    if vidx < 0 or vidx >= len(variant_ids):\n"
    "        vidx = 0\n"
    "    piece = 0\n"
    "    verts = prim.vertices()\n"
    "    if verts:\n"
    "        pt = verts[0].point()\n"
    "        try: piece = int(pt.attribValue('piece'))\n"
    "        except Exception: piece = 0\n"
    "    cid = variant_ids[vidx] + '_' + str(piece)\n"
    "    prim.setAttribValue('component_id', cid)\n"
)

# Out
out = geo.createNode("null", "OUT")
out.setInput(0, idfix)
out.setDisplayFlag(True)
geo.layoutChildren()

# ════════════════════════════════════════════════════════════════════════
# STAGE 7 — Cook each node IN ORDER so we find exactly which one fails.
# ════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("COOKING EACH NODE IN ORDER (finds the exact failure point)")
print("=" * 60)

chain = [
    ("variant_a", va),
    ("variant_b", vb),
    ("merge_variants", merge),
    ("pack_variants", pack),
    ("scatter_points", scatter),
    ("copy_dispatch", copy),
    ("unpack", unpack),
    ("connect", connect),
    ("idfix", idfix),
    ("OUT", out),
]

for label, node in chain:
    try:
        node.cook(force=True)
        # Read geometry stats if available.
        try:
            g = node.geometry()
            npts = len(g.points()) if g is not None else 0
            nprims = len(g.prims()) if g is not None else 0
            print(f"  OK   {label:20s}  points={npts:5d}  prims={nprims:5d}")
        except Exception:
            print(f"  OK   {label:20s}  (no geometry / container)")
    except Exception as e:
        print(f"  FAIL {label:20s}  -> {e}")
        # Surface this node's own stored errors + warnings (Houdini keeps them).
        try:
            errs = list(node.errors() or [])
            warns = list(node.warnings() or [])
        except Exception:
            errs, warns = [], []
        for er in errs:
            print(f"        error:   {er}")
        for w in warns:
            print(f"        warning: {w}")
        print()
        print(f">>> The chain breaks at '{label}'. Inspect THAT node in")
        print(f"    /obj/variant_diag — its message above is the real cause.")
        break
else:
    # All nodes cooked — report final geometry.
    g = out.geometry()
    print()
    print("=" * 60)
    print("ALL NODES COOKED OK — inspecting final geometry")
    print("=" * 60)
    print("point_count:", len(g.points()))
    print("prim_count:", len(g.prims()))

    # ── Per-instance inspection: which variant landed where? ────────────
    # Check what attributes actually survive on the unpacked geometry.
    pt_attrs = sorted(a.name() for a in g.pointAttribs())
    prim_attrs = sorted(a.name() for a in g.primAttribs())
    print("\npoint attributes:", pt_attrs)
    print("prim attributes:", prim_attrs)

    # Group prims by component_id and report variant + piece per instance.
    # NOTE: `variant` and `piece` are PRIM attributes (survive unpack), NOT
    # point attributes — Copy to Points does not transfer target-point
    # attributes onto instance geometry.
    from collections import defaultdict
    instances = defaultdict(lambda: {"count": 0, "variant": None, "piece": None})
    for prim in g.prims():
        try:
            cid = prim.stringAttribValue("component_id")
        except Exception:
            cid = "?"
        rec = instances[cid]
        rec["count"] += 1
        # Read variant from the PRIM; piece from the prim's first POINT
        # (Connectivity writes `piece` onto points, not prims).
        if rec["variant"] is None:
            try: rec["variant"] = int(prim.attribValue("variant"))
            except Exception: rec["variant"] = "??"
        if rec["piece"] is None:
            verts = prim.vertices()
            if verts:
                pt = verts[0].point()
                try: rec["piece"] = int(pt.attribValue("piece"))
                except Exception: rec["piece"] = "??"
    print("\n── per-instance breakdown ──")
    for cid in sorted(instances):
        rec = instances[cid]
        print(f"  {cid:16s}  prims={rec['count']:3d}  "
              f"variant={rec['variant']}  piece={rec['piece']}")
    # Distinct variant values present tells us if dispatch mixed shapes.
    variants_seen = sorted({rec["variant"] for rec in instances.values()
                            if isinstance(rec["variant"], int)})
    print(f"\nvariant values across instances: {variants_seen}")
    print("(expected both 0 and 1 if piece dispatch worked; "
          "only [0] means all got box)")

print()
print("INSPECT EACH NODE:")
print("  variant_a / variant_b — the two source geometries (i@variant = 0/1)")
print("  merge_variants       — both merged")
print("  pack_variants        — packbyname=1, nameattribute='variant'")
print("                         should be 2 packed prims (one per variant)")
print("  scatter_points       — 6 points, each with i@variant = 0 or 1")
print("  copy_dispatch        — useidattrib=1, idattrib='variant' (CHECK!)")
print("  unpack               — back to polygons")
print("  idfix / OUT          — per-instance component_id assigned")
print()
print("If copy_dispatch shows a MIX of boxes and spheres, the workflow works.")
print("If it shows only ONE shape (or empty), the piece dispatch isn't firing")
print("— check that attribfrompieces.pieceattrib and copy.idattrib are 'variant'.")
