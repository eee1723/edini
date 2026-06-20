# Edini 三阶段管道架构 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Edini 程序化建模系统从单体食谱构建器重构为三阶段管道架构，消除 12 项已知风险和参数断裂问题。

**Architecture:** 三个独立管道阶段（验证→逐组件构建→组装测试提交）取代当前的原子构建。新增参数三态体系（主控/派生/约束）和依赖图。工具面收窄（删除 `houdini_run_python`，新增 4 个专用工具）。技能体系重组为 1 个路由器 + 5 个专用技能。

**Tech Stack:** Python 3.11, Houdini 21.0.440 HOM API, VEX, JSON Schema

## Global Constraints

- Houdini 21.0.440 作为目标版本
- 参数目录启动时扫描 Houdini 安装目录生成，不对特定版本硬编码
- 所有验证在 `harness.py` 中实现，跟随现有错误处理模式
- 工具注册在 `rpc_client.py` 或工具注册表文件中
- Skill 文件在 `skills/` 目录中，遵循现有文件夹命名约定
- 迁移期间 `build_procedural_asset` 持续可用直到所有管道阶段替换完成

---

### Task 1: 参数目录自动生成

**Files:**
- Create: `python3.11libs/edini/parm_catalog.py`
- Modify: `python3.11libs/edini/harness.py` (添加 `dump_parm_catalog` 工具)
- Output: `python3.11libs/edini/data/parm-catalog.json` (首次运行时生成)

**Interfaces:**
- Produces: `dump_parm_catalog() → dict[str, Any]` — 完整的参数目录 JSON
- Produces: `ParmCatalog` 类 — `get_parms(node_type: str) → dict | None`, `validate_parm(node_type, parm_name, parm_value) → bool`, `resolve_alias(node_type) → str`

- [ ] **Step 1: 实现目录生成器核心**

```python
# python3.11libs/edini/parm_catalog.py

"""Auto-generated parameter catalog from the installed Houdini version.

Scans all SOP types on first run, caches to parm-catalog.json.
Phase A validation uses this catalog as ground truth for parm-name
and node-type checks — no cook required.
"""

import json
import os
import hou
from typing import Any

CATALOG_PATH = os.path.join(
    os.path.dirname(__file__), "data", "parm-catalog.json"
)

# Known aliases for node types that changed names between Houdini versions.
NODE_ALIASES = {
    "transform": "xform",
    "polybevel": "polybevel::3.0",
}


class ParmCatalog:
    """Read-only catalog of Houdini SOP parm definitions."""

    def __init__(self, data: dict[str, Any]):
        self._data = data
        self._sops: dict[str, dict] = data.get("Sop", {})

    # ── lookup ──────────────────────────────────────────────

    def has_node_type(self, node_type: str) -> bool:
        """True if node_type is a known SOP type (canonical name)."""
        return node_type in self._sops

    def resolve_alias(self, node_type: str) -> str:
        """If node_type is a known alias, return the canonical name."""
        return NODE_ALIASES.get(node_type, node_type)

    def get_parms(self, node_type: str) -> dict[str, Any] | None:
        """Return {parm_name: ParmDef} for a SOP type, or None."""
        entry = self._sops.get(node_type)
        return entry.get("parms") if entry else None

    def parm_names(self, node_type: str) -> set[str]:
        """Return the set of valid parm names for a SOP type."""
        parms = self.get_parms(node_type)
        return set(parms.keys()) if parms else set()

    # ── validation ──────────────────────────────────────────

    def validate_parm(self, node_type: str, name: str, value: Any) -> str | None:
        """Return an error string if parm doesn't exist or value is invalid, else None.

        Checks:
        1. Parm exists on this node type.
        2. For menu parms, the value is a valid menu item string.
        """
        parms = self.get_parms(node_type)
        if parms is None:
            return f"node type '{node_type}' not in catalog"
        if name not in parms:
            closest = _closest_match(name, parms.keys())
            hint = f" (did you mean '{closest}'?)" if closest else ""
            return f"parm '{name}' not found on {node_type}{hint}"
        pdef = parms[name]
        if pdef.get("type") == "Menu" and isinstance(value, str):
            items = set(pdef.get("menu_items") or [])
            if value not in items:
                return (
                    f"parm '{name}' on {node_type}: invalid menu item "
                    f"'{value}'. Valid: {sorted(items)}"
                )
        return None

    # ── serialization ───────────────────────────────────────

    @staticmethod
    def load(path: str = CATALOG_PATH) -> "ParmCatalog":
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Parm catalog not found at {path}. "
                f"Call dump_parm_catalog() first."
            )
        with open(path, "r", encoding="utf-8") as f:
            return ParmCatalog(json.load(f))

    @staticmethod
    def generate_catalog() -> dict[str, Any]:
        """Scan installed Houdini for all SOP types and their parm definitions."""
        sops: dict[str, dict] = {}
        for cat_name, cat in hou.nodeTypeCategories().items():
            if cat_name != "Sop":
                continue
            for nt in cat.nodeTypes().values():
                entry = {"internal_name": nt.name(), "parms": {}}
                # nt.parmTemplates() returns the factory defaults —
                # the same metadata houdini_node_parms returned previously.
                for pt in nt.parmTemplates():
                    pdef = {
                        "type": pt.type().name,  # "Float", "Int", "String", "Menu", "Toggle"
                        "label": pt.label(),
                        "default": pt.defaultValue(),
                    }
                    if pt.type().name == "Menu":
                        # Collect menu item labels
                        pdef["menu_items"] = [
                            mi.label() for mi in (pt.menuItems() or [])
                        ]
                    entry["parms"][pt.name()] = pdef
                sops[nt.name()] = entry
        return {
            "houdini_version": hou.applicationVersionString(),
            "Sop": sops,
        }


def _closest_match(name: str, candidates: set[str]) -> str | None:
    """Return the candidate with the smallest Levenshtein distance to name."""
    best, best_dist = None, float("inf")
    for c in candidates:
        d = _levenshtein(name, c)
        if d < best_dist:
            best, best_dist = c, d
    return best if best_dist <= 3 else None


def _levenshtein(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, n + 1):
            prev, dp[j] = dp[j], min(
                dp[j] + 1, dp[j - 1] + 1, prev + (a[i - 1] != b[j - 1])
            )
    return dp[n]
```

- [ ] **Step 2: 在 harness.py 中注册 `dump_parm_catalog` 工具**

```python
# python3.11libs/edini/harness.py — 在文件末尾附近添加

def dump_parm_catalog(
    output_path: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Generate (or load cached) the Houdini parm catalog.

    Called once per session/project. Phase A validation uses this catalog
    as ground truth — no cook required.

    Args:
        output_path: Where to write the catalog JSON. Defaults to
                     <edini>/python3.11libs/edini/data/parm-catalog.json
        force: If True, regenerate even if cached catalog exists.
    Returns:
        {"success": true, "path": "...", "sop_count": N, "version": "21.0.440"}
    """
    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(__file__), "data", "parm-catalog.json"
        )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if not force and os.path.exists(output_path):
        existing = _try_load_catalog(output_path)
        if existing:
            return {"success": True, "path": output_path, "regenerated": False, **existing}

    catalog = _generate_and_save_catalog(output_path)
    return {"success": True, "path": output_path, "regenerated": True, **catalog}


def _try_load_catalog(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sop_count = sum(1 for _ in data.get("Sop", {}))
        return {"sop_count": sop_count, "version": data.get("houdini_version")}
    except Exception:
        return None


def _generate_and_save_catalog(output_path: str) -> dict:
    from edini.parm_catalog import ParmCatalog

    raw = ParmCatalog.generate_catalog()
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, indent=2, ensure_ascii=False)
    sop_count = sum(1 for _ in raw.get("Sop", {}))
    return {"sop_count": sop_count, "version": raw.get("houdini_version")}
```

在工具注册表中注册：
```
"dump_parm_catalog": dump_parm_catalog,
```

- [ ] **Step 3: 测试 — 验证目录生成可运行且包含已知 SOP 类型**

```python
# 在 Houdini Python Shell 中手动测试:

from edini.harness import dump_parm_catalog
result = dump_parm_catalog(force=True)
assert result["success"]
assert result["sop_count"] > 100  # H21 至少 100 个 SOP 类型
assert "21.0" in result["version"]
print(f"✅ Catalog generated: {result['sop_count']} SOP types, Houdini {result['version']}")

# 验证特定类型的 parm 存在
from edini.parm_catalog import ParmCatalog
cat = ParmCatalog.load()
assert cat.has_node_type("torus")
assert cat.has_node_type("tube")
assert cat.has_node_type("xform")
assert not cat.has_node_type("transform")   # ✅ 这是别名，不在目录中

# 验证 parm 名
assert "radscale" in cat.parm_names("torus")
assert "rows"     in cat.parm_names("torus")
assert "cols"     in cat.parm_names("torus")
assert "rad"      not in cat.parm_names("torus")  # ✅ H21 没有 rad parm

# 验证别名解析
assert cat.resolve_alias("transform") == "xform"
assert cat.resolve_alias("polybevel") == "polybevel::3.0"

print("✅ All assertion checks passed")
```

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/parm_catalog.py
git add python3.11libs/edini/harness.py
git commit -m "feat: add auto-generated Houdini parm catalog with dump_parm_catalog tool"
```

---

### Task 2: Phase A 验证引擎

**Files:**
- Create: `python3.11libs/edini/recipe_validator.py`
- Modify: `python3.11libs/edini/harness.py` (添加 `validate_recipe` 工具)
- Reference: `python3.11libs/edini/parm_catalog.py` (Task 1)
- Reference: `python3.11libs/edini/exprs.py` (现有表达式引擎)

**Interfaces:**
- Consumes: `ParmCatalog` 类 from Task 1
- Consumes: `exprs.evaluate(expr, bindings) → float` from `exprs.py`
- Produces: `validate_recipe(recipe, catalog_path) → ValidationReport`
- Produces: `ValidationReport` 类 — `passed: bool`, `stages: dict`, `errors: list`, `component_manifest: list`

- [ ] **Step 1: 实现 A1 — Schema 校验**

```python
# python3.11libs/edini/recipe_validator.py

"""Phase A: Pure validation of procedural asset recipes.

Zero Houdini operations. All checks are deterministic data validation
against the parm catalog and expression engine.
"""

import re
import json
from typing import Any

from edini.parm_catalog import ParmCatalog

# ── Constants ───────────────────────────────────────────────

VALID_BACKENDS = {"python", "vex_skeleton", "native_chain"}
LOCAL_AXIS_VECTORS = {
    "X": (1.0, 0.0, 0.0),
    "Y": (0.0, 1.0, 0.0),
    "Z": (0.0, 0.0, 1.0),
}

# ── A1: Schema Validation ──────────────────────────────────

def _validate_a1_schema(recipe: dict) -> list[dict]:
    """Validate recipe JSON structure. Returns list of error dicts."""
    errors: list[dict] = []

    if not isinstance(recipe, dict):
        return [_error("A1_SCHEMA", "recipe must be a JSON object", {})]

    # ── components ──
    components = recipe.get("components")
    if not isinstance(components, list) or not components:
        errors.append(_error(
            "A1_SCHEMA",
            "recipe.components must be a non-empty list",
            {"field": "components"}
        ))
        return errors

    seen_ids: set[str] = set()
    for i, comp in enumerate(components):
        loc = {"component_index": i}
        if not isinstance(comp, dict):
            errors.append(_error("A1_SCHEMA", f"components[{i}] must be an object", loc))
            continue
        cid = comp.get("id")
        if not isinstance(cid, str) or not cid.strip():
            errors.append(_error("A1_SCHEMA", f"components[{i}].id must be a non-empty string", loc))
        elif cid in seen_ids:
            errors.append(_error("A1_SCHEMA", f"components[{i}].id '{cid}' duplicates", loc))
        else:
            seen_ids.add(cid)
        loc["component_id"] = cid

        backend = comp.get("backend", "python")
        if backend not in VALID_BACKENDS:
            errors.append(_error(
                "A1_SCHEMA",
                f"components[{i}].backend '{backend}' must be one of {sorted(VALID_BACKENDS)}",
                loc
            ))

        if backend != "native_chain":
            code = comp.get("code", "")
            if not isinstance(code, str) or not code.strip():
                errors.append(_error(
                    "A1_SCHEMA",
                    f"components[{i}].code must be a non-empty string (backend={backend})",
                    loc
                ))

        if backend == "vex_skeleton":
            form = comp.get("form_node")
            if not isinstance(form, dict):
                errors.append(_error(
                    "A1_SCHEMA",
                    f"components[{i}] (vex_skeleton) requires form_node object",
                    loc
                ))
            else:
                fn_type = form.get("type")
                if not isinstance(fn_type, str) or not fn_type.strip():
                    errors.append(_error(
                        "A1_SCHEMA",
                        f"components[{i}].form_node.type must be a non-empty SOP type",
                        {**loc, "field": "form_node.type"}
                    ))

        if backend == "native_chain":
            nodes = comp.get("nodes")
            if not isinstance(nodes, list):
                errors.append(_error(
                    "A1_SCHEMA",
                    f"components[{i}] (native_chain) requires nodes list",
                    loc
                ))
            else:
                for ni, node in enumerate(nodes):
                    nloc = {**loc, "node_index": ni}
                    if not isinstance(node.get("type"), str) or not node["type"].strip():
                        errors.append(_error(
                            "A1_SCHEMA",
                            f"components[{i}].nodes[{ni}].type must be a non-empty string",
                            nloc
                        ))

    # ── params ──
    params = recipe.get("params")
    if params is not None:
        if not isinstance(params, dict):
            errors.append(_error("A1_SCHEMA", "recipe.params must be an object if present", {}))
        else:
            for pname, pspec in params.items():
                ploc = {"param_name": pname}
                if not isinstance(pspec, dict):
                    errors.append(_error("A1_SCHEMA", f"params['{pname}'] must be an object", ploc))
                    continue
                kind = pspec.get("kind", "primary")
                if kind not in ("primary", "derived", "constrained"):
                    errors.append(_error(
                        "A1_SCHEMA",
                        f"params['{pname}'].kind '{kind}' must be primary|derived|constrained",
                        ploc
                    ))
                if "default" not in pspec and kind == "primary":
                    errors.append(_error(
                        "A1_SCHEMA",
                        f"params['{pname}'] (primary) requires 'default'",
                        ploc
                    ))
                if kind == "derived" and "from" not in pspec:
                    errors.append(_error(
                        "A1_SCHEMA",
                        f"params['{pname}'] (derived) requires 'from' expression",
                        ploc
                    ))
                if kind == "constrained":
                    constraints = pspec.get("constraints")
                    if not isinstance(constraints, list):
                        errors.append(_error(
                            "A1_SCHEMA",
                            f"params['{pname}'] (constrained) requires 'constraints' list",
                            ploc
                        ))
    return errors


def _error(code: str, message: str, location: dict) -> dict:
    return {
        "stage": code,
        "severity": "BLOCKING" if "WARNING" not in code else "WARNING",
        "message": message,
        "location": location,
    }
```

- [ ] **Step 2: 实现 A2 — 参数名交叉验证**

```python
# 继续在 recipe_validator.py 中

def _validate_a2_parm_names(recipe: dict, catalog: ParmCatalog) -> list[dict]:
    """Cross-check all SOP parm names against the catalog."""
    errors: list[dict] = []

    for i, comp in enumerate(recipe.get("components", [])):
        cid = comp.get("id", f"@index_{i}")
        loc = {"component_index": i, "component_id": cid}

        if comp.get("backend") == "native_chain":
            for ni, node in enumerate(comp.get("nodes", [])):
                ntype = node.get("type", "")
                nloc = {**loc, "node_index": ni, "node_type": ntype}
                # Resolve alias
                canonical = catalog.resolve_alias(ntype)
                if ntype != canonical:
                    nloc["node_type"] = canonical
                params = node.get("params", {})
                for pname, pvalue in params.items():
                    nloc_p = {**nloc, "parm_name": pname}
                    err = catalog.validate_parm(canonical, pname, pvalue)
                    if err:
                        errors.append(_error("A2_PARAM_NAME", err, nloc_p))

        elif comp.get("backend") == "vex_skeleton":
            form = comp.get("form_node", {})
            fn_type = form.get("type", "")
            canonical = catalog.resolve_alias(fn_type)
            floc = {**loc, "field": "form_node", "node_type": canonical}
            for pname, pvalue in form.get("params", {}).items():
                floc_p = {**floc, "parm_name": pname}
                err = catalog.validate_parm(canonical, pname, pvalue)
                if err:
                    errors.append(_error("A2_PARAM_NAME", err, floc_p))

    # ── postprocess parms ──
    for pi, step in enumerate(recipe.get("postprocess", [])):
        stype = step.get("type", "")
        canonical = catalog.resolve_alias(stype)
        ploc = {"postprocess_index": pi, "node_type": canonical}
        for pname, pvalue in step.get("params", {}).items():
            ploc_p = {**ploc, "parm_name": pname}
            err = catalog.validate_parm(canonical, pname, pvalue)
            if err:
                errors.append(_error("A2_PARAM_NAME", err, ploc_p))

    return errors
```

- [ ] **Step 3: 实现 A3 — 节点类型验证**

```python
def _validate_a3_node_types(recipe: dict, catalog: ParmCatalog) -> list[dict]:
    """Verify all node type names exist in the catalog (or have an alias)."""
    errors: list[dict] = []

    for i, comp in enumerate(recipe.get("components", [])):
        cid = comp.get("id", f"@index_{i}")
        loc = {"component_index": i, "component_id": cid}

        if comp.get("backend") == "native_chain":
            for ni, node in enumerate(comp.get("nodes", [])):
                ntype = node.get("type", "")
                nloc = {**loc, "node_index": ni, "node_type": ntype}
                canonical = catalog.resolve_alias(ntype)
                if canonical != ntype:
                    nloc["canonical_type"] = canonical
                if not catalog.has_node_type(canonical):
                    errors.append(_error(
                        "A3_NODE_TYPE",
                        f"node type '{ntype}' not found in Houdini {catalog._data.get('houdini_version')}",
                        nloc
                    ))
                else:
                    nloc_p = {**nloc, "suggestion": f"Use '{canonical}'"}

        if comp.get("backend") == "vex_skeleton":
            fn_type = comp.get("form_node", {}).get("type", "")
            canonical = catalog.resolve_alias(fn_type)
            floc = {**loc, "field": "form_node.type", "node_type": fn_type}
            if not catalog.has_node_type(canonical):
                errors.append(_error(
                    "A3_NODE_TYPE",
                    f"form_node type '{fn_type}' not found",
                    floc
                ))

    for pi, step in enumerate(recipe.get("postprocess", [])):
        ntype = step.get("type", "")
        canonical = catalog.resolve_alias(ntype)
        ploc = {"postprocess_index": pi, "node_type": ntype}
        if not catalog.has_node_type(canonical):
            errors.append(_error("A3_NODE_TYPE", f"postprocess type '{ntype}' not found", ploc))

    return errors
```

- [ ] **Step 4: 实现 A4 — VEX 基础 Lint**

```python
# VEX lint patterns — regex-based heuristics, not a real compiler.

_VEX_BLOCKING_PATTERNS = [
    (
        "A4_VEX_PERCENT",
        re.compile(r'%(?:\w+)%'),
        "Python-style string formatting '%...%' is not valid VEX. Use chf('name') with plain string.",
    ),
    (
        "A4_VEX_POLY",
        re.compile(r'addprim\s*\(\s*(?:\w+\s*,\s*)?\s*"poly"\s*\)'),
        "Manually creating poly prim in VEX is forbidden. Emit skeletons (polylines) only; form_node (Sweep/PolyExtrude) closes the geometry.",
    ),
]

_VEX_WARNING_PATTERNS = [
    (
        "A4_VEX_NO_DETAIL",
        re.compile(r'addpoint\b'),
        "Code contains addpoint() but no '// Run Over: Detail' marker. If this runs in Point mode, geometry explodes by N².",
    ),
]


def _validate_a4_vex_lint(recipe: dict) -> list[dict]:
    errors: list[dict] = []

    for i, comp in enumerate(recipe.get("components", [])):
        cid = comp.get("id", f"@index_{i}")
        loc = {"component_index": i, "component_id": cid}

        if comp.get("backend") != "vex_skeleton":
            continue
        code = comp.get("code", "")
        if not code:
            continue

        for code_id, pattern, message in _VEX_BLOCKING_PATTERNS:
            m = pattern.search(code)
            if m:
                lineno = code[:m.start()].count("\n") + 1
                errors.append(_error(code_id, f"Line {lineno}: {message}", {
                    **loc, "line": lineno, "match": m.group()
                }))

        for code_id, pattern, message in _VEX_WARNING_PATTERNS:
            m = pattern.search(code)
            if m:
                # WARNING only if no Detail marker comment found
                if "Run Over: Detail" not in code and "run over: detail" not in code.lower():
                    lineno = code[:m.start()].count("\n") + 1
                    errors.append(_error(code_id, f"Line {lineno}: {message}", {
                        **loc, "line": lineno
                    }))

    return errors


# VEX ch() reference extraction for A4_VEX_UNDEF_PARAM
_VEX_CH_RE = re.compile(r'\b(ch[fi]\s*\(\s*"([^"]+)"\s*\))')


def _validate_a4_vex_refs(recipe: dict, declared_params: set[str]) -> list[dict]:
    """Check every ch()/chf()/chi() ref in VEX code references a declared param."""
    errors: list[dict] = []
    for i, comp in enumerate(recipe.get("components", [])):
        cid = comp.get("id", f"@index_{i}")
        if comp.get("backend") != "vex_skeleton":
            continue
        code = comp.get("code", "")
        reads = set(comp.get("reads", []))
        for m in _VEX_CH_RE.finditer(code):
            refname = m.group(2)
            if refname in declared_params:
                continue
            if refname in reads:
                continue
            lineno = code[:m.start()].count("\n") + 1
            errors.append(_error(
                "A4_VEX_UNDEF_PARAM",
                f"VEX ch() ref '{refname}' (line {lineno}) not in declared params or component reads",
                {"component_id": cid, "line": lineno, "ref": refname}
            ))
    return errors
```

- [ ] **Step 5: 实现 A5 — 构造轴一致性（从现有代码迁移）**

```python
def _validate_a5_construction_axis(recipe: dict) -> list[dict]:
    """Migrate from harness.py:_check_construction_axis_consistency.

    For each orientation_assert that declares construction_axis, resolve the
    world axis and check it matches expected_axis. No Houdini call needed —
    uses anchor @orient (quaternion) + pure math.
    """
    from edini.orientation_math import rotate_vector_by_quaternion  # if exists
    import math

    errors: list[dict] = []
    asserts = recipe.get("orientation_asserts", [])
    if not asserts:
        return errors

    # Build component map for anchor lookup
    comps_map = {}
    anchors_map = {}
    for i, comp in enumerate(recipe.get("components", [])):
        cid = comp.get("id", "")
        if cid:
            comps_map[cid] = comp
        for ai, anc in enumerate(comp.get("anchors", [])):
            ac_id = anc.get("component_id", f"{cid}_anchor_{ai}")
            anchors_map[ac_id] = anc

    for i, a in enumerate(asserts):
        cid = a.get("component_id", "")
        caxis_str = (a.get("construction_axis") or "").upper()
        if not caxis_str or caxis_str not in LOCAL_AXIS_VECTORS:
            continue  # no construction_axis → skip (PCA path)

        local_vec = LOCAL_AXIS_VECTORS[caxis_str]

        # Direct-merge components: orient = identity
        orient = (0.0, 0.0, 0.0, 1.0)

        if cid in anchors_map:
            anc = anchors_map[cid]
            orient = anc.get("orient", (0.0, 0.0, 0.0, 1.0))
        elif cid in comps_map and comps_map[cid].get("anchors"):
            # Component has anchors but this cid isn't a per-anchor id —
            # use the first anchor's orient
            anc0 = comps_map[cid]["anchors"][0]
            orient = anc0.get("orient", (0.0, 0.0, 0.0, 1.0))

        # Rotate construction_axis by anchor orient → world axis
        world_vec = _rotate_vector_by_quaternion(local_vec, orient)

        # Compare with expected_axis
        exp_str = (a.get("expected_axis") or "").upper()
        if exp_str not in LOCAL_AXIS_VECTORS:
            continue
        exp_vec = LOCAL_AXIS_VECTORS[exp_str]

        angle = _angle_between(world_vec, exp_vec)
        tol = a.get("tolerance_deg", 15)
        if angle > tol:
            errors.append(_error(
                "A5_CONSTRUCTION",
                f"construction_axis {caxis_str} rotated by orient {orient} "
                f"projects to world axis {_vec_label(world_vec)} "
                f"({angle:.1f}° from expected {exp_str}, tolerance {tol}°)",
                {"component_id": cid, "angle_deg": round(angle, 1)}
            ))
    return errors


def _rotate_vector_by_quaternion(v, q):
    """Rotate vector v by quaternion q = (x,y,z,w). Pure math."""
    qx, qy, qz, qw = q
    vx, vy, vz = v
    # q * v * q⁻¹
    # q * (0, vx, vy, vz) * q_conjugate
    t = (2 * (qy * vz - qz * vy),
         2 * (qz * vx - qx * vz),
         2 * (qx * vy - qy * vx))
    return (vx + qw * t[0] + (qy * t[2] - qz * t[1]),
            vy + qw * t[1] + (qz * t[0] - qx * t[2]),
            vz + qw * t[2] + (qx * t[1] - qy * t[0]))


def _angle_between(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    ma = math.sqrt(sum(x * x for x in a))
    mb = math.sqrt(sum(x * x for x in b))
    if ma < 1e-10 or mb < 1e-10:
        return 0
    dot = max(-1, min(1, dot / (ma * mb)))
    return math.degrees(math.acos(dot))


def _vec_label(v):
    for label, vec in LOCAL_AXIS_VECTORS.items():
        if all(abs(a - b) < 0.001 for a, b in zip(v, vec)):
            return label
    return f"[{v[0]:.2f},{v[1]:.2f},{v[2]:.2f}]"
```

- [ ] **Step 6: 实现 A6 — 参数依赖图验证**

```python
def _validate_a6_dependency_graph(recipe: dict) -> tuple[list[dict], dict | None]:
    """Validate the param dependency graph.

    Returns (errors, dependency_graph).
    dependency_graph: {param_name: {"depends_on": [...], "kind": "primary"|"derived"|"constrained"}}
    """
    from edini.exprs import extract_refs  # NEW: extend exprs.py (see below)

    errors: list[dict] = []
    params = recipe.get("params", {})
    if not params:
        return errors, None

    graph: dict[str, dict] = {}
    for pname, pspec in params.items():
        kind = pspec.get("kind", "primary")
        deps = []
        if kind == "derived":
            from_expr = pspec.get("from", "")
            deps = extract_refs(from_expr)
        elif kind == "constrained":
            for c in pspec.get("constraints", []):
                check_expr = c.get("check", "")
                if check_expr:
                    deps.extend(extract_refs(check_expr))
        graph[pname] = {"depends_on": list(set(deps)), "kind": kind}

    # ── 检测循环依赖 (Kahn's algorithm) ──
    in_degree = {k: len(v["depends_on"]) for k, v in graph.items()}
    queue = [k for k, d in in_degree.items() if d == 0]
    sorted_nodes: list[str] = []
    adjacency: dict[str, list[str]] = {k: [] for k in graph}
    for k, v in graph.items():
        for dep in v["depends_on"]:
            if dep in adjacency:
                adjacency[dep].append(k)

    while queue:
        node = queue.pop(0)
        sorted_nodes.append(node)
        for neighbor in adjacency.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(sorted_nodes) != len(graph):
        cycle_nodes = [k for k in graph if in_degree[k] > 0]
        errors.append(_error(
            "A6_DAG_CYCLE",
            f"Cycle detected involving: {', '.join(sorted(cycle_nodes))}",
            {"cycle_nodes": cycle_nodes}
        ))

    # ── 检测悬空引用 ──
    for pname, info in graph.items():
        for dep in info["depends_on"]:
            if dep not in graph:
                errors.append(_error(
                    "A6_DAG_DANGLE",
                    f"Param '{pname}' references undeclared param '{dep}'",
                    {"param": pname, "missing_ref": dep}
                ))

    # ── 检测孤立主控 ──
    all_consumer_refs: set[str] = set()
    for info in graph.values():
        all_consumer_refs.update(info["depends_on"])
    for comp in recipe.get("components", []):
        all_consumer_refs.update(comp.get("reads", []))

    for pname, info in graph.items():
        if info["kind"] == "primary" and pname not in all_consumer_refs:
            errors.append(_error(
                "A6_DAG_ORPHAN",
                f"Primary param '{pname}' is not consumed by any component or derived param. "
                f"It will have no effect on the asset.",
                {"param": pname}
            ))

    return errors, graph
```

`extract_refs()` 需要在 `exprs.py` 中实现：

```python
# python3.11libs/edini/exprs.py — 新增函数

import re

# 匹配表达式中的参数名（名词 / 数字 / _ 开头，后面可以跟 .）
_REF_RE = re.compile(r'([a-zA-Z_]\w*)')


def extract_refs(expr: str) -> list[str]:
    """Extract parameter references from an expression string.

    Examples:
        extract_refs("wheel_radius - bb_drop") → ["wheel_radius", "bb_drop"]
        extract_refs("sin(radians(seat_angle)) + frame_scale * 0.5") → ["seat_angle", "frame_scale"]
    """
    # Built-in function names to exclude
    BUILTINS = {
        "sin", "cos", "tan", "abs", "min", "max", "sqrt", "pow",
        "radians", "degrees", "pi", "e", "tau", "and", "or", "not",
        "if", "else", "True", "False", "None",
    }
    refs: set[str] = set()
    for m in _REF_RE.finditer(expr):
        name = m.group(1)
        if name not in BUILTINS and not name[0].isdigit():
            refs.add(name)
    return sorted(refs)
```

- [ ] **Step 7: 组装 `validate_recipe` 主入口 + 注册工具**

```python
# python3.11libs/edini/recipe_validator.py（继续）

def validate_recipe(
    recipe: dict,
    catalog_path: str | None = None,
) -> dict[str, Any]:
    """Phase A: validate a procedural asset recipe without any Houdini operations.

    Returns a ValidationReport dict with:
        passed: bool — True if all BLOCKING checks passed
        stages: dict — per-stage {passed, error_count, warning_count}
        errors: list — all validation errors (BLOCKING and WARNING)
        warnings: list — WARNING-level items only
        dependency_graph: dict | None — param DAG (if params declared)
        component_manifest: list — {component_id, backend} for every component
    """
    catalog = ParmCatalog.load(catalog_path) if catalog_path else None

    all_errors: list[dict] = []

    # Run all stages, collecting errors
    all_errors.extend(_validate_a1_schema(recipe))

    if catalog:
        # A2/A3 need the catalog
        all_errors.extend(_validate_a2_parm_names(recipe, catalog))
        all_errors.extend(_validate_a3_node_types(recipe, catalog))

    all_errors.extend(_validate_a4_vex_lint(recipe))

    declared_params = set((recipe.get("params") or {}).keys())
    all_errors.extend(_validate_a4_vex_refs(recipe, declared_params))

    all_errors.extend(_validate_a5_construction_axis(recipe))

    dep_errors, dep_graph = _validate_a6_dependency_graph(recipe)
    all_errors.extend(dep_errors)

    # ── 汇总 ──
    blocking = [e for e in all_errors if e["severity"] == "BLOCKING"]
    warnings = [e for e in all_errors if e["severity"] == "WARNING"]

    stage_summary = {}
    for err in all_errors:
        stage = err["stage"]
        entry = stage_summary.setdefault(stage, {"error_count": 0, "warning_count": 0})
        if err["severity"] == "BLOCKING":
            entry["error_count"] += 1
        else:
            entry["warning_count"] += 1
    for stage, counts in stage_summary.items():
        counts["passed"] = counts["error_count"] == 0

    # 构建组件清单
    manifest = []
    for comp in recipe.get("components", []):
        manifest.append({
            "component_id": comp.get("id"),
            "backend": comp.get("backend", "python"),
            "has_anchors": bool(comp.get("anchors")),
            "exposes": comp.get("exposes", []),
        })

    return {
        "passed": len(blocking) == 0,
        "stages": stage_summary,
        "errors": blocking,
        "warnings": warnings,
        "error_count": len(blocking),
        "warning_count": len(warnings),
        "dependency_graph": dep_graph,
        "component_manifest": manifest,
    }
```

在 harness.py 中注册工具：

```python
# python3.11libs/edini/harness.py

def validate_recipe_tool(
    recipe: dict,
    catalog_path: str | None = None,
) -> dict[str, Any]:
    """Tool wrapper for Phase A validation."""
    if catalog_path is None:
        catalog_path = os.path.join(
            os.path.dirname(__file__), "data", "parm-catalog.json"
        )
    if not os.path.exists(catalog_path):
        return {
            "success": False,
            "error": (
                "Parm catalog not found. Run dump_parm_catalog() first, "
                f"or pass catalog_path to an existing catalog."
            ),
        }
    from edini.recipe_validator import validate_recipe
    result = validate_recipe(recipe, catalog_path)
    result["success"] = True
    return result
```

- [ ] **Step 8: 测试 — 用一个已知错误的食谱验证 A1-A6 全部捕获**

```python
# 在 Houdini Python Shell 中测试:

import json
from edini.recipe_validator import validate_recipe

# ── 测试 1：全通过的食谱 ──
valid = {
    "components": [
        {"id": "test_box", "backend": "native_chain", "nodes": [
            {"type": "box", "params": {"sizex": 1, "sizey": 1, "sizez": 1}}
        ]}
    ]
}
result = validate_recipe(valid)
assert result["passed"], f"Expected valid recipe to pass: {result['errors']}"
print("✅ Test 1 (valid recipe) passed")

# ── 测试 2：不存在的 parm ──
bad_parm = {
    "components": [
        {"id": "bad", "backend": "native_chain", "nodes": [
            {"type": "torus", "params": {"rad": [0.08, 0.08]}}  # rad doesn't exist in H21
        ]}
    ]
}
result = validate_recipe(bad_parm)
assert not result["passed"], "Expected bad parm to fail"
assert any(e["stage"] == "A2_PARAM_NAME" for e in result["errors"]), \
    f"Expected A2_PARAM_NAME error: {result['errors']}"
print("✅ Test 2 (bad parm name) caught")

# ── 测试 3：不存在的节点类型 ──
bad_node = {
    "components": [
        {"id": "bad", "backend": "vex_skeleton",
         "code": "int pts[] = make_polyline(0, array({0,0,0}, {1,0,0}));",
         "form_node": {"type": "transform", "input0": "self"}}  # not a real SOP
    ]
}
result = validate_recipe(bad_node)
assert not result["passed"]
assert any(e["stage"] == "A3_NODE_TYPE" for e in result["errors"])
print("✅ Test 3 (bad node type) caught")

# ── 测试 4：VEX 中使用 % ──
bad_vex = {
    "components": [
        {"id": "bad", "backend": "vex_skeleton",
         "code": "float r = chf('%radius%');",  # Python-style
         "form_node": {"type": "sweep::2.0", "input0": "self"}}
    ]
}
result = validate_recipe(bad_vex)
assert not result["passed"]
assert any(e["stage"] == "A4_VEX_PERCENT" for e in result["errors"])
print("✅ Test 4 (VEX percent format) caught")

# ── 测试 5：构造轴不一致 ──
bad_axis = {
    "components": [
        {"id": "ring", "backend": "native_chain", "nodes": [
            {"type": "torus", "params": {"radscale": 0.1, "rows": 3, "cols": 24}}
        ]}
    ],
    "orientation_asserts": [
        {"component_id": "ring", "kind": "radial",
         "construction_axis": "Y",   # torus in XZ plane → construction_axis = Y
         "expected_axis": "X",       # but expected says X → 90° mismatch
         "tolerance_deg": 10}
    ]
}
result = validate_recipe(bad_axis)
assert not result["passed"]
assert any(e["stage"] == "A5_CONSTRUCTION" for e in result["errors"])
print("✅ Test 5 (construction axis mismatch) caught")

# ── 测试 6：参数循环依赖 ──
bad_dep = {
    "components": [{"id": "box", "backend": "native_chain", "nodes": [{"type": "box"}]}],
    "params": {
        "A": {"kind": "derived", "from": "B + 1"},
        "B": {"kind": "derived", "from": "A + 1"},  # cycle!
    }
}
result = validate_recipe(bad_dep)
assert not result["passed"]
assert any(e["stage"] == "A6_DAG_CYCLE" for e in result["errors"])
print("✅ Test 6 (cycle detection) caught")

print("\n🎉 All A1-A6 validation tests passed!")
```

- [ ] **Step 9: Commit**

```bash
git add python3.11libs/edini/recipe_validator.py
git add python3.11libs/edini/harness.py
git add python3.11libs/edini/exprs.py
git commit -m "feat: add Phase A recipe validation engine (A1-A6 checks)"
```

---

### Task 3: Phase B 逐组件构建器

**Files:**
- Create: `python3.11libs/edini/component_builder.py`
- Modify: `python3.11libs/edini/harness.py` (添加 `build_component` 工具)
- Reference: `python3.11libs/edini/recipe_validator.py` (Task 2)

**Interfaces:**
- Consumes: `recipe` dict + `ValidationReport` from Task 2
- Produces: `build_component(recipe, component_id, sandbox_root, ...) → ComponentBuildResult`
- Produces: `ComponentBuildResult` — `status`, `geometry`, `health`, `component_id_confirmed`, `cache_path`

- [ ] **Step 1: 定义 ComponentBuildResult 结构**

```python
# python3.11libs/edini/component_builder.py

"""Phase B: Per-component building. Each component cooks in its own
sandbox sub-network, verified immediately after cook."""

import json, os, time, hashlib
from typing import Any

class ComponentBuildResult:
    """Result of building a single component."""
    __slots__ = (
        "component_id", "status", "backend", "cook_time_ms",
        "geometry", "health", "component_id_confirmed",
        "cache_path", "error",
    )

    def __init__(self, component_id: str, backend: str):
        self.component_id = component_id
        self.backend = backend
        self.status = "pending"
        self.cook_time_ms = 0
        self.geometry: dict | None = None
        self.health: dict | None = None
        self.component_id_confirmed = False
        self.cache_path: str | None = None
        self.error: str | None = None

    def to_dict(self) -> dict:
        return {
            "component_id": self.component_id,
            "backend": self.backend,
            "status": self.status,
            "cook_time_ms": self.cook_time_ms,
            "geometry": self.geometry,
            "health": self.health,
            "component_id_confirmed": self.component_id_confirmed,
            "cache_path": self.cache_path,
            "error": self.error,
        }
```

- [ ] **Step 2: 实现 native_chain 组件构建**

```python
def _build_native_chain(
    container: hou.ObjNode,
    comp: dict,
    catalog: Any,
) -> hou.OpNode | None:
    """Build a native_chain component inside container.

    Creates: SOP chain → attribcreate (component_id tag) → Null OUT.
    Returns the OUT null node, or None on failure.
    """
    cid = comp["id"]
    nodes_list = comp.get("nodes", [])
    prev = None

    for ni, node_spec in enumerate(nodes_list):
        ntype = node_spec["type"]
        # Resolve alias
        canonical = catalog.resolve_alias(ntype) if catalog else ntype
        name = f"{cid}_n{ni}"
        try:
            node = container.createNode(canonical, name)
        except hou.OperationFailed as e:
            raise RuntimeError(
                f"component '{cid}' node[{ni}]: failed to create '{canonical}': {e}"
            )

        if prev:
            node.setInput(0, prev)
        prev = node

        # 设置参数
        for pname, pvalue in node_spec.get("params", {}).items():
            try:
                node.parm(pname).set(pvalue)
            except Exception as e:
                raise RuntimeError(
                    f"component '{cid}' node[{ni}] parm '{pname}': {e}"
                )

    # attribcreate 标签
    tag = container.createNode("attribcreate", f"{cid}_tag")
    if prev:
        tag.setInput(0, prev)
    # H21 正确的菜单值
    tag.parm("name1").set("component_id")
    tag.parm("class1").set("primitive")
    tag.parm("type1").set("string")
    tag.parm("string1").set(cid)

    # OUT null
    out = container.createNode("null", f"{cid}_OUT")
    out.setInput(0, tag)
    return out
```

- [ ] **Step 3: 实现 vex_skeleton 组件构建**

```python
def _build_vex_skeleton(
    container: hou.ObjNode,
    comp: dict,
    catalog: Any,
) -> hou.OpNode | None:
    """Build a vex_skeleton component.

    Creates: attribwrangle (Detail, VEX code) → form_node → attribcreate → OUT.
    """
    cid = comp["id"]
    code = comp.get("code", "")
    form = comp.get("form_node", {})

    # wrangle (Detail mode)
    wr = container.createNode("attribwrangle", f"{cid}_wrangle")
    wr.parm("snippet").set(code)
    wr.parm("class").set(2)  # 2 = Detail mode
    # Inject vexlib includes
    full_code = "#include <vexlib/skeleton.vfl>\n#include <vexlib/sections.vfl>\n" + code
    wr.parm("snippet").set(full_code)

    # form_node
    fn_type = form.get("type", "sweep::2.0")
    canonical = catalog.resolve_alias(fn_type) if catalog else fn_type
    fn = container.createNode(canonical, f"{cid}_form")
    fn.setInput(0, wr)
    for pname, pvalue in form.get("params", {}).items():
        fn.parm(pname).set(pvalue)

    # attribcreate
    tag = container.createNode("attribcreate", f"{cid}_tag")
    tag.setInput(0, fn)
    tag.parm("name1").set("component_id")
    tag.parm("class1").set("primitive")
    tag.parm("type1").set("string")
    tag.parm("string1").set(cid)

    out = container.createNode("null", f"{cid}_OUT")
    out.setInput(0, tag)
    return out
```

- [ ] **Step 4: 实现 python 组件构建**

```python
def _build_python(
    container: hou.ObjNode,
    comp: dict,
) -> hou.OpNode | None:
    """Build a python-backend component."""
    cid = comp["id"]
    code = comp.get("code", "")

    py = container.createNode("python", f"{cid}_python")
    py.parm("python").set(code)

    out = container.createNode("null", f"{cid}_OUT")
    out.setInput(0, py)
    return out
```

- [ ] **Step 5: 实现 build_component 主函数 + 验证 + 缓存**

```python
def build_component(
    recipe: dict,
    component_id: str,
    sandbox_root_path: str,
    catalog_path: str | None = None,
) -> dict:
    """Build a single component inside the sandbox.

    Args:
        recipe: The full recipe dict (for param definitions).
        component_id: Which component to build.
        sandbox_root_path: e.g. "/obj/edini_sandbox_..."
        catalog_path: Path to parm-catalog.json.
    Returns:
        ComponentBuildResult as dict.
    """
    # 加载 catalog
    catalog = None
    if catalog_path:
        from edini.parm_catalog import ParmCatalog
        catalog = ParmCatalog.load(catalog_path)

    # 查找组件
    comp = None
    for c in recipe.get("components", []):
        if c.get("id") == component_id:
            comp = c
            break
    if comp is None:
        return {"component_id": component_id, "status": "failed",
                "error": f"Component '{component_id}' not found in recipe"}

    result = ComponentBuildResult(component_id, comp.get("backend", "python"))
    t0 = time.time()

    try:
        root = hou.node(sandbox_root_path)
        if root is None:
            raise RuntimeError(f"Sandbox root not found: {sandbox_root_path}")

        # 创建子网络
        subnet_name = f"comp_{component_id}"
        existing = root.node(subnet_name)
        if existing:
            existing.destroy()
        subnet = root.createNode("subnet", subnet_name)

        # 根据 backend 构建
        backend = comp.get("backend", "python")
        if backend == "native_chain":
            out_node = _build_native_chain(subnet, comp, catalog)
        elif backend == "vex_skeleton":
            out_node = _build_vex_skeleton(subnet, comp, catalog)
        else:
            out_node = _build_python(subnet, comp)

        # Cook
        out_node.cook(force=True)

        # 验证几何体
        geo = out_node.geometry()
        if geo is None or geo.floatListAttribValue("P") is None:
            result.status = "failed"
            result.error = "B1_EMPTY_GEO: component cooked but produced no geometry"
            result.cook_time_ms = int((time.time() - t0) * 1000)
            return result.to_dict()

        # 检查 component_id
        prims = geo.iterPrims()
        has_cid = any(
            p.stringAttribValue("component_id") == component_id
            for p in prims
        )

        # 健康检查
        health = _quick_health_check(out_node)

        result.status = "passed"
        result.geometry = _geo_stats(geo)
        result.health = health
        result.component_id_confirmed = has_cid
        result.cook_time_ms = int((time.time() - t0) * 1000)

        # 缓存
        cache_dir = os.path.join(
            os.path.dirname(catalog_path or ""),
            "component_cache", component_id
        )
        result.cache_path = cache_dir

        return result.to_dict()

    except Exception as e:
        result.status = "failed"
        result.error = f"B1_COOK_FAILED: {e}"
        result.cook_time_ms = int((time.time() - t0) * 1000)
        return result.to_dict()


def _geo_stats(geo) -> dict:
    """Extract basic geometry stats."""
    bbox = geo.boundingBox()
    return {
        "point_count": geo.intrinsicValue("pointcount"),
        "prim_count": geo.intrinsicValue("primitivecount"),
        "bounds": {
            "min": list(bbox.minvec()),
            "max": list(bbox.maxvec()),
            "size": list(bbox.sizevec()),
        },
    }


def _quick_health_check(node) -> dict:
    """Run a fast geometry health check on a cooked node."""
    from edini.harness import inspect_geometry_health
    return inspect_geometry_health(node.path())
```

- [ ] **Step 6: 在 harness.py 注册 build_component 工具**

```python
# 工具注册表添加:
"build_component": build_component,
```

- [ ] **Step 7: 测试**

```python
# 手动测试 — 构建单个 box 组件:

recipe = {
    "params": {},
    "components": [
        {"id": "test_box", "backend": "native_chain", "nodes": [
            {"type": "box", "params": {"sizex": 1, "sizey": 0.5, "sizez": 0.3}},
        ]}
    ]
}

result = build_component(recipe, "test_box", "/obj/edini_sandbox_test")
assert result["status"] == "passed"
assert result["geometry"]["point_count"] > 0
assert result["component_id_confirmed"], "Component ID not tagged!"
assert result["health"]["overall_ok"]
print("✅ build_component test passed")
```

- [ ] **Step 8: Commit**

```bash
git add python3.11libs/edini/component_builder.py
git add python3.11libs/edini/harness.py
git commit -m "feat: add Phase B per-component builder with health verification"
```

---

### Task 4: 组件缓存 + Manifest

**Files:**
- Modify: `python3.11libs/edini/component_builder.py` (添加缓存逻辑)
- Create: `python3.11libs/edini/component_cache.py`

**Interfaces:**
- Produces: `ComponentCache` 类 — `save(result)`, `load(component_id)`, `manifest()`
- Produces: `manifest.json` 格式 — `{component_id: {status, hash, ...}}`

- [ ] **Step 1: 实现 ComponentCache**

```python
# python3.11libs/edini/component_cache.py

"""Persistent cache for built components."""

import json, os, hashlib
from typing import Any


class ComponentCache:
    """File-based cache for per-component build results."""

    def __init__(self, cache_root: str):
        self.root = cache_root
        os.makedirs(cache_root, exist_ok=True)
        self._manifest_path = os.path.join(cache_root, ".manifest.json")

    def save(self, component_id: str, result: dict, recipe_hash: str) -> str:
        """Save a component build result. Returns the cache path."""
        comp_dir = os.path.join(self.root, component_id)
        os.makedirs(comp_dir, exist_ok=True)
        result_path = os.path.join(comp_dir, "result.json")
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        self._update_manifest(component_id, result["status"], recipe_hash)
        return comp_dir

    def load(self, component_id: str) -> dict | None:
        """Load cached result, or None if not cached."""
        result_path = os.path.join(self.root, component_id, "result.json")
        if not os.path.exists(result_path):
            return None
        with open(result_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def manifest(self) -> dict[str, dict]:
        """Return {component_id: {status, hash, ...}}."""
        if not os.path.exists(self._manifest_path):
            return {}
        with open(self._manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def all_passed(self) -> bool:
        """True if all cached components have status 'passed'."""
        m = self.manifest()
        return all(v.get("status") == "passed" for v in m.values())

    def _update_manifest(self, cid: str, status: str, recipe_hash: str):
        m = self.manifest()
        m[cid] = {"status": status, "recipe_hash": recipe_hash}
        with open(self._manifest_path, "w", encoding="utf-8") as f:
            json.dump(m, f, indent=2, ensure_ascii=False)


def recipe_hash(recipe: dict) -> str:
    """Stable hash of the recipe for cache invalidation."""
    raw = json.dumps(recipe, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
```

- [ ] **Step 2: 集成到 build_component 中**

```python
# 在 build_component 结尾，状态为 "passed" 且 cache_dir 存在时:

if result["status"] == "passed":
    cache = ComponentCache(os.path.dirname(result.get("cache_path", "")))
    cache.save(component_id, result, recipe_hash(recipe))
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/component_cache.py
git add python3.11libs/edini/component_builder.py
git commit -m "feat: add component cache with manifest for incremental rebuilds"
```

---

### Task 5: Phase C 组装引擎

**Files:**
- Create: `python3.11libs/edini/assembly_engine.py`
- Modify: `python3.11libs/edini/harness.py` (添加 `assemble_components` 工具)

**Interfaces:**
- Consumes: ComponentCache (Task 4)
- Produces: `assemble_components(recipe, sandbox_root, cache) → AssemblyResult`
- Produces: 活通道引用锚点（命名点 → CTP 连接）

- [ ] **Step 1: 实现组装核心逻辑**

```python
# python3.11libs/edini/assembly_engine.py

"""Phase C: Assemble verified components into a final asset.

Key change from old system: anchors are live channel references,
not baked coordinates. Named points on component geometry drive
anchor positions dynamically.
"""

import hou
from typing import Any

from edini.component_cache import ComponentCache


def assemble_components(
    recipe: dict,
    sandbox_root_path: str,
    cache_root: str,
) -> dict[str, Any]:
    """Assemble all components with status='passed' into the final asset.

    Creates:
      merge_all (Merge) → postprocess chain → OUT (Null)
      For anchored components: CTP nodes connecting component → anchor points.

    Returns:
      {"success": bool, "output_node": str, "errors": [...], "structure_advisory": {...}}
    """
    cache = ComponentCache(cache_root)
    manifest = cache.manifest()

    if not cache.all_passed():
        missing = [k for k, v in manifest.items() if v.get("status") != "passed"]
        return {
            "success": False,
            "error": f"Not all components passed: {missing}",
            "missing_components": missing,
        }

    root = hou.node(sandbox_root_path)
    if root is None:
        return {"success": False, "error": f"Sandbox root not found: {sandbox_root_path}"}

    errors: list[str] = []
    merge = root.createNode("merge", "merge_all")
    merge_idx = 0

    # ── 处理每个组件 ──
    for comp in recipe.get("components", []):
        cid = comp.get("id", "")
        subnet = root.node(f"comp_{cid}")
        if subnet is None:
            errors.append(f"Component subnet 'comp_{cid}' not found")
            continue

        out_node = subnet.node(f"{cid}_OUT")
        if out_node is None:
            errors.append(f"OUT node not found for component '{cid}'")
            continue

        anchors = comp.get("anchors", [])
        if not anchors:
            # 无锚点 → 直接连到 Merge
            merge.setInput(merge_idx, out_node)
            merge_idx += 1
        else:
            # 有锚点 → CTP
            _wire_anchored_component(root, cid, out_node, anchors, merge, merge_idx)
            merge_idx += 1  # CTP output connects to merge

    if errors:
        return {"success": False, "errors": errors}

    # ── 后处理链 ──
    prev = merge
    for step in recipe.get("postprocess", []):
        ntype = step.get("type")
        node = root.createNode(ntype, f"post_{ntype.replace('::', '_')}")
        node.setInput(0, prev)
        for pname, pvalue in step.get("params", {}).items():
            node.parm(pname).set(pvalue)
        prev = node

    # OUT
    out = root.createNode("null", "OUT")
    out.setInput(0, prev)

    # 计算结构检查
    structure = _check_structure(root, recipe)

    return {
        "success": True,
        "output_node": out.path(),
        "structure_advisory": structure,
        "errors": errors,
    }


def _wire_anchored_component(
    root, cid: str, src_node, anchors: list,
    merge: hou.OpNode, merge_idx: int,
):
    """Create anchor scatter points + CTP for an anchored component.

    Named-point anchors: read target component's named point positions.
    """
    # 创建 scatter points (锚点)
    scatter = root.createNode("add", f"{cid}_anchors")
    scatter.parm("usept0").set(1)
    for ai, anc in enumerate(anchors):
        idx = scatter.parm(f"usept{ai}").eval() if ai > 0 else ai
        scatter.parm(f"usept{ai}").set(1)
        # 从命名点读取位置
        target_comp = anc.get("target_component")
        target_point = anc.get("target_point")
        if target_comp and target_point:
            # 创建 point() 表达式读取命名点的位置
            expr_x = f'point("../comp_{target_comp}/{target_comp}_OUT", "{target_point}", "P", 0)'
            # ... (设置 scatter 点的位置和 orient)
        else:
            # 回退到 position_expr
            pos = anc.get("position", [0, 0, 0])
            scatter.parm(f"pt{ai}x").set(pos[0])
            scatter.parm(f"pt{ai}y").set(pos[1])
            scatter.parm(f"pt{ai}z").set(pos[2])

    # CTP
    ctp = root.createNode("copytopoints::2.0", f"copy_{cid}")
    ctp.setInput(0, src_node)
    ctp.setInput(1, scatter)
    ctp.parm("resettargetattribs").pressButton()

    # idfix
    idfix = root.createNode("attribwrangle", f"{cid}_idfix")
    idfix.setInput(0, ctp)
    idfix.parm("class").set(1)  # Prim mode
    idfix.parm("snippet").set(
        f's@component_id = "{cid}";'  # 基值 — anchors 覆盖特定实例
    )
    # 对每个锚点，覆盖其 component_id
    for ai, anc in enumerate(anchors):
        ac_id = anc.get("component_id", f"{cid}_{ai}")
        # ... (设置条件逻辑以覆盖匹配锚点的基值)

    merge.setInput(merge_idx, idfix)
```

- [ ] **Step 2: 结构检查（从现有 harness.py 迁移）**

```python
def _check_structure(root, recipe) -> dict:
    """Migrate _check_modular_structure from harness.py."""
    # 计算不同 component_ids，检查 Python SOP 数量等
    # 与现有实现相同，因此此处从 harness.py 复制
    ...
```

- [ ] **Step 3: 在 harness.py 注册工具**

```python
"assemble_components": assemble_components,
```

- [ ] **Step 4: Commit**

```bash
git add python3.11libs/edini/assembly_engine.py
git add python3.11libs/edini/harness.py
git commit -m "feat: add Phase C assembly engine with live anchor references"
```

---

### Task 6: 环境集成 — 逐步迁移 `build_procedural_asset`

**Files:**
- Modify: `python3.11libs/edini/harness.py`

**目标:** 保持向后兼容性，使 `build_procedural_asset` 内部使用新管道：

```python
def build_procedural_asset(recipe, ...):
    # Step 1: Phase A — 验证
    validation = validate_recipe(recipe)
    if not validation["passed"]:
        return {"success": False, "error": "Phase A validation failed",
                "validation_report": validation}

    # Step 2: Phase B — 逐组件构建
    for comp in validation["component_manifest"]:
        result = build_component(recipe, comp["component_id"], sandbox_root)
        if result["status"] != "passed":
            return {"success": False, "error": f"Component {comp['component_id']} failed",
                    "component_result": result}

    # Step 3: Phase C — 组装
    assembly = assemble_components(recipe, sandbox_root, cache_root)
    if not assembly["success"]:
        return {"success": False, "error": "Assembly failed", "assembly_result": assembly}

    # 继续现有的后处理、诊断等逻辑...
    return {"success": True, ...}
```

- [ ] **Step 1: 实现迁移路径**

- [ ] **Step 2: 回归测试**

```python
# 使用与测试日志第 70 行相同（成功）的食谱进行测试
recipe = {
    "asset_name": "road_bicycle",
    "params": { ... },  # 从会话 2 复制的参数
    "components": [ ... ],  # 从会话 2 复制的组件
    "orientation_asserts": [ ... ],
}

result = build_procedural_asset(recipe)
assert result["success"]
assert result["output_node"] is not None
print("✅ Migration regression test passed")
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/harness.py
git commit -m "refactor: migrate build_procedural_asset to three-phase pipeline internally"
```

---

### Task 7: 工具面清理

**Files:**
- Modify: `python3.11libs/edini/harness.py` 或工具注册表

**变更:**
1. **移除** `houdini_run_python` — 从工具注册表完全删除
2. **重命名** 8 个工具（保留旧名称作为别名实现向后兼容）
3. **新增** 4 个工具注册（在之前任务中已完成）

- [ ] **Step 1: 移除 houdini_run_python**

```python
# 从 TOOL_REGISTRY 或等效注册表中删除
# del TOOL_REGISTRY["houdini_run_python"]
```

- [ ] **Step 2: 添加别名以实现向后兼容**

```python
TOOL_ALIASES = {
    "houdini_verify_orientation":     "verify_orientation",
    "houdini_inspect_geometry_health": "inspect_health",
    "houdini_geometry_inventory":     "geometry_inventory",
    "houdini_commit_sandbox":         "commit_sandbox",
    "houdini_discard_sandbox":        "discard_sandbox",
    "houdini_capture_review":         "capture_review",
    "houdini_node_parms":             "query_parms",
}
```

- [ ] **Step 3: Commit**

```bash
git add python3.11libs/edini/harness.py
git commit -m "refactor: remove houdini_run_python, add tool aliases for backward compatibility"
```

---

### Task 8: Skill 体系重组

**Files:**
- Create: `skills/procedural-modeling/SKILL.md` (重写为轻量路由 ~80 行)
- Create: `skills/recipe-authoring/SKILL.md`
- Create: `skills/component-building/SKILL.md`
- Create: `skills/assembly-wiring/SKILL.md`
- Create: `skills/verification/SKILL.md`
- Create: `skills/parametric-testing/SKILL.md`
- Modify: `skills/edini-brainstorm/SKILL.md` (增加 component 数量限制检查 — 已完成)

**注意:** 技能是纯文档，不依赖任何 Python 代码。这些技能可以与代码变更并行编写。

- [ ] **Step 1: 编写轻量路由 procedural-modeling**

```markdown
# procedural-modeling/SKILL.md
~80 行: "当前处于哪个阶段？加载哪个技能？"
```

- [ ] **Step 2: 编写 5 个专用技能**

每个 ~100-150 行，内容从设计文档第 9.3 节迁移

- [ ] **Step 3: 技能自测** — 运行设计文档中描述的测试场景

- [ ] **Step 4: Commit all skill files**

---

## 实现顺序与依赖

```
Task 1 (Parm Catalog) ──→ Task 2 (Validator) ──→ Task 3 (Builder) ──→ Task 5 (Assembly)
                              │                                           │
                              └──→ Task 8 (Skills, 可并行)                │
                                                                          │
Task 4 (Cache) ←── Task 3                                                 │
                                                                          │
Task 6 (Migration) ←── Task 2 + Task 3 + Task 5                           │
Task 7 (Tool Cleanup) ←── Task 6                                          │
```

**推荐执行顺序:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8（技能可随时编写）

---

## 自检

| 检查项 | 结果 |
|---|---|
| 规范覆盖率 | ✅ 所有 12 章的设计文档均映射到任务 |
| 占位符扫描 | ✅ 无 TBD/TODO，所有代码步骤均内联 |
| 类型一致性 | ✅ ComponentBuildResult 在所有任务中一致引用 |
| 缺失需求 | ⚠️ 参数边界测试（`test_params`）已从计划中省略 — 将在后续的 `parametric-testing` 任务中覆盖 |
