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

# 模拟 LLM 在 chassis subnet 加一个 spare parm "length"。
chassis = core.node("chassis")
tmpl = hou.FloatParmTemplate("length", "Length", 1)
chassis.addSpareParmTuple(tmpl)

# 跑 promote。
res = promote_params(core)
result["steps"]["promote_result"] = res
# 检查 core 上出现了 chassis_length。
p = core.parm("chassis_length")
result["steps"]["s4_core_parm_exists"] = p is not None
if p is not None:
    result["steps"]["s4_expr"] = p.expression()
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
        """§8 步骤4: promote 后 core 出现 chassis_length，表达式正确。"""
        res, _ = self._run()
        self.assertTrue(res["steps"]["s4_core_parm_exists"],
                        f"chassis_length not created: {res}")
        expr = res["steps"].get("s4_expr", "")
        self.assertIn("chassis", expr)
        self.assertIn("length", expr,
                      f"expression should ref chassis/length: {expr!r}")


_FULL_HARNESS = r"""
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
core = create_project_hda(name="proj_full")
decl = empty_declaration("proj_full")
add_component(decl, "chassis", purpose="车架",
              ports_out=[
                  {"index": 0, "kind": "geometry"},
                  {"index": 1, "kind": "anchors", "points": [
                      {"name": "wheel_mount", "role": "mount"}]}])
add_component(decl, "wheels", purpose="车轮")

# 全链路：scaffold → 加锚点 → 加 spare parm → promote
build_project_scaffold(core, declaration=decl)
chassis = core.node("chassis")
wr = chassis.createNode("attribwrangle", "make_anchors")
wr.parm("snippet").set('addpoint(0, set(2,0,1));\n'
    'setpointattrib(0, "name", 0, "wheel_mount", "set");')
wr.parm("class").set("detail")  # detail 模式：空输入也跑一次 addpoint
chassis.node("out_anchors").setInput(0, wr)
chassis.node("out_anchors").cook(force=True)  # 强制 cook 确保 output_1 有几何

tmpl = hou.FloatParmTemplate("length", "Length", 1)
chassis.addSpareParmTuple(tmpl)  # 真实 API（Task 5 验证）：addSpareParmTuple
promote_params(core)

result["steps"]["anchors_ok"] = (len(chassis.node("output_1").geometry().points()) == 1)
result["steps"]["promote_ok"] = (core.parm("chassis_length") is not None)
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
        """scaffold→锚点→promote→重建幂等 全链路。"""
        res, _ = self._run()
        self.assertTrue(res["steps"]["anchors_ok"], f"anchors: {res}")
        self.assertTrue(res["steps"]["promote_ok"], f"promote: {res}")
        self.assertTrue(res["steps"]["anchors_after_rebuild"],
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


if __name__ == "__main__":
    unittest.main()
