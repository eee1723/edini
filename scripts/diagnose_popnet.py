"""diagnose_popnet.py — 诊断 Pop_Force / popnet 的真实类型信息。

目的:搞清楚真实 Houdini 里,popnet 节点的 type().name() 到底返回什么,
从而确认 recipe_capture_tree 穿透 bug 的确切机制。

Houdini Python Shell 里 paste 运行。会打印每个关键节点的:
  - path / name
  - type().name()  ← 关键
  - type().category().name()
  - type().description()
  - children 数量 + 每个子节点的 type name

然后把控制台输出整段贴回给 agent。
"""
import hou


def _safe(fn, *args, default="?"):
    try:
        return fn(*args)
    except Exception as e:
        return f"<err: {e}>"


def describe(node, label=""):
    print(f"\n{'='*60}")
    print(f"{label}: {node.path()}")
    print(f"  name           = {node.name()}")
    print(f"  type().name()  = {_safe(lambda: node.type().name())}")
    print(f"  category       = {_safe(lambda: node.type().category().name())}")
    print(f"  description    = {_safe(lambda: node.type().description())}")
    kids = _safe(node.children, default=[]) or []
    print(f"  children_count = {len(kids)}")
    for c in kids[:8]:
        print(f"    - {c.name()}  type={_safe(lambda: c.type().name())}")


print("#" * 60)
print("# Pop_Force / popnet 诊断")
print("#" * 60)

# 1. 找 Pop_Force
candidates = []
for root_path in ("/obj/subnet1/sopnet1", "/obj/sopnet1", "/obj"):
    n = hou.node(root_path)
    if n is None:
        continue
    for c in n.allSubChildren():
        try:
            if c.name() == "Pop_Force":
                candidates.append(c)
        except Exception:
            pass

if not candidates:
    print("\n没找到 Pop_Force 节点。请确认场景里有没有。")
    print("改用所有名字含 'pop' 或 'Pop' 的节点:")
    for root_path in ("/obj/subnet1", "/obj"):
        n = hou.node(root_path)
        if n is None:
            continue
        for c in n.allSubChildren():
            try:
                nm = c.name().lower()
                if "pop" in nm:
                    candidates.append(c)
            except Exception:
                pass

for pf in candidates[:3]:
    describe(pf, "Pop_Force 候选")
    # 描述它的直接子节点里像网络容器的
    try:
        for c in pf.children():
            tn = _safe(lambda: c.type().name())
            if tn in ("popnet", "dopnet", "sopnet", "ropnet", "subnet", "geo"):
                describe(c, f"  └─ 网络容器子节点")
                # 再往下看一层
                try:
                    for cc in c.children()[:5]:
                        describe(cc, f"      └─ 内部子节点")
                except Exception:
                    pass
    except Exception as e:
        print(f"  遍历子节点出错: {e}")

print("\n" + "#" * 60)
print("# 关键问题:把上面每个节点的 type().name() 整段贴给 agent。")
print("# 特别关注 popnet 节点的 type().name() 是 'popnet' 还是 'subnet'。")
print("#" * 60)
