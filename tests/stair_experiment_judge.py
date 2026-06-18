"""
楼梯实验验收脚本。

在每个实验条件跑完后，调用此脚本采集 6 项量化指标。
设计为在 Houdini Python 环境（通过 houdini_run_python）中运行。

用法:
    # 在 houdini_run_python 里
    import sys; sys.path.insert(0, r"E:\\edini\\tests")
    from stair_experiment_judge import judge, to_csv_row, CSV_HEADER
    r = judge("/obj/edini_sandbox_xxx/OUT", condition="C", run=1, build_attempts=2)
    print(CSV_HEADER); print(to_csv_row(r))

指标:
    1. first_try_success   第1次构建是否出几何
    2. sealed              封闭性（一票否决）: nonmanifold=0 AND open_boundary=0
                           AND degenerate=0 AND orphan=0
    3. build_attempts      达到可用几何的构建次数
    4. code_lines          等价代码行数（手动填，judge 不采集）
    5. total_user_parms    用户可调参数数
    6. steps_present       12 个踏步组件存在数
"""
from __future__ import annotations

REQUIRED_PARMS = {"step_count", "tread_depth", "riser_height", "width"}
EXPECTED_STEP_COUNT = 12


def _get_health(node_path: str) -> dict:
    """调用 houdini_inspect_geometry_health。"""
    from edini.node_utils import inspect_geometry_health
    return inspect_geometry_health(node_path)


def _get_inventory(node_path: str) -> dict:
    """调用 houdini_geometry_inventory。"""
    from edini.node_utils import geometry_inventory
    return geometry_inventory(node_path)


def _list_parms(node_path: str) -> list[dict]:
    """列出节点所有参数（name + eval value）。"""
    import hou
    node = hou.node(node_path)
    if node is None:
        return []
    out = []
    for p in node.parms():
        try:
            out.append({"name": p.name(), "value": p.eval()})
        except Exception:
            out.append({"name": getattr(p, "name", lambda: "?")(), "value": None})
    return out


def _find_asset_root(out_path: str) -> str:
    """从 OUT 路径向上找 sandbox root（装参数的地方）。
    OUT = /obj/edini_sandbox_xxx/OUT → root = /obj/edini_sandbox_xxx
    """
    import hou
    node = hou.node(out_path)
    if node is None:
        return out_path
    parent = node.parent()
    while parent is not None:
        # sandbox root 通常是 obj 下的 GeometryContainer
        if parent.parent() is not None and parent.parent().path() == "/obj":
            return parent.path()
        parent = parent.parent()
    return out_path


def judge(
    node_path: str,
    condition: str,
    run: int,
    build_attempts: int = 1,
    code_lines: int | None = None,
    native_node_count: int | None = None,
) -> dict:
    """采集一个实验条件的全部指标。

    Args:
        node_path: OUT 节点路径
        condition: "0"|"A"|"B"|"C"|"D"
        run: 第几次运行（条件 C 跑 2 次）
        build_attempts: 达到可用几何的构建次数（1=一次成功）
        code_lines: 等价代码行数（手动统计后传入）
        native_node_count: 原生 SOP 节点数（手动统计后传入）

    Returns:
        包含全部指标的 dict。
    """
    result = {
        "condition": condition,
        "run": run,
        "node_path": node_path,
        "build_attempts": build_attempts,
        "code_lines": code_lines,
        "native_node_count": native_node_count,
    }

    # ── 指标 2: 封闭性（一票否决）──
    try:
        health = _get_health(node_path)
        summary = health.get("summary", {})
        nm = int(summary.get("nonmanifold_edges", -1))
        ob = int(summary.get("open_boundary_edges", -1))
        dp = int(summary.get("degenerate_prims", -1))
        op = int(summary.get("orphan_points", -1))
        oc = int(summary.get("open_curves", -1))
    except Exception as e:
        result["error"] = f"health check failed: {e}"
        nm = ob = dp = op = oc = -1

    sealed = (nm == 0 and ob == 0 and dp == 0 and op == 0 and oc == 0)
    result["nonmanifold_edges"] = nm
    result["open_boundary_edges"] = ob
    result["degenerate_prims"] = dp
    result["orphan_points"] = op
    result["open_curves"] = oc
    result["sealed"] = sealed

    # ── 指标 1 & 3: 成功率 & 重试 ──
    try:
        point_count = int(health.get("point_count", 0)) if isinstance(health, dict) else 0
    except Exception:
        point_count = 0
    result["has_geometry"] = point_count > 0
    result["point_count"] = point_count
    result["first_try_success"] = (build_attempts == 1 and point_count > 0)

    # ── 指标 5: 参数化程度 ──
    root_path = _find_asset_root(node_path)
    parms = _list_parms(root_path)
    parm_names = {p["name"] for p in parms}
    # 过滤掉 Houdini 内置参数（如 stdswitcher, execute 之类），只数用户参数
    builtin_prefixes = ("stdswitcher", "folder_", "execute", "reload",
                        "help", "cwd_", "dir_", "file_")
    user_parms = {n for n in parm_names
                  if not any(n.startswith(p) for p in builtin_prefixes)}
    result["required_parms_present"] = REQUIRED_PARMS.issubset(parm_names)
    result["missing_required_parms"] = sorted(REQUIRED_PARMS - parm_names)
    result["total_user_parms"] = len(user_parms)

    # ── 组件完整性（踏步数）──
    try:
        inv = _get_inventory(node_path)
        comps = {c.get("component_id"): c.get("prim_count", 0)
                 for c in inv.get("components", [])}
    except Exception as e:
        comps = {}
        result["inventory_error"] = str(e)

    expected_steps = {f"step_{i}" for i in range(EXPECTED_STEP_COUNT)}
    present_steps = {s for s in expected_steps if comps.get(s, 0) > 0}
    result["steps_present"] = len(present_steps)
    result["missing_steps"] = sorted(expected_steps - present_steps)
    result["total_prims"] = sum(comps.values())

    # ── 综合判定 ──
    result["overall_pass"] = bool(
        sealed
        and result["required_parms_present"]
        and result["steps_present"] == EXPECTED_STEP_COUNT
        and point_count > 0
    )
    return result


CSV_COLUMNS = [
    "condition", "run", "overall_pass", "sealed", "first_try_success",
    "build_attempts", "has_geometry", "point_count",
    "nonmanifold_edges", "open_boundary_edges", "degenerate_prims",
    "orphan_points", "open_curves",
    "required_parms_present", "total_user_parms", "missing_required_parms",
    "steps_present", "missing_steps", "total_prims",
    "code_lines", "native_node_count",
]
CSV_HEADER = ",".join(CSV_COLUMNS)


def to_csv_row(r: dict) -> str:
    """把 judge() 结果转成一行 CSV。list 用 ';' 连接。"""
    def fmt(v):
        if isinstance(v, list):
            return ";".join(str(x) for x in v) if v else "-"
        if v is None:
            return ""
        if isinstance(v, bool):
            return "1" if v else "0"
        return str(v)
    return ",".join(fmt(r.get(k, "")) for k in CSV_COLUMNS)


def judge_and_print(
    node_path: str,
    condition: str,
    run: int,
    build_attempts: int = 1,
    code_lines: int | None = None,
    native_node_count: int | None = None,
) -> dict:
    """便捷函数：采集 + 打印 CSV。"""
    r = judge(node_path, condition, run, build_attempts,
              code_lines, native_node_count)
    print("=" * 60)
    print(f"Condition {condition} (run {run}) — {node_path}")
    print("-" * 60)
    for k in CSV_COLUMNS:
        v = r.get(k, "")
        if isinstance(v, list):
            v = ";".join(str(x) for x in v) if v else "-"
        print(f"  {k:28s}: {v}")
    print("=" * 60)
    print("CSV:")
    print(CSV_HEADER)
    print(to_csv_row(r))
    return r
