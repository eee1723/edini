"""楼梯 E2E v4 — 参数关联 + resettargetattribs + 无多余节点。

exec(open(r'Z:\EEE_Project\Edini\tests\manual_stair_e2e.py').read())
"""
import hou

old = hou.node("/obj/stair_e2e")
if old: old.destroy()

geo = hou.node("/obj").createNode("geo", "stair_e2e", run_init_scripts=False)

STEPS = 12
TREAD = 0.3
RISER = 0.18
WIDTH = 1.2
THICK = RISER  # 厚度 = 踏高，踏步紧密堆积无间隙

# ── 踏步模板：box 尺寸由参数驱动 ──
box = geo.createNode("box", "step_template")
box.parm("sizex").set(TREAD)
box.parm("sizey").set(THICK)
box.parm("sizez").set(WIDTH)
box.parm("ty").set(THICK * 0.5)  # 底面移到 Y=0

# ── 散布点：每步中心位置 ——
w = geo.createNode("attribwrangle", "scatter")
w.parm("class").set(0)
w.parm("snippet").set(
    'int n = %d;\n'
    'float tread = %.4f;\n'
    'float riser = %.4f;\n'
    'vector dir = set(1,0,0);\n'
    'vector pos = set(tread * 0.5, 0, 0);\n'
    'for (int i = 0; i < n; i++) {\n'
    '    int pt = addpoint(0, pos);\n'
    '    vector4 ori = set(0.0, 0.0, 0.0, 1.0);\n'
    '    setpointattrib(0, "orient", pt, ori);\n'
    '    setpointattrib(0, "pscale", pt, 1.0);\n'
    '    setpointattrib(0, "id", pt, i);\n'
    '    pos += dir * tread + set(0, riser, 0);\n'
    '}\n'
    % (STEPS, TREAD, RISER)
)

# ── CTP + resettargetattribs ──
ctp = geo.createNode("copytopoints", "ctp")
ctp.setInput(0, box)
ctp.setInput(1, w)
ctp.parm("resettargetattribs").pressButton()

# ── Normal ──
norm = geo.createNode("normal", "norm")
norm.setInput(0, ctp)

out = geo.createNode("null", "OUT")
out.setInput(0, norm)
out.setDisplayFlag(True)
geo.layoutChildren()

out.cook(force=True)
errs = list(out.errors() or [])
gs = out.geometry()
npts = gs.intrinsicValue("pointcount") if gs else 0
nprims = gs.intrinsicValue("primitivecount") if gs else 0
bbox = gs.boundingBox() if gs and npts > 0 else None

print("=" * 50)
print("楼梯 v4 · %d步 · box+CTP · resettargetattribs" % STEPS)
print("  tread=%.2f  riser=%.2f  width=%.2f  thick=%.2f" % (TREAD, RISER, WIDTH, THICK))
print("  点: %d  面: %d" % (npts, nprims))
print("  错误: %s" % errs)
if bbox:
    bb = bbox
    print("  包围盒: (%.2f,%.2f,%.2f) → (%.2f,%.2f,%.2f)" % (
        bb.minvec()[0], bb.minvec()[1], bb.minvec()[2],
        bb.maxvec()[0], bb.maxvec()[1], bb.maxvec()[2]))
print("  /obj/stair_e2e → viewport")
