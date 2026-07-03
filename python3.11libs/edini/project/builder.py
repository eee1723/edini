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

from edini.project.state import (
    load_declaration, save_declaration, append_log,
    get_design_params_for_component,
)
from edini.project.ports import (
    OUT_GEOMETRY_NODE, OUT_ANCHORS_NODE, OUTPUT_0_NODE, OUTPUT_1_NODE,
    validate_component_ports,
)
from edini.vex_strategies import build_mount_vex, VexStrategyError


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

    # 第三遍：core 层输出收集——把每个组件的主几何（subnet output 0）merge 到
    # 一个 OUT null，并设 display flag。没有这个，组件内部建模再正确，几何也
    # 不会在 core/viewport 显示（spec §3.1 画的 OUT 之前缺失，导致 agent 放弃
    # 新流程退回 sandbox）。幂等：重建只补缺失，不重复。
    _ensure_core_output(core_node, [c["id"] for c in components])

    # 第四遍：core 层 design_params —— 在 core HDA 顶层安装声明里的设计参数
    # （带 default/min/max）。core 是参数的单一真相源（spec §6 / 参数方向反转）；
    # 组件 subnet 在 promote 后用 ch("../<name>") 引用它们。幂等：已存在的跳过。
    _ensure_core_design_params(core_node, decl)

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


def _ensure_core_design_params(core_node: "hou.Node", decl: dict) -> None:
    """在 core HDA 顶层安装声明里的 design_params（带 default/min/max）。

    core 是参数的单一真相源。每个 design_param 成为一个 core spare parm
    （放 "Design" folder），带具体的 default/min/max 值（不是表达式）。
    组件 subnet 在 promote 时用 ch("../<name>") 引用它们。

    幂等：已存在的 parm 跳过（不覆盖用户调整过的值）。
    """
    for p in decl.get("design_params", []):
        name = p["name"]
        if core_node.parm(name) is not None:
            continue  # 已存在，不覆盖用户改过的值
        default = p.get("default", 0.0)
        pmin = p.get("min")
        pmax = p.get("max")
        # FloatParmTemplate kwargs: min/max are the slider range; use the
        # declared range if given, else a sensible default around the value.
        rmin = float(pmin) if pmin is not None else 0.0
        rmax = float(pmax) if pmax is not None else max(10.0, float(default) * 2)
        tmpl = hou.FloatParmTemplate(
            name, p.get("label", name), 1,
            default_value=([float(default)]),
            min=rmin, max=rmax,
        )
        core_node.addSpareParmTuple(tmpl, in_folder=("Design",),
                                    create_missing_folders=True)


def _ensure_core_output(core_node: "hou.Node", component_ids: list[str]) -> None:
    """确保 core 有一个 OUT 收集所有组件的主几何（subnet output 0）。

    结构：每个组件 subnet 的 output 0 → merge_all（若 >1 个组件）→ OUT（null,
    display flag）。单组件则 subnet → OUT 直连。这是 core 层的显示收集——没有
    它，组件内部建模再正确，几何也不会在 core/viewport 显示。

    幂等：OUT/merge 已存在则跳过创建；连线每次确保（setInput 幂等）。组件
    subnet 由前序步骤保证存在。
    """
    if not component_ids:
        return
    # 收集存在的组件 subnet。
    subnets = [core_node.node(cid) for cid in component_ids
               if core_node.node(cid) is not None]
    if not subnets:
        return

    out = _ensure_node(core_node, "null", "OUT")
    if len(subnets) == 1:
        # 单组件：直连 subnet output 0 → OUT。
        out.setInput(0, subnets[0], 0)
    else:
        # 多组件：merge_all 收集所有 subnet output 0 → OUT。
        merge = _ensure_node(core_node, "merge", "merge_all")
        for i, sub in enumerate(subnets):
            merge.setInput(i, sub, 0)
        out.setInput(0, merge)
    # OUT 是 core 的显示输出。
    out.setDisplayFlag(True)
    out.setRenderFlag(True)
    core_node.layoutChildren()


def promote_params(core_node: "hou.Node") -> dict:
    """把 core 的 design_params 接到引用它们的组件 subnet（core 为源）。

    方向（反转后的新范式）：core 顶层 parm 是单一真相源（带 default/min/max，
    由 build_scaffold 的 _ensure_core_design_params 安装）。本函数对每个
    design_param，在引用它的组件 subnet 上建一个同名 spare parm，表达式
    ch("../<name>") 引用 core。这样组件内部节点用 ch("./<name>") 或
    ch("<name>") 就拿到 core 驱动的值。用户改 core → 所有 subnet 跟变 →
    几何 + 程序化锚点 live 重算。

    幂等：已存在的 subnet parm 只更新表达式，不重复建。
    返回 {success, promoted: [{component, parm}], project}。
    """
    decl = load_declaration(core_node)
    promoted = []

    for comp in decl.get("components", []):
        cid = comp["id"]
        subnet = core_node.node(cid)
        if subnet is None:
            continue
        # 这个组件引用哪些 design_param（components=None 表示全部组件）。
        for p in get_design_params_for_component(decl, cid):
            pname = p["name"]
            # core 必须已有这个 parm（build_scaffold 建的）；没有则跳过。
            if core_node.parm(pname) is None:
                continue
            _install_subnet_parm_ref(subnet, pname)
            promoted.append({"component": cid, "parm": pname})

    append_log(decl, kind="promote",
               summary=f"promoted {len(promoted)} parm ref(s)",
               payload={"promoted": promoted}, result_ok=True)
    save_declaration(core_node, decl)
    return {"success": True, "promoted": promoted,
            "project": core_node.path()}


def _install_subnet_parm_ref(subnet: "hou.Node", parm_name: str) -> None:
    """在组件 subnet 上建/更新一个 spare parm，表达式引用 core 的同名 parm。

    subnet 内部节点用 ch("./<parm_name>") 或 ch("<parm_name>") 取值。
    幂等：已存在则只更新表达式。
    """
    existing = subnet.parm(parm_name)
    if existing is not None:
        existing.setExpression(f'ch("../{parm_name}")')
        return
    tmpl = hou.FloatParmTemplate(parm_name, parm_name, 1)
    subnet.addSpareParmTuple(tmpl, in_folder=("Design",),
                             create_missing_folders=True)
    p = subnet.parm(parm_name)
    if p is not None:
        p.setExpression(f'ch("../{parm_name}")')


def add_anchors(core_node: "hou.Node", component_id: str,
                anchors: list[dict],
                upstream_node_name: str = OUT_GEOMETRY_NODE) -> dict:
    """Procedurally generate anchor points from a component's geometry.

    Replaces hardcoded addpoint coordinates: each anchor is a measurement spec
    (e.g. {"measure":"bbox_corner","axes":"+X-Y+Z","name":"leg_mount_fr"})
    resolved into a LIVE VEX wrangle (via vex_strategies.build_mount_vex) that
    reads the upstream geometry's bbox on every cook. Change the geometry (via a
    core design param) → the bbox changes → the anchor re-computes automatically.

    For each anchor, creates an attribwrangle inside the component subnet:
      - input 0 = the upstream node (default out_geometry, i.e. the component's
        main geometry — so anchors derive from the actual built shape)
      - runs the measurement VEX (emits the measured point(s))
      - tags the emitted point(s) with @name = the anchor's name
    All anchor wrangles are merged into out_anchors (the component's anchor port).

    Args:
        core_node: the edini::project SOP HDA instance.
        component_id: which component subnet emits these anchors.
        anchors: list of {measure, name, ...measure-params}. `measure` selects
            the strategy (bbox_corner/bbox_face_center/grid_on_face/...); `name`
            is the @name tag (the anchor's identity for downstream consumption).
        upstream_node_name: name of the node inside the subnet whose cooked
            geometry is measured (default "out_geometry").

    Returns {success, anchors_built, project}. Idempotent: re-running replaces
    the anchor wrangles (named anchor_<name>) so changes to the spec take effect.
    """
    subnet = core_node.node(component_id)
    if subnet is None:
        return {"success": False,
                "error": f"component subnet not found: {component_id}"}
    upstream = subnet.node(upstream_node_name)
    if upstream is None:
        return {"success": False,
                "error": f"upstream node '{upstream_node_name}' not found in {component_id}"}

    built = []
    anchor_wrangles = []
    for spec in anchors:
        name = spec.get("name")
        if not name:
            return {"success": False, "error": f"anchor missing 'name': {spec}"}
        # Build the measurement VEX from the spec (minus our 'name' key).
        vex_spec = {k: v for k, v in spec.items() if k != "name"}
        try:
            snippet, parms = build_mount_vex(vex_spec)
        except VexStrategyError as e:
            return {"success": False,
                    "error": f"anchor {name!r}: {e}"}
        # Create/replace the anchor wrangle (named anchor_<name>).
        wr_name = f"anchor_{name}"
        existing = subnet.node(wr_name)
        if existing is not None:
            existing.destroy()
        wr = subnet.createNode("attribwrangle", wr_name)
        wr.parm("snippet").set(snippet + f'\nsetpointattrib(0, "name", __newpts[0], "{name}", "set");')
        wr.parm("class").set("detail")
        wr.setInput(0, upstream)
        # Install the measurement parms (cx/cy/cz etc.) as concrete values.
        # These are NOT default attribwrangle parms — they must be added as
        # spare parms (the VEX reads them via chi("cx") etc.).
        for pname, pval in parms.items():
            p = wr.parm(pname)
            if p is None:
                tmpl = hou.IntParmTemplate(pname, pname, 1)
                wr.addSpareParmTuple(tmpl)
                p = wr.parm(pname)
            if p is not None:
                p.set(int(pval))
        anchor_wrangles.append(wr)
        built.append(name)

    # Merge all anchor wrangles into out_anchors (the component's anchor port).
    out_anc = subnet.node(OUT_ANCHORS_NODE)
    if out_anc is not None:
        if len(anchor_wrangles) == 1:
            out_anc.setInput(0, anchor_wrangles[0])
        else:
            merge = subnet.node("anchor_merge")
            if merge is None:
                merge = subnet.createNode("merge", "anchor_merge")
            for i, wr in enumerate(anchor_wrangles):
                merge.setInput(i, wr)
            out_anc.setInput(0, merge)
    subnet.layoutChildren()

    # Log it.
    decl = load_declaration(core_node)
    append_log(decl, kind="anchors",
               summary=f"added {len(built)} anchor(s) to {component_id}",
               payload={"component": component_id, "anchors": built},
               result_ok=True)
    save_declaration(core_node, decl)
    return {"success": True, "anchors_built": built,
            "project": core_node.path()}
