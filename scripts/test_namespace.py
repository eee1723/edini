"""Test: resolve preferred namespace for node creation in Houdini.

Usage in Houdini Python Shell:
    exec(open(r"E:\edini\scripts\test_namespace.py").read())

Change NODE_TYPE below to test a different node.
"""
import hou

NODE_TYPE = "copytopoints"
PARENT = "/obj"

print(f"Testing: {NODE_TYPE}")

# ── Step 1: Try bare createNode ──
print(f"\n1. createNode('{NODE_TYPE}') ...")
try:
    node_bare = hou.node(PARENT).createNode(NODE_TYPE, node_name="test_bare")
    print(f"   OK → {node_bare.path()} (type: {node_bare.type().name()})")
    bare_ok = True
except hou.OperationFailed as e:
    print(f"   FAILED: {e}")
    bare_ok = False
    node_bare = None

# ── Step 2: Find NodeType and namespaceOrder ──
print(f"\n2. Looking up NodeType for '{NODE_TYPE}' ...")
qualified_name = None
for cat_name, cat in [
    ("SOP", hou.sopNodeTypeCategory()),
    ("OBJ", hou.objNodeTypeCategory()),
    ("DOP", hou.dopNodeTypeCategory()),
    ("VOP", hou.vopNodeTypeCategory()),
    ("SHOP", hou.shopNodeTypeCategory()),
    ("ROP", hou.ropNodeTypeCategory()),
]:
    nt = hou.nodeType(cat, NODE_TYPE)
    if nt is not None:
        namespaces = nt.namespaceOrder()
        print(f"   Found in {cat_name}, namespaceOrder: {namespaces}")
        if namespaces:
            qualified_name = namespaces[0]
        break
else:
    # Not found as bare name — try scanning all SOP types for partial match
    print(f"   Not found as bare type. Scanning SOP types...")
    for nt in hou.nodeType(cat).installedNodeTypes().values():
        name = nt.name()
        if NODE_TYPE in name:
            namespaces = nt.namespaceOrder()
            print(f"   Match: {name}, namespaceOrder: {namespaces}")
            if namespaces:
                qualified_name = namespaces[0]
                break

if not qualified_name:
    # Fallback: try common namespace patterns
    for suffix in ["::2.0", "::1.0", "::3.0"]:
        candidate = NODE_TYPE + suffix
        try:
            test = hou.node(PARENT).createNode(candidate, node_name="_test")
            test.destroy()
            qualified_name = candidate
            print(f"   Fallback: '{candidate}' works")
            break
        except hou.OperationFailed:
            continue

if not qualified_name:
    print("   ⚠ Could not resolve any valid qualified name.")
else:
    print(f"   → Resolved: '{qualified_name}'")

# ── Step 3: Create with qualified name ──
if qualified_name:
    print(f"\n3. createNode('{qualified_name}') ...")
    node_qualified = hou.node(PARENT).createNode(
        qualified_name, node_name="test_qualified")
    print(f"   OK → {node_qualified.path()} (type: {node_qualified.type().name()})")

    # ── Step 4: Compare if bare also worked ──
    if bare_ok and node_bare:
        print(f"\n4. Parameter comparison:")
        p_bare = {p.name(): p.eval() for p in node_bare.parms()}
        p_qual = {p.name(): p.eval() for p in node_qualified.parms()}
        all_keys = sorted(set(p_bare.keys()) | set(p_qual.keys()))
        diffs = 0
        for k in all_keys:
            v1 = p_bare.get(k)
            v2 = p_qual.get(k)
            if v1 != v2:
                diffs += 1
                print(f"   {k}:  bare={v1!r}  →  qualified={v2!r}")
        if diffs == 0:
            print("   (all parameters identical)")
        else:
            print(f"   Total {diffs} parameter(s) differ")
        node_bare.destroy()

    node_qualified.destroy()

print("\nDone.")
