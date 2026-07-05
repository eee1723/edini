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


def validate_component_ports(ports: dict, component_id: str = "") -> list[str]:
    """Validate a component's ports structure. Returns a list of error strings.

    Collects ALL errors (does not raise on first) so the agent can fix every
    field in one retry instead of discovering them one at a time.

    Checks (spec §3.2 / §4.1):
      - out[0] must be {index:0, kind:'geometry'}
      - anchors ports: points[].name must exist and be legal
      - in[] entries: must have 'from', 'anchor', 'port' fields
    """
    errors: list[str] = []
    prefix = f"component '{component_id}': " if component_id else ""
    out_ports = ports.get("out", [])
    in_ports = ports.get("in", [])

    # out[0] must be geometry.
    if out_ports:
        first = out_ports[0]
        if first.get("index") != GEOMETRY_PORT_INDEX or \
           first.get("kind") != PORT_KIND_GEOMETRY:
            errors.append(
                f"{prefix}ports.out[0] must be {{index:0, kind:'geometry'}} "
                f"(main geometry), got: {first}")

    for op in out_ports:
        if op.get("kind") == PORT_KIND_ANCHORS:
            for pt in op.get("points", []):
                name = pt.get("name")
                if not name or not _ANCHOR_NAME_RE.match(name):
                    errors.append(
                        f"{prefix}anchor point missing/illegal @name: {name!r}. "
                        f"Must match [A-Za-z][A-Za-z0-9_]*.")

    seen_in_anchors: set[str] = set()
    for ip in in_ports:
        if not ip.get("from"):
            errors.append(
                f"{prefix}ports.in entry missing 'from' (source component id): {ip}")
        anchor = ip.get("anchor")
        if not anchor or not _ANCHOR_NAME_RE.match(anchor):
            errors.append(
                f"{prefix}ports.in entry missing/illegal 'anchor': {anchor!r}. "
                f"Must match [A-Za-z][A-Za-z0-9_]* — it names the internal "
                f"input node in_<from>_<anchor>.")
        if "port" not in ip:
            errors.append(
                f"{prefix}ports.in entry missing 'port' (source output port index, "
                f"usually 1 for anchors): {ip}")
        if anchor:
            if anchor in seen_in_anchors:
                errors.append(
                    f"{prefix}duplicate ports.in[].anchor within one component: "
                    f"{anchor!r}. In-port anchors must be unique.")
            seen_in_anchors.add(anchor)

    return errors


if __name__ == "__main__":
    # Smoke: validate a known-good ports dict.
    _good = {"out": [
        {"index": 0, "kind": PORT_KIND_GEOMETRY, "description": "main"},
        {"index": 1, "kind": PORT_KIND_ANCHORS, "points": [
            {"name": "a", "role": "mount"}]}],
        "in": []}
    errors = validate_component_ports(_good)
    assert not errors, f"expected no errors, got: {errors}"
    print("ports.py smoke ok")
