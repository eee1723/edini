"""Project HDA → component scaffold builder + parameter promoter.

Component-pipeline paradigm (replaces old rooted-assembly build_project_model):
  - build_project_scaffold: create empty component subnets (each with
    out_geometry/out_anchors nulls + output_0/output_1 output nodes forming
    the subnet's multi-output ports). Geometry is left for the LLM.
  - promote_params: lift component subnet spare parms to the core HDA
    interface (Task 5).

The scaffold is the deterministic, drift-detectable part; geometry + wiring
are the LLM's free part. See spec §5 / §3.3.

Pure reuse of edini.project.state (declaration read/write) and
edini.project.ports (node-name constants + validation). This module is the
ONLY one here that builds real geometry, so it imports real hou.
"""
from __future__ import annotations

import hou  # real hou at runtime

from edini.project.state import load_declaration, save_declaration, append_log
from edini.project.ports import (
    OUT_GEOMETRY_NODE, OUT_ANCHORS_NODE, OUTPUT_0_NODE, OUTPUT_1_NODE,
    validate_component_ports,
)


def build_project_scaffold(core_node: "hou.Node",
                           *, declaration: dict | None = None) -> dict:
    """建/更新组件脚手架（空 subnet + 4 节点 + 2 连线）。

    幂等：对已存在的 component subnet / 内部节点跳过，只补缺失的。
    不碰几何（几何归 LLM）。返回 {success, components_built, components_skipped}。

    Args:
        core_node: edini::project SOP HDA 实例（脚手架建在其内部网络）。
        declaration: 可选，传入则先 set + save 到 core（convenience）；
            省略则从 core 的隐藏 parm 读现有声明。
    """
    # 可选地更新声明。
    if declaration is not None:
        save_declaration(core_node, declaration)

    decl = load_declaration(core_node)
    components = decl.get("components", [])

    built, skipped = [], []
    for comp in components:
        # 先校验 ports（shift-left：建之前先挡非法结构）。
        validate_component_ports(comp.get("ports", {}))
        cid = comp["id"]
        subnet = _ensure_component_subnet(core_node, cid)
        _ensure_scaffold_nodes(subnet)
        built.append(cid) if cid not in skipped else None

    # 第二遍：跨组件输入连线。必须在所有 subnet 建好之后做——外部连线
    # setInput(i, upstream, port) 要求 upstream/downstream subnet 都已存在。
    for comp in components:
        cid = comp["id"]
        subnet = core_node.node(cid)
        if subnet is None:
            continue
        _ensure_input_scaffold(core_node, comp, subnet)

    # 记日志（成功）。
    decl = load_declaration(core_node)
    append_log(decl, kind="scaffold",
               summary=f"built {len(built)} component scaffold(s)",
               payload={"built": built, "skipped": skipped},
               result_ok=True)
    save_declaration(core_node, decl)

    return {"success": True, "components_built": built,
            "components_skipped": skipped,
            "project": core_node.path()}


def _ensure_component_subnet(parent: "hou.Node", component_id: str) -> "hou.Node":
    """确保 parent 下有名为 component_id 的 subnet，返回它。幂等。

    已存在则直接返回；不存在则 createNode("subnet")。
    """
    existing = parent.node(component_id)
    if existing is not None:
        return existing
    subnet = parent.createNode("subnet", node_name=component_id)
    return subnet


def _ensure_scaffold_nodes(subnet: "hou.Node") -> None:
    """确保 subnet 内有 4 个脚手架节点 + 2 条连线。幂等。

    out_geometry (null) → output_0 (output)   [subnet output 1 = 主几何]
    out_anchors  (null) → output_1 (output)   [subnet output 2 = 锚点云]

    已存在的节点跳过创建；连线每次确保（setInput 幂等）。
    """
    out_geo = _ensure_node(subnet, "null", OUT_GEOMETRY_NODE)
    out_anc = _ensure_node(subnet, "null", OUT_ANCHORS_NODE)
    output_0 = _ensure_node(subnet, "output", OUTPUT_0_NODE)
    output_1 = _ensure_node(subnet, "output", OUTPUT_1_NODE)

    # 连线：null 的输出 → output 节点的输入 0。
    output_0.setInput(0, out_geo)
    output_1.setInput(0, out_anc)

    # 整理布局（真机观感，不影响逻辑）。
    subnet.layoutChildren()


def _ensure_input_scaffold(core_node: "hou.Node", comp: dict,
                           subnet: "hou.Node") -> None:
    """为一个组件建/维护输入脚手架（外部连线 + 内部命名 null）。幂等。

    对 comp 的 ports.in[] 的第 i 条：
      - 外部：downstream.setInput(i, upstream, from_port) — downstream 的第 i
        个输入连接器 ← upstream（in_entry["from"]）的第 from_port 个输出。
      - 内部：建命名 null in_<from>_<anchor>，setInput(0, indirectInputs()[i])。
        indirectInputs()[i] 对应外部第 i 个输入连接器。

    upstream 不存在则跳过该条（局部声明安全）。已存在的内部节点跳过创建，
    setInput 幂等——重跑只补缺失，不碰 LLM 接在 in_* 下游的连线。
    """
    in_ports = comp.get("ports", {}).get("in", [])
    if not in_ports:
        return
    indirect_inputs = subnet.indirectInputs()
    for i, in_entry in enumerate(in_ports):
        from_id = in_entry["from"]
        from_port = in_entry["port"]
        anchor = in_entry["anchor"]
        upstream = core_node.node(from_id)
        if upstream is None:
            # upstream 组件未建（局部声明）——跳过，留以后补。
            continue
        # 外部：下游第 i 输入 ← 上游第 from_port 输出。
        subnet.setInput(i, upstream, from_port)
        # 内部：命名 null ← indirectInputs()[i]。
        in_name = f"in_{from_id}_{anchor}"
        in_node = _ensure_node(subnet, "null", in_name)
        indirect = indirect_inputs[i]
        in_node.setInput(0, indirect)


def _ensure_node(parent: "hou.Node", node_type: str,
                 node_name: str) -> "hou.Node":
    """确保 parent 下有名为 node_name 的 node_type 节点。幂等。"""
    existing = parent.node(node_name)
    if existing is not None:
        return existing
    return parent.createNode(node_type, node_name=node_name)


def promote_params(core_node: "hou.Node") -> dict:
    """把所有组件 subnet 的 spare parm 提取到 core HDA 顶层。

    对 core 下每个组件 subnet（./chassis, ./wheels, ...）：
      读它的 spareParms() → 每个 hou.Parm <name>：
        在 core 建 parm "<component>_<name>"（放 "<component>" folder）
        设其表达式 ch("./<component>/<name>")
    结果：用户在 core 顶层调 chassis_length → 驱动 chassis subnet → 几何 live。

    幂等：已存在的 core parm 只更新表达式，不重复建。
    返回 {success, promoted: [{component, parm}], project}。

    真机 API（H21 hython 验证，Task 5）：节点上没有 spareParmGroup()/
    setSpareParmGroup()（handoff bug#1 假设错误）。读用 spareParms()，
    写用 addSpareParmFolder()/addSpareParmTuple()。
    """
    decl = load_declaration(core_node)
    promoted = []

    for comp in decl.get("components", []):
        cid = comp["id"]
        subnet = core_node.node(cid)
        if subnet is None:
            continue
        # 读组件 subnet 的 spare parm 列表（真机 API：spareParms()）。
        try:
            spare_parms = subnet.spareParms()
        except Exception:
            continue
        for sparmparm in spare_parms:
            pname = _parm_name(sparmparm)
            if pname is None:
                continue
            core_parm_name = f"{cid}_{pname}"
            _install_core_parm(core_node, cid, pname, core_parm_name)
            promoted.append({"component": cid, "parm": core_parm_name})

    append_log(decl, kind="promote",
               summary=f"promoted {len(promoted)} parm(s)",
               payload={"promoted": promoted}, result_ok=True)
    save_declaration(core_node, decl)
    return {"success": True, "promoted": promoted,
            "project": core_node.path()}


def _parm_name(sparmparm) -> str | None:
    """从 spare parm 取 parm 名。

    真机 spareParms() 返回 list[hou.Parm]，每个有 .name()。
    """
    try:
        return sparmparm.name()
    except Exception:
        return None


def _install_core_parm(core_node: "hou.Node", component_id: str,
                       subnet_parm: str, core_parm: str) -> None:
    """在 core HDA 安装一个 parm，表达式引用组件 subnet 的同名 parm。

    真机 API（H21 验证）：用 addSpareParmFolder() 建 folder +
    addSpareParmTuple(template, in_folder=(folder,), create_missing_folders=True)
    把 Float parm 放进该 folder。表达式设为相对 channel 引用。
    幂等：已存在则只更新表达式（不再重复建 folder/parm）。
    """
    # 幂等：已存在的 core parm 只更新表达式。
    existing = core_node.parm(core_parm)
    if existing is not None:
        existing.setExpression(f'ch("./{component_id}/{subnet_parm}")')
        return
    # 建 Float parm template（最常见类型）。
    tmpl = hou.FloatParmTemplate(core_parm, core_parm, 1)
    # create_missing_folders=True：folder 不存在则自动建，幂等友好。
    core_node.addSpareParmTuple(tmpl, in_folder=(component_id,),
                                create_missing_folders=True)
    # 建完后设表达式。
    p = core_node.parm(core_parm)
    if p is not None:
        p.setExpression(f'ch("./{component_id}/{subnet_parm}")')
