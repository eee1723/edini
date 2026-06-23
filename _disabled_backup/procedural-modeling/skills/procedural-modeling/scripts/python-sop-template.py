# Python SOP generator skeleton.
# Single-SOP mode (default): one self-contained generator (a fractal, a
# parametric surface, a single wheel template).
#
# For MULTI-COMPONENT assets (body + wheels + handles via Copy-to-Points),
# do NOT hand-write the network below — use `build_procedural_asset(recipe)`.
# It builds the Copy-to-Points/merge/postprocess network deterministically
# AND bakes edini_world_axis (required to pass the G3 commit gate). A raw
# network_mode hand-written network cannot pass G3.
#
# IRON RULES (from SKILL.md):
#   1. NEVER call createNode inside this cook body -> infinite recursion.
#      Multi-component: use build_procedural_asset (it owns the network).
#   2. Declare ALL attributes BEFORE creating any geometry.
#   3. Tag every prim with component_id.

node = hou.pwd()
geo = node.geometry()
geo.clear()

# --- 1. Declare attributes FIRST (before any geometry) ---
geo.addAttrib(hou.attribType.Prim, "component_id", "")
geo.addAttrib(hou.attribType.Prim, "material_zone", "")
geo.addAttrib(hou.attribType.Point, "height", 0.0)

# ── add_box helper (canonical, outward-facing winding) ──────────────
# Reuse this instead of hand-writing a box every component. Verified:
# a SINGLE box emits ZERO non-manifold edges regardless of winding (the
# health-check detector counts edges shared by >=3 prims; a box edge is
# always shared by exactly 2 faces). Non-manifold edges ONLY appear when
# ADJACENT boxes share coincident points (e.g. a door panel inset whose
# back face is coplanar with the slab front). That is fixed by a `fuse`
# SOP in postprocess, NOT by changing this winding table.
#
# Point order:  0=(x0,y0,z0) 1=(x1,y0,z0) 2=(x1,y1,z0) 3=(x0,y1,z0)
#               4=(x0,y0,z1) 5=(x1,y0,z1) 6=(x1,y1,z1) 7=(x0,y1,z1)
# Faces (outward CCW viewed from outside):
#   bottom [0,3,2,1]  top    [4,5,6,7]
#   front  [0,1,2,3]  back   [7,6,5,4]
#   left   [0,4,7,3]  right  [1,2,6,5]
def add_box(geo, pmin, pmax, comp_id, mat=""):
    x0, y0, z0 = pmin
    x1, y1, z1 = pmax
    pts = []
    for x, y, z in [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
                    (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]:
        p = geo.createPoint(); p.setPosition((x, y, z)); pts.append(p)
    for idx in ([0,3,2,1],[4,5,6,7],[0,1,2,3],[7,6,5,4],[0,4,7,3],[1,2,6,5]):
        poly = geo.createPolygon()
        for i in idx:
            poly.addVertex(pts[i])
        poly.setAttribValue("component_id", comp_id)
        if mat:
            poly.setAttribValue("material_zone", mat)

# --- 2. Install spare parameters idempotently (first cook only) ---
PARM_SPECS = [
    ("radius", hou.FloatParmTemplate("radius", "Radius", 1,
        default_value=((0.35,),), min=0.05, max=2.0,
        naming_scheme=hou.parmNamingScheme.Base1)),
    ("count",  hou.IntParmTemplate("count", "Count", 1,
        default_value=((8,),), min=3, max=64,
        naming_scheme=hou.parmNamingScheme.Base1)),
]
ptg = node.parmTemplateGroup()
missing = [tmpl for name, tmpl in PARM_SPECS if ptg.find(name) is None]
for tmpl in missing:
    ptg.append(tmpl)
if missing:
    node.setParmTemplateGroup(ptg)  # triggers recook; this cook uses defaults

# --- 3. Read params (guaranteed to exist after install) ---
radius = node.evalParm("radius")
count  = node.evalParm("count")

# --- 4. Emit geometry (tag every prim with component_id) ---
# Example: unit-radius wheel ring in XZ plane
import math
for i in range(count):
    angle = 2 * math.pi * i / count
    pt = geo.createPoint()
    pt.setPosition((radius * math.cos(angle), 0, radius * math.sin(angle)))
    pt.setAttribValue("height", 0.0)

poly = geo.createPolygon()
poly.setAttribValue("component_id", "wheel_template")
poly.setAttribValue("material_zone", "rubber")
# poly.addVertex(...) for each corner


# =====================================================================
# NETWORK MODE — DEPRECATED for multi-component assets.
# The block below shows the OLD hand-written network pattern. It is kept
# only as a reference for genuinely single-piece assets that a recipe
# cannot express (and even then, the geometry must NOT carry @component_id
# prims, or the G3 commit gate refuses it for lacking edini_world_axis).
#
# For any multi-component / repeated-part asset, use build_procedural_asset.
# Pass network_mode=true to houdini_run_python_sandbox ONLY for last-resort
# single-piece topologies, with a documented reason.
# =====================================================================
#
# container = sandbox_root            # injected; == hou.node(sandbox_root_path)
#
# # 1. Body: emits anchor points with @component_id/@orient/@pscale
# body = container.createNode("python", "body_generate")
# body.parm("python").set(BODY_CODE)   # BODY_CODE builds frame + anchor points
#
# # 2. One sub-component generator (single wheel, modeled at unit radius)
# wheel = container.createNode("python", "wheel_component")
# wheel.parm("python").set(WHEEL_CODE)
#
# # 3. Sweep the tube profile along a curve (no ForEach bookkeeping)
# #    profile = container.createNode("circle", "tube_profile")
# #    spine   = container.createNode("curve", ...)
# #    sweep   = container.createNode("sweep::2.0", "frame_sweep")
# #    sweep.setInput(0, spine); sweep.setInput(1, profile)
#
# # 4. Copy-to-Points: instance wheel onto the body's anchor points
# copy = container.createNode("copytopoints::2.0", "copy_wheels")
# copy.setInput(0, wheel)   # geometry to stamp
# copy.setInput(1, body)    # points to stamp onto
#
# # 5. Merge everything + OUT (the harness auto-finds this node)
# merge = container.createNode("merge", "merge_all")
# merge.setInput(0, copy)
# out = container.createNode("null", "OUT")
# out.setInput(0, merge)
# out.setDisplayFlag(True)
#
# # Each generator (BODY_CODE, WHEEL_CODE) is single-SOP-style:
# #   node = hou.pwd(); geo = node.geometry(); geo.clear(); ...
# # It runs when that child Python SOP cooks (fine — only emits its OWN geo).
# # The createNode calls live in the network-mode BODY, not in a cook.
