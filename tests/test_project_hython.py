"""Real-Houdini (hython) decisive tests for the component scaffold.

Verifies spec §8 steps 1-3, 5 (subnet structure, anchor consumption,
idempotency). mock_hou cannot model subnet internal `output` nodes or
multi-output-port formation, so these MUST run under real hython.

Auto-discovers hython via the same _find_hython() as test_assembly_hython
(覆盖两台开发机). Skips when not found.

Run: py -3 -m pytest tests/test_project_hython.py -v
"""
import json
import os
import shutil
import subprocess
import sys
import unittest

_HOUDINI_CANDIDATES = [
    r"C:\Program Files\Side Effects Software",  # 精创机
    r"D:\houdini",                               # 另一台机
    "/Applications/Houdini",
    "/opt/hfs",
]


def _find_hython():
    env = os.environ.get("EDINI_HYTHON") or os.environ.get("HYTHON")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("hython") or shutil.which("hython.exe")
    if found:
        return found
    for base in _HOUDINI_CANDIDATES:
        if not os.path.isdir(base):
            continue
        candidates = []
        for exe in ("hython.exe" if os.name == "nt" else "hython",):
            exe_path = os.path.join(base, "bin", exe)
            if os.path.isfile(exe_path):
                candidates.append(("0-direct", exe_path))
        for name in os.listdir(base):
            exe = os.path.join(base, name, "bin",
                               "hython.exe" if os.name == "nt" else "hython")
            if os.path.isfile(exe):
                candidates.append((name, exe))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
    return None


HYTHON = _find_hython()
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# 在 hython 子进程里跑的验证脚本（spec §8 步骤 1-3、5）。
_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou

# 确保 edini::project 类型可用（安装仓库的 HDA 定义）。
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)

from edini.project.state import empty_declaration, add_component, save_declaration
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.project.ports import (OUT_GEOMETRY_NODE, OUT_ANCHORS_NODE,
                                 OUTPUT_0_NODE, OUTPUT_1_NODE)

result = {"steps": {}}

# --- 步骤 1: 建脚手架（2 组件）---
core = create_project_hda(name="proj_test")
decl = empty_declaration("proj_test")
add_component(decl, "chassis", purpose="车架",
              ports_out=[
                  {"index": 0, "kind": "geometry", "description": "车架"},
                  {"index": 1, "kind": "anchors", "points": [
                      {"name": "wheel_mount", "role": "mount"}]}])
add_component(decl, "wheels", purpose="车轮")
res = build_project_scaffold(core, declaration=decl)
result["steps"]["build"] = res

# 断言：两个 subnet 存在，各有 4 节点。
chassis = core.node("chassis")
wheels = core.node("wheels")
result["steps"]["s1_chassis_exists"] = chassis is not None
result["steps"]["s1_wheels_exists"] = wheels is not None
ch_names = sorted(c.name() for c in chassis.children()) if chassis else []
result["steps"]["s1_chassis_children"] = ch_names

# --- 步骤 2: 模拟 LLM 在 chassis/out_anchors 上游加锚点 ---
# 往 out_anchors null 的输入端接一个 addpoint wrangle。
wr = chassis.createNode("attribwrangle", "make_anchors")
wr.parm("snippet").set(
    'addpoint(0, set(2, 0, 1));\n'
    'setpointattrib(0, "name", 0, "wheel_mount", "set");\n'
    'setpointattrib(0, "orient", 0, {0,0,0,1}, "set");')
wr.parm("class").set("detail") if wr.parm("class") else None
chassis.node("out_anchors").setInput(0, wr)
chassis.node("out_anchors").cook(force=True)
# 读 out_anchors output 端的锚点。
geo = chassis.node(OUTPUT_1_NODE).geometry()
pts = geo.points()
result["steps"]["s2_anchor_count"] = len(pts)
names = []
for p in pts:
    try:
        names.append(p.stringAttribValue("name"))
    except Exception:
        pass
result["steps"]["s2_anchor_names"] = names

# --- 步骤 5: 幂等 —— 再跑一次 builder，节点不重复 ---
before = sorted(c.name() for c in chassis.children())
build_project_scaffold(core)
after = sorted(c.name() for c in chassis.children())
result["steps"]["s5_idempotent"] = (before == after)
result["steps"]["s5_chassis_children_after"] = after

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestScaffoldHython(unittest.TestCase):
    def _run_harness(self):
        proc = subprocess.run(
            [HYTHON, "-c", _HARNESS],
            capture_output=True, text=True, timeout=180,
            cwd=_REPO)
        combined = proc.stdout + proc.stderr
        # 找 RESULT_JSON 行。
        for line in combined.splitlines():
            if line.startswith("RESULT_JSON:"):
                return json.loads(line[len("RESULT_JSON:"):]), combined
        self.fail(f"no RESULT_JSON in output.\n--- stdout ---\n{proc.stdout}\n"
                  f"--- stderr ---\n{proc.stderr}")

    def test_step1_scaffold_structure(self):
        """§8 步骤1: 两个 subnet 存在，chassis 有 4 脚手架节点。"""
        res, _ = self._run_harness()
        self.assertTrue(res["steps"]["s1_chassis_exists"],
                        f"chassis subnet missing: {res}")
        self.assertTrue(res["steps"]["s1_wheels_exists"],
                        f"wheels subnet missing: {res}")
        ch = res["steps"]["s1_chassis_children"]
        for expected in ("out_geometry", "out_anchors", "output_0", "output_1"):
            self.assertIn(expected, ch, f"missing scaffold node {expected}: {ch}")

    def test_step2_anchor_emission(self):
        """§8 步骤2: LLM 加的锚点从 output_1 cook 出来，带 @name。"""
        res, _ = self._run_harness()
        self.assertEqual(res["steps"]["s2_anchor_count"], 1,
                         f"expected 1 anchor point: {res['steps']}")
        self.assertIn("wheel_mount", res["steps"]["s2_anchor_names"])

    def test_step5_idempotent(self):
        """§8 步骤5: 重跑 builder 不重复建节点。"""
        res, _ = self._run_harness()
        self.assertTrue(res["steps"]["s5_idempotent"],
                        f"not idempotent: {res['steps']}")


_PROMOTE_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold, promote_params

result = {"steps": {}}
core = create_project_hda(name="proj_promote")
decl = empty_declaration("proj_promote")
add_component(decl, "chassis", purpose="车架")
build_project_scaffold(core, declaration=decl)

# 自底向上: agent 在 chassis subnet 建 spare parm (建模副产物, 带 min/max).
chassis = core.node("chassis")
tmpl = hou.FloatParmTemplate("length", "车长", 1, (4.0,), 1.0, 20.0)
chassis.addSpareParmTuple(tmpl)

# promote: 扫 subnet spareParms → core 按分组建 chassis_length (带 min/max),
# subnet length 改引用 core (ch("../chassis_length")).
res = promote_params(core)
result["steps"]["promote_result"] = res
cp = core.parm("chassis_length")
result["steps"]["s4_core_parm_exists"] = cp is not None
if cp is not None:
    result["steps"]["s4_core_default"] = cp.eval()
    t = cp.parmTemplate()
    result["steps"]["s4_core_min"] = t.minValue()
    result["steps"]["s4_core_max"] = t.maxValue()
# subnet length 应改成引用 core.
sp = chassis.parm("length")
result["steps"]["s4_subnet_expr"] = sp.expression() if sp else None
result["steps"]["s4_subnet_follows_core"] = sp.eval() if sp else None
print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestPromoteHython(unittest.TestCase):
    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _PROMOTE_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO)
        combined = proc.stdout + proc.stderr
        for line in combined.splitlines():
            if line.startswith("RESULT_JSON:"):
                return json.loads(line[len("RESULT_JSON:"):]), combined
        self.fail(f"no RESULT_JSON.\nstdout:{proc.stdout}\nstderr:{proc.stderr}")

    def test_step4_promote_creates_core_parm(self):
        """自底向上: subnet 建 parm (带 min/max) → promote 提到 core 按分组 + subnet 改引用 core。"""
        res, _ = self._run()
        s = res["steps"]
        # core 按 分组建 chassis_length (带 default/min/max 透传).
        self.assertTrue(s["s4_core_parm_exists"], f"core chassis_length not created: {res}")
        self.assertEqual(s["s4_core_default"], 4.0)
        self.assertEqual(s["s4_core_min"], 1.0)
        self.assertEqual(s["s4_core_max"], 20.0)
        # subnet length 改成引用 core (ch("../chassis_length")).
        self.assertIn("chassis_length", s["s4_subnet_expr"],
                      f"subnet expr should ref core: {s['s4_subnet_expr']!r}")
        self.assertEqual(s["s4_subnet_follows_core"], 4.0, "subnet should follow core")


_FULL_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold, promote_params, add_anchors

result = {"steps": {}}
core = create_project_hda(name="proj_full")
decl = empty_declaration("proj_full")
add_component(decl, "chassis", purpose="车架",
              ports_out=[
                  {"index": 0, "kind": "geometry"},
                  {"index": 1, "kind": "anchors", "points": [
                      {"name": "wheel_mount", "role": "mount"}]}])
add_component(decl, "wheels", purpose="车轮")

# 全链路 (自底向上): scaffold → chassis 建几何+spare parm → 程序化锚点 → promote
build_project_scaffold(core, declaration=decl)
chassis = core.node("chassis")

# 给 chassis 建主几何 + spare parm (建模副产物)
box = chassis.createNode("box", "root_box")
box.parm("sizex").set(4.0); box.parm("sizey").set(0.5); box.parm("sizez").set(2)
chassis.node("out_geometry").setInput(0, box)
chassis.addSpareParmTuple(hou.FloatParmTemplate("length", "车长", 1, (4.0,), 1.0, 20.0))

# 程序化锚点 (从 box 几何测量, 不是硬编码!)
add_anchors(core, "chassis", [
    {"measure": "bbox_corner", "axes": "+X-Y+Z", "name": "wheel_mount"}])

# promote: 自底向上, 把 chassis.length 提到 core (chassis_length), subnet 改引用 core.
promote_params(core)

result["steps"]["anchors_ok"] = (
    len(chassis.node("output_1").geometry().points()) == 1)
result["steps"]["promote_ok"] = (core.parm("chassis_length") is not None)
result["steps"]["subnet_refs_core"] = chassis.parm("length").expression()
# 再跑 scaffold 确认幂等不破坏已加的内容。
build_project_scaffold(core)
result["steps"]["anchors_after_rebuild"] = (
    len(chassis.node("output_1").geometry().points()) == 1)
print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestFullChainHython(unittest.TestCase):
    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _FULL_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO)
        combined = proc.stdout + proc.stderr
        for line in combined.splitlines():
            if line.startswith("RESULT_JSON:"):
                return json.loads(line[len("RESULT_JSON:"):]), combined
        self.fail(f"no RESULT_JSON.\nstdout:{proc.stdout}\nstderr:{proc.stderr}")

    def test_full_chain(self):
        """全链路 (自底向上): scaffold→几何+spare parm→程序化锚点→promote→重建幂等。"""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["anchors_ok"], f"anchors: {res}")
        self.assertTrue(s["promote_ok"], f"core chassis_length not created by promote: {res}")
        self.assertIn("chassis_length", s["subnet_refs_core"],
                      f"subnet should ref core: {s['subnet_refs_core']!r}")
        self.assertTrue(s["anchors_after_rebuild"],
                        f"rebuild broke anchors: {res}")


_INPUT_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold

result = {"steps": {}}
core = create_project_hda(name="proj_input")
decl = empty_declaration("proj_input")
add_component(decl, "chassis", purpose="车架",
    ports_out=[
        {"index": 0, "kind": "geometry"},
        {"index": 1, "kind": "anchors", "points": [
            {"name": "wheel_mount", "role": "mount"}]}])
add_component(decl, "wheels", purpose="车轮",
    ports_in=[{"from": "chassis", "port": 1, "anchor": "wheel_mount",
               "description": "前轮定位"}])
build_project_scaffold(core, declaration=decl)
chassis = core.node("chassis")
wheels = core.node("wheels")

# 给 chassis 造锚点
wr = chassis.createNode("attribwrangle", "mk")
wr.parm("snippet").set('addpoint(0, set(3,0,3));\n'
    'setpointattrib(0, "name", 0, "wheel_mount", "set");')
wr.parm("class").set("detail")
chassis.node("out_anchors").setInput(0, wr)

# 检查 builder 建的输入脚手架
result["steps"]["in_node_exists"] = wheels.node("in_chassis_wheel_mount") is not None

# wheels 内部：模拟 LLM 在 in_chassis_wheel_mount 之后接建模
in_node = wheels.node("in_chassis_wheel_mount")
in_node.cook(force=True)
geo = in_node.geometry()
result["steps"]["in_node_point_count"] = len(geo.points())
result["steps"]["in_node_anchor_name"] = (
    geo.points()[0].stringAttribValue("name") if geo.points() else None)

# LLM 用 copytopoints 把轮子盖到锚点
shape = wheels.createNode("sphere", "wheel_shape")
mount = wheels.createNode("copytopoints", "mount_wheel")
mount.setInput(0, shape)
mount.setInput(1, in_node)
wheels.node("out_geometry").setInput(0, mount)
wheels.node("out_geometry").cook(force=True)
out_geo = wheels.node("output_0").geometry()
result["steps"]["wheels_output_points"] = len(out_geo.points())

# 幂等：rebuild 后 in_node 和 LLM 连线保持
build_project_scaffold(core)
result["steps"]["in_node_after_rebuild"] = wheels.node("in_chassis_wheel_mount") is not None
mount_after = wheels.node("mount_wheel")
result["steps"]["llm_link_survives"] = (
    mount_after is not None and
    mount_after.inputs()[1] is not None and
    mount_after.inputs()[1].name() == "in_chassis_wheel_mount")

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestInputScaffoldHython(unittest.TestCase):
    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _INPUT_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO)
        combined = proc.stdout + proc.stderr
        for line in combined.splitlines():
            if line.startswith("RESULT_JSON:"):
                return json.loads(line[len("RESULT_JSON:"):]), combined
        self.fail(f"no RESULT_JSON.\nstdout:{proc.stdout}\nstderr:{proc.stderr}")

    def test_input_scaffold_consumes_upstream(self):
        """wheels 通过 in_chassis_wheel_mount 拿到 chassis 锚点并建模。"""
        res, _ = self._run()
        self.assertTrue(res["steps"]["in_node_exists"],
                        f"in_chassis_wheel_mount not built: {res}")
        self.assertEqual(res["steps"]["in_node_point_count"], 1,
                         f"should receive 1 anchor: {res['steps']}")
        self.assertEqual(res["steps"]["in_node_anchor_name"], "wheel_mount")
        self.assertGreater(res["steps"]["wheels_output_points"], 0,
                           "wheels should produce geometry from anchor")
        self.assertTrue(res["steps"]["in_node_after_rebuild"],
                        "in_node destroyed by rebuild")
        self.assertTrue(res["steps"]["llm_link_survives"],
                        "rebuild broke LLM's downstream wiring")


# ============================================================================
# 子系统 1.5: agent 工具链建模验证 — 扩展后的 connect_nodes (output_index)
# + set_param (vector/expression) 能否驱动 agent 在 Project HDA 内完整建模。
# 这条 harness 全程用工具函数 (node_utils.connect_nodes / set_param) 而非直接
# hou.node 操作，证明 agent 工具面足够建模，地基能被"用起来"。
# ============================================================================
_AGENT_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)

from edini.project.state import empty_declaration, add_component
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold, promote_params
from edini.node_utils import create_node, connect_nodes, set_param

result = {"steps": {}}
core = create_project_hda(name="proj_agent")
decl = empty_declaration("proj_agent")
add_component(decl, "chassis", purpose="车架",
    ports_out=[
        {"index": 0, "kind": "geometry", "description": "车架"},
        {"index": 1, "kind": "anchors", "points": [
            {"name": "wheel_mount", "role": "mount"}]}])
add_component(decl, "wheels", purpose="车轮",
    ports_in=[{"from": "chassis", "port": 1, "anchor": "wheel_mount",
               "description": "前轮定位"}])
build_project_scaffold(core, declaration=decl)

chassis_path = core.node("chassis").path()
wheels_path = core.node("wheels").path()

# --- agent 在 chassis 内：wrangle 造锚点（set_param 标量 + connect_nodes）---
wr = create_node("attribwrangle", name="make_anchors", parent_path=chassis_path)
result["steps"]["create_wr"] = wr
r_class = set_param(wr["path"], "class", "detail")
result["steps"]["set_class"] = r_class
r_snip = set_param(wr["path"], "snippet",
    'addpoint(0, set(2, 0, 1));\n'
    'setpointattrib(0, "name", 0, "wheel_mount", "set");')
result["steps"]["set_snip"] = r_snip
r_conn1 = connect_nodes(from_path=wr["path"],
                        to_path=chassis_path + "/out_anchors")
result["steps"]["conn_wr_to_anchors"] = r_conn1
core.node("chassis/out_anchors").cook(force=True)

# --- agent 在 wheels 内：建 box + wheel_radius spare parm (建模副产物) ---
box = create_node("box", name="wheel_box", parent_path=wheels_path)
result["steps"]["create_box"] = box
r_size = set_param(box["path"], "size", [1, 1, 1])
result["steps"]["set_size_vector"] = r_size
# agent 在 wheels subnet 建 wheel_radius spare parm (自底向上, 带 min/max)
wheels_node = core.node("wheels")
wheels_node.addSpareParmTuple(hou.FloatParmTemplate("wheel_radius", "radius", 1, (0.5,), 0.1, 2.0))
# box sizex 引用 subnet 的 wheel_radius
r_expr = set_param(box["path"], "sizex", 'ch("../wheel_radius")')
result["steps"]["set_sizex_expr"] = r_expr
# connect_nodes 3 参 output_index：agent 独立取 chassis 的第 2 输出端（锚点云）。
# builder 已按 ports.in 建了 in_chassis_wheel_mount 并接好 chassis output1（验证 builder 路径）；
# 这里 agent 再用一个独立 null 直接接 chassis output1，证明工具本身能取多输出端。
probe = create_node("null", name="anchor_probe", parent_path=core.path())
r_conn2 = connect_nodes(from_path=chassis_path, to_path=probe["path"],
                        input_index=0, output_index=1)
result["steps"]["conn_chassis_anchor_to_probe"] = r_conn2
probe_node = core.node("anchor_probe")
probe_node.cook(force=True) if probe_node else None
result["steps"]["probe_got_anchor"] = (
    probe_node is not None and
    len(probe_node.geometry().points()) == 1)
# 验证 builder 建的 in_chassis_wheel_mount 也拿到锚点（builder 路径用 output_index）。
in_node = core.node("wheels/in_chassis_wheel_mount")
in_node.cook(force=True) if in_node else None
result["steps"]["wheels_got_anchor"] = (
    in_node is not None and
    len(in_node.geometry().points()) == 1)

# 验证 box sizex 是表达式（live）。
sizex = core.node("wheels/wheel_box").parm("sizex")
result["steps"]["sizex_is_expression"] = (
    sizex is not None and len(sizex.expression()) > 0)
result["steps"]["sizex_expr_value"] = (
    sizex.expression() if sizex and sizex.expression() else None)

# 自底向上 promote: 把 wheels.wheel_radius 提到 core (wheels_wheel_radius),
# subnet wheel_radius 改引用 core.
promote_params(core)
result["steps"]["core_has_wheels_wheel_radius"] = (
    core.parm("wheels_wheel_radius") is not None)
if core.parm("wheels_wheel_radius"):
    result["steps"]["core_default"] = core.parm("wheels_wheel_radius").eval()
result["steps"]["subnet_refs_core"] = wheels_node.parm("wheel_radius").expression()

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestAgentToolsHython(unittest.TestCase):
    """agent 用扩展后的工具（connect_nodes output_index + set_param 向量/表达式）
    能在 Project HDA 内完整建模。这是地基能被 agent '用起来' 的决定性证据。"""

    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _AGENT_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO)
        combined = proc.stdout + proc.stderr
        for line in combined.splitlines():
            if line.startswith("RESULT_JSON:"):
                return json.loads(line[len("RESULT_JSON:"):]), combined
        self.fail(f"no RESULT_JSON.\nstdout:{proc.stdout}\nstderr:{proc.stderr}")

    def test_agent_modeling_via_tools(self):
        res, _ = self._run()
        s = res["steps"]
        # create_node 工作。
        self.assertTrue(s["create_wr"]["success"], f"create wrangle failed: {s['create_wr']}")
        self.assertTrue(s["create_box"]["success"], f"create box failed: {s['create_box']}")
        # set_param 标量（class detail + VEX snippet）。
        self.assertTrue(s["set_class"]["success"], f"set class failed: {s['set_class']}")
        self.assertTrue(s["set_snip"]["success"], f"set snippet failed: {s['set_snip']}")
        # connect_nodes 2 参（wr → out_anchors）。
        self.assertTrue(s["conn_wr_to_anchors"]["success"])
        # set_param 向量（box size [1,1,1]）。
        self.assertTrue(s["set_size_vector"]["success"],
                        f"set vector size failed: {s['set_size_vector']}")
        # set_param 表达式（sizex = ch("../wheel_radius")）—— 走 setExpression。
        self.assertTrue(s["set_sizex_expr"]["success"],
                        f"set expression failed: {s['set_sizex_expr']}")
        self.assertTrue(s["sizex_is_expression"],
                        "sizex should be an expression after ch() set")
        self.assertIn("wheel_radius", s["sizex_expr_value"])
        # connect_nodes 3 参 output_index=1：agent 独立取 chassis 锚点端。
        self.assertTrue(s["conn_chassis_anchor_to_probe"]["success"],
                        f"3-arg connect failed: {s['conn_chassis_anchor_to_probe']}")
        self.assertTrue(s["probe_got_anchor"],
                        "probe didn't receive chassis anchor via output_index=1")
        # builder 建的 in_chassis_wheel_mount 也拿到锚点（builder 路径）。
        self.assertTrue(s["wheels_got_anchor"],
                        "builder's in_chassis_wheel_mount didn't receive anchor")
        # 自底向上 promote: core 有 wheels_wheel_radius (按分组), subnet 引用 core.
        self.assertTrue(s["core_has_wheels_wheel_radius"],
                        "core should have wheels_wheel_radius after promote")
        self.assertEqual(s["core_default"], 0.5, "core should inherit subnet default")
        self.assertIn("wheels_wheel_radius", s["subnet_refs_core"],
                      f"subnet should ref core: {s['subnet_refs_core']!r}")


if __name__ == "__main__":
    unittest.main()
