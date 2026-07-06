"""Port protocol for component subnets.

Defines the physical contract of a component's subnet outputs:
  out[0]  (output_0 node) ← out_geometry null  → main geometry
  out[1+] (output_1 node) ← out_anchors null   → anchor point cloud
                                        (points carry @P/@orient/@name/@custom)

Constants are the single source of truth shared by the builder (creates
these nodes), drift (checks they exist), and the schema (validates the
declaration). Pure logic — no hou import — so fully unit-testable.

See spec §3.2 / §3.3.
"""
from __future__ import annotations

import re

# --- Port indices / kinds ------------------------------------------------
PORT_KIND_GEOMETRY = "geometry"
PORT_KIND_ANCHORS = "anchors"
GEOMETRY_PORT_INDEX = 0          # out[0] is always main geometry
FIRST_ANCHOR_PORT_INDEX = 1      # out[1..n] are anchor clouds

# --- Scaffold node names (inside each component subnet) ------------------
# These are the deterministic nodes the builder creates per component. Names
# are fixed so drift can find them deterministically, and so promote/drift
# share one vocabulary with the schema.
OUT_GEOMETRY_NODE = "out_geometry"   # null — main geometry汇入点
OUT_ANCHORS_NODE = "out_anchors"     # null — anchor cloud汇入点
OUTPUT_0_NODE = "output_0"           # output node → forms subnet output 1
OUTPUT_1_NODE = "output_1"           # output node → forms subnet output 2
# tag_component: prim-class attribwrangle the scaffold auto-emits between
# out_geometry and __edini_axis_bake. Bakes ONLY component_id (= subnet name).
# This node is AGENT-EDITABLE — the agent may overwrite its snippet (e.g. to
# add per-component attribs). Because it only ever sets component_id by
# default, an overwrite can never silently drop the orientation axis (which
# lives in the separate __edini_axis_bake node). See Round-2 Fix A.
TAG_COMPONENT_NODE = "tag_component"
# __edini_axis_bake: INTERNAL prim-class attribwrangle that bakes
# edini_world_axis (the orientation contract verify_orientation/G3a reads).
# The "__" prefix marks it internal (like __edini_state) — the agent must not
# edit it, and the scaffold re-forces its snippet on every rebuild so even a
# manual edit is restored. Splitting the axis out of tag_component (Round-2
# Fix A) closes the "agent overwrites tag_component's snippet and silently
# deletes the axis" hole seen in session 2.
AXIS_BAKE_NODE = "__edini_axis_bake"
# filter_<from>_<anchor>: Blast node the scaffold inserts between an in-port's
# indirectInput and the named in_<from>_<anchor> null. Keeps ONLY points whose
# @name matches the declared anchor, so a downstream copytopoints can never
# receive points meant for a sibling component (the chair-log "5 points into
# the leg port" silent cross-talk bug). Enforces the declared `anchor` field
# as a real filter, not just a naming hint.
INPUT_FILTER_PREFIX = "filter_"
# __edini_anchor_clean_<from>_<anchor>: INTERNAL detail-class attribwrangle
# after the Blast that strips ALL prims, guaranteeing the in-port is a pure
# point cloud regardless of upstream wiring errors (Round-2 Fix B — the log
# showed 72 degenerate prims leaking through when the agent mis-wired seat
# geometry into the anchor port).
ANCHOR_CLEAN_PREFIX = "__edini_anchor_clean_"


def is_internal_scaffold_node(name: str) -> bool:
    """True if `name` is an internal scaffold node the agent must not edit.

    Internal nodes are ``__``-prefixed (matching the existing ``__edini_state``
    parm convention). They bake platform contracts (orientation axis, anchor
    purification) that the agent should never need to touch — and the scaffold
    re-forces them on every rebuild. The set_param guard refuses snippet edits
    on these nodes so the agent can't silently corrupt a contract (Round-2
    Fix A defense-in-depth). Pure logic — no hou.
    """
    return isinstance(name, str) and name.startswith("__")

# --- Validation -----------------------------------------------------------
# Anchor @name must be a legal point-group name (letters/digits/underscore).
_ANCHOR_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# --- Per-component orientation axis (Round-3 Fix D1) ----------------------
# A component may declare its construction `axis` (X/Y/Z/-X/-Y/-Z). The scaffold
# bakes it into __edini_axis_bake as edini_world_axis; verify_orientation reads
# that prim attr as ground truth. Default Y is correct for most components
# (seat, tabletop, legs, wheels-on-ground). Side-facing panels (a backrest, a
# side board) declare e.g. "Z". Sharing the vocabulary with verify_orientation's
# expected_axis keeps the two consistent.
DEFAULT_COMPONENT_AXIS = "Y"
# Maps an axis token to its 3-float vector. Reused by builder._ensure_axis_bake
# and (defensively) anywhere that needs to resolve a declared axis to a vector.
# Pure logic — no hou — so fully unit-testable.
AXIS_VECTORS: dict[str, tuple[float, float, float]] = {
    "X": (1.0, 0.0, 0.0),
    "Y": (0.0, 1.0, 0.0),
    "Z": (0.0, 0.0, 1.0),
    "-X": (-1.0, 0.0, 0.0),
    "-Y": (0.0, -1.0, 0.0),
    "-Z": (0.0, 0.0, -1.0),
}


def resolve_axis_vector(axis: str) -> tuple[float, float, float]:
    """Resolve an axis token ("X"/"Y"/"Z"/"-X"/"-Y"/"-Z") to a 3-float vector.

    Raises ValueError on an unrecognized token (so callers surface a clear
    error rather than baking a wrong axis silently). Pure logic.
    """
    vec = AXIS_VECTORS.get(axis)
    if vec is None:
        raise ValueError(
            f"bad axis {axis!r}: must be one of {sorted(AXIS_VECTORS)}.")
    return vec


def expected_ports_schema() -> dict:
    """A filled-in example of the ports dict a component declares.

    Returned so error messages and tool prompts can show the FULL expected
    shape at once (instead of forcing the caller to learn it one error at a
    time). This is the authoritative contract; keep it in sync with
    validate_component_ports below.
    """
    return {
        "out": [
            # out[0] is ALWAYS the main-geometry port: {index:0, kind:"geometry"}.
            {"index": 0, "kind": "geometry", "description": "main geometry"},
            # out[1+] are anchor clouds (points carry @name/@P/@orient).
            {"index": 1, "kind": "anchors", "description": "mount points", "points": [
                {"name": "leg_mount", "role": "mount"},  # name: ^[A-Za-z][A-Za-z0-9_]*$
            ]},
        ],
        "in": [
            # Each in-port consumes an upstream component's output port.
            #   from   : source component id (required)
            #   port   : source component's OUTPUT index (required, int >= 0;
            #            1 = the anchor cloud from the example above)
            #   anchor : the consumed anchor's @name (required; unique per
            #            component; names the internal node in_<from>_<anchor>)
            {"from": "tabletop", "port": 1, "anchor": "leg_mount"},
        ],
        # axis (OPTIONAL, Round-3 Fix D1): the component's construction
        # orientation. Default "Y". The scaffold bakes it as edini_world_axis;
        # verify_orientation reads it as ground truth. Declare "Z" for a
        # side-facing panel (backrest), "X" for a transverse part, etc.
        "axis": DEFAULT_COMPONENT_AXIS,
    }


def validate_component_ports(ports: dict) -> None:
    """校验一个组件的 ports 结构。不合法则 raise ValueError。

    Collects ALL violations (not first-wins) and raises a single aggregated
    error whose message includes the full expected schema — so the caller sees
    the entire contract at once instead of discovering it one field at a time.

    检查（spec §3.2 / §4.1）：
      - out[0] 必须是 {index:0, kind:"geometry"}
      - anchors 类型的 port，其 points[].name 必须存在且合法
      - in[] 的每个连接必须有 from / port / anchor，且 anchor 合法且唯一
    """
    if not isinstance(ports, dict):
        raise ValueError(
            f"ports must be a dict, got {type(ports).__name__}. "
            f"Expected shape: {expected_ports_schema()}")

    out_ports = ports.get("out", [])
    in_ports = ports.get("in", [])
    errors: list[str] = []

    # out[0] must be geometry.
    if out_ports:
        first = out_ports[0]
        if not isinstance(first, dict) or \
           first.get("index") != GEOMETRY_PORT_INDEX or \
           first.get("kind") != PORT_KIND_GEOMETRY:
            errors.append(
                "ports.out[0] must be {index:0, kind:'geometry'} (main geometry)")

    for op in out_ports:
        if isinstance(op, dict) and op.get("kind") == PORT_KIND_ANCHORS:
            for pt in op.get("points", []):
                name = pt.get("name") if isinstance(pt, dict) else None
                if not name or not _ANCHOR_NAME_RE.match(name):
                    errors.append(
                        f"anchor point missing/illegal @name: {name!r}. "
                        f"Must match [A-Za-z][A-Za-z0-9_]*.")

    seen_in_anchors: set[str] = set()
    for ip in in_ports:
        if not isinstance(ip, dict):
            errors.append(f"ports.in entry must be a dict, got {ip!r}")
            continue
        if not ip.get("from"):
            errors.append(
                f"ports.in entry missing 'from' (source component id): {ip}")
        # port: required, must be an int >= 0 (the upstream output index).
        port = ip.get("port")
        if port is None:
            errors.append(
                f"ports.in entry missing 'port' (upstream output index, int>=0): {ip}")
        elif not isinstance(port, int) or isinstance(port, bool) or port < 0:
            errors.append(
                f"ports.in entry illegal 'port': {port!r} (must be int >= 0): {ip}")
        # anchor 必填 + 合法名（= 内部命名节点 in_<from>_<anchor> 的键）。
        anchor = ip.get("anchor")
        if not anchor or not _ANCHOR_NAME_RE.match(anchor):
            errors.append(
                f"ports.in entry missing/illegal 'anchor': {anchor!r}. "
                f"Must match [A-Za-z][A-Za-z0-9_]* — it names the internal "
                f"input node in_<from>_<anchor>.")
        # 同组件内 anchor 撞名 → 节点名冲突（幂等重建会撞 duplicate node name）。
        elif anchor in seen_in_anchors:
            errors.append(
                f"duplicate ports.in[].anchor within one component: {anchor!r}. "
                f"In-port anchors must be unique (they form node names).")
        else:
            seen_in_anchors.add(anchor)

    if errors:
        raise ValueError(
            "Invalid component ports:\n  - " + "\n  - ".join(errors) +
            f"\n\nExpected ports shape:\n{expected_ports_schema()}")


def validate_route_contract(declaration: dict) -> list[dict]:
    """Static cross-component anchor-routing check (pure logic, no hou).

    For every component's ``ports.in[]`` entry ``{from, port, anchor}``:
      - the upstream component ``from`` must exist in the declaration;
      - the ``anchor`` name must be declared in that upstream's
        ``out[].points[].name`` for some anchor-kind (index>=1) output port.

    Returns a list of ``route_warnings`` (empty = contract clean). Each warning
    is ``{component, from, anchor, port, reason}``. This is a *soft* check — it
    surfaces typos/mismatched names at scaffold time (before any geometry is
    built) rather than letting them manifest as silent cross-talk at
    copytopoints. The runtime Blast filter (builder._ensure_input_scaffold) is
    the *hard* enforcement; this static check is the early, cheap signal.

    A missing upstream or undeclared anchor name is not fatal: the build
    proceeds (the declaration may be locally partial / built incrementally),
    but the warning tells the agent exactly which wire won't carry the right
    points.
    """
    warnings: list[dict] = []
    components = declaration.get("components", []) if isinstance(declaration, dict) else []
    # Map component id -> set of declared anchor @names across all its
    # anchor-kind (index>=1) output ports.
    declared_anchors: dict[str, set[str]] = {}
    component_ids: set[str] = set()
    for comp in components:
        if not isinstance(comp, dict):
            continue
        cid = comp.get("id")
        if not cid:
            continue
        component_ids.add(cid)
        names: set[str] = set()
        for op in comp.get("ports", {}).get("out", []):
            if isinstance(op, dict) and op.get("kind") == PORT_KIND_ANCHORS:
                for pt in op.get("points", []):
                    nm = pt.get("name") if isinstance(pt, dict) else None
                    if nm:
                        names.add(nm)
        declared_anchors[cid] = names

    for comp in components:
        if not isinstance(comp, dict):
            continue
        cid = comp.get("id", "<unknown>")
        for ip in comp.get("ports", {}).get("in", []):
            if not isinstance(ip, dict):
                continue
            frm = ip.get("from")
            port = ip.get("port")
            anchor = ip.get("anchor")
            if not frm or not anchor:
                continue  # validate_component_ports already flags these
            if frm not in component_ids:
                warnings.append({
                    "component": cid, "from": frm, "anchor": anchor,
                    "port": port,
                    "reason": f"upstream component '{frm}' is not declared — "
                              f"this in-port will receive nothing until it is.",
                })
                continue
            upstream_names = declared_anchors.get(frm, set())
            if upstream_names and anchor not in upstream_names:
                warnings.append({
                    "component": cid, "from": frm, "anchor": anchor,
                    "port": port,
                    "reason": f"anchor '{anchor}' is not emitted by '{frm}' "
                              f"(declared: {sorted(upstream_names)}). The "
                              f"runtime filter will drop ALL points on this "
                              f"wire — fix the name or add the anchor.",
                })
    return warnings


if __name__ == "__main__":
    # Smoke: validate a known-good ports dict.
    _good = {"out": [
        {"index": 0, "kind": PORT_KIND_GEOMETRY, "description": "main"},
        {"index": 1, "kind": PORT_KIND_ANCHORS, "points": [
            {"name": "a", "role": "mount"}]}],
        "in": []}
    validate_component_ports(_good)  # raises on invalid; no-op on valid
    print("ports.py smoke ok")
