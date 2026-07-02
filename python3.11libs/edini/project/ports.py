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


def validate_component_ports(ports: dict) -> None:
    """校验一个组件的 ports 结构。不合法则 raise ValueError。

    检查（spec §3.2 / §4.1）：
      - out[0] 必须是 kind=geometry
      - anchors 类型的 port，其 points[].name 必须存在且合法
      - in[] 的每个连接必须有 from 字段
    """
    out_ports = ports.get("out", [])
    in_ports = ports.get("in", [])

    # out[0] 必须是 geometry。
    if out_ports:
        first = out_ports[0]
        if first.get("index") != GEOMETRY_PORT_INDEX or \
           first.get("kind") != PORT_KIND_GEOMETRY:
            raise ValueError(
                "ports.out[0] must be {index:0, kind:'geometry'} (main geometry)")

    for op in out_ports:
        if op.get("kind") == PORT_KIND_ANCHORS:
            for pt in op.get("points", []):
                name = pt.get("name")
                if not name or not _ANCHOR_NAME_RE.match(name):
                    raise ValueError(
                        f"anchor point missing/illegal @name: {name!r}. "
                        f"Must match [A-Za-z][A-Za-z0-9_]*.")

    for ip in in_ports:
        if not ip.get("from"):
            raise ValueError(
                f"ports.in entry missing 'from' (source component id): {ip}")


if __name__ == "__main__":
    # Smoke: validate a known-good ports dict.
    _good = {"out": [
        {"index": 0, "kind": PORT_KIND_GEOMETRY, "description": "main"},
        {"index": 1, "kind": PORT_KIND_ANCHORS, "points": [
            {"name": "a", "role": "mount"}]}],
        "in": []}
    validate_component_ports(_good)
    print("ports.py smoke ok")
