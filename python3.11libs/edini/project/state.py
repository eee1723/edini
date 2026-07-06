"""Project declaration state: schema + JSON <-> hidden-parm bridge.

Pure Python (no `hou` import) so it is unit-testable with a fake node.
The declaration JSON is the knowledge graph (see spec §5). It is persisted
in a hidden string parm `STATE_PARM` on the Project HDA node.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

# Name of the hidden string parm on the Project HDA that holds the JSON.
STATE_PARM = "__edini_state"
SCHEMA_VERSION = 1


def empty_declaration(project_name: str, goal: str | None = None) -> dict:
    """Return a fresh empty declaration (the "empty project" state)."""
    return {
        "version": SCHEMA_VERSION,
        "project": {
            "name": project_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "goal": goal,
        },
        "plan": [],
        "design_params": [],
        "components": [],
        "log": [],
        "drift": [],
    }


def ensure_state_parm(node) -> None:
    """Ensure the node has the __edini_state hidden parm. Auto-install if missing.

    Old or manually-installed Project HDAs may lack this parm. Without it,
    save_declaration crashes with a confusing RuntimeError much later in the
    pipeline. This function is called by load_declaration (and project_create's
    reuse path) to self-heal at the earliest opportunity.
    """
    if node.parm(STATE_PARM) is None:
        try:
            from edini.project.node import build_state_parm_template
            node.addSpareParmTuple(build_state_parm_template())
        except Exception:
            pass  # Best-effort; save_declaration will give a clear error if still missing


def load_declaration(node) -> dict:
    """Read the declaration JSON from the node's hidden parm.

    Returns a safe empty skeleton if the parm is absent, empty, or corrupt.
    Never raises. Auto-installs the parm if missing (self-heal) so that a
    subsequent save_declaration won't crash.
    """
    parm = node.parm(STATE_PARM)
    if parm is None:
        ensure_state_parm(node)
        parm = node.parm(STATE_PARM)
    raw = parm.eval() if parm is not None else ""
    if not raw:
        return empty_declaration(None)
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or "version" not in data:
            return empty_declaration(None)
        return data
    except (json.JSONDecodeError, TypeError):
        return empty_declaration(None)


def save_declaration(node, declaration: dict) -> None:
    """Write the declaration JSON to the node's hidden parm.

    Precondition: the STATE_PARM must already be installed on the node
    (see edini.project.node.build_state_parm_template + create_project_hda,
    which installs it). Raises RuntimeError if the parm is absent.
    """
    parm = node.parm(STATE_PARM)
    if parm is None:
        raise RuntimeError(
            f"Cannot save declaration: node has no '{STATE_PARM}' parm. "
            f"Install it via build_state_parm_template first."
        )
    parm.set(json.dumps(declaration))


_STEP_STATUSES = ("pending", "in_progress", "done", "skipped")


def add_plan_step(declaration: dict, step_id: str, title: str,
                  parent: str | None = None, detail: str = "",
                  status: str = "pending") -> dict:
    """Append a plan step to the declaration. Returns the new step.

    Raises ValueError if step_id already exists.
    """
    if any(s["id"] == step_id for s in declaration["plan"]):
        raise ValueError(f"plan step id already exists: {step_id}")
    step = {"id": step_id, "title": title, "parent": parent,
            "status": status, "detail": detail}
    declaration["plan"].append(step)
    return step


def set_step_status(declaration: dict, step_id: str, status: str) -> None:
    """Set a plan step's status. Raises KeyError if step_id unknown,
    ValueError if status not in _STEP_STATUSES."""
    if status not in _STEP_STATUSES:
        raise ValueError(f"bad status: {status}")
    for step in declaration["plan"]:
        if step["id"] == step_id:
            step["status"] = status
            return
    raise KeyError(f"unknown plan step id: {step_id}")


def append_log(declaration: dict, kind: str, summary: str,
               payload: dict | None = None, result_ok: bool = True) -> dict:
    """Append an audit/experience entry to the declaration log."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "summary": summary,
        "payload": payload or {},
        "result_ok": result_ok,
    }
    declaration["log"].append(entry)
    return entry


import re as _re

# 组件 id = subnet 名，必须是合法 Houdini 节点名（字母/数字/下划线）。
# 这也是 drift 检测的承重键（subnet 名 ↔ 组件 id 一一对应）。
_COMPONENT_ID_RE = _re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def add_component(declaration: dict, component_id: str, purpose: str = "",
                  params: list | None = None,
                  ports_out: list | None = None,
                  ports_in: list | None = None) -> dict:
    """向声明追加一个组件。返回新组件 dict。

    组件 id 必须合法（= subnet 名规则）。ports_out/ports_in/params 为 None
    时置空列表。详见 spec §4.1。
    """
    if not _COMPONENT_ID_RE.match(component_id or ""):
        raise ValueError(
            f"bad component id: {component_id!r}. Must match "
            f"[A-Za-z][A-Za-z0-9_]* (it becomes the subnet name).")
    if any(c["id"] == component_id for c in declaration["components"]):
        raise ValueError(f"component id already exists: {component_id}")
    component = {
        "id": component_id,
        "subnet_path": f"./{component_id}",
        "purpose": purpose,
        "params": list(params or []),
        "ports": {
            "out": list(ports_out or []),
            "in": list(ports_in or []),
        },
    }
    declaration["components"].append(component)
    return component


def get_component(declaration: dict, component_id: str) -> dict | None:
    """按 id 查找组件，找不到返回 None。"""
    for c in declaration["components"]:
        if c["id"] == component_id:
            return c
    return None


# --- Design params (core-as-source parameter definitions) ------------------
#
# design_params is the SINGLE SOURCE OF TRUTH for the project's adjustable
# parameters. Each entry defines a parm that lives on the core HDA top level
# (with default/min/max), and component subnets REFERENCE it via
# ch("../<name>"). This is the opposite of the old promote direction (which
# scanned subnet spare parms and made core follow). Here core owns the value;
# subnets are dependents.
#
# Shape: {"name","label","default","min","max","components":[ids that use it]}

_PARAM_NAME_RE = _re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def add_design_param(declaration: dict, name: str, default: float,
                     min: float | None = None, max: float | None = None,
                     label: str | None = None,
                     components: list[str] | None = None) -> dict:
    """Define an adjustable parameter at the core HDA level (source of truth).

    The parm is created on the core during build_scaffold (with default/min/max),
    and component subnets reference it via ch("../<name>") after promote. This
    makes the core the single source — change it and every dependent component
    (and any procedurally-computed anchors) update live.

    Args:
        name: parm name (must be a legal parm name; becomes the core parm).
        default: default value.
        min/max: optional range (for the core parm's UI slider).
        label: optional human label.
        components: optional list of component ids that use this parm (for
            promote to know which subnets to wire). If None, all components.
    """
    if not _PARAM_NAME_RE.match(name or ""):
        raise ValueError(f"bad param name: {name!r}")
    if any(p["name"] == name for p in declaration["design_params"]):
        raise ValueError(f"design param already exists: {name}")
    param = {
        "name": name,
        "label": label or name,
        "default": float(default),
        "min": float(min) if min is not None else None,
        "max": float(max) if max is not None else None,
        "components": list(components) if components is not None else None,
    }
    declaration["design_params"].append(param)
    return param


def get_design_params_for_component(declaration: dict,
                                    component_id: str) -> list[dict]:
    """Return the design params that apply to a given component.

    A param applies if its `components` is None (all components) or lists this
    component id. Used by promote to know which subnet parms to wire.
    """
    result = []
    for p in declaration["design_params"]:
        comps = p.get("components")
        if comps is None or component_id in comps:
            result.append(p)
    return result

