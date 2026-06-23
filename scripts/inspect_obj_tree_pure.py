#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""inspect_obj_tree_pure.py — 精简版:只显示用户搭建的真实节点,过滤 Houdini 内部噪声。

噪声 = 这些是节点类型自己 cook 出来的内部子节点,不是用户搭的:
  - curve::2.0 的 stashed_geo / output0 / groupdelete*
  - 任何 geo 节点里的 output/stashed
  - SOP 节点的内部 cooked children

判断:如果一个节点的父节点类型不是 subnet/geo(即父是 SOP 节点如 curve/sweep),
那它的子节点基本都是内部的,不显示。

Houdini Python Shell 里 paste 运行。
"""
from __future__ import annotations
import hou

# 用户视为"真实搭建"的容器类型(其子节点算用户搭的)
_CONTAINER_TYPES = {"subnet", "geo", "obj", "manager"}

# 直接忽略的节点类型(永远不当 recipe 节点)
_NOISE_TYPES = {"output", "stashed_geo", "subnetconnector", "null"}


def _is_real(node) -> bool:
    """这个节点是不是用户'真实搭建'的(非内部 cook 噪声)。"""
    try:
        t = node.type().name()
    except Exception:
        return False
    if t in _NOISE_TYPES:
        return False
    return True


def _is_container(node) -> bool:
    """是否为容器(其子节点值得展开看)。"""
    try:
        t = node.type().name()
    except Exception:
        return False
    # subnet / geo 在 Object 层是容器;在 Sop 层 subnet 也算
    try:
        cat = node.type().category().name()
    except Exception:
        cat = "?"
    return t in ("subnet", "geo") or cat in ("Object", "Manager")


def _input_list(node) -> list:
    out = []
    try:
        for i, src in enumerate(node.inputs()):
            if src is not None and _is_real(src):
                out.append(f"{src.name()}→[{i}]")
    except Exception:
        pass
    return out


def walk(node, prefix="", is_last=True, depth=0, max_depth=8):
    if depth > max_depth:
        return
    connector = "└─ " if is_last else "├─ "
    try:
        tname = node.type().name()
    except Exception:
        tname = "?"
    try:
        cat = node.type().category().name()
    except Exception:
        cat = "?"

    ins = _input_list(node)
    in_str = f"  in:[{', '.join(ins)}]" if ins else ""

    notes = ""
    try:
        c = (node.comment() or "").strip()
        if c:
            notes = f'  notes="{c[:60]}"'
    except Exception:
        pass

    star = " ★" if _is_container(node) else ""
    print(f"{prefix}{connector}{node.name()} ({tname}/{cat}){star}{in_str}{notes}")

    # 只展开容器;非容器(SOP)的子节点 = 内部 cook,跳过
    if _is_container(node):
        try:
            kids = [c for c in node.children() if _is_real(c)]
        except Exception:
            kids = []
        extension = "   " if is_last else "│  "
        for i, kid in enumerate(kids):
            walk(kid, prefix + extension, i == len(kids) - 1, depth + 1, max_depth)


root = hou.node("/obj")
print("=" * 70)
print("场景真实结构(已过滤 Houdini 内部 cook 噪声,★=容器)")
print("=" * 70)
for i, kid in enumerate(root.children()):
    walk(kid, "", i == len(root.children()) - 1)
print("=" * 70)
print("★ 标记的是容器(subnet/geo),其内部是用户搭建的真实节点网络。")
print("把上面这段输出整段粘给 agent。")
