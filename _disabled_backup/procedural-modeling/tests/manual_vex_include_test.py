"""Manual test: verify VEX #include mechanism in Houdini 21 attribwrangle.

Usage (in Houdini Python Shell or via houdini_run_python):
    exec(open(r'Z:\EEE_Project\Edini\tests\manual_vex_include_test.py').read())
    run_test()

This script tests whether attribwrangle can #include custom .vfl files
from the vexlib directory. If #include works, the vexlib functions are
callable directly. If not, the fallback is "snippet inlining" — the skill
documentation embeds full function bodies for the LLM to copy.
"""

import tempfile
import os

VEXLIB_DIR = r"Z:\EEE_Project\Edini\skills\procedural-modeling\scripts\vexlib"

def run_test():
    """Run the include test in a temporary geo container."""
    import hou

    # Create a temp geo node
    parent = hou.node("/obj")
    geo = parent.createNode("geo", "vex_include_test", run_init_scripts=False)

    # ── Test 1: Direct #include with absolute path ──
    test1 = geo.createNode("attribwrangle", "test_abs_path")
    test1.parm("class").set(0)  # Detail mode

    vex_code_abs = f'#include "{VEXLIB_DIR}\\skeleton.vfl"\n'
    vex_code_abs += 'int pts[] = make_polyline(0, array({{0,0,0}},{{1,0,0}},{{1,1,0}}));\n'
    vex_code_abs += 'printf("make_polyline returned %d points\\n", len(pts));\n'
    test1.parm("snippet").set(vex_code_abs)

    print("=" * 60)
    print("Test 1: #include with absolute Windows path")
    print(f"  Code: {vex_code_abs.strip()}")
    try:
        test1.cook(force=True)
        errs = list(test1.errors() or [])
        warns = list(test1.warnings() or [])
        has_geo = test1.geometry() is not None
        if errs:
            print(f"  ❌ FAILED: {errs}")
        else:
            print(f"  ✅ PASSED: errors=0, has_geometry={has_geo}, warnings={warns}")
    except Exception as e:
        print(f"  ❌ CRASHED: {e}")

    # ── Test 2: #include with < > bracket syntax (HOUDINI_VEX_PATH) ──
    test2 = geo.createNode("attribwrangle", "test_bracket")
    test2.parm("class").set(0)

    vex_code_br = '#include <vexlib/skeleton.vfl>\n'
    vex_code_br += '#include <vexlib/sections.vfl>\n'
    vex_code_br += 'int prof[] = make_rect_section(0, 1.0, 2.0, "XY");\n'
    vex_code_br += 'printf("make_rect_section returned %d points\\n", len(prof));\n'
    test2.parm("snippet").set(vex_code_br)

    print("\n" + "=" * 60)
    print("Test 2: #include <vexlib/...> bracket syntax")
    print(f"  HOUDINI_VEX_PATH check: {'HOUDINI_VEX_PATH' in os.environ}")
    if 'HOUDINI_VEX_PATH' in os.environ:
        print(f"  HOUDINI_VEX_PATH = {os.environ['HOUDINI_VEX_PATH']}")
    print(f"  Code: {vex_code_br.strip()}")
    try:
        test2.cook(force=True)
        errs = list(test2.errors() or [])
        warns = list(test2.warnings() or [])
        has_geo = test2.geometry() is not None
        if errs:
            print(f"  ❌ FAILED: {errs}")
            # Check if it's an include failure specifically
            for e in errs:
                if "include" in e.lower() or "cannot" in e.lower():
                    print(f"  → Include failure detected: {e}")
        else:
            print(f"  ✅ PASSED: errors=0, has_geometry={has_geo}, warnings={warns}")
    except Exception as e:
        print(f"  ❌ CRASHED: {e}")

    # ── Test 3: Minimal inline (single function, no includes) ──
    print("\n" + "=" * 60)
    print("Test 3a: Minimal inline — single function body + call")
    minimal_code = (
        'int make_polyline(int geohandle; vector positions[])\n'
        '{\n'
        '    int result[] = array();\n'
        '    for (int i = 0; i < len(positions); i++)\n'
        '    {\n'
        '        int pt = addpoint(geohandle, positions[i]);\n'
        '        append(result, pt);\n'
        '    }\n'
        '    for (int i = 0; i < len(result) - 1; i++)\n'
        '    {\n'
        '        addprim(geohandle, "polyline", result[i], result[i+1]);\n'
        '    }\n'
        '    return result;\n'
        '}\n'
        '\n'
        'int pts[] = make_polyline(0, array({0,0,0},{1,0,0},{1,1,0}));\n'
        'printf("points: %d\\n", len(pts));\n'
    )

    test3a = geo.createNode("attribwrangle", "test_inline_min")
    test3a.parm("class").set(0)
    test3a.parm("snippet").set(minimal_code)
    try:
        test3a.cook(force=True)
        errs = list(test3a.errors() or [])
        warns = list(test3a.warnings() or [])
        has_geo = test3a.geometry() is not None
        npts = test3a.geometry().intrinsicValue("pointcount") if has_geo else -1
        if errs:
            print(f"  ❌ FAILED: {errs}")
        else:
            print(f"  ✅ PASSED: errors=0, point_count={npts}")
    except Exception as e:
        print(f"  ❌ CRASHED: {e}")

    # ── Test 3b: Inline full vexlib (with #include stripped) ──
    print("\n" + "=" * 60)
    print("Test 3b: Inline full vexlib (all 3 .vfl files concatenated)")
    skeleton_path = os.path.join(VEXLIB_DIR, "skeleton.vfl")
    sections_path = os.path.join(VEXLIB_DIR, "sections.vfl")
    attribs_path = os.path.join(VEXLIB_DIR, "attribs.vfl")

    def read_stripped(fp):
        """Read .vfl file, strip header comments, keep only code."""
        with open(fp, 'r') as f:
            return f.read()

    skel_code = read_stripped(skeleton_path)
    sect_code = read_stripped(sections_path)
    attr_code = read_stripped(attribs_path)

    inline_code = skel_code + "\n" + sect_code + "\n" + attr_code + "\n"
    inline_code += 'int path[] = make_stair_path(0, 4, 0.3, 0.18, {0,0,0}, {1,0,0});\n'
    inline_code += 'printf("make_stair_path returned %d points\\n", len(path));\n'

    test3b = geo.createNode("attribwrangle", "test_inline_full")
    test3b.parm("class").set(0)
    test3b.parm("snippet").set(inline_code)

    print(f"  Total VEX code: {len(inline_code)} bytes")
    try:
        test3b.cook(force=True)
        errs = list(test3b.errors() or [])
        warns = list(test3b.warnings() or [])
        has_geo = test3b.geometry() is not None
        npts = test3b.geometry().intrinsicValue("pointcount") if has_geo else -1
        if errs:
            print(f"  ❌ FAILED: {errs[:3]}")  # first 3 errors
        else:
            print(f"  ✅ PASSED: errors=0, point_count={npts}")
    except Exception as e:
        print(f"  ❌ CRASHED: {type(e).__name__}: {str(e)[:200]}")

    # ── Summary ──
    print("\n" + "=" * 60)
    print("SUMMARY")
    print(f"  VEXLIB_DIR: {VEXLIB_DIR}")
    print(f"  HOUDINI_VEX_PATH: {os.environ.get('HOUDINI_VEX_PATH', 'NOT SET')}")
    print(f"  If Test 1 ✅ and Test 2 ❌:")
    print(f"    → Set HOUDINI_VEX_PATH to include {os.path.dirname(VEXLIB_DIR)}")
    print(f"    → Then #include <vexlib/skeleton.vfl> should work")
    print(f"  If all #include tests ❌:")
    print(f"    → Use snippet inlining (Test 3 pattern) as fallback")
    print(f"    → Update SKILL.md to say 'copy the function bodies inline'")

    # Cleanup
    try:
        geo.destroy()
    except Exception:
        pass

    return "Done. Check output above."


# Always run when this file is loaded/exec'd (Houdini compat)
run_test()
