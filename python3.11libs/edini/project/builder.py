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


def _ensure_node(parent: "hou.Node", node_type: str,
                 node_name: str) -> "hou.Node":
    """确保 parent 下有名为 node_name 的 node_type 节点。幂等。"""
    existing = parent.node(node_name)
    if existing is not None:
        return existing
    return parent.createNode(node_type, node_name=node_name)
