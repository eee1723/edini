"""VEX 工具链 Smoke Test — 覆盖全部修复点。

exec(open(r'Z:\EEE_Project\Edini\tests\manual_vex_smoke.py').read())
"""
import hou

old = hou.node("/obj/vex_smoke")
if old: old.destroy()

geo = hou.node("/obj").createNode("geo", "vex_smoke", run_init_scripts=False)
passed = 0
failed = 0

def check(label, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print("  PASS:", label)
    else:
        failed += 1
        print("  FAIL:", label, "|", detail)

print("=" * 50)
print("1. make_closed_polyline → 单根连续 polyline")
w1 = geo.createNode("attribwrangle", "test_closed")
w1.parm("class").set(0)
w1.parm("snippet").set(
    '#include <vexlib/skeleton.vfl>\n'
    'int p[] = make_closed_polyline(0, array({0,0,0},{1,0,0},{1,1,0},{0,1,0}));\n'
)
w1.cook(force=True)
errs1 = list(w1.errors() or [])
nprims1 = w1.geometry().intrinsicValue("primitivecount") if w1.geometry() else 0
check("无编译错误", len(errs1) == 0, str(errs1))
check("只有 1 个 prim（单根闭合曲线）", nprims1 == 1, "prims=%d" % nprims1)

print("\n2. run_vex 设 Detail 模式 → scatter 点正确")
w2 = geo.createNode("attribwrangle", "test_scatter")
w2.parm("class").set(0)
w2.parm("snippet").set(
    'int n = 5;\n'
    'vector pos = set(0,0,0);\n'
    'for (int i = 0; i < n; i++) {\n'
    '    int pt = addpoint(0, pos);\n'
    '    vector4 ori = set(0.0,0.0,0.0,1.0);\n'
    '    setpointattrib(0, "orient", pt, ori);\n'
    '    setpointattrib(0, "pscale", pt, 1.0);\n'
    '    pos += set(1, 0, 0);\n'
    '}\n'
)
w2.cook(force=True)
errs2 = list(w2.errors() or [])
npts2 = w2.geometry().intrinsicValue("pointcount") if w2.geometry() else 0
check("无编译错误（set() + vector4 显式类型）", len(errs2) == 0, str(errs2))
check("产出 5 个点（Detail 模式正确）", npts2 == 5, "pts=%d" % npts2)

print("\n3. #include <vexlib/...> 三件套全通过")
w3 = geo.createNode("attribwrangle", "test_all_inc")
w3.parm("class").set(0)
w3.parm("snippet").set(
    '#include <vexlib/skeleton.vfl>\n'
    '#include <vexlib/sections.vfl>\n'
    '#include <vexlib/attribs.vfl>\n'
    'int path[] = make_stair_path(0, 3, 0.3, 0.18, {0,0,0}, {1,0,0});\n'
    'int prof[] = make_circle_section(0, 0.1, 8, "XY", {0,0,0});\n'
    'set_component_id_by_index(0, "test_", 0, 1);\n'
)
w3.cook(force=True)
errs3 = list(w3.errors() or [])
check("三件套 include 无编译错误", len(errs3) == 0, str(errs3))

print("\n4. CTP + resettargetattribs + box 模板 → 楼梯")
box4 = geo.createNode("box", "step4")
box4.parm("sizex").set(0.3)
box4.parm("sizey").set(0.18)
box4.parm("sizez").set(1.2)
box4.parm("ty").set(0.09)
w4 = geo.createNode("attribwrangle", "scatter4")
w4.parm("class").set(0)
w4.parm("snippet").set(
    'int n = 5;\n'
    'float t = 0.3;\n'
    'float r = 0.18;\n'
    'vector pos = set(t*0.5, 0, 0);\n'
    'for (int i = 0; i < n; i++) {\n'
    '    int pt = addpoint(0, pos);\n'
    '    vector4 ori = set(0.0,0.0,0.0,1.0);\n'
    '    setpointattrib(0, "orient", pt, ori);\n'
    '    setpointattrib(0, "pscale", pt, 1.0);\n'
    '    pos += set(t, r, 0);\n'
    '}\n'
)
w4.cook(force=True)
ctp4 = geo.createNode("copytopoints", "ctp4")
ctp4.setInput(0, box4)
ctp4.setInput(1, w4)
ctp4.parm("resettargetattribs").pressButton()
norm4 = geo.createNode("normal", "norm4")
norm4.setInput(0, ctp4)
out4 = geo.createNode("null", "OUT4")
out4.setInput(0, norm4)
out4.cook(force=True)
errs4 = list(out4.errors() or [])
npts4 = out4.geometry().intrinsicValue("pointcount") if out4.geometry() else 0
check("CTP 楼梯无错误", len(errs4) == 0, str(errs4))
check("有几何产出（>40点=5步×8点/box）", npts4 >= 40, "pts=%d" % npts4)

geo.layoutChildren()
geo.setDisplayFlag(False)  # 不干扰 viewport

print("\n" + "=" * 50)
print("结果: %d 通过 / %d 失败（共 %d 项）" % (passed, failed, passed + failed))
if failed:
    print("节点保留: /obj/vex_smoke → 可手动检查失败的节点")
    out4.setDisplayFlag(True)
else:
    print("全部通过 ✅ — /obj/vex_smoke 可删除")
