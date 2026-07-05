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

    # Dry-run validation: collect ALL port errors before building anything,
    # so the agent gets every field wrong in one shot instead of one-at-a-time.
    all_errors: list[str] = []
    seen_ids: set[str] = set()
    for i, comp in enumerate(components):
        cid = comp.get("id", f"<missing id at [{i}]>")
        if not cid or cid in seen_ids:
            all_errors.append(f"duplicate or missing component id: {cid!r}")
        seen_ids.add(cid)
        errs = validate_component_ports(comp.get("ports", {}), component_id=cid)
        all_errors.extend(errs)
    if all_errors:
        return {
            "success": False,
            "error": f"Declaration validation failed — {len(all_errors)} error(s). "
                     f"Fix ALL of them before retrying:",
            "validation_errors": all_errors,
            "schema_hint": (
                "Each component needs: {id, purpose, ports:{out:[...], in:[...]}}. "
                "out[0] must be {index:0, kind:'geometry'}. "
                "Each ports.in entry needs: {from:<component_id>, port:<int>, anchor:<name>}. "
                "Example: {from:'tabletop', port:1, anchor:'leg_mount_fr'}"
            ),
        }

    built, skipped = [], []
    for comp in components:
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

    # Auto-create design params as spare parms on the core node.
    # design_params in the declaration define the project's adjustable knobs
    # (length, width, etc.). They MUST exist as real Houdini spare parms on the
    # core node so that component subnets can reference them via ch("../../../<name>")
    # or ch("/abs/path"). Without this, ch() references produce zero geometry.
    design_params = decl.get("design_params", [])
    params_created = _ensure_design_params(core_node, design_params)

    # 记日志（成功）。
    decl = load_declaration(core_node)
    append_log(decl, kind="scaffold",
               summary=f"built {len(built)} component scaffold(s), {params_created} design param(s)",
               payload={"built": built, "skipped": skipped,
                        "design_params": params_created},
               result_ok=True)
    save_declaration(core_node, decl)

    return {"success": True, "components_built": built,
            "components_skipped": skipped,
            "design_params_created": params_created,
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


from edini.project.state import (
    load_declaration, save_declaration, append_log,
)
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


def _ensure_design_params(core_node: "hou.Node", design_params: list[dict]) -> int:
    """Create design params as spare parms on the core node. Idempotent.

    design_params is the SINGLE SOURCE OF TRUTH for the project's adjustable
    knobs (length, width, height, etc.). Each entry:
        {"name","label","default","min","max","components":[ids that use it]}

    These MUST exist as real Houdini spare parms on the core node so component
    subnets can reference them via ch("/abs/path/to/core/<name>"). Without this,
    ch() references evaluate to 0 and the geometry collapses to a point.

    Creates a FloatParmTemplate per design param in a "Design Params" folder.
    Skips parms that already exist (idempotent). Returns count of params
    ensured (created or already-present).
    """
    if not design_params:
        return 0
    import hou
    count = 0
    for dp in design_params:
        name = dp.get("name")
        if not name:
            continue
        # Skip if parm already exists on core.
        if core_node.parm(name) is not None:
            count += 1
            continue
        # Create a float spare parm with default/min/max.
        default = dp.get("default", 0.0)
        try:
            default = float(default)
        except (TypeError, ValueError):
            default = 0.0
        tmpl = hou.FloatParmTemplate(
            name=name,
            label=dp.get("label", name),
            num_components=1,
            default=(default,),
        )
        mn = dp.get("min")
        mx = dp.get("max")
        if mn is not None:
            try:
                tmpl.setMin(float(mn))
            except (TypeError, ValueError):
                pass
        if mx is not None:
            try:
                tmpl.setMax(float(mx))
            except (TypeError, ValueError):
                pass
        try:
            core_node.addSpareParmTuple(
                tmpl, in_folder=("Design Params",),
                create_missing_folders=True)
            count += 1
        except Exception:
            pass
    return count


def promote_params(core_node: "hou.Node") -> dict:
    """把组件 subnet 的 spare parm 提到 core HDA（自底向上，按组件分组）。

    流程（用户拍板的方向，符合建模直觉）：
      1. agent 在 subnet 建模时自然建 spare parm（测试好，参数是建模的副产物）
      2. 本函数扫每个组件 subnet 的 spareParms()
      3. 在 core 按组件分组创建 parm（<component>_<parm>，放 "<component>" folder），
         带 min/max/default（从 subnet parm 的 template 读，解决问题2）
      4. 把 subnet parm 改成引用 core：subnet.parm 表达式 = ch("../<component>_<parm>")
         —— 这样用户改 core → subnet 跟变 → 几何/锚点 live

    core 是最终的调整入口（带 min/max），subnet 是引用（被 core 驱动）。
    幂等：已存在的 core parm 只更新表达式。
    """
    decl = load_declaration(core_node)
    promoted = []

    for comp in decl.get("components", []):
        cid = comp["id"]
        subnet = core_node.node(cid)
        if subnet is None:
            continue
        try:
            spare_parms = subnet.spareParms()
        except Exception:
            continue
        for sparmparm in spare_parms:
            pname = sparmparm.name()
            core_parm_name = f"{cid}_{pname}"
            _promote_one_parm(core_node, subnet, cid, pname, core_parm_name)
            promoted.append({"component": cid, "parm": core_parm_name})

    append_log(decl, kind="promote",
               summary=f"promoted {len(promoted)} parm(s)",
               payload={"promoted": promoted}, result_ok=True)
    save_declaration(core_node, decl)
    return {"success": True, "promoted": promoted,
            "project": core_node.path()}


def _promote_one_parm(core_node: "hou.Node", subnet: "hou.Node",
                      component_id: str, subnet_parm: str,
                      core_parm: str) -> None:
    """把一个 subnet spare parm 提到 core（按组件 folder 分组）+ subnet 改引用 core。

    - 读 subnet parm 的 template（含 default/min/max），在 core 建同名 parm。
    - core parm 放 "<component_id>" folder，命名 <component_id>_<subnet_parm>。
    - subnet parm 表达式改成 ch("../<core_parm>") —— subnet 被 core 驱动。
    幂等：core parm 已存在则只更新；subnet 表达式每次确保。
    """
    sub_p = subnet.parm(subnet_parm)
    if sub_p is None:
        return
    sub_tmpl = sub_p.parmTemplate()
    default_val = sub_p.eval()

    existing = core_node.parm(core_parm)
    if existing is None:
        # 在 core 建 parm，复制 subnet parm 的类型/default/min/max。
        # 复用 subnet 的 template 但改名 + 放 component folder。
        new_tmpl = sub_tmpl.clone()
        new_tmpl.setName(core_parm)
        new_tmpl.setLabel(f"{component_id} {subnet_parm}")
        core_node.addSpareParmTuple(new_tmpl, in_folder=(component_id,),
                                    create_missing_folders=True)
        cp = core_node.parm(core_parm)
        if cp is not None:
            cp.set(default_val)
    # subnet parm 改成引用 core（ch("../<core_parm>")）—— subnet 被 core 驱动。
    sub_p.setExpression(f'ch("../{core_parm}")')


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
        except (VexStrategyError, ValueError) as e:
            # Catch VexStrategyError (unknown measure) AND ValueError subclasses
            # (MeasureError for bad axes/face format) so the agent gets a
            # friendly "anchor 'xxx': ..." message instead of a raw traceback.
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
