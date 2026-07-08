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
    TAG_COMPONENT_NODE, AXIS_BAKE_NODE, INPUT_FILTER_PREFIX, ANCHOR_CLEAN_PREFIX,
    DEFAULT_COMPONENT_AXIS, resolve_axis_vector,
    validate_component_ports, validate_route_contract,
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
        try:
            validate_component_ports(comp.get("ports", {}))
        except ValueError as e:
            # Prefix with the component id so multi-component declarations
            # pinpoint which component failed.
            all_errors.append(f"component '{cid}': {e}")
        # Round-3 Fix D1: validate the optional per-component axis token here
        # (it's a component-level field, sibling of ports). Bad token → the
        # scaffold can't resolve it to a vector; surface it now, aggregated.
        if "axis" in comp and comp["axis"] is not None:
            try:
                resolve_axis_vector(comp["axis"])
            except ValueError as e:
                all_errors.append(f"component '{cid}': {e}")
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
        # Round-3 Fix D1: read the optional per-component axis (default Y). The
        # scaffold bakes it into __edini_axis_bake so verify_orientation sees
        # the correct construction axis without any agent node editing.
        axis = comp.get("axis", DEFAULT_COMPONENT_AXIS) or DEFAULT_COMPONENT_AXIS
        subnet = _ensure_component_subnet(core_node, cid)
        _ensure_scaffold_nodes(subnet, axis)
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

    # 第四遍：把 design_params 落成 core 的真实 spare parm（自顶向下参数源）。
    # 没有这步，子网里的 ch('../../width') 引用会归零——core 上根本没有 width。
    # design_params 声明定义了项目的可调旋钮（length/width 等），必须作为真实
    # Houdini spare parm 存在于 core 节点上，子网才能通过 ch("../../../<name>")
    # 或 ch("/abs/path") 引用。文档（state.py add_design_param docstring）一直
    # 声称 build_scaffold 会创建这些 parm，但此前从未实现，导致 live 参数链断裂。
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

    # Fix 2: static cross-component anchor-routing check. Cheap (no cook),
    # surfaces typo'd anchor names / missing upstreams BEFORE any geometry is
    # built. Soft — build still succeeds; warnings tell the agent which wires
    # won't carry the right points (the runtime Blast filter is the hard
    # enforcement; this is the early signal).
    route_warnings = validate_route_contract(decl)

    # Read back the ACTUAL cross-component wiring state and report it as
    # ground-truth. This is the cure for the "agent doesn't trust the
    # scaffold and wastes 10 minutes reconnecting a correct wire" failure
    # (session log 1, shelf incident). Empty list under mock_hou.
    input_wires = _collect_input_wires(core_node, decl)

    return {"success": True, "components_built": built,
            "components_skipped": skipped,
            "design_params_created": params_created,
            "route_warnings": route_warnings,
            "input_wires": input_wires,
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


def _ensure_scaffold_nodes(subnet: "hou.Node",
                           axis: str = DEFAULT_COMPONENT_AXIS) -> None:
    """确保 subnet 内有脚手架节点 + 连线。幂等。

    [agent geometry…] → out_geometry (null) → tag_component → __edini_axis_bake → output_0 (output)
      (agent connects here)   (component_id)    (edini_world_axis)        [subnet output 1 = 主几何]
                         out_anchors  (null) → output_1 (output)   [subnet output 2 = 锚点云]

    Round-2 Fix A: the orientation axis lives in a SEPARATE internal node
    (__edini_axis_bake) from the agent-editable tag_component. This closes the
    session-2 hole where the agent overwrote tag_component's snippet with
    's@component_id="seat";' and silently deleted the auto-baked axis. Now:
      - tag_component: AGENT-EDITABLE, holds ONLY component_id by default.
        An overwrite can never drop the axis (it's in the next node).
      - __edini_axis_bake: INTERNAL (__-prefixed), holds edini_world_axis.
        Re-forced on every rebuild; the guard refuses agent edits to it.

    The agent keeps connecting its last node into out_geometry (unchanged
    contract). Both bake nodes sit between out_geometry and output_0 so every
    downstream reader (core OUT, inventory, orientation) sees both attrs.

    已存在的节点跳过创建；连线每次确保（setInput 幂等）。
    """
    out_geo = _ensure_node(subnet, "null", OUT_GEOMETRY_NODE)
    tag = _ensure_tag_component(subnet)
    axis_node = _ensure_axis_bake(subnet, axis)
    out_anc = _ensure_node(subnet, "null", OUT_ANCHORS_NODE)
    output_0 = _ensure_node(subnet, "output", OUTPUT_0_NODE)
    output_1 = _ensure_node(subnet, "output", OUTPUT_1_NODE)

    # 连线：out_geometry → tag_component → __edini_axis_bake → output_0。
    tag.setInput(0, out_geo)
    axis_node.setInput(0, tag)
    output_0.setInput(0, axis_node)
    output_1.setInput(0, out_anc)

    # 整理布局（真机观感，不影响逻辑）。
    subnet.layoutChildren()


def _ensure_tag_component(subnet: "hou.Node") -> "hou.Node":
    """Ensure the agent-editable tag_component exists + has component_id baked.

    Holds ONLY component_id (prim-class, = subnet name). The orientation axis
    is deliberately NOT here — it lives in __edini_axis_bake so an agent
    overwriting this snippet can't drop it. Idempotent: re-applies component_id
    on every rebuild so subnet renames propagate. Pure component_id only — the
    agent is free to extend this snippet with per-component attribs.
    """
    tag = _ensure_node(subnet, "attribwrangle", TAG_COMPONENT_NODE)
    cid = subnet.name()
    snippet = (
        f'// AGENT-EDITABLE. Default bakes component_id (prim-class).\n'
        f'// The orientation axis is baked separately in __edini_axis_bake —\n'
        f'// do NOT add edini_world_axis here (it would be ignored downstream).\n'
        f's@component_id = "{cid}";\n'
    )
    try:
        tag.parm("snippet").set(snippet)
        tag.parm("class").set("primitive")
    except Exception:
        pass
    return tag


def _ensure_axis_bake(subnet: "hou.Node",
                      axis: str = DEFAULT_COMPONENT_AXIS) -> "hou.Node":
    """Ensure the INTERNAL __edini_axis_bake node exists + axis is baked.

    Round-3 Fix D1: the axis now comes from the component declaration (default
    Y), not a hardcoded {0,1,0}. Always re-forces the snippet on every call, so
    changing the declared axis + rebuilding updates the baked edini_world_axis
    deterministically — the agent never edits this node (and the guard refuses
    such edits). This is the structural enforcement: the axis survives
    tag_component overwrites because it's a different node the scaffold owns,
    AND it's correct per-component because it's read from the declaration.
    """
    axis_node = _ensure_node(subnet, "attribwrangle", AXIS_BAKE_NODE)
    # Resolve the declared axis token to a 3-float vector. Bad token would have
    # been caught by the scaffold's validation pass; fall back to Y defensively.
    try:
        vx, vy, vz = resolve_axis_vector(axis)
    except ValueError:
        vx, vy, vz = 0.0, 1.0, 0.0
    snippet = (
        f'// INTERNAL scaffold node. Do not edit — re-forced on every rebuild.\n'
        f'// Bakes the orientation axis (from the component declaration, default Y)\n'
        f'// that verify_orientation / the commit gate read as a prim attribute.\n'
        f'// To change it, set "axis" on the component and rebuild the scaffold.\n'
        f'v@edini_world_axis = {{{vx}, {vy}, {vz}}};\n'
    )
    try:
        axis_node.parm("snippet").set(snippet)
        axis_node.parm("class").set("primitive")
    except Exception:
        pass
    return axis_node


def _ensure_input_scaffold(core_node: "hou.Node", comp: dict,
                           subnet: "hou.Node") -> None:
    """为一个组件建/维护输入脚手架（外部连线 + 内部命名 null + @name 过滤）。幂等。

    对 comp 的 ports.in[] 的第 i 条 {from, port, anchor}：
      - 外部：downstream.setInput(i, upstream, from_port) — downstream 的第 i
        个输入连接器 ← upstream（in_entry["from"]）的第 from_port 个输出。
      - 内部：indirectInputs()[i] → filter_<from>_<anchor> (Blast) → in_<from>_<anchor> (null)。
        Blast keeps ONLY points whose @name == anchor — so a downstream
        copytopoints can never receive points meant for a sibling component
        (the chair-log "5 points into the leg port" silent cross-talk). The
        declared `anchor` field is now a REAL filter, not a naming hint.

    upstream 不存在则跳过该条（局部声明安全）。已存在的内部节点跳过创建，
    setInput 幂等——重跑只补缺失，不碰 LLM 接在 in_* 下游的连线。
    """
    in_ports = comp.get("ports", {}).get("in", [])
    if not in_ports:
        return
    indirect_inputs = subnet.indirectInputs()
    for i, in_entry in enumerate(in_ports):
        # validate_component_ports (called before this) guarantees these three
        # fields exist + are legal, but read defensively — a raw KeyError deep
        # in the build is a poor experience. Missing → skip this entry.
        from_id = in_entry.get("from")
        from_port = in_entry.get("port")
        anchor = in_entry.get("anchor")
        if from_id is None or from_port is None or anchor is None:
            continue
        upstream = core_node.node(from_id)
        if upstream is None:
            # upstream 组件未建（局部声明）——跳过，留以后补。
            continue
        # 外部：下游第 i 输入 ← 上游第 from_port 输出。
        subnet.setInput(i, upstream, from_port)
        indirect = indirect_inputs[i]

        # ── @name filter (Fix 2) ──
        # Blast: group=@name=<anchor>, grouptype=points, negate=1 (Delete
        # Non-Selected → keep ONLY the declared anchor's points). Verified on
        # real Houdini: the default grouptype ("guess") does NOT match a point
        # group, and default negate=0 DELETES the match — so BOTH must be set
        # explicitly or the filter does the opposite of what we want.
        # Idempotent: re-ensure by name; re-set the filter parms each run
        # (setInput/parm.set are idempotent). If the upstream anchor cloud has
        # no @name attribute yet (e.g. the LLM hasn't emitted anchors), the
        # Blast still cooks cleanly (matches nothing → 0 points) — far better
        # than silently passing through unrelated points.
        filter_name = f"{INPUT_FILTER_PREFIX}{from_id}_{anchor}"
        blast = _ensure_node(subnet, "blast", filter_name)
        try:
            # @name=<anchor> selects the anchor's points. grouptype MUST be
            # 'points' (anchor clouds are point groups); 'guess' mis-resolves.
            blast.parm("group").set(f"@name={anchor}")
            gp = blast.parm("grouptype")
            if gp is not None:
                gp.set("points")
            # negate=1 = "Delete Non-Selected" → keep only the matching points.
            neg = blast.parm("negate")
            if neg is not None:
                neg.set(1)
        except Exception:
            # If the Blast version's parms differ, the node still exists; the
            # @name group is the load-bearing part. Don't abort the scaffold.
            pass
        blast.setInput(0, indirect)

        # ── prim-strip purifier (Round-2 Fix B) ──
        # The Blast keeps the right POINTS but does NOT guarantee the port is
        # prim-free: if the upstream was mis-wired (e.g. seat geometry, not
        # just an anchor point cloud), degenerate prims flow through. Session 2
        # showed 72 zero-vertex prims reaching copytopoints' 2nd input, costing
        # the agent ~40 steps to patch. This detail-class wrangle strips ALL
        # prims so the in-port is a PURE point cloud regardless of upstream
        # wiring — enforcing the port contract, not just the @name condition.
        clean_name = f"{ANCHOR_CLEAN_PREFIX}{from_id}_{anchor}"
        clean = _ensure_node(subnet, "attribwrangle", clean_name)
        try:
            # Remove every prim (and its vertices), keep all points. Reverse
            # iteration is the safe idiom (indices shift on forward removal).
            clean.parm("snippet").set(
                "int n = nprimitives(0);\n"
                "for (int i = n - 1; i >= 0; i--) {\n"
                "    removeprim(0, i, 1);\n"
                "}\n"
            )
            clean.parm("class").set("detail")
        except Exception:
            pass
        clean.setInput(0, blast)

        # 内部：命名 null ← purifier (not raw blast). The agent's copytopoints
        # wires to this null and now sees ONLY the declared anchor's points,
        # guaranteed prim-free.
        in_name = f"in_{from_id}_{anchor}"
        in_node = _ensure_node(subnet, "null", in_name)
        in_node.setInput(0, clean)


def _ensure_node(parent: "hou.Node", node_type: str,
                 node_name: str) -> "hou.Node":
    """确保 parent 下有名为 node_name 的 node_type 节点。幂等。"""
    existing = parent.node(node_name)
    if existing is not None:
        return existing
    return parent.createNode(node_type, node_name=node_name)


def _has_input(node, idx: int = 0) -> bool:
    """True if ``node`` has a non-None input at ``idx`` — the disconnect check.

    Catches the case where a chain node still EXISTS but its input was dropped
    (e.g. the agent ran ``setInput(0, None)``).
    """
    try:
        return node.input(idx) is not None
    except Exception:
        return False


def _input_name_is(node, idx: int, expected) -> bool:
    """True if ``node``'s input ``idx`` is ``expected`` (compared by node name).

    Used to verify the internal filter→clean→in_null chain is wired in the
    right ORDER (clean ← blast, in_null ← clean). Name comparison is robust
    across hou.Node object identities (which can differ across queries) and
    avoids the SubnetIndirectInput identity-comparison pitfall.
    """
    try:
        actual = node.input(idx)
    except Exception:
        return False
    if actual is None:
        return False
    try:
        return actual.name() == expected.name()
    except Exception:
        return False


def _collect_input_wires(core_node: "hou.Node", decl: dict) -> list[dict]:
    """Read back the ACTUAL cross-component wiring state and report ground-truth.

    For each ports.in entry {from, port, anchor} declared on a downstream
    component, this reads the downstream subnet's real `inputConnections()`
    and reports:
      - whether an external wire exists at that input index,
      - which upstream output port it's wired from (vs the declared `port`),
      - whether the internal filter/clean/null three-piece chain exists.

    This is the cure for the "agent doesn't trust the scaffold and wastes 10
    minutes reconnecting a wire that was correct" failure (session log 1,
    shelf incident). The scaffold's `_ensure_input_scaffold` already calls
    `subnet.setInput(i, upstream, from_port)` correctly; this function merely
    reflects that fact back so the agent can SEE it without probing.

    Returns a list of wire descriptors (one per declared ports.in entry).
    Degrades gracefully under mock_hou (no inputConnections()) — returns an
    empty list rather than crashing, so mock-based tests are unaffected.
    """
    wires: list[dict] = []
    for comp in decl.get("components", []):
        cid = comp.get("id")
        subnet = core_node.node(cid) if cid else None
        if subnet is None:
            continue
        in_ports = comp.get("ports", {}).get("in", []) or []
        # Read the real connection list ONCE per subnet. inputConnections()
        # returns hou.NodeConnection objects with inputIndex()/outputNode()/
        # outputIndex(). Real Houdini only; mock_hou lacks it.
        try:
            connections = subnet.inputConnections()
        except Exception:
            # mock_hou or an exotic node — can't read ground-truth. Bail out
            # cleanly rather than fabricate a wrong answer.
            return []
        # Index connections by input_index for O(1) lookup.
        conn_by_index: dict[int, "hou.NodeConnection"] = {}
        for conn in connections:
            try:
                conn_by_index[int(conn.inputIndex())] = conn
            except Exception:
                continue
        for i, in_entry in enumerate(in_ports):
            from_id = in_entry.get("from")
            declared_port = in_entry.get("port")
            anchor = in_entry.get("anchor")
            wire = {
                "component": cid,
                "input_index": i,
                "from": from_id,
                "declared_port": declared_port,
                "anchor": anchor,
                # Defaults — refined below if the connection exists.
                "wired": False,
                "actual_output_index": None,
                "actual_upstream": None,
                "port_matches": None,
                "carries": None,
                "internal_chain_ready": False,
            }
            # The authoritative upstream node for input i. NOTE: do NOT use
            # conn.outputNode() — despite its name, on a subnet connection it
            # returns the DOWNSTREAM node (the subnet itself), not the source.
            # subnet.input(i) returns the actual upstream node directly.
            upstream_node = None
            try:
                upstream_node = subnet.input(i)
            except Exception:
                upstream_node = None
            conn = conn_by_index.get(i)
            if upstream_node is not None and conn is not None:
                wire["wired"] = True
                try:
                    wire["actual_upstream"] = upstream_node.path()
                except Exception:
                    pass
                try:
                    wire["actual_output_index"] = int(conn.outputIndex())
                except Exception:
                    pass
                # Does the real wire match the declaration? This is the single
                # most useful field for the agent: if True, don't touch it.
                if (wire["actual_output_index"] == declared_port
                        and from_id is not None):
                    # Confirm the upstream IS the declared component (by name),
                    # not a sibling that happened to land on the port.
                    if upstream_node.name() == from_id:
                        wire["port_matches"] = True
                        wire["carries"] = ("anchors" if declared_port >= 1
                                           else "geometry")
                # Internal three-piece chain: indirect→filter(blast)→clean→in_null.
                # Phase 1b: verify the nodes EXIST and are actually WIRED (not just
                # present). A disconnected chain (e.g. the agent ran
                # setInput(0,None), or a wire got dropped) now reports
                # internal_chain_ready=False — closes the audit's false-positive
                # gap (session-logs-analysis xfail → now genuinely verified).
                blast = subnet.node(f"{INPUT_FILTER_PREFIX}{from_id}_{anchor}")
                clean_n = subnet.node(f"{ANCHOR_CLEAN_PREFIX}{from_id}_{anchor}")
                in_null = subnet.node(f"in_{from_id}_{anchor}")
                wire["internal_chain_ready"] = (
                    blast is not None and clean_n is not None and in_null is not None
                    and _has_input(blast, 0)                       # blast ← indirect (not disconnected)
                    and _input_name_is(clean_n, 0, blast)         # clean ← blast
                    and _input_name_is(in_null, 0, clean_n))      # in_null ← clean
            wires.append(wire)
    return wires


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
    """把 design_params 落成 core 的真实 spare Float parm（自顶向下参数源）。幂等。

    design_params 是项目可调旋钮（length/width/height 等）的单一真相源。每个条目：
        {"name","label","default","min","max","components":[使用它的组件 id]}
    这些 MUST 作为真实 Houdini spare parm 存在于 core 节点上，子网才能通过
    ch("/abs/path/to/core/<name>") 引用。没有这步，ch() 求值为 0，几何塌成点。

    在 "Design Params" folder 下为每个 design param 创建 FloatParmTemplate。
    已存在的 parm 跳过（幂等，不覆盖 agent/用户已调过的值）。返回已确保的 parm
    计数（新建 + 已存在）。单个 parm 创建失败不中断整体（某些节点类型/build 不
    支持 spare parm）。
    """
    if not design_params:
        return 0
    count = 0
    for dp in design_params:
        if not isinstance(dp, dict):
            continue
        name = dp.get("name")
        if not name:
            continue
        # 幂等：已存在则不动（保留 agent/用户可能已调过的值）。
        if core_node.parm(name) is not None:
            count += 1
            continue
        # Create a float spare parm with default/min/max.
        label = dp.get("label", name)
        default = dp.get("default", 0.0)
        try:
            default = float(default)
        except (TypeError, ValueError):
            default = 0.0
        mn = dp.get("min")
        mx = dp.get("max")
        try:
            tmpl = hou.FloatParmTemplate(name, label, 1, (default,))
            if mn is not None:
                tmpl.setMinValue(float(mn))
            if mx is not None:
                tmpl.setMaxValue(float(mx))
            core_node.addSpareParmTuple(
                tmpl, in_folder=("Design Params",),
                create_missing_folders=True)
            count += 1
        except Exception:
            # Fallback: older FloatParmTemplate signature without default tuple,
            # then set the value explicitly after install.
            try:
                tmpl = hou.FloatParmTemplate(name, label, 1)
                core_node.addSpareParmTuple(
                    tmpl, in_folder=("Design Params",),
                    create_missing_folders=True)
                p = core_node.parm(name)
                if p is not None:
                    p.set(default)
                count += 1
            except Exception:
                # Spare-parm creation can fail on some node types / builds;
                # don't let one bad parm abort the whole scaffold build.
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
    # Pre-flight check: confirm the upstream node exists so we fail early with a
    # clear message. (Do NOT hold this handle across the loop — see below.)
    if subnet.node(upstream_node_name) is None:
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
        # Re-resolve the upstream handle AFTER the (optional) destroy above.
        # Holding a hou.Node handle across a destroy() in the same subnet risks
        # Houdini's "Attempt to access an object that no longer exists" — the
        # subnet's child table may be invalidated by the destroy. A fresh
        # subnet.node(...) lookup per iteration is safe.
        upstream = subnet.node(upstream_node_name)
        if upstream is None:
            return {"success": False,
                    "error": f"upstream node '{upstream_node_name}' vanished "
                             f"during anchor rebuild in {component_id}"}
        wr = subnet.createNode("attribwrangle", wr_name)
        wr.parm("snippet").set(snippet + f'\nsetpointattrib(0, "name", __newpts[0], "{name}", "set");')
        wr.parm("class").set("detail")
        wr.setInput(0, upstream)
        # Install the measurement parms (cx/cy/cz etc.) as concrete values.
        # These are NOT default attribwrangle parms — they must be added as
        # spare parms (the VEX reads them via chi("cx") etc.).
        #
        # Type-aware: a STRING value (e.g. by_name's marker) gets a
        # StringParmTemplate and is set as a string; everything else is an int
        # (the historical case — cx/cy/cz/rows/cols/face_axis). A leading "_"
        # in the key is stripped (matches the array strategy's _origin/_step0
        # convention used by the legacy rooted pipeline).
        for raw_pname, pval in parms.items():
            pname = raw_pname.lstrip("_")
            is_string = isinstance(pval, str)
            p = wr.parm(pname)
            if p is None:
                if is_string:
                    tmpl = hou.StringParmTemplate(pname, pname, 1)
                else:
                    tmpl = hou.IntParmTemplate(pname, pname, 1)
                wr.addSpareParmTuple(tmpl)
                p = wr.parm(pname)
            if p is not None:
                p.set(pval if is_string else int(pval))
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
