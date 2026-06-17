# Python SOP generator skeleton.
# Single-SOP mode (default). For multi-component, see network_mode block below.
#
# IRON RULES (from SKILL.md):
#   1. NEVER call createNode inside this cook body -> infinite recursion.
#      To build a network, use network_mode=true (see bottom).
#   2. Declare ALL attributes BEFORE creating any geometry.
#   3. Tag every prim with component_id.

node = hou.pwd()
geo = node.geometry()
geo.clear()

# --- 1. Declare attributes FIRST (before any geometry) ---
geo.addAttrib(hou.attribType.Prim, "component_id", "")
geo.addAttrib(hou.attribType.Prim, "material_zone", "")
geo.addAttrib(hou.attribType.Point, "height", 0.0)

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
# NETWORK MODE (for multi-component assets). Do NOT mix with the above.
# Pass network_mode=true to houdini_run_python_sandbox. The code below runs
# in the sandbox geo container (NOT inside a cook), so createNode is safe.
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
