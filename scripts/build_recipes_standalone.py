"""Build recipe subnets as a STANDALONE tree in /obj/recipe_build.

Run via houdini_run_python_sandbox(network_mode=True). This file is exec'd
directly (no cross-layer string escaping). Network mode lets us createNode
freely inside the sandbox geo container WITHOUT the infinite-recursion guard
that bites single-SOP mode.

We build standalone (NOT inside the locked edini_recipe_manager HDA) to avoid
the HDA lock/relock cycle. After building, recipe_capture_tree extracts them.
The user can then move the subnets into the HDA + Accept to persist.
"""
import hou
import traceback

BUILD_ROOT = "/obj/recipe_build"


def _notes(lines):
    return "\n".join(lines)


def _ensure_root():
    root = hou.node(BUILD_ROOT)
    if root is None:
        root = hou.node("/obj").createNode("geo", "recipe_build")
        root.setComment("Edini recipe build area (standalone)")
    return root


def _recreate(parent, name):
    old = parent.node(name)
    if old is not None:
        try:
            for c in old.allSubChildren():
                c.bypass = True
        except Exception:
            pass
        old.destroy()
    sn = parent.createNode("subnet", name)
    return sn


def _set_display(sn, node):
    """Mark `node` as the display/render output of the subnet."""
    for c in sn.children():
        if c.type().name() not in ("output", "stashed_geo", "subnetconnector"):
            c.setDisplayFlag(False)
            c.setRenderFlag(False)
    node.setDisplayFlag(True)
    node.setRenderFlag(True)


def build_tube_along_curve(root):
    sn = _recreate(root, "tube_along_curve")
    sn.setComment(_notes([
        "功能：沿任意输入曲线生成封闭圆柱管材（sweep::2.0 + 圆截面）",
        "用途：弯把、前叉弯曲段、链条撑、座撑、车架直管——任何「一条曲线 + 半径 = 一根管」的场景",
        "输入：第0输入=路径曲线（决定管材走向，由布局层提供形状）",
        "重要参数：surfacetype, endcaptype, rad",
        "不要用于：变径管（需改 sweep scaleramp）、空心管",
    ]))
    sn.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    # path: line node (two-point straight path; layout layer can swap to a
    # curve input). curve::2.0 is interactive (no scriptable coords parm).
    path = sn.createNode("line", "path_line")
    path.parm("dist").set(1.0)
    path.parm("dirx").set(0.0)
    path.parm("diry").set(1.0)  # +Y
    path.parm("dirz").set(0.0)
    section = sn.createNode("circle", "section")
    section.parm("radx").set(0.012)
    section.parm("rady").set(0.012)
    section.parm("type").set(1)  # NURBS
    sweep = sn.createNode("sweep::2.0", "sweep1")
    sweep.setInput(0, path)
    sweep.setInput(1, section)
    sweep.parm("surfacetype").set(2)   # tube
    sweep.parm("endcaptype").set(1)    # cap both ends -> closed
    out = sn.createNode("null", "OUT")
    out.setInput(0, sweep)
    sn.layoutChildren()
    _set_display(sn, out)
    return "tube_along_curve: nodes={} endcaptype={}".format(
        len(sn.children()), sweep.parm("endcaptype").eval())


def build_extrude_solid(root):
    sn = _recreate(root, "extrude_solid")
    sn.setComment(_notes([
        "功能：闭合 2D 截面轮廓沿法向挤出成封闭实体（polyextrude::2.0，正反两面都封）",
        "用途：牙盘、曲柄、踏板、把立、链轮片——任何「一个平面闭合形状 + 厚度 = 一块板状实体」的场景",
        "输入：第0输入=闭合 2D 轮廓（polyline/poly 面，形状由布局层决定）",
        "重要参数：dist, outputfront, outputback",
        "不要用于：管材（用 tube_along_curve）、旋转体（用 revolve_profile）",
    ]))
    sn.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    prof = sn.createNode("box", "profile_box")
    prof.parm("sizex").set(0.1)
    prof.parm("sizey").set(0.005)
    prof.parm("sizez").set(0.1)
    polyx = sn.createNode("polyextrude::2.0", "polyextrude1")
    polyx.setInput(0, prof)
    polyx.parm("dist").set(0.005)
    polyx.parm("outputfront").set(1)
    polyx.parm("outputback").set(1)
    polyx.parm("divs").set(2)
    out = sn.createNode("null", "OUT")
    out.setInput(0, polyx)
    sn.layoutChildren()
    _set_display(sn, out)
    return "extrude_solid: nodes={} outputback={}".format(
        len(sn.children()), polyx.parm("outputback").eval())


def build_revolve_profile(root):
    sn = _recreate(root, "revolve_profile")
    sn.setComment(_notes([
        "功能：2D 母线轮廓绕轴旋转一周生成回转实体（revolve，封端）",
        "用途：外胎（torus特例）、把套、花鼓锥面、脚踏体外壳——任何「一条 2D 侧轮廓绕轴转 = 回转体」的场景",
        "输入：第0输入=母线曲线（2D polyline，定义回转体侧轮廓；位于过轴平面内）",
        "重要参数：surftype, cap, dir, divs",
        "不要用于：非回转对称件（用 extrude_solid）",
    ]))
    sn.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    # profile: a line segment from axis outward (XY plane), revolved around Y.
    # curve::2.0 is interactive (no scriptable coords), so use a line node.
    prof = sn.createNode("line", "profile_line")
    prof.parm("originx").set(0.30)
    prof.parm("originy").set(0.0)
    prof.parm("originz").set(0.0)
    prof.parm("dirx").set(0.0)
    prof.parm("diry").set(1.0)
    prof.parm("dirz").set(0.0)
    prof.parm("dist").set(0.06)
    rev = sn.createNode("revolve", "revolve1")
    rev.setInput(0, prof)
    rev.parm("surftype").set(4)     # bezier mesh
    rev.parm("cap").set(1)          # cap ends
    rev.parm("divs").set(32)
    rev.parm("dirx").set(0.0)
    rev.parm("diry").set(1.0)
    rev.parm("dirz").set(0.0)
    out = sn.createNode("null", "OUT")
    out.setInput(0, rev)
    sn.layoutChildren()
    _set_display(sn, out)
    return "revolve_profile: nodes={} cap={}".format(
        len(sn.children()), rev.parm("cap").eval())


def build_radial_copy(root):
    sn = _recreate(root, "radial_copy")
    sn.setComment(_notes([
        "功能：单位模板复制到绕指定轴均匀分布的 N 个点上（Detail wrangle 布点 + copytopoints）",
        "用途：辐条（24/28/32根绕花鼓均布）、齿牙、转子叶片、螺栓圆周阵列——任何「一个模板 + 绕轴 N 等分 = 环形阵列」的场景",
        "输入：第0输入=模板几何（单位尺寸，原点；形状由布局层决定）",
        "重要参数：radial_count, radial_radius, radial_axis",
        "不要用于：沿曲线非均匀分布（用 linear_array_copy）、随机散布（用 scatter+copytopoints）",
    ]))
    sn.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    tmpl = sn.createNode("tube", "template")
    tmpl.parm("rad1").set(0.001)
    tmpl.parm("rad2").set(0.001)
    tmpl.parm("height").set(0.3)
    tmpl.parm("cols").set(6)
    ring = sn.createNode("attribwrangle", "ring1")
    ring.parm("class").set(0)  # Detail
    ring.parm("snippet").set(
        'int n=chi("radial_count"); float r=chf("radial_radius");\n'
        'for(int i=0;i<n;i++){float a=2.0*M_PI*float(i)/float(n);\n'
        'int pt=addpoint(0,set(r*cos(a),0,r*sin(a)));\n'
        'vector tang=normalize(set(-sin(a),0,cos(a)));\n'
        'matrix3 m=lookat(set(0,0,0),tang*0.001,{0,1,0});\n'
        'setpointattrib(0,"orient",pt,qconvert(m));}'
    )
    ctp = sn.createNode("copytopoints::2.0", "copytopoints1")
    ctp.setInput(0, tmpl)
    ctp.setInput(1, ring)
    ctp.parm("pack").set(0)
    out = sn.createNode("null", "OUT")
    out.setInput(0, ctp)
    sn.layoutChildren()
    _set_display(sn, out)
    return "radial_copy: nodes={}".format(len(sn.children()))


def build_mirror_bilateral(root):
    sn = _recreate(root, "mirror_bilateral")
    sn.setComment(_notes([
        "功能：左右镜像半边几何并焊接对称面（mirror，保留原始 + consolidatepts 焊缝，消除对称面幽灵非流形边）",
        "用途：自行车/摩托车/载具整车——任何「左右对称物体只建半边，镜像出另半边」的场景",
        "输入：第0输入=半边几何（建在 X>=0 一侧，对称面为 YZ 平面）",
        "重要参数：dir, keepOriginal, consolidatepts, consolidatetol",
        "不要用于：非对称物体、四向对称（需多次镜像）、仅平移复制（用 copytopoints）",
    ]))
    sn.setGenericFlag(hou.nodeFlag.DisplayComment, True)
    mir = sn.createNode("mirror", "mirror1")
    mir.parm("dirx").set(1.0)
    mir.parm("diry").set(0.0)
    mir.parm("dirz").set(0.0)
    mir.parm("keepOriginal").set(1)
    mir.parm("consolidatepts").set(1)
    nrm = sn.createNode("normal", "normal1")
    nrm.setInput(0, mir)
    out = sn.createNode("null", "OUT")
    out.setInput(0, nrm)
    sn.layoutChildren()
    _set_display(sn, out)
    return "mirror_bilateral: nodes={} keepOriginal={}".format(
        len(sn.children()), mir.parm("keepOriginal").eval())


def main():
    root = _ensure_root()
    results = []
    for fn in (build_tube_along_curve, build_extrude_solid,
               build_revolve_profile, build_radial_copy, build_mirror_bilateral):
        try:
            results.append(fn(root))
        except Exception:
            results.append(fn.__name__ + " FAILED:\n" + traceback.format_exc())
    root.layoutChildren()
    return "\n".join(results)


RESULT = main()
