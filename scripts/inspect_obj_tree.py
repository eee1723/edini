#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""inspect_obj_tree.py — 提取 /obj 下所有节点、连接、层级关系。

用途:对齐 recipe 提取思路。打印场景的节点树 + 连接图,并导出完整 JSON,
方便人和 agent 一起看清场景结构。

两种跑法
--------
1. Houdini Python Shell:把整段脚本 paste 进去(默认 root=/obj,无参数)
2. hython 命令行:
     hython scripts/inspect_obj_tree.py [--root /obj] [--params] [--out PATH]

输出
----
- 控制台:ASCII 树形视图 + 连接边列表 + 统计汇总
- JSON  :写到 hip 目录旁边的 obj_tree_dump.json(或 --out 指定)
"""
from __future__ import annotations

import json
import os
import sys

# ── hou 导入(必须在 Houdini 环境里跑)─────────────────────
try:
    import hou
except ImportError:
    sys.stderr.write("ERROR: 此脚本必须在 Houdini 环境运行(hython 或 Python Shell)。\n")
    raise


# ── 工具函数 ───────────────────────────────────────────────
def _safe(fn, *args, default=None):
    """容错调用:houdini 某些 API 在特定节点类型上会抛异常。"""
    try:
        return fn(*args)
    except Exception:
        return default


# Houdini 自动管理的参数(参考 recipe_library._is_auto_param)
_AUTO_PARM_PATTERNS = ("time", "frame", "*frame*", "*seed*", "*cache*", "display*")


def _is_auto_parm(name: str) -> bool:
    import fnmatch
    return any(fnmatch.fnmatch(name, p) for p in _AUTO_PARM_PATTERNS)


# ── 核心:递归提取 ─────────────────────────────────────────
def extract(node, depth: int = 0, collect_params: bool = False) -> dict:
    """递归提取一个节点及其所有子节点的结构信息。"""
    # 输入:谁连到我的第 i 个输入
    inputs = []
    for i, src in enumerate(node.inputs()):
        if src is not None:
            inputs.append({
                "index": i,
                "source_path": src.path(),
                "source_name": src.name(),
                "source_type": _safe(src.type().name, default="?"),
            })

    # 输出:我连到谁(outputConnections 能拿到下游节点的 input index)
    outputs = []
    for conn in _safe(node.outputConnections, default=[]) or []:
        downstream = _safe(conn.inputNode)
        if downstream is None:
            continue
        outputs.append({
            "target_path": downstream.path(),
            "target_name": downstream.name(),
            "target_input_index": _safe(conn.inputIndex, default=0),
        })

    children = _safe(node.children, default=[]) or []
    ntype = _safe(node.type)

    entry = {
        "name": node.name(),
        "path": node.path(),
        "type": _safe(ntype.name, default="?"),
        "category": _safe(lambda: ntype.category().name(), default="?"),
        "depth": depth,
        "comment": _safe(node.comment, default="") or "",
        "children_count": len(children),
        "has_children": len(children) > 0,
        "inputs": inputs,
        "outputs": outputs,
        "children": [],
    }

    # 可选:收集非自动参数(过滤 time/frame/seed/cache/display)
    if collect_params:
        params = []
        for p in _safe(node.parms, default=[]) or []:
            try:
                pname = p.name()
            except Exception:
                continue
            if _is_auto_parm(pname):
                continue
            params.append({"name": pname, "value": _safe(p.eval)})
        entry["params"] = params

    for c in children:
        entry["children"].append(extract(c, depth + 1, collect_params))
    return entry


# ── 打印:ASCII 树形 ───────────────────────────────────────
def _conn_summary(entry: dict) -> str:
    parts = []
    if entry["inputs"]:
        s = ", ".join(f"{i['source_name']}→[{i['index']}]" for i in entry["inputs"])
        parts.append(f"in:[{s}]")
    if entry["outputs"]:
        s = ", ".join(
            f"→{o['target_name']}[{o['target_input_index']}]" for o in entry["outputs"]
        )
        parts.append(f"out:[{s}]")
    return "  ".join(parts)


def print_tree(entry: dict, prefix: str = "", is_last: bool = True,
               lines: list = None) -> None:
    if lines is None:
        lines = []
    connector = "└─ " if is_last else "├─ "
    tag = f" [{entry['children_count']} children]" if entry["has_children"] else ""
    conn = _conn_summary(entry)
    conn_str = f"  {conn}" if conn else ""
    notes = f'  notes="{entry["comment"]}"' if entry["comment"] else ""
    lines.append(
        f"{prefix}{connector}{entry['name']} ({entry['type']}/{entry['category']})"
        f"{tag}{conn_str}{notes}"
    )
    extension = "   " if is_last else "│  "
    kids = entry["children"]
    for i, kid in enumerate(kids):
        print_tree(kid, prefix + extension, i == len(kids) - 1, lines)
    return lines


# ── 统计 + 连接边 ──────────────────────────────────────────
def compute_stats(tree: dict) -> dict:
    counts = {"nodes": 0, "containers": 0, "leaves": 0, "edges": 0, "max_depth": 0}

    def walk(e):
        counts["nodes"] += 1
        counts["edges"] += len(e["inputs"])
        if e["has_children"]:
            counts["containers"] += 1
        else:
            counts["leaves"] += 1
        counts["max_depth"] = max(counts["max_depth"], e["depth"])
        for c in e["children"]:
            walk(c)

    walk(tree)
    return counts


def collect_edges(tree: dict) -> list:
    """扁平化所有连接边(source → target,带 input index)。"""
    edges = []

    def walk(e):
        for i in e["inputs"]:
            edges.append(
                f'{i["source_name"]}({i["source_type"]}) --[{i["index"]}]--> '
                f'{e["name"]}({e["type"]})'
            )
        for c in e["children"]:
            walk(c)

    walk(tree)
    return edges


# ── 主流程 ─────────────────────────────────────────────────
def main(root: str = "/obj", collect_params: bool = False,
         out_path: str = None) -> dict:
    node = hou.node(root)
    if node is None:
        sys.stderr.write(f"ERROR: 节点不存在: {root}\n")
        return {}

    tree = extract(node, collect_params=collect_params)

    # 控制台:树形
    print("=" * 64)
    print(f"场景结构树  root={root}")
    print("=" * 64)
    lines = print_tree(tree)
    print("\n".join(lines))

    # 控制台:统计
    s = compute_stats(tree)
    print("\n" + "-" * 64)
    print(
        f"统计: {s['nodes']} 节点 | {s['containers']} 容器 | "
        f"{s['leaves']} 叶子 | {s['edges']} 连接边 | 最深 {s['max_depth']} 层"
    )

    # 控制台:连接边
    edges = collect_edges(tree)
    if edges:
        print("\n连接边(数据流 source → target):")
        for e in edges:
            print(f"  {e}")

    # JSON 导出
    if out_path is None:
        hip = _safe(hou.hipFile.path) or ""
        hip_dir = os.path.dirname(hip) if hip else os.getcwd()
        out_path = os.path.join(hip_dir, "obj_tree_dump.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[JSON 已导出] {out_path}")
    print("(把这个文件内容贴给 agent,或者贴上面的控制台树形输出即可)")
    return tree


def _run_from_entry() -> None:
    """paste / hython 通用入口。"""
    root = "/obj"
    collect_params = False
    out_path = None
    # 只在我们的参数出现时才解析,避免吞掉 Houdini 自己的 argv
    args = [a for a in sys.argv[1:] if a.startswith("--")]
    if args:
        import argparse
        p = argparse.ArgumentParser(description="Inspect /obj node tree")
        p.add_argument("--root", default="/obj", help="起始节点路径(默认 /obj)")
        p.add_argument("--params", action="store_true", help="同时收集非自动参数")
        p.add_argument("--out", default=None, help="JSON 输出路径")
        ns, _ = p.parse_known_args(args)
        root, collect_params, out_path = ns.root, ns.params, ns.out
    main(root, collect_params, out_path)


# paste 到 Python Shell 或 hython 运行都会走到这里
_run_from_entry()
