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
# These are the 4 nodes the builder creates per component. Names are fixed
# so drift can find them deterministically, and so promote/drift share one
# vocabulary with the schema.
OUT_GEOMETRY_NODE = "out_geometry"   # null — main geometry汇入点
OUT_ANCHORS_NODE = "out_anchors"     # null — anchor cloud汇入点
OUTPUT_0_NODE = "output_0"           # output node → forms subnet output 1
OUTPUT_1_NODE = "output_1"           # output node → forms subnet output 2

# --- Validation -----------------------------------------------------------
# Anchor @name must be a legal point-group name (letters/digits/underscore).
_ANCHOR_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


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

    # out[0] 必须是 geometry。
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


if __name__ == "__main__":
    # Smoke: validate a known-good ports dict.
    _good = {"out": [
        {"index": 0, "kind": PORT_KIND_GEOMETRY, "description": "main"},
        {"index": 1, "kind": PORT_KIND_ANCHORS, "points": [
            {"name": "a", "role": "mount"}]}],
        "in": []}
    validate_component_ports(_good)
    print("ports.py smoke ok")
