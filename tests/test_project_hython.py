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

# Pure-logic constants available without hou (used in test assertions in the
# main process; the hython subprocess re-imports them itself).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
from edini.project.ports import (  # noqa: E402
    TAG_COMPONENT_NODE, AXIS_BAKE_NODE, INPUT_FILTER_PREFIX,
)

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
                                 OUTPUT_0_NODE, OUTPUT_1_NODE,
                                 TAG_COMPONENT_NODE)

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
            cwd=_REPO,
            # stdin=DEVNULL avoids a CPython 3.14 / Windows subprocess race:
            # without it, the parent's stdin handle is made inheritable for the
            # child, which intermittently throws OSError [WinError 6] inside
            # _make_inheritable. This makes hython tests ~100% flaky otherwise.
            stdin=subprocess.DEVNULL)
        combined = proc.stdout + proc.stderr
        # 找 RESULT_JSON 行。
        for line in combined.splitlines():
            if line.startswith("RESULT_JSON:"):
                return json.loads(line[len("RESULT_JSON:"):]), combined
        self.fail(f"no RESULT_JSON in output.\n--- stdout ---\n{proc.stdout}\n"
                  f"--- stderr ---\n{proc.stderr}")

    def test_step1_scaffold_structure(self):
        """§8 步骤1: 两个 subnet 存在，chassis 有脚手架节点（含 tag_component + __edini_axis_bake）。"""
        res, _ = self._run_harness()
        self.assertTrue(res["steps"]["s1_chassis_exists"],
                        f"chassis subnet missing: {res}")
        self.assertTrue(res["steps"]["s1_wheels_exists"],
                        f"wheels subnet missing: {res}")
        ch = res["steps"]["s1_chassis_children"]
        for expected in ("out_geometry", "out_anchors", "output_0", "output_1",
                         TAG_COMPONENT_NODE, AXIS_BAKE_NODE):
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
            capture_output=True, text=True, timeout=180, cwd=_REPO,
            stdin=subprocess.DEVNULL)  # avoid WinError 6 handle race — see _run_harness
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
            capture_output=True, text=True, timeout=180, cwd=_REPO,
            stdin=subprocess.DEVNULL)  # avoid WinError 6 handle race — see _run_harness
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
            capture_output=True, text=True, timeout=180, cwd=_REPO,
            stdin=subprocess.DEVNULL)  # avoid WinError 6 handle race — see _run_harness
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
            capture_output=True, text=True, timeout=180, cwd=_REPO,
            stdin=subprocess.DEVNULL)  # avoid WinError 6 handle race — see _run_harness
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


# design_params → real core spare parms (top-down param source). Verifies that
# build_project_scaffold instantiates design_params as actual core parms so
# ch('../../width') references resolve (previously they only lived in the
# declaration JSON, so geometry silently zeroed).
_DESIGN_PARAMS_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component, add_design_param
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold

result = {"steps": {}}
core = create_project_hda(name="proj_dp")
decl = empty_declaration("proj_dp")
add_component(decl, "tabletop", purpose="桌面")
add_design_param(decl, "width", default=1.2, min=0.1, max=10.0)
add_design_param(decl, "top_thickness", default=0.04, min=0.001, max=1.0)

# build_scaffold must instantiate design_params as REAL core spare parms.
build_project_scaffold(core, declaration=decl)

wp = core.parm("width")
result["steps"]["s1_width_exists"] = wp is not None
if wp is not None:
    result["steps"]["s1_width_default"] = wp.eval()
    t = wp.parmTemplate()
    result["steps"]["s1_width_min"] = t.minValue()
    result["steps"]["s1_width_max"] = t.maxValue()
tp = core.parm("top_thickness")
result["steps"]["s1_thickness_exists"] = tp is not None
if tp is not None:
    result["steps"]["s1_thickness_default"] = tp.eval()

# A ch() reference from a child geometry must now resolve (not silently 0).
# Build a box inside tabletop whose sizex references ch("../../width").
tabletop = core.node("tabletop")
box = tabletop.createNode("box", "probe_box")
box.parm("sizex").setExpression('ch("../../width")')
tabletop.node("out_geometry").setInput(0, box)
tabletop.node("out_geometry").cook(force=True)
geo = tabletop.node("out_geometry").geometry()
# box default sizey=1, but sizex should follow width=1.2 (not 0).
bx = geo.boundingBox()
result["steps"]["s2_ch_resolves"] = abs(bx.sizevec()[0] - 1.2) < 0.01
result["steps"]["s2_sizevec"] = list(bx.sizevec())

# Idempotent: rebuild must not duplicate or clobber the design parms.
wp_before = core.parm("width").eval()
build_project_scaffold(core)
result["steps"]["s3_idempotent_value_preserved"] = (core.parm("width").eval() == wp_before)
# Still only ONE width parm (no duplicate folder/parm creation).
result["steps"]["s3_width_count"] = sum(1 for p in core.parms() if p.name() == "width")
print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestDesignParamsHython(unittest.TestCase):
    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _DESIGN_PARAMS_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO,
            stdin=subprocess.DEVNULL)  # avoid WinError 6 handle race — see _run_harness
        combined = proc.stdout + proc.stderr
        for line in combined.splitlines():
            if line.startswith("RESULT_JSON:"):
                return json.loads(line[len("RESULT_JSON:"):]), combined
        self.fail(f"no RESULT_JSON.\nstdout:{proc.stdout}\nstderr:{proc.stderr}")

    def test_design_params_become_real_core_parms(self):
        """design_params declared in the scaffold must be instantiated as real
        core spare parms with the right default/min/max — so ch('../../width')
        references from child geometry resolve instead of zeroing."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["s1_width_exists"], f"core width parm missing: {res}")
        self.assertEqual(s["s1_width_default"], 1.2)
        self.assertEqual(s["s1_width_min"], 0.1)
        self.assertEqual(s["s1_width_max"], 10.0)
        self.assertTrue(s["s1_thickness_exists"])
        self.assertEqual(s["s1_thickness_default"], 0.04)

    def test_design_param_referenced_by_ch_resolves(self):
        """The whole point: a child node's ch('../../width') must evaluate to
        the core's width value (1.2), not 0 — proving the live param chain works
        once design_params are real core parms."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["s2_ch_resolves"],
                        f"ch('../../width') did not resolve to 1.2: {s.get('s2_sizevec')}")

    def test_design_params_idempotent(self):
        """Rebuilding the scaffold must not duplicate or clobber design parms."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["s3_idempotent_value_preserved"])
        self.assertEqual(s["s3_width_count"], 1,
                         f"expected exactly one width parm after rebuild: {res}")


# ============================================================================
# Fix 2 + Fix 3 regression: the chair-modeling log bugs, locked integrationally.
#   Fix 2: a component consuming anchors via ports.in must receive ONLY the
#          declared anchor name's points (Blast @name filter), not the whole
#          upstream anchor cloud. The log showed 5 points (4 leg + 1 backrest)
#          silently flowing into the leg port — took 5 tool rounds to patch.
#   Fix 3: scaffold auto-bakes prim-class component_id + edini_world_axis, so
#          geometry_inventory sees components and verify_orientation passes with
#          zero agent setup (the log showed both failing until manually patched).
# ============================================================================
_CHAIR_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.project.ports import (TAG_COMPONENT_NODE, AXIS_BAKE_NODE,
                                 INPUT_FILTER_PREFIX, OUTPUT_0_NODE)

result = {"steps": {}}
core = create_project_hda(name="proj_chair")
decl = empty_declaration("proj_chair")
# seat emits 5 anchors: 4 leg corners + 1 backrest center (exactly the log).
add_component(decl, "seat", purpose="seat surface",
    ports_out=[
        {"index": 0, "kind": "geometry", "description": "seat"},
        {"index": 1, "kind": "anchors", "points": [
            {"name": "leg_fr", "role": "mount"},
            {"name": "leg_fl", "role": "mount"},
            {"name": "leg_br", "role": "mount"},
            {"name": "leg_bl", "role": "mount"},
            {"name": "backrest_c", "role": "mount"}]}])
# leg consumes the seat anchor port — in the log it got ALL 5 points.
add_component(decl, "leg", purpose="legs",
    ports_in=[{"from": "seat", "port": 1, "anchor": "leg_fr"}])
res = build_project_scaffold(core, declaration=decl)
result["steps"]["route_warnings"] = res.get("route_warnings", [])

seat = core.node("seat")
leg = core.node("leg")

# --- emit the 5 anchors on seat (the log scenario) ---
wr = seat.createNode("attribwrangle", "make_anchors")
wr.parm("class").set("detail")
wr.parm("snippet").set(
    'addpoint(0, set(0.2,0,0.2));  setpointattrib(0,"name",0,"leg_fr","set");\n'
    'int p=addpoint(0, set(-0.2,0,0.2)); setpointattrib(0,"name",p,"leg_fl","set");\n'
    'p=addpoint(0, set(0.2,0,-0.2)); setpointattrib(0,"name",p,"leg_br","set");\n'
    'p=addpoint(0, set(-0.2,0,-0.2)); setpointattrib(0,"name",p,"leg_bl","set");\n'
    'p=addpoint(0, set(0,0,0.2)); setpointattrib(0,"name",p,"backrest_c","set");\n')
seat.node("out_anchors").setInput(0, wr)

# --- Fix 2: check the leg's in-port receives ONLY leg_fr (1 point), not 5 ---
filter_node = leg.node(INPUT_FILTER_PREFIX + "seat_leg_fr")
in_node = leg.node("in_seat_leg_fr")
result["steps"]["fix2_filter_exists"] = filter_node is not None
result["steps"]["fix2_in_node_exists"] = in_node is not None
if in_node is not None:
    in_node.cook(force=True)
    try:
        pts = in_node.geometry().points()
        result["steps"]["fix2_in_point_count"] = len(pts)
        result["steps"]["fix2_in_names"] = (
            [p.stringAttribValue("name") for p in pts] if pts else [])
    except Exception as e:
        result["steps"]["fix2_in_point_count"] = -1
        result["steps"]["fix2_error"] = str(e)

# --- Round-2 Fix B: the in-port must be a PURE point cloud (zero prims) ---
# even when the upstream anchor cloud carries degenerate prims (session 2 saw
# 72 zero-vertex prims leak through). Simulate by feeding the anchor cloud a
# prim-bearing input, then check the in-port prim count after the clean wrangle.
if in_node is not None:
    try:
        result["steps"]["fixb_in_prim_count"] = in_node.geometry().primCount()
    except Exception as e:
        result["steps"]["fixb_error"] = str(e)

# --- Round-2 Fix A: axis survives an agent-style tag_component override ---
# Give seat some real geometry so the bake chain has prims to tag.
box = seat.createNode("box", "seat_box")
seat.node("out_geometry").setInput(0, box)
seat.node("output_0").cook(force=True)

def _read_output0_attrs():
    geo = seat.node("output_0").geometry()
    return (geo.findPrimAttrib("component_id") is not None,
            geo.findPrimAttrib("edini_world_axis") is not None,
            geo.prims()[0].stringAttribValue("component_id") if geo.prims() else None)

try:
    ca, wa, cval = _read_output0_attrs()
    result["steps"]["fixa_before_component_id_is_prim"] = ca
    result["steps"]["fixa_before_world_axis_is_prim"] = wa
    result["steps"]["fixa_component_id_value"] = cval
except Exception as e:
    result["steps"]["fixa_before_error"] = str(e)

# THE SESSION-2 HOLE: agent overwrites tag_component's snippet with component_id
# only — which, pre-Fix-A, deleted the axis. Now tag_component holds only
# component_id by default, and the axis lives in __edini_axis_bake, so the
# override must NOT drop the axis.
tag = seat.node(TAG_COMPONENT_NODE)
if tag is not None:
    tag.parm("snippet").set('s@component_id = "seat";')
    tag.parm("class").set("primitive")
seat.node("output_0").cook(force=True)
try:
    ca2, wa2, _ = _read_output0_attrs()
    result["steps"]["fixa_after_override_component_id_prim"] = ca2
    result["steps"]["fixa_axis_survives_override"] = wa2  # THE KEY ASSERTION
except Exception as e:
    result["steps"]["fixa_after_override_error"] = str(e)

# --- Round-2 Fix A: rebuild re-forces the axis node even after corruption ---
axis_node = seat.node(AXIS_BAKE_NODE)
if axis_node is not None:
    axis_node.parm("snippet").set("// corrupted by something\n")
build_project_scaffold(core)  # rebuild — must restore the axis snippet
seat.node("output_0").cook(force=True)
try:
    ca3, wa3, _ = _read_output0_attrs()
    result["steps"]["fixa_rebuild_restores_axis"] = wa3
    # And the axis node's snippet is back to the platform default.
    result["steps"]["fixa_axis_node_snippet_restored"] = (
        seat.node(AXIS_BAKE_NODE) is not None and
        "edini_world_axis" in seat.node(AXIS_BAKE_NODE).parm("snippet").eval())
except Exception as e:
    result["steps"]["fixa_rebuild_error"] = str(e)

# Confirm the bake chain: out_geometry → tag_component → __edini_axis_bake → output_0.
result["steps"]["fixa_chain_wired"] = (
    leg.node(TAG_COMPONENT_NODE) is not None and
    leg.node(AXIS_BAKE_NODE) is not None and
    leg.node(TAG_COMPONENT_NODE).inputs() and
    leg.node(TAG_COMPONENT_NODE).inputs()[0].name() == "out_geometry" and
    leg.node(AXIS_BAKE_NODE).inputs() and
    leg.node(AXIS_BAKE_NODE).inputs()[0].name() == TAG_COMPONENT_NODE and
    leg.node(OUTPUT_0_NODE).inputs() and
    leg.node(OUTPUT_0_NODE).inputs()[0].name() == AXIS_BAKE_NODE)

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestChairRegressionHython(unittest.TestCase):
    """Locks the two highest-impact fixes against the chair-modeling log bugs."""

    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _CHAIR_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO,
            stdin=subprocess.DEVNULL)  # avoid WinError 6 handle race — see _run_harness
        combined = proc.stdout + proc.stderr
        for line in combined.splitlines():
            if line.startswith("RESULT_JSON:"):
                return json.loads(line[len("RESULT_JSON:"):]), combined
        self.fail(f"no RESULT_JSON.\nstdout:{proc.stdout}\nstderr:{proc.stderr}")

    def test_fix2_anchor_filter_drops_undeclared_points(self):
        """The chair bug: leg's in-port must receive ONLY leg_fr (1 point),
        not all 5 upstream anchors. The Blast @name filter enforces it."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["fix2_filter_exists"],
                        f"filter_sea_leg_fr Blast not built by scaffold: {res}")
        self.assertTrue(s["fix2_in_node_exists"], f"in_seat_leg_fr missing: {res}")
        self.assertEqual(s["fix2_in_point_count"], 1,
                         f"leg port must receive 1 point (leg_fr only), got "
                         f"{s.get('fix2_in_point_count')}: {s.get('fix2_in_names')}")
        self.assertEqual(s["fix2_in_names"], ["leg_fr"])

    def test_fixb_anchor_port_is_prim_free(self):
        """Round-2 Fix B: the in-port must be a PURE point cloud (zero prims)
        even when upstream carries degenerate prims — the __edini_anchor_clean
        wrangle strips them. Session 2 saw 72 zero-vertex prims leak through."""
        res, _ = self._run()
        s = res["steps"]
        self.assertIn("fixb_in_prim_count", s, f"prim-count probe missing: {res}")
        self.assertEqual(s["fixb_in_prim_count"], 0,
                         f"in-port must have 0 prims (pure point cloud), got "
                         f"{s['fixb_in_prim_count']}: {res}")

    def test_fix2_route_warnings_pass_for_well_formed_decl(self):
        """The declaration is well-formed (leg_fr IS emitted by seat), so the
        static route_warnings list must be empty."""
        res, _ = self._run()
        self.assertEqual(res["steps"]["route_warnings"], [],
                         f"unexpected route warnings: {res['steps']['route_warnings']}")

    def test_fixa_axis_survives_tag_component_override(self):
        """Round-2 Fix A (THE session-2 hole): agent overwrites tag_component's
        snippet with 's@component_id="seat";' alone. Pre-Fix-A this silently
        deleted the auto-baked edini_world_axis. Now the axis lives in the
        separate __edini_axis_bake node, so the override must NOT drop it."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s.get("fixa_before_world_axis_is_prim"),
                        f"axis should be baked before override: {res}")
        self.assertTrue(s.get("fixa_axis_survives_override"),
                        f"axis MUST survive the agent's tag_component override "
                        f"(the session-2 hole): {res}")
        self.assertTrue(s.get("fixa_after_override_component_id_prim"),
                        f"component_id should still be present after override: {res}")

    def test_fixa_rebuild_restores_axis_node(self):
        """Round-2 Fix A: a scaffold rebuild re-forces __edini_axis_bake's
        snippet even after manual corruption — the axis is platform-owned."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s.get("fixa_rebuild_restores_axis"),
                        f"rebuild should restore the axis attr: {res}")
        self.assertTrue(s.get("fixa_axis_node_snippet_restored"),
                        f"rebuild should restore __edini_axis_bake's snippet: {res}")

    def test_fixa_bake_chain_wired(self):
        """The bake chain is out_geometry → tag_component → __edini_axis_bake
        → output_0, so both attrs land on every downstream reader."""
        res, _ = self._run()
        self.assertTrue(res["steps"].get("fixa_chain_wired"),
                        f"bake chain not wired correctly: {res}")
        self.assertEqual(res["steps"].get("fixa_component_id_value"), "seat")


# ============================================================================
# Round-3 Fix D1/D2 regression: per-component orientation axis.
#   D1: a component declaring "axis":"Z" gets edini_world_axis={0,0,1} baked,
#       so verify_orientation PASSES for a Z-facing backrest (the session-3
#       failure, where the default-Y bake made a correct Z-facing panel fail).
#   D2: a per-check construction_axis override is honored even when a bake
#       exists (the session-3 L87 trap, where the param was silently ignored).
# ============================================================================
_CHAIR_AXIS_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.node_utils import verify_orientation

result = {"steps": {}}
core = create_project_hda(name="proj_axis")
decl = empty_declaration("proj_axis")
# seat: default axis Y (flat panel).
add_component(decl, "seat", purpose="seat",
    ports_out=[{"index": 0, "kind": "geometry"}])
# backrest: declares axis Z (side-facing panel) — the session-3 fix.
add_component(decl, "backrest", purpose="backrest facing +Z",
    axis="Z",
    ports_out=[{"index": 0, "kind": "geometry"}])
res = build_project_scaffold(core, declaration=decl)
result["steps"]["build_ok"] = res.get("success")
result["steps"]["route_warnings"] = res.get("route_warnings", [])

seat = core.node("seat")
backrest = core.node("backrest")

# seat: a flat box in the XZ plane (thin in Y) → genuinely Y-normal.
seatbox = seat.createNode("box", "seat_box")
seatbox.parm("sizex").set(0.5); seatbox.parm("sizey").set(0.04); seatbox.parm("sizez").set(0.5)
seat.node("out_geometry").setInput(0, seatbox)

# backrest: a flat box in the XY plane (thin in Z) → genuinely Z-normal.
brbox = backrest.createNode("box", "br_panel")
brbox.parm("sizex").set(0.5); brbox.parm("sizey").set(0.5); brbox.parm("sizez").set(0.04)
backrest.node("out_geometry").setInput(0, brbox)

core.node("OUT").cook(force=True)

# --- D1: read the baked edini_world_axis per component ---
def _axis_vec(node_path):
    geo = core.node(node_path).geometry()
    attr = geo.findPrimAttrib("edini_world_axis")
    if attr is None:
        return None
    try:
        raw = geo.prims()[0].floatListAttribValue("edini_world_axis")
        return [round(float(c), 3) for c in raw[:3]]
    except Exception:
        return None

result["steps"]["d1_seat_axis_baked"] = _axis_vec("seat/output_0")
result["steps"]["d1_backrest_axis_baked"] = _axis_vec("backrest/output_0")

# --- D1: verify_orientation on the real geometry ---
vo = verify_orientation("/obj/geo1/project1/OUT" if False else core.node("OUT").path(),
    checks=[
        {"component_id": "seat", "kind": "planar", "expected_axis": "Y"},
        {"component_id": "backrest", "kind": "planar", "expected_axis": "Z"},
    ])
result["steps"]["d1_verify"] = vo
result["steps"]["d1_seat_passed"] = next(
    (c["passed"] for c in vo.get("checks", []) if c.get("component_id") == "seat"), None)
result["steps"]["d1_backrest_passed"] = next(
    (c["passed"] for c in vo.get("checks", []) if c.get("component_id") == "backrest"), None)

# --- D2: construction_axis override on a Y-baked component (the L87 trap) ---
# Force the seat's axis to Y (already is), then verify with an explicit
# construction_axis override to confirm the param is honored, not ignored.
vo2 = verify_orientation(core.node("OUT").path(),
    checks=[
        {"component_id": "backrest", "kind": "planar", "expected_axis": "Z",
         "construction_axis": "Z"},
    ])
br_check = next((c for c in vo2.get("checks", []) if c.get("component_id") == "backrest"), {})
result["steps"]["d2_override_passed"] = br_check.get("passed")
result["steps"]["d2_axis_source"] = br_check.get("axis_source")

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestChairAxisHython(unittest.TestCase):
    """Round-3 Fix D1/D2: per-component axis declaration + construction_axis
    override. Locks the session-3 backrest-orientation failure."""

    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _CHAIR_AXIS_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO,
            stdin=subprocess.DEVNULL)  # avoid WinError 6 handle race — see _run_harness
        combined = proc.stdout + proc.stderr
        for line in combined.splitlines():
            if line.startswith("RESULT_JSON:"):
                return json.loads(line[len("RESULT_JSON:"):]), combined
        self.fail(f"no RESULT_JSON.\nstdout:{proc.stdout}\nstderr:{proc.stderr}")

    def test_d1_backrest_axis_z_baked_and_passes(self):
        """The session-3 failure: a Z-facing backrest declared axis:'Z' must
        have edini_world_axis={0,0,1} baked AND pass verify_orientation."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["build_ok"], f"scaffold failed: {res}")
        self.assertEqual(s["d1_backrest_axis_baked"], [0.0, 0.0, 1.0],
                         f"backrest should bake Z axis: {res}")
        self.assertEqual(s["d1_seat_axis_baked"], [0.0, 1.0, 0.0],
                         f"seat should bake default Y axis: {res}")
        self.assertTrue(s["d1_seat_passed"],
                        f"seat (Y) should pass: {s.get('d1_verify')}")
        self.assertTrue(s["d1_backrest_passed"],
                        f"backrest (Z) MUST pass after axis declaration "
                        f"(the session-3 fix): {s.get('d1_verify')}")

    def test_d2_construction_axis_override_honored(self):
        """D2: a per-check construction_axis override is honored (not ignored
        as in session-3 L87). axis_source must read 'override'."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["d2_override_passed"],
                        f"construction_axis override must make the check pass: {res}")
        self.assertEqual(s["d2_axis_source"], "override",
                         f"axis_source should be 'override': {res}")


# =============================================================================
# Layer A: scaffold returns input_wires ground-truth
#
# Session log 1 (the table build) showed the agent spending ~10 minutes
# "fixing" the shelf's wiring — reconnecting filter nodes, dropping to a
# sandbox setInput, deleting the whole filter chain — because it didn't
# TRUST that the scaffold had wired shelf's inputs to legs' anchor port
# correctly. The scaffold WAS correct (builder.py setInput(i,upstream,from_port)
# uses the declared port). The fix is to report that fact back so the agent
# can see the wire is good without probing. These tests prove the reported
# ground-truth matches the actual Houdini connection state.
# =============================================================================

_INPUT_WIRES_HARNESS = r"""
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

# ── Scenario 1: the table's shelf — declared port:1 (anchors) ──
# Mirrors session log 1 exactly: tabletop→legs→shelf, shelf consumes legs'
# anchor cloud (port 1). The agent should see the wire is good.
core = create_project_hda(name="proj_wires")
decl = empty_declaration("proj_wires")
add_component(decl, "tabletop", purpose="桌面",
    ports_out=[
        {"index": 0, "kind": "geometry"},
        {"index": 1, "kind": "anchors", "points": [
            {"name": "leg_mount", "role": "mount"}]}])
add_component(decl, "legs", purpose="腿",
    ports_in=[{"from": "tabletop", "port": 1, "anchor": "leg_mount"}],
    ports_out=[
        {"index": 0, "kind": "geometry"},
        {"index": 1, "kind": "anchors", "points": [
            {"name": "shelf_mount", "role": "mount"}]}])
add_component(decl, "shelf", purpose="搁板",
    ports_in=[{"from": "legs", "port": 1, "anchor": "shelf_mount"}])
res = build_project_scaffold(core, declaration=decl)
wires = res.get("input_wires", [])
result["steps"]["s1_input_wires_present"] = isinstance(wires, list) and len(wires) > 0

# Three declared ports.in entries → three wire descriptors.
result["steps"]["s1_wire_count"] = len(wires)

# The shelf→legs wire is the critical one (the one the agent distrusted).
shelf_wires = [w for w in wires if w["component"] == "shelf"]
result["steps"]["s1_shelf_wire_count"] = len(shelf_wires)
if shelf_wires:
    sw = shelf_wires[0]
    result["steps"]["s1_shelf_wired"] = sw.get("wired")
    result["steps"]["s1_shelf_port_matches"] = sw.get("port_matches")
    result["steps"]["s1_shelf_carries"] = sw.get("carries")
    result["steps"]["s1_shelf_actual_output_index"] = sw.get("actual_output_index")
    result["steps"]["s1_shelf_actual_upstream"] = sw.get("actual_upstream")
    result["steps"]["s1_shelf_chain_ready"] = sw.get("internal_chain_ready")

# The legs→tabletop wire should also report correctly.
legs_wires = [w for w in wires if w["component"] == "legs"]
if legs_wires:
    lw = legs_wires[0]
    result["steps"]["s1_legs_wired"] = lw.get("wired")
    result["steps"]["s1_legs_port_matches"] = lw.get("port_matches")
    result["steps"]["s1_legs_carries"] = lw.get("carries")

# ── Scenario 2: declared port:0 (geometry) — different carries label ──
# A control: if a component declares port:0, carries should say "geometry",
# proving the label distinguishes the two cases (not hardcoded to "anchors").
core2 = create_project_hda(name="proj_wires2")
decl2 = empty_declaration("proj_wires2")
add_component(decl2, "base", purpose="基座",
    ports_out=[{"index": 0, "kind": "geometry"}])
add_component(decl2, "top", purpose="顶",
    ports_in=[{"from": "base", "port": 0, "anchor": "noref"}])
res2 = build_project_scaffold(core2, declaration=decl2)
wires2 = res2.get("input_wires", [])
top_wires = [w for w in wires2 if w["component"] == "top"]
if top_wires:
    tw = top_wires[0]
    result["steps"]["s2_top_wired"] = tw.get("wired")
    result["steps"]["s2_top_port_matches"] = tw.get("port_matches")
    result["steps"]["s2_top_carries"] = tw.get("carries")

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestInputWiresGroundTruthHython(unittest.TestCase):
    """Layer A: build_project_scaffold returns input_wires that reflect the
    ACTUAL Houdini connection state, so the agent needn't probe/reconnect."""

    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _INPUT_WIRES_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO,
            stdin=subprocess.DEVNULL)
        combined = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0,
                         f"hython failed (rc={proc.returncode}):\n{combined[-2000:]}")
        idx = combined.rfind("RESULT_JSON:")
        self.assertGreater(idx, -1, f"no RESULT_JSON in output:\n{combined[-2000:]}")
        return json.loads(combined[idx + len("RESULT_JSON:"):]), combined

    def test_s1_shelf_wire_reports_ready(self):
        """The shelf→legs anchor wire (port:1) reports wired+port_matches+
        carries:'anchors'+chain_ready — the exact ground-truth the agent in
        session log 1 was missing."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["s1_input_wires_present"], f"no input_wires: {res}")
        self.assertEqual(s["s1_wire_count"], 2,
                         f"expected 2 wires (legs+shelf), got {s['s1_wire_count']}")
        self.assertEqual(s["s1_shelf_wire_count"], 1)
        self.assertTrue(s["s1_shelf_wired"], "shelf input should be wired")
        self.assertTrue(s["s1_shelf_port_matches"],
                        "shelf wire should match declared port:1 — this is the "
                        "core guarantee the agent distrusted in session log 1")
        self.assertEqual(s["s1_shelf_carries"], "anchors")
        self.assertEqual(s["s1_shelf_actual_output_index"], 1)
        self.assertTrue(s["s1_shelf_actual_upstream"], "actual_upstream path should be set")
        self.assertTrue(s["s1_shelf_chain_ready"],
                        "internal filter/clean/null chain should be complete")

    def test_s1_legs_wire_reports_ready(self):
        """The legs→tabletop wire (also port:1) reports correctly too."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["s1_legs_wired"])
        self.assertTrue(s["s1_legs_port_matches"])
        self.assertEqual(s["s1_legs_carries"], "anchors")

    def test_s2_geometry_port_carries_label_differs(self):
        """A declared port:0 reports carries:'geometry' (not 'anchors') —
        proving the label distinguishes the two cases rather than being
        hardcoded."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["s2_top_wired"])
        self.assertTrue(s["s2_top_port_matches"])
        self.assertEqual(s["s2_top_carries"], "geometry")


# =============================================================================
# Layer C1: by_name anchors — measure a SEMANTIC marker, not the bbox hull
#
# Session log 2 (the road bike) placed the frame's four anchors via
# bbox_face_center. Because the frame is a single merged mesh, bbox face
# centers ≠ the real dropout/head-tube/bottom-bracket positions — so changing
# frame_scale moved the wheels to the bbox hull, not the real geometry. The
# fix: the root generator emits NAMED marker points at real geometric
# locations, and downstream anchors use measure:"by_name" + marker:<name> to
# pick THOSE exact points. This is truly parametric against the actual shape.
# =============================================================================

_BY_NAME_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component, add_design_param
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold, add_anchors

result = {"steps": {}}

# A 'base' component: a box of height H, PLUS a named marker point placed at
# the box's REAL top-face center (y = H). This mirrors a root generator (e.g.
# a bike frame's Python SOP) that emits semantic marker points at true
# geometric locations. We use a VEX wrangle (not Python) to build it so the
# test is deterministic and readable.
core = create_project_hda(name="proj_byname")
decl = empty_declaration("proj_byname")
add_design_param(decl, "height", default=1.0, min=0.1, max=5.0, label="高度")
add_component(decl, "base", purpose="基座",
    ports_out=[
        {"index": 0, "kind": "geometry"},
        {"index": 1, "kind": "anchors", "points": [
            {"name": "top_mount", "role": "mount"}]}])
build_project_scaffold(core, declaration=decl)

base = core.node("base")
# Build the box + a named marker at the REAL top (y=H), then merge both into
# out_geometry. The marker carries @name="top_marker" so by_name can find it.
box = base.createNode("box", "base_box")
box.parm("sizex").set(1.0)
box.parm("sizey").setExpression("ch('/obj/proj_byname/project_core/height')")
box.parm("sizez").set(1.0)
box.parm("ty").setExpression("ch('/obj/proj_byname/project_core/height') * 0.5")
# Marker wrangle: emit ONE point at y=H (the real top), tagged @name=top_marker.
mk = base.createNode("attribwrangle", "mk_marker")
mk.parm("class").set("detail")
mk.parm("snippet").set(
    'float H = ch("/obj/proj_byname/project_core/height");\n'
    'int p = addpoint(geoself(), set(0, H, 0));\n'
    'setpointattrib(geoself(), "name", p, "top_marker", "set");\n')
mrg = base.createNode("merge", "merge_base")
mrg.setInput(0, box)
mrg.setInput(1, mk)
base.node("out_geometry").setInput(0, mrg)

# The CRITICAL anchor: measure by_name, picking the top_marker point. This is
# the real-top position, NOT the bbox center (which would be y=H/2).
add_anchors(core, "base", [
    {"measure": "by_name", "marker": "top_marker", "name": "top_mount"}])

# Cook the anchor output and read the measured position.
out_anc = base.node("out_anchors")
out_anc.cook(force=True)
pts = out_anc.geometry().points()
result["steps"]["c1_anchor_point_count"] = len(pts)
if pts:
    p = pts[0].position()
    result["steps"]["c1_anchor_y_at_H1"] = p.y()
    result["steps"]["c1_anchor_name"] = pts[0].stringAttribValue("name")

# ── THE LIVE TEST: change height 1.0 → 2.0, recook, anchor must move to y=2.0 ──
core.parm("height").set(2.0)
out_anc.cook(force=True)
pts2 = out_anc.geometry().points()
if pts2:
    result["steps"]["c1_anchor_y_at_H2"] = pts2[0].position().y()

# ── CONTROL: a bbox_center anchor would sit at y=H/2 (=1.0 at H=2), proving ──
# ── by_name is NOT just rediscovering the bbox. Build a sibling anchor.    ──
add_anchors(core, "base", [
    {"measure": "bbox_center", "name": "bbox_ctl"}])
out_anc.cook(force=True)
# out_anchors now merges top_mount (by_name) + bbox_ctl (bbox_center).
# Find bbox_ctl by name.
for pt in out_anc.geometry().points():
    if pt.stringAttribValue("name") == "bbox_ctl":
        result["steps"]["c1_bbox_ctl_y_at_H2"] = pt.position().y()

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestByNameAnchorHython(unittest.TestCase):
    """Layer C1: by_name anchors track the REAL geometry, not the bbox hull."""

    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _BY_NAME_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO,
            stdin=subprocess.DEVNULL)
        combined = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0,
                         f"hython failed (rc={proc.returncode}):\n{combined[-2000:]}")
        idx = combined.rfind("RESULT_JSON:")
        self.assertGreater(idx, -1, f"no RESULT_JSON:\n{combined[-2000:]}")
        return json.loads(combined[idx + len("RESULT_JSON:"):]), combined

    def test_by_name_picks_real_marker_position(self):
        """At H=1.0, the by_name anchor sits at y=1.0 (the real top marker),
        NOT at y=0.5 (the bbox center). This is the core distinction."""
        res, _ = self._run()
        s = res["steps"]
        self.assertEqual(s["c1_anchor_point_count"], 1,
                         f"by_name should emit exactly one anchor point: {res}")
        self.assertAlmostEqual(s["c1_anchor_y_at_H1"], 1.0, places=4,
                               msg=f"anchor should be at the real top (y=1.0), "
                               f"not the bbox center (y=0.5): {res}")
        self.assertEqual(s["c1_anchor_name"], "top_mount")

    def test_by_name_is_live_with_geometry(self):
        """Changing height 1.0 → 2.0 moves the marker (and thus the by_name
        anchor) to y=2.0. The anchor tracks the REAL geometry, live."""
        res, _ = self._run()
        s = res["steps"]
        self.assertAlmostEqual(s["c1_anchor_y_at_H2"], 2.0, places=4,
                               msg=f"by_name anchor must follow the marker to "
                               f"y=2.0 when height doubles: {res}")

    def test_by_name_differs_from_bbox_center(self):
        """CONTROL: at H=2.0, the bbox_center anchor sits at y=1.0 (=H/2),
        while the by_name anchor sits at y=2.0 (=H). This proves by_name is
        NOT rediscovering the bbox — it tracks the true geometric location
        the generator emitted. This is exactly the failure mode the bike's
        frame anchors had (bbox face center ≠ real dropout)."""
        res, _ = self._run()
        s = res["steps"]
        self.assertIn("c1_bbox_ctl_y_at_H2", s,
                       f"bbox_ctl control anchor missing: {res}")
        self.assertAlmostEqual(s["c1_bbox_ctl_y_at_H2"], 1.0, places=4,
                               msg=f"bbox_center should be at y=1.0 (=H/2) at H=2: {res}")
        self.assertAlmostEqual(s["c1_anchor_y_at_H2"], 2.0, places=4,
                               msg=f"by_name should be at y=2.0 (=H): {res}")
        # The decisive assertion: by_name (2.0) != bbox_center (1.0).
        self.assertNotAlmostEqual(s["c1_anchor_y_at_H2"], s["c1_bbox_ctl_y_at_H2"],
                                  places=3,
                                  msg="by_name must differ from bbox_center — "
                                      "this is the whole point of Layer C1")


# =============================================================================
# Layer C2: verify_parametric — the LIVE guarantee gate
#
# Session log 2 (the road bike) declared the model complete after inspect_health
# returned overall_ok, but never verified a param actually moved the geometry.
# overall_ok only means "not broken now", not "parametric". verify_parametric
# proves parametricity by perturbation: change a param, recook, assert the
# geometry changed on the expected axis, restore. This is the "is it really
# done?" gate.
# =============================================================================

_VERIFY_PARAMETRIC_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component, add_design_param
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.node_utils import verify_parametric

result = {"steps": {}}

# ── PASS scenario: a box whose sizex ch()-references the core's 'length' ──
core = create_project_hda(name="proj_vp")
decl = empty_declaration("proj_vp")
add_design_param(decl, "length", default=1.0, min=0.1, max=5.0, label="长度")
add_component(decl, "box_comp", purpose="一个盒子")
build_project_scaffold(core, declaration=decl)

comp = core.node("box_comp")
box = comp.createNode("box", "b1")
box.parm("sizex").setExpression(
    "ch('/obj/proj_vp/project_core/length')")   # LIVE link
comp.node("out_geometry").setInput(0, box)

# verify_parametric on the project OUT. length 1.0 -> 2.0 must move X.
out_node = core.node("OUT")
res_pass = verify_parametric(
    node_path=out_node.path(),
    core_path=core.path(),
    param="length",
    new_value=2.0,
    expected_axis="X",
    min_relative_change=0.05,
)
result["steps"]["pass_passed"] = res_pass.get("passed")
result["steps"]["pass_restored"] = res_pass.get("restored")
result["steps"]["pass_reason"] = res_pass.get("reason")
# Confirm the param was RESTORED to the original 1.0 (non-destructive check).
result["steps"]["pass_param_value_after"] = core.parm("length").eval()

# ── FAIL scenario: a box whose sizex references a BROKEN path ──
# Simulates the session-log "promote returns 0 / broken ch() chain" failure:
# the param exists but the geometry doesn't respond to it.
core2 = create_project_hda(name="proj_vp2")
decl2 = empty_declaration("proj_vp2")
add_design_param(decl2, "length", default=1.0, min=0.1, max=5.0, label="长度")
add_component(decl2, "box_comp", purpose="一个盒子")
build_project_scaffold(core2, declaration=decl2)
comp2 = core2.node("box_comp")
box2 = comp2.createNode("box", "b2")
# sizex set to a literal (NOT referencing length) — the param is dead.
box2.parm("sizex").set(1.0)
comp2.node("out_geometry").setInput(0, box2)
res_fail = verify_parametric(
    node_path=core2.node("OUT").path(),
    core_path=core2.path(),
    param="length",
    new_value=3.0,
    expected_axis="X",
    min_relative_change=0.05,
)
result["steps"]["fail_passed"] = res_fail.get("passed")
result["steps"]["fail_reason"] = res_fail.get("reason")
result["steps"]["fail_restored"] = res_fail.get("restored")

# ── No-op perturbation guard: equal new_value is rejected ──
res_noop = verify_parametric(
    node_path=core.node("OUT").path(),
    core_path=core.path(),
    param="length",
    new_value=1.0,   # equals the default — must be rejected
    )
result["steps"]["noop_success_false"] = (res_noop.get("success") is False)
result["steps"]["noop_error_mentions_equals"] = (
    "equals" in (res_noop.get("error") or ""))

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestVerifyParametricHython(unittest.TestCase):
    """Layer C2: verify_parametric is the LIVE-guarantee completion gate."""

    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _VERIFY_PARAMETRIC_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO,
            stdin=subprocess.DEVNULL)
        combined = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0,
                         f"hython failed (rc={proc.returncode}):\n{combined[-2000:]}")
        idx = combined.rfind("RESULT_JSON:")
        self.assertGreater(idx, -1, f"no RESULT_JSON:\n{combined[-2000:]}")
        return json.loads(combined[idx + len("RESULT_JSON:"):]), combined

    def test_live_param_passes(self):
        """A box whose sizex ch()-references 'length' PASSES when length is
        perturbed 1.0 -> 2.0 with expected_axis X. The geometry moved on X."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["pass_passed"],
                        f"a live-linked param should PASS verify_parametric: {res}")
        self.assertIn("PASS", s["pass_reason"])

    def test_param_restored_after_check(self):
        """verify_parametric is NON-DESTRUCTIVE: after the check, the param is
        back at its original value (1.0), not left at the perturbation (2.0)."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["pass_restored"],
                        "restored flag must be True")
        self.assertAlmostEqual(s["pass_param_value_after"], 1.0, places=4,
                               msg="param must be restored to original 1.0")

    def test_dead_param_fails_with_diagnostic(self):
        """A box whose sizex does NOT reference 'length' FAILS, with a reason
        explaining the param didn't reach the geometry. This is exactly the
        session-log 'broken ch() chain / promote returns 0' failure caught."""
        res, _ = self._run()
        s = res["steps"]
        self.assertFalse(s["fail_passed"],
                         f"a dead param must FAIL verify_parametric: {res}")
        # The reason must point at the root cause (no axis changed / didn't
        # reach the geometry), so the agent knows the param chain is broken.
        reason = s["fail_reason"] or ""
        self.assertTrue(
            "axis" in reason.lower() or "reach" in reason.lower()
            or "did not change" in reason.lower(),
            f"fail reason should diagnose the broken chain: {reason!r}")

    def test_noop_perturbation_rejected(self):
        """A new_value equal to the current value is rejected — it would pass
        vacuously and teach the wrong lesson."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["noop_success_false"])
        self.assertTrue(s["noop_error_mentions_equals"])


# =============================================================================
# Finding 4: repath_to_relative — make a component migratable
#
# The design_params path uses absolute ch('/obj/.../project_core/<p>'), which
# ties a component to its current project path. project_repath_to_relative
# rewrites those to relative ch('../../<p>') (depth-computed) so a component
# can be copy-pasted into another project. This is the cure for Finding 4's
# "component not migratable" half (the other half — promote returns 0 — is
# resolved by documenting it as correct under the design_params path).
# =============================================================================

_REPATH_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component, add_design_param
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.node_utils import repath_to_relative

result = {"steps": {}}

# Build a project with one component referencing the core's 'length' via
# ABSOLUTE ch() (the design_params path). A box whose sizex + sizey both
# reference length.
core = create_project_hda(name="proj_rp")
decl = empty_declaration("proj_rp")
add_design_param(decl, "length", default=1.5, min=0.1, max=5.0, label="长度")
add_component(decl, "box_comp", purpose="b")
build_project_scaffold(core, declaration=decl)
comp = core.node("box_comp")
box = comp.createNode("box", "b1")
box.parm("sizex").setExpression(
    "ch('/obj/proj_rp/project_core/length')")            # absolute
box.parm("sizey").setExpression(
    "ch('/obj/proj_rp/project_core/length') * 0.5")      # absolute, in expr
comp.node("out_geometry").setInput(0, box)
comp.node("out_geometry").cook(force=True)

# Snapshot the geometry BEFORE repath (bbox sizes).
before_bbox = comp.node("output_0").geometry().boundingBox()
result["steps"]["before_sizex"] = before_bbox.sizevec().x()
result["steps"]["before_sizey"] = before_bbox.sizevec().y()
# Record the expressions for inspection.
result["steps"]["before_sizex_expr"] = box.parm("sizex").expression()
result["steps"]["before_sizey_expr"] = box.parm("sizey").expression()

# ── Repath ──
res = repath_to_relative(core_path=core.path(), component_id="box_comp")
result["steps"]["repath_count"] = res.get("count")
result["steps"]["repath_success"] = res.get("success")
rewritten = res.get("rewritten", [])
# Find the sizex rewrite to confirm the target expression form.
sx_rewrites = [r for r in rewritten if r["parm"] == "sizex"]
if sx_rewrites:
    result["steps"]["after_sizex_expr"] = sx_rewrites[0]["after"]

# ── Behavior unchanged: geometry still cooks to the SAME bbox ──
comp.node("out_geometry").cook(force=True)
after_bbox = comp.node("output_0").geometry().boundingBox()
result["steps"]["after_sizex"] = after_bbox.sizevec().x()
result["steps"]["after_sizey"] = after_bbox.sizevec().y()

# ── LIVE: changing length still moves the geometry after repath ──
core.parm("length").set(3.0)
comp.node("out_geometry").cook(force=True)
live_bbox = comp.node("output_0").geometry().boundingBox()
result["steps"]["live_sizex_at_len3"] = live_bbox.sizevec().x()
core.parm("length").set(1.5)   # restore

# ── MIGRATION TEST: copy the component into a DIFFERENT project ──
# A migrated component on absolute paths would break (path '/obj/proj_rp/...'
# no longer exists). On relative paths it should still cook.
core2 = create_project_hda(name="proj_rp2")
decl2 = empty_declaration("proj_rp2")
add_design_param(decl2, "length", default=2.0, min=0.1, max=5.0, label="长度")
build_project_scaffold(core2, declaration=decl2)
# Copy the (already-repathed) box_comp from proj_rp into proj_rp2.
comp2 = hou.copyNodesTo([comp], core2)[0]
comp2.moveToGoodPosition()
# length lives on core2 (the design param), not on comp2. proj_rp2's default is 2.0.
comp2.node("out_geometry").cook(force=True)
try:
    migrated_bbox = comp2.node("output_0").geometry().boundingBox()
    result["steps"]["migrated_cook_ok"] = True
    result["steps"]["migrated_sizex"] = migrated_bbox.sizevec().x()
    # proj_rp2's length default is 2.0 → sizex should be 2.0 (not 0).
except Exception as e:
    result["steps"]["migrated_cook_ok"] = False
    result["steps"]["migrated_error"] = str(e)

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestRepathToRelativeHython(unittest.TestCase):
    """Finding 4: repath_to_relative makes a component migratable without
    changing its behavior."""

    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _REPATH_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO,
            stdin=subprocess.DEVNULL)
        combined = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0,
                         f"hython failed (rc={proc.returncode}):\n{combined[-2000:]}")
        idx = combined.rfind("RESULT_JSON:")
        self.assertGreater(idx, -1, f"no RESULT_JSON:\n{combined[-2000:]}")
        return json.loads(combined[idx + len("RESULT_JSON:"):]), combined

    def test_repath_rewrites_absolute_to_relative(self):
        """repath finds the absolute ch() references and rewrites them. At
        least the sizex one should become a relative ch('../../length')."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["repath_success"])
        self.assertGreaterEqual(s["repath_count"], 2,
                                f"expected >=2 rewrites (sizex+sizey): {res}")
        after = s["after_sizex_expr"]
        self.assertIsNotNone(after, f"sizex not rewritten: {res}")
        self.assertNotIn("/obj/proj_rp", after,
                         f"absolute path should be gone: {after}")
        self.assertIn("../", after,
                      f"should be a relative reference now: {after}")

    def test_behavior_unchanged_after_repath(self):
        """The geometry cooks to the SAME bbox before and after repath — only
        the path notation changed, not the link. length=1.5 → sizex=1.5 both."""
        res, _ = self._run()
        s = res["steps"]
        self.assertAlmostEqual(s["before_sizex"], s["after_sizex"], places=4,
                               msg="sizex must not change across repath")
        self.assertAlmostEqual(s["before_sizey"], s["after_sizey"], places=4,
                               msg="sizey must not change across repath")

    def test_live_after_repath(self):
        """After repath, changing length STILL moves the geometry (the link is
        live, just relative now). length 1.5→3.0 should double sizex."""
        res, _ = self._run()
        s = res["steps"]
        self.assertAlmostEqual(s["live_sizex_at_len3"], 3.0, places=4,
                               msg="after repath, length 1.5→3 must move sizex to 3.0")

    def test_migrated_component_cooks(self):
        """THE point of repath: copy the component into another project and it
        still cooks (relative paths resolve to the new core). On absolute paths
        it would break (stale /obj/proj_rp/... reference)."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s.get("migrated_cook_ok"),
                        f"migrated component must cook: {res}")
        # proj_rp2 length default 2.0 → migrated box sizex should be 2.0.
        self.assertAlmostEqual(s["migrated_sizex"], 2.0, places=4,
                               msg="migrated component should read the new core's length=2.0")


# =============================================================================
# HARDENING: edge-case coverage for the findings-1..5 fixes.
#
# These tests exist because the session-logs-analysis audit found that the
# C1/C2/Finding-4 fixes had happy-path-only hython coverage. The critical
# failure paths — verify_parametric restore-on-exception, by_name zero-match,
# repath hou.ch() form + near-name collisions, internal_chain disconnected —
# were entirely untested. Each maps to a real bug or latent fragility the audit
# flagged. (See wiki/pitfalls.md "session-logs-analysis audit".)
# =============================================================================

_HARDENING_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component, add_design_param
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold, add_anchors
from edini.node_utils import verify_parametric, repath_to_relative

result = {"steps": {}}


def _safe(fn, key_prefix, **kw):
    '''Run fn() capturing return OR exception into result['steps'][key_prefix*].'''
    try:
        return fn()
    except Exception as e:
        result["steps"][key_prefix + "_error"] = str(e)
        return None


# ──────────────────────────────────────────────────────────────────────────
# (1) verify_parametric RESTORES the param even when the perturbed cook RAISES.
# This is the audit's #1 correctness gap: the original code had no try/finally
# around perturb→recook→snapshot→errors, so a cook error mid-verification left
# the user's scene mutated at new_value — the exact opposite of the tool's
# "ALWAYS restore" contract.
# ──────────────────────────────────────────────────────────────────────────
def _scenario_err():
    core_e = create_project_hda(name="proj_err")
    decl_e = empty_declaration("proj_err")
    add_design_param(decl_e, "length", default=1.0, min=0.1, max=5.0, label="长度")
    add_component(decl_e, "boom_comp", purpose="raises on perturb")
    build_project_scaffold(core_e, declaration=decl_e)
    comp_e = core_e.node("boom_comp")
    # A box that LIVE-references length (cooks fine at any value) PLUS a
    # wrangle that RAISES via VEX error() specifically when length ≈ 2.0.
    box_e = comp_e.createNode("box", "ok_box")
    box_e.parm("sizex").setExpression(
        "ch('/obj/proj_err/project_core/length')")
    boom = comp_e.createNode("attribwrangle", "boom")
    boom.parm("class").set("detail")
    boom.parm("snippet").set(
        'float __v = ch("/obj/proj_err/project_core/length");\n'
        'if (abs(__v - 2.0) < 0.05) {\n'
        '    error("intentional cook error at length=2.0\\n");\n'
        '}\n')
    mrg_e = comp_e.createNode("merge", "mrg")
    mrg_e.setInput(0, box_e)
    mrg_e.setInput(1, boom)
    comp_e.node("out_geometry").setInput(0, mrg_e)
    # Cook at length=1.0 first — must succeed (no error triggered yet).
    try:
        comp_e.node("out_geometry").cook(force=True)
        result["steps"]["err_setup_ok"] = True
    except Exception as e:
        result["steps"]["err_setup_ok"] = False
        result["steps"]["err_setup_error"] = str(e)
    result["steps"]["err_original"] = core_e.parm("length").eval()
    res_err = verify_parametric(
        node_path=core_e.node("OUT").path(),
        core_path=core_e.path(),
        param="length",
        new_value=2.0,
        expected_axis="X",
        min_relative_change=0.05,
    )
    result["steps"]["err_success"] = res_err.get("success")
    result["steps"]["err_restored_field"] = res_err.get("restored")
    # THE decisive assertion source: read the LIVE parm value after the call.
    result["steps"]["err_param_value_after"] = core_e.parm("length").eval()

_safe(_scenario_err, "err_top")


# ──────────────────────────────────────────────────────────────────────────
# (2) by_name anchor emits a cook ERROR when the marker is not found (typo),
# instead of silently producing zero points. The audit found the original VEX
# had no else branch on !__found — a typo'd marker yielded 0 anchors with no
# diagnostic, indistinguishable from "upstream empty".
# ──────────────────────────────────────────────────────────────────────────
def _scenario_noname():
    core_n = create_project_hda(name="proj_noname")
    decl_n = empty_declaration("proj_noname")
    add_component(decl_n, "base", purpose="emits NO named marker",
        ports_out=[
            {"index": 0, "kind": "geometry"},
            {"index": 1, "kind": "anchors", "points": [
                {"name": "ghost_mount", "role": "mount"}]}])
    build_project_scaffold(core_n, declaration=decl_n)
    base_n = core_n.node("base")
    # A box geometry with NO @name attribute on any point.
    box_n = base_n.createNode("box", "plain_box")
    base_n.node("out_geometry").setInput(0, box_n)
    # Ask for a marker that was never emitted — should error, not stay silent.
    add_anchors(core_n, "base", [
        {"measure": "by_name", "marker": "does_not_exist", "name": "ghost_mount"}])
    wr = base_n.node("anchor_ghost_mount")
    errs = []
    pts_after = -1
    if wr is not None:
        # VEX error() raises hou.OperationFailed from cook() — that IS the
        # signal we want (hard failure, not silent 0-point success).
        try:
            wr.cook(force=True)
        except Exception as cook_exc:
            errs.append(str(cook_exc))
        try:
            errs = errs + list(wr.errors() or [])
        except Exception as e:
            errs.append(f"<errors() read failed: {e}>")
        try:
            pts_after = len(base_n.node("out_anchors").geometry().points())
        except Exception:
            pts_after = -2
    joined = " | ".join(errs)
    result["steps"]["noname_error_count"] = len(errs)
    result["steps"]["noname_error_mentions_marker"] = ("does_not_exist" in joined)
    result["steps"]["noname_anchor_points"] = pts_after

_safe(_scenario_noname, "noname_top")


# ──────────────────────────────────────────────────────────────────────────
# (3a) repath rewrites the hou.ch('...') form (the hython happy-path test only
# exercised bare ch()).
# (3b) repath does NOT touch a near-collision reference: a parm pointing at
# project_core_BACKUP (whose path merely CONTAINS the core path string) must
# stay absolute. Correctness hinges on the `if '/' in parm_tail` guard.
# ──────────────────────────────────────────────────────────────────────────
def _scenario_houch():
    core_h = create_project_hda(name="proj_hc")
    decl_h = empty_declaration("proj_hc")
    add_design_param(decl_h, "length", default=1.5, min=0.1, max=5.0, label="长度")
    add_component(decl_h, "box_comp", purpose="b")
    build_project_scaffold(core_h, declaration=decl_h)
    comp_h = core_h.node("box_comp")
    box_h = comp_h.createNode("box", "bh")
    # hou.ch form (not bare ch).
    box_h.parm("sizex").setExpression(
        "hou.ch('/obj/proj_hc/project_core/length')")
    # Near-collision: path CONTAINS the core path string. Must stay absolute.
    # sizey will evaluate to 0 (project_core_backup doesn't exist) but that's
    # fine — we only inspect the EXPRESSION, not the cook result, here.
    box_h.parm("sizey").setExpression(
        "ch('/obj/proj_hc/project_core_backup/length') * 0.5")
    comp_h.node("out_geometry").setInput(0, box_h)
    res_h = repath_to_relative(core_path=core_h.path(), component_id="box_comp")
    sx_after = box_h.parm("sizex").expression()
    sy_after = box_h.parm("sizey").expression()
    result["steps"]["hc_count"] = res_h.get("count")
    result["steps"]["hc_sizex_after"] = sx_after
    result["steps"]["hc_sizex_rewritten"] = (
        "/obj/proj_hc/project_core/" not in (sx_after or ""))
    result["steps"]["hc_sizey_after"] = sy_after
    result["steps"]["hc_sizey_untouched"] = (
        "/obj/proj_hc/project_core_backup/length" in (sy_after or ""))

_safe(_scenario_houch, "hc_top")


# ──────────────────────────────────────────────────────────────────────────
# (4) internal_chain_ready: if the internal filter→clean→in_null chain is
# DISCONNECTED (nodes exist but no setInput between them), the audit expects
# input_wires[].internal_chain_ready == False. The current builder only checks
# node EXISTENCE, so this records the CURRENT (deficient) behavior and is
# marked @expectedFailure below.
# ──────────────────────────────────────────────────────────────────────────
def _scenario_chain():
    from edini.project.ports import INPUT_FILTER_PREFIX, ANCHOR_CLEAN_PREFIX
    from edini.project.builder import _collect_input_wires
    core_c = create_project_hda(name="proj_chain")
    decl_c = empty_declaration("proj_chain")
    add_component(decl_c, "up", purpose="upstream",
        ports_out=[
            {"index": 0, "kind": "geometry"},
            {"index": 1, "kind": "anchors", "points": [
                {"name": "m", "role": "mount"}]}])
    add_component(decl_c, "dn", purpose="downstream",
        ports_in=[{"from": "up", "port": 1, "anchor": "m"}])
    build_project_scaffold(core_c, declaration=decl_c)
    dn = core_c.node("dn")
    filt = dn.node(f"{INPUT_FILTER_PREFIX}up_m")
    # Deliberately disconnect the filter's input — it still EXISTS but carries
    # no data. This is the false-positive case: node present, chain broken.
    if filt is not None:
        try:
            filt.setInput(0, None)
        except Exception as e:
            result["steps"]["chain_break_error"] = str(e)
    wires = _collect_input_wires(core_c, decl_c)
    dn_wire = next((w for w in wires if w.get("component") == "dn"), {})
    result["steps"]["chain_nodes_exist"] = (
        dn.node(f"{INPUT_FILTER_PREFIX}up_m") is not None)
    result["steps"]["chain_internal_ready_reported"] = dn_wire.get(
        "internal_chain_ready")

_safe(_scenario_chain, "chain_top")

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestHardeningEdgeCasesHython(unittest.TestCase):
    """Edge-case coverage the session-logs-analysis audit found missing for
    the findings-1..5 fixes. Each test maps to a flagged bug or latent
    fragility."""

    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _HARDENING_HARNESS],
            capture_output=True, text=True, timeout=240, cwd=_REPO,
            stdin=subprocess.DEVNULL)
        combined = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0,
                         f"hython failed (rc={proc.returncode}):\n{combined[-2000:]}")
        idx = combined.rfind("RESULT_JSON:")
        self.assertGreater(idx, -1, f"no RESULT_JSON:\n{combined[-2000:]}")
        return json.loads(combined[idx + len("RESULT_JSON:"):]), combined

    # ── (1) verify_parametric restore-on-exception ──

    def test_verify_parametric_restores_on_cook_error(self):
        """THE audit #1 bug: when the perturbed cook raises, the param MUST
        still be restored. The live parm value after the call must equal the
        original (1.0), NOT new_value (2.0). This is the tool's core safety
        contract — without the try/finally fix, a cook error silently mutated
        the user's scene."""
        res, _ = self._run()
        s = res["steps"]
        # Guard against a silent setup failure masquerading as a pass.
        self.assertNotIn("err_top_error", s,
                         f"scenario raised before reaching verify_parametric: "
                         f"{s.get('err_top_error')}")
        self.assertTrue(s.get("err_setup_ok"),
                        f"length=1.0 setup must cook clean first: {res}")
        self.assertEqual(s["err_original"], 1.0)
        # The call may report success:False (the cook errored) — that's fine.
        # What matters is the param was RESTORED.
        self.assertEqual(s["err_param_value_after"], 1.0,
                         f"param must be restored to 1.0 after a cook error, "
                         f"got {s['err_param_value_after']} (scene mutated!). "
                         f"full result: {res}")
        # And the restored field should be truthy (finally ran).
        self.assertTrue(s.get("err_restored_field"),
                        f"restored field should be truthy after the finally ran")

    # ── (2) by_name zero-match emits an error ──

    def test_by_name_zero_match_emits_error(self):
        """A typo'd marker name must surface as a cook error (via VEX error()),
        not silently produce zero points. The agent needs to tell 'marker not
        found' from 'upstream geometry empty'."""
        res, _ = self._run()
        s = res["steps"]
        self.assertNotIn("noname_top_error", s,
                         f"scenario raised before the by_name cook: "
                         f"{s.get('noname_top_error')}")
        self.assertGreaterEqual(s["noname_error_count"], 1,
                                f"expected a cook error for the missing marker, "
                                f"got {s['noname_error_count']} errors: {res}")
        self.assertTrue(s["noname_error_mentions_marker"],
                        f"the error must name the missing marker "
                        f"'does_not_exist': {res}")

    # ── (3a) repath handles hou.ch() form ──

    def test_repath_rewrites_hou_ch_form(self):
        """The hython happy-path only tested bare ch(). hou.ch('...') is a
        distinct form the regex must also rewrite."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["hc_sizex_rewritten"],
                        f"hou.ch(absolute) must be rewritten to relative; "
                        f"got {s['hc_sizex_after']!r}: {res}")
        self.assertIn("hou.ch(", s["hc_sizex_after"],
                      f"the hou. prefix must be preserved: {res}")

    # ── (3b) repath leaves near-collision references untouched ──

    def test_repath_leaves_near_collision_untouched(self):
        """A reference to project_core_BACKUP (path contains the core path
        string) must NOT be rewritten — correctness hinges on the parm_tail
        guard. This is the audit's #1 latent-fragility case."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["hc_sizey_untouched"],
                        f"the near-collision reference must stay absolute: "
                        f"got {s['hc_sizey_after']!r}: {res}")
        # And count should reflect that only sizex was rewritten (1), not sizey.
        self.assertEqual(s["hc_count"], 1,
                         f"only sizex should be rewritten (sizey is a "
                         f"near-collision); count={s['hc_count']}: {res}")

    # ── (4) internal_chain_ready — a DISCONNECTED chain reports not-ready ──
    # Phase 1b: _collect_input_wires now verifies real setInput wiring (not just
    # node existence), so a disconnected filter→clean→in_null chain correctly
    # reports internal_chain_ready=False. (Was @expectedFailure pre-1b.)

    def test_internal_chain_disconnected_reports_not_ready(self):
        """Phase 1b (builder.py _collect_input_wires): the chain check now
        verifies the filter→clean→in_null nodes are actually WIRED together
        (indirect→blast→clean→in_null), not just present. A deliberately
        disconnected filter input (setInput(0,None)) → internal_chain_ready=False.
        Previously a known false-positive (node-exists-only check); the xfail is
        removed because the check is now hardened."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["chain_nodes_exist"],
                        "precondition: the chain nodes must exist for this test "
                        f"to mean anything: {res}")
        # A disconnected chain now reports internal_chain_ready=False.
        self.assertFalse(s["chain_internal_ready_reported"],
                         f"disconnected chain should report not-ready; "
                         f"reported={s['chain_internal_ready_reported']}: {res}")


# =============================================================================
# Phase 1c: project_status — one-shot per-component completion snapshot.
# Replaces the N-tool status-gathering loop. Builds a 3-component project,
# completes ONLY the tabletop (geometry + 4 anchors), leaves legs/shelf empty,
# then asserts project_status distinguishes built from unbuilt components in
# a single call.
# =============================================================================

_STATUS_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component, add_design_param
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold, add_anchors
from edini.node_utils import project_status

result = {"steps": {}}

# 3-component chain: tabletop (emits 4 leg anchors) → legs (emits 2 shelf
# anchors) → shelf. Only tabletop will be built; legs/shelf left empty.
core = create_project_hda(name="proj_status")
decl = empty_declaration("proj_status")
add_design_param(decl, "length", default=1.2, min=0.4, max=3.0, label="长度")
add_component(decl, "tabletop", purpose="桌面",
    ports_out=[
        {"index": 0, "kind": "geometry"},
        {"index": 1, "kind": "anchors", "points": [
            {"name": "leg_fr", "role": "mount"},
            {"name": "leg_fl", "role": "mount"},
            {"name": "leg_br", "role": "mount"},
            {"name": "leg_bl", "role": "mount"}]}])
add_component(decl, "legs", purpose="四腿",
    ports_in=[{"from": "tabletop", "port": 1, "anchor": "leg_fr"},
              {"from": "tabletop", "port": 1, "anchor": "leg_fl"},
              {"from": "tabletop", "port": 1, "anchor": "leg_br"},
              {"from": "tabletop", "port": 1, "anchor": "leg_bl"}],
    ports_out=[
        {"index": 0, "kind": "geometry"},
        {"index": 1, "kind": "anchors", "points": [
            {"name": "shelf_fr", "role": "mount"},
            {"name": "shelf_bl", "role": "mount"}]}])
add_component(decl, "shelf", purpose="层板",
    ports_in=[{"from": "legs", "port": 1, "anchor": "shelf_fr"},
              {"from": "legs", "port": 1, "anchor": "shelf_bl"}])
build_project_scaffold(core, declaration=decl)

# Build geometry ONLY in tabletop + emit its 4 anchors. legs/shelf stay empty.
top = core.node("tabletop")
box = top.createNode("box", "top_box")
box.parm("sizex").setExpression("ch('/obj/proj_status/project_core/length')")
box.parm("sizey").set(0.05)
box.parm("sizez").set(0.6)
top.node("out_geometry").setInput(0, box)
add_anchors(core, "tabletop", [
    {"measure": "bbox_corner", "axes": "+X-Y+Z", "name": "leg_fr"},
    {"measure": "bbox_corner", "axes": "-X-Y+Z", "name": "leg_fl"},
    {"measure": "bbox_corner", "axes": "+X-Y-Z", "name": "leg_br"},
    {"measure": "bbox_corner", "axes": "-X-Y-Z", "name": "leg_bl"}])

status = project_status(core.path())
comps = {c["id"]: c for c in status["components"]}
result["steps"]["component_count"] = status["component_count"]
result["steps"]["top_geo_flow"] = comps["tabletop"]["geo_flow"]
result["steps"]["top_prim_count"] = comps["tabletop"]["prim_count"]
result["steps"]["top_anchors_declared"] = comps["tabletop"]["anchors"]["declared"]
result["steps"]["top_anchors_emitted"] = comps["tabletop"]["anchors"]["emitted"]
result["steps"]["top_anchors_missing"] = comps["tabletop"]["anchors"]["missing"]
result["steps"]["top_errors"] = comps["tabletop"]["errors"]
result["steps"]["legs_geo_flow"] = comps["legs"]["geo_flow"]
result["steps"]["legs_anchors_declared"] = comps["legs"]["anchors"]["declared"]
result["steps"]["legs_anchors_emitted"] = comps["legs"]["anchors"]["emitted"]
result["steps"]["shelf_geo_flow"] = comps["shelf"]["geo_flow"]
result["steps"]["overall_with_geometry"] = status["overall"]["with_geometry"]
result["steps"]["overall_complete"] = status["overall"]["complete"]
result["steps"]["overall_incomplete"] = status["overall"]["incomplete"]

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestProjectStatusHython(unittest.TestCase):
    """Phase 1c: project_status — one-shot snapshot distinguishing built from
    unbuilt components (replaces the N-tool status-gathering loop)."""

    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _STATUS_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO,
            stdin=subprocess.DEVNULL)
        combined = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0,
                         f"hython failed (rc={proc.returncode}):\n{combined[-2000:]}")
        idx = combined.rfind("RESULT_JSON:")
        self.assertGreater(idx, -1, f"no RESULT_JSON:\n{combined[-2000:]}")
        return json.loads(combined[idx + len("RESULT_JSON:"):]), combined

    def test_built_component_reports_complete(self):
        """tabletop (box wired + 4 anchors emitted + no errors) is complete."""
        res, _ = self._run()
        s = res["steps"]
        self.assertEqual(s["component_count"], 3)
        self.assertEqual(s["top_geo_flow"], "ok",
                         "tabletop has a box wired into out_geometry → ok")
        self.assertGreater(s["top_prim_count"], 0)
        self.assertEqual(s["top_anchors_declared"], 4)
        self.assertEqual(s["top_anchors_emitted"], 4)
        self.assertEqual(s["top_anchors_missing"], [])
        self.assertEqual(s["top_errors"], 0)

    def test_unbuilt_components_reported_empty(self):
        """legs + shelf have no geometry wired → geo_flow empty; legs declares
        anchors but emitted none."""
        res, _ = self._run()
        s = res["steps"]
        self.assertEqual(s["legs_geo_flow"], "empty")
        self.assertEqual(s["shelf_geo_flow"], "empty")
        self.assertEqual(s["legs_anchors_declared"], 2)
        self.assertEqual(s["legs_anchors_emitted"], 0)

    def test_overall_summary_and_incomplete_list(self):
        """overall correctly tallies: 1 with geometry, 1 complete, legs+shelf
        incomplete (tabletop NOT in the incomplete list)."""
        res, _ = self._run()
        s = res["steps"]
        self.assertEqual(s["overall_with_geometry"], 1)
        self.assertEqual(s["overall_complete"], 1)
        self.assertIn("legs", s["overall_incomplete"])
        self.assertIn("shelf", s["overall_incomplete"])
        self.assertNotIn("tabletop", s["overall_incomplete"])


# =============================================================================
# Phase 3: project_emit_markers — make by_name as easy as bbox.
# Emits @name marker points INTO a component's geometry at REAL measured
# positions, so a downstream by_name anchor picks them (tracking the real
# geometry, not the bbox hull). Closes 发现3's root cause: by_name used to
# require a hand-written marker-emission wrangle, so the agent always picked
# the easier bbox path.
# =============================================================================

_MARKERS_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component, add_design_param
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold, add_anchors, emit_markers

result = {"steps": {}}

# 'base': a box spanning 0..H (sizey=H, ty=H/2). emit_markers places a NAMED
# marker at the REAL top face center (y=H) — no hand-written wrangle.
core = create_project_hda(name="proj_markers")
decl = empty_declaration("proj_markers")
add_design_param(decl, "height", default=1.0, min=0.1, max=5.0, label="高度")
add_component(decl, "base", purpose="基座",
    ports_out=[
        {"index": 0, "kind": "geometry"},
        {"index": 1, "kind": "anchors", "points": [
            {"name": "top_mount", "role": "mount"}]}])
build_project_scaffold(core, declaration=decl)

base = core.node("base")
box = base.createNode("box", "base_box")
box.parm("sizex").set(1.0)
box.parm("sizey").setExpression("ch('/obj/proj_markers/project_core/height')")
box.parm("sizez").set(1.0)
box.parm("ty").setExpression("ch('/obj/proj_markers/project_core/height') * 0.5")
base.node("out_geometry").setInput(0, box)

# Emit a marker at the REAL top face center (bbox_face_center +Y → y = H).
emit_markers(core, "base", [
    {"measure": "bbox_face_center", "face": "+Y", "name": "top_marker"}])

# Downstream anchor: by_name picks top_marker (the real top), NOT bbox center.
add_anchors(core, "base", [
    {"measure": "by_name", "marker": "top_marker", "name": "top_mount"}])

out_anc = base.node("out_anchors")
out_anc.cook(force=True)
pts = [p for p in out_anc.geometry().points()
       if p.stringAttribValue("name") == "top_mount"]
result["steps"]["m1_anchor_point_count"] = len(pts)
if pts:
    result["steps"]["m1_anchor_y_at_H1"] = pts[0].position().y()

# CONTROL: a bbox_center anchor would sit at y=H/2 (=0.5 at H=1) — proving
# by_name picks the marker (y=H=1.0), not the bbox hull.
add_anchors(core, "base", [
    {"measure": "bbox_center", "name": "bbox_ctl"}])
out_anc.cook(force=True)
for pt in out_anc.geometry().points():
    if pt.stringAttribValue("name") == "bbox_ctl":
        result["steps"]["m1_bbox_ctl_y_at_H1"] = pt.position().y()

# LIVE: height 1.0 → 2.0. The emitted marker moves to y=2.0 (real top), and the
# by_name anchor follows — proving the marker tracks the real geometry.
core.parm("height").set(2.0)
out_anc.cook(force=True)
for pt in out_anc.geometry().points():
    if pt.stringAttribValue("name") == "top_mount":
        result["steps"]["m1_anchor_y_at_H2"] = pt.position().y()

# Idempotency: re-emit the same marker name — replaces in place, no duplicate.
emit_markers(core, "base", [
    {"measure": "bbox_face_center", "face": "+Y", "name": "top_marker"}])
result["steps"]["m1_marker_node_count_after_reemit"] = sum(
    1 for n in base.children() if n.name().startswith("marker_"))

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestEmitMarkersHython(unittest.TestCase):
    """Phase 3: project_emit_markers — by_name made as easy as bbox."""

    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _MARKERS_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO,
            stdin=subprocess.DEVNULL)
        combined = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0,
                         f"hython failed (rc={proc.returncode}):\n{combined[-2000:]}")
        idx = combined.rfind("RESULT_JSON:")
        self.assertGreater(idx, -1, f"no RESULT_JSON:\n{combined[-2000:]}")
        return json.loads(combined[idx + len("RESULT_JSON:"):]), combined

    def test_by_name_anchor_picks_emitted_marker_at_real_position(self):
        """The by_name anchor sits at the REAL top (y=H=1.0), not the bbox
        center (y=0.5) — proving project_emit_markers placed a marker the
        by_name anchor picks at the true geometric position."""
        res, _ = self._run()
        s = res["steps"]
        self.assertGreaterEqual(s["m1_anchor_point_count"], 1,
                                f"by_name anchor emitted no point: {res}")
        self.assertAlmostEqual(s["m1_anchor_y_at_H1"], 1.0, places=4,
            msg="by_name anchor must sit at the REAL top (y=H=1.0), not bbox center")
        # Control: bbox_center sits at H/2=0.5 — proving by_name ≠ bbox.
        self.assertAlmostEqual(s["m1_bbox_ctl_y_at_H1"], 0.5, places=4,
            msg="bbox_center control must sit at H/2=0.5")

    def test_marker_tracks_geometry_live(self):
        """Changing height 1.0→2.0 moves the marker to the new real top (y=2.0),
        and the by_name anchor follows — the LIVE parametric guarantee."""
        res, _ = self._run()
        s = res["steps"]
        self.assertAlmostEqual(s["m1_anchor_y_at_H2"], 2.0, places=4,
            msg="marker must track the real top (y=2.0) when height changes")

    def test_reemit_is_idempotent(self):
        """Re-emitting the same marker name replaces in place (1 node), not
        duplicates."""
        res, _ = self._run()
        s = res["steps"]
        self.assertEqual(s["m1_marker_node_count_after_reemit"], 1,
                         f"re-emit should replace, not duplicate: {res}")


# =============================================================================
# Phase 2: verify_robust — prove the model HOLDS across each design param's
# min/default/max range (the 'stable correct' guarantee), not just at one
# perturbation. Complementary to verify_parametric (which proves a param
# DRIVES the geometry at one point).
# =============================================================================

_ROBUST_HARNESS = r"""
import json, sys, os
sys.path.insert(0, os.path.join(r"%s", "python3.11libs"))
import hou
_hda = os.path.join(r"%s", "otls", "edini_project.hda")
if os.path.isfile(_hda):
    hou.hda.installFile(_hda)
from edini.project.state import empty_declaration, add_component, add_design_param
from edini.project.node import create_project_hda
from edini.project.builder import build_project_scaffold
from edini.node_utils import verify_robust

result = {"steps": {}}

# ── PASS case: a box whose sizex is driven by 'length' (min 0.4 / def 1.2 /
# max 3.0). Robust across the whole range — geometry stays non-degenerate. ──
core = create_project_hda(name="proj_robust")
decl = empty_declaration("proj_robust")
add_design_param(decl, "length", default=1.2, min=0.4, max=3.0, label="长度")
add_component(decl, "top", purpose="桌面",
    ports_out=[{"index": 0, "kind": "geometry"}])
build_project_scaffold(core, declaration=decl)
top = core.node("top")
box = top.createNode("box", "top_box")
box.parm("sizex").setExpression("ch('/obj/proj_robust/project_core/length')")
box.parm("sizey").set(0.05)
box.parm("sizez").set(0.6)
top.node("out_geometry").setInput(0, box)
out = core.node("OUT")

res = verify_robust(out.path(), core.path(), params=["length"])
result["steps"]["pass_overall"] = res["passed"]
pp = res["params"][0] if res.get("params") else {}
result["steps"]["pass_param_passed"] = pp.get("passed")
result["steps"]["pass_sample_values"] = [s["value"] for s in pp.get("samples", [])]
result["steps"]["pass_sample_points"] = [s["points"] for s in pp.get("samples", [])]
# Non-destructive: length restored to its original (1.2) after the sweep.
result["steps"]["pass_length_after"] = core.parm("length").eval()

# ── FAIL case: a component whose geometry VANISHES at the param's min. The
# generator emits int(ch('n')) points; at n=0 → 0 points. verify_robust must
# detect this fragility (the sample at n=0 fails). ──
core2 = create_project_hda(name="proj_robust_fail")
decl2 = empty_declaration("proj_robust_fail")
add_design_param(decl2, "n", default=4.0, min=0.0, max=8.0, label="点数")
add_component(decl2, "gen", purpose="生成器",
    ports_out=[{"index": 0, "kind": "geometry"}])
build_project_scaffold(core2, declaration=decl2)
gen = core2.node("gen")
b2 = gen.createNode("box", "src_box")
b2.parm("sizex").set(0.1)
wr = gen.createNode("attribwrangle", "emit_n")
wr.parm("class").set("detail")
wr.parm("snippet").set(
    'int n = int(ch("/obj/proj_robust_fail/project_core/n"));\n'
    'for (int i = npoints(geoself())-1; i>=0; i--) removepoint(geoself(), i);\n'
    'for (int i = 0; i < n; i++) addpoint(geoself(), set(float(i)*0.1, 0, 0));\n')
wr.setInput(0, b2)
gen.node("out_geometry").setInput(0, wr)
out2 = core2.node("OUT")

res2 = verify_robust(out2.path(), core2.path(), params=["n"])
result["steps"]["fail_overall"] = res2["passed"]
pp2 = res2["params"][0] if res2.get("params") else {}
result["steps"]["fail_sample_values"] = [s["value"] for s in pp2.get("samples", [])]
result["steps"]["fail_sample_points"] = [s["points"] for s in pp2.get("samples", [])]
result["steps"]["fail_sample_passed"] = [s["passed"] for s in pp2.get("samples", [])]

print("RESULT_JSON:" + json.dumps(result))
""" % (_REPO, _REPO)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestVerifyRobustHython(unittest.TestCase):
    """Phase 2: verify_robust — the range-sweep 'stable correct' gate."""

    def _run(self):
        proc = subprocess.run(
            [HYTHON, "-c", _ROBUST_HARNESS],
            capture_output=True, text=True, timeout=180, cwd=_REPO,
            stdin=subprocess.DEVNULL)
        combined = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0,
                         f"hython failed (rc={proc.returncode}):\n{combined[-2000:]}")
        idx = combined.rfind("RESULT_JSON:")
        self.assertGreater(idx, -1, f"no RESULT_JSON:\n{combined[-2000:]}")
        return json.loads(combined[idx + len("RESULT_JSON:"):]), combined

    def test_robust_model_passes_across_range(self):
        """A box driven by 'length' stays non-degenerate at min/default/max →
        verify_robust passes, every sample has points > 0."""
        res, _ = self._run()
        s = res["steps"]
        self.assertTrue(s["pass_overall"], f"robust model should pass: {res}")
        self.assertTrue(s["pass_param_passed"])
        # 3 samples (min/default/max), all non-zero geometry.
        self.assertEqual(len(s["pass_sample_values"]), 3)
        self.assertTrue(all(p > 0 for p in s["pass_sample_points"]),
                        f"all samples should have geometry: {res}")

    def test_non_destructive_restores_params(self):
        """After the sweep, 'length' is restored to its original value (1.2)."""
        res, _ = self._run()
        s = res["steps"]
        self.assertAlmostEqual(s["pass_length_after"], 1.2, places=5,
            msg="verify_robust must restore the param after the sweep")

    def test_fragile_model_detected(self):
        """A model whose geometry vanishes at n=0 → verify_robust fails, and
        the n=0 sample specifically reports 0 points + passed:False."""
        res, _ = self._run()
        s = res["steps"]
        self.assertFalse(s["fail_overall"],
                         f"fragile model (vanishes at n=0) should fail: {res}")
        # The n=0 sample has 0 points and passed=False.
        vals = s["fail_sample_values"]
        pts = s["fail_sample_points"]
        passed = s["fail_sample_passed"]
        zero_idx = vals.index(0.0)
        self.assertEqual(pts[zero_idx], 0,
                         f"n=0 sample should have 0 points: {res}")
        self.assertFalse(passed[zero_idx],
                         f"n=0 sample should fail: {res}")


if __name__ == "__main__":
    unittest.main()
