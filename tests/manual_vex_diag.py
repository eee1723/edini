"""Diagnose which .vfl #include fails in Houdini."""
import hou

geo = hou.node("/obj").createNode("geo", "vex_diag", run_init_scripts=False)
VEXLIB = r"Z:\EEE_Project\Edini\skills\procedural-modeling\scripts\vexlib"

# Test each .vfl individually
tests = [
    ("skeleton.vfl only",
     '#include "' + VEXLIB + '/skeleton.vfl"\n'
     'int p[] = make_polyline(0, array({0,0,0},{1,0,0}));'),
    ("sections.vfl only",
     '#include "' + VEXLIB + '/sections.vfl"\n'),
    ("attribs.vfl only",
     '#include "' + VEXLIB + '/attribs.vfl"\n'),
    ("skeleton + sections",
     '#include "' + VEXLIB + '/skeleton.vfl"\n'
     '#include "' + VEXLIB + '/sections.vfl"\n'
     'int p[] = make_rect_section(0, 1.0, 2.0, "XY");'),
    ("skeleton + attribs",
     '#include "' + VEXLIB + '/skeleton.vfl"\n'
     '#include "' + VEXLIB + '/attribs.vfl"\n'
     'int p[] = make_polyline(0, array({0,0,0},{1,0,0}));'
     'set_orient_from_tangent(0, p[0], {0,0,1}, {0,1,0});'),
    ("all three",
     '#include "' + VEXLIB + '/skeleton.vfl"\n'
     '#include "' + VEXLIB + '/sections.vfl"\n'
     '#include "' + VEXLIB + '/attribs.vfl"\n'
     'int path[] = make_polyline(0, array({0,0,0},{0,1,0},{1,2,0}));'
     'int prof[] = make_circle_section(0, 0.5, 8, "XY", {0,0,0});'),
]

for label, code in tests:
    w = geo.createNode("attribwrangle", label.replace(" ", "_"))
    w.parm("class").set(0)
    w.parm("snippet").set(code)
    try:
        w.cook(force=True)
        errs = list(w.errors() or [])
        if errs:
            print("FAIL: " + label + " -> " + str(errs[:2]))
        else:
            print("OK:   " + label)
    except Exception as e:
        print("CRASH:" + label + " -> " + str(e)[:200])

geo.destroy()
print("\nDone.")
