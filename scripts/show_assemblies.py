"""Build the four verified assemblies (car / bicycle / keyboard / stairs) in
real Houdini, save a .hip you can open, and print a geometry report to verify
the results match your expectations.

Run with hython:
    D:/houdini/bin/hython.exe scripts/show_assemblies.py
or:
    python scripts/show_assemblies.py            # uses EDINI_HYTHON or auto-detect

Output:
  - <repo>/edini_showcase.hip   open this in the Houdini GUI to look around
  - a printed report: every leaf's measured position + size, the whole-model
    bounding box, point/prim counts — so you can eyeball correctness.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "python3.11libs"))

import hou
from edini.assembly_builder import build_assembly

# Each example builds under its own /obj container so all three coexist in one
# .hip. The containers are offset in X so they don't overlap when you open it.
EXAMPLES = [
    ("car_showcase", -9.0, {
        "id": "car",
        "params": {"length": 4.0, "width": 2.0, "thickness": 0.5,
                   "wheel_radius": 0.4, "wheel_tube_r": 0.08},
        "root": {"shape": {"type": "box", "params": {
            "size": ["length", "thickness", "width"]}}},
        "mounts": [
            {"id": "wheel_" + c, "position": {"measure": "bbox_corner",
                "from": "root", "axes": axes},
             "orient": {"from": "root", "align_axis": "+Y",
                "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
                "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}}}
            for c, axes in [("fr", "+X-Y+Z"), ("fl", "+X-Y-Z"),
                            ("br", "-X-Y+Z"), ("bl", "-X-Y-Z")]
        ],
        "leaves": [
            {"id": "wheel_" + c, "mount": "wheel_" + c, "scale": "wheel_radius",
             "shape": {"type": "torus", "params": {
                 "radx": 1.0, "rady": "wheel_tube_r", "rows": 24, "cols": 12}}}
            for c in ("fr", "fl", "br", "bl")
        ],
    }),
    ("bicycle_showcase", -3.0, {
        # Exercises ALL FOUR leaf-align fixes: align_axis +Y (torus disc stands
        # on its axle), origin normalization (wheel pushed clear of platform),
        # grouped CTP (4 identical wheels → 1 shape + 1 CTP), orient point-class.
        "id": "bicycle",
        "params": {"length": 4.0, "width": 2.0, "thickness": 0.5,
                   "wheel_radius": 0.4, "wheel_tube_r": 0.08,
                   "wheel_clearance": 0.1},
        "root": {"shape": {"type": "box", "params": {
            "size": ["length", "thickness", "width"]}}},
        "mounts": [
            {"id": "wheel_" + c, "position": {"measure": "bbox_corner",
                "from": "root", "axes": axes},
             "orient": {"from": "root", "align_axis": "+Y",
                "from_a": {"measure": "bbox_corner", "axes": "-X-Y+Z"},
                "from_b": {"measure": "bbox_corner", "axes": "+X-Y+Z"}}}
            for c, axes in [("fr", "+X-Y+Z"), ("fl", "+X-Y-Z"),
                            ("br", "-X-Y+Z"), ("bl", "-X-Y-Z")]
        ],
        "leaves": [
            {"id": "wheel_" + c, "mount": "wheel_" + c, "scale": "wheel_radius",
             "origin": {"anchor": "bbox_center", "offset": [0, 0, "wheel_clearance"]},
             "shape": {"type": "torus", "params": {
                 "radx": 1.0, "rady": "wheel_tube_r", "rows": 24, "cols": 12}}}
            for c in ("fr", "fl", "br", "bl")
        ],
    }),
    ("keyboard_showcase", 3.0, {
        # A REAL 60% keyboard via `cells`: keys of different sizes (a 6.25u
        # spacebar + 1u/1.25u/1.5u/2u keys) with staggered rows — the strategy
        # grid_on_face cannot express (uniform cells only). Each cell carries
        # its own size via per-point v@scale; one CTP stamps them all. The unit
        # is DERIVED from the tray's span, so the layout FILLS the tray and
        # rescales when tray_width changes (measurement-driven placement).
        "id": "keyboard",
        "params": {"tray_width": 16.0, "tray_depth": 6.0, "tray_thick": 0.4,
                   "key_height": 0.4},
        "root": {"shape": {"type": "box", "params": {
            "size": ["tray_width", "tray_thick", "tray_depth"]}}},
        "mounts": [
            {"id": "keys", "position": {"measure": "cells",
                "from": "root", "face": "+Y", "margin": 0.5, "gap": 0.04,
                "square": True,        # keys stay square (unit=min), like a real keyboard
                "cells": [
                    # Row 0 (number row): 15 1u keys across.
                    *[{"gx": c, "gz": 0, "w": 1, "d": 1} for c in range(15)],
                    # Row 1 (QWERTY): Tab 1.5u + 13 1u keys + \ 1.5u (staggered).
                    {"gx": 0, "gz": 1, "w": 1.5, "d": 1},
                    *[{"gx": 1.5 + c, "gz": 1, "w": 1, "d": 1} for c in range(13)],
                    {"gx": 14.5, "gz": 1, "w": 1.5, "d": 1},
                    # Row 2 (ASDF): Caps 1.75u + 12 1u keys + Enter 2.25u.
                    {"gx": 0, "gz": 2, "w": 1.75, "d": 1},
                    *[{"gx": 1.75 + c, "gz": 2, "w": 1, "d": 1} for c in range(12)],
                    {"gx": 13.75, "gz": 2, "w": 2.25, "d": 1},
                    # Row 3 (ZXCV): Shift 2.25u + 11 1u keys + Shift 2.75u.
                    {"gx": 0, "gz": 3, "w": 2.25, "d": 1},
                    *[{"gx": 2.25 + c, "gz": 3, "w": 1, "d": 1} for c in range(11)],
                    {"gx": 13.25, "gz": 3, "w": 2.75, "d": 1},
                    # Row 4 (bottom): Ctrl/Alt/Win/Space/Alt/Win/Menu/Ctrl.
                    {"gx": 0, "gz": 4, "w": 1.25, "d": 1},
                    {"gx": 1.25, "gz": 4, "w": 1.25, "d": 1},
                    {"gx": 2.5, "gz": 4, "w": 1.25, "d": 1},
                    {"gx": 3.75, "gz": 4, "w": 6.25, "d": 1},   # spacebar
                    {"gx": 10.0, "gz": 4, "w": 1.25, "d": 1},
                    {"gx": 11.25, "gz": 4, "w": 1.25, "d": 1},
                    {"gx": 12.5, "gz": 4, "w": 1.25, "d": 1},
                    {"gx": 13.75, "gz": 4, "w": 1.25, "d": 1},
                ]}},
        ],
        # The leaf is a 1u BASIS box; the per-cell v@scale (physical w*unit_x,
        # d*unit_z, where unit is derived from the tray) grows it to each cell's
        # footprint. Height is the leaf's own property (key_height).
        "leaves": [
            {"id": "key", "mount": "keys",
             "shape": {"type": "box", "params": {
                 "size": [1, "key_height", 1]}}},
        ],
    }),
    ("stairs_showcase", 9.0, {
        "id": "stairs",
        "params": {"base_w": 3.0, "base_h": 0.2, "base_d": 1.0,
                   "tread_w": 0.6, "tread_h": 0.05, "tread_d": 0.25,
                   "rise": 0.3, "run": 0.5},
        "root": {"shape": {"type": "box", "params": {
            "size": ["base_w", "base_h", "base_d"]}}},
        "mounts": [
            {"id": "treads", "position": {"measure": "array", "from": "root",
                "origin": {"measure": "bbox_face_center", "face": "+Y"},
                "count": [3, 1, 1],
                "step": [["run", "rise", 0], [0, 0, 0], [0, 0, 0]]}},
        ],
        "leaves": [
            {"id": "tread", "mount": "treads", "shape": {"type": "box",
                "params": {"size": ["tread_w", "tread_h", "tread_d"]}}},
        ],
    }),
]


def _geo_summary(node):
    """Point/prim counts + bounding box of a node's cooked geometry."""
    geo = node.geometry()
    pts = geo.intrinsicValue("pointcount")
    prims = geo.intrinsicValue("primitivecount")
    b = geo.intrinsicValue("bounds")  # xmin,xmax,ymin,ymax,zmin,zmax
    return pts, prims, b


def _fmt_pos(p):
    return f"({p[0]:+.3f}, {p[1]:+.3f}, {p[2]:+.3f})"


def _first_mount_pts(root, res):
    """Read the first mount wrangle's cooked points (the live placement cloud)."""
    mids = res.get("mount_ids") or []
    if not mids:
        return []
    mw = hou.node(f"{root.path()}/mount_{mids[0]}")
    if mw is None:
        return []
    try:
        mw.cook(force=True)
        return [list(p.position()) for p in mw.geometry().points()]
    except Exception:
        return []


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    hip_path = os.path.join(repo_root, "edini_showcase.hip")
    obj = hou.node("/obj")

    print("=" * 72)
    print("Building 4 assemblies in real Houdini " + hou.applicationVersionString())
    print("=" * 72)

    for name, x_offset, assembly in EXAMPLES:
        print(f"\n### {name}  (offset X by {x_offset} so models don't overlap)")
        root = obj.createNode("geo", name)
        # Move the whole container so the three models sit side by side.
        root.parmTuple("t").set((x_offset, 0.0, 0.0))

        res = build_assembly(assembly, root.path())
        if not res["success"]:
            print(f"  BUILD FAILED: {res.get('error')}")
            continue

        # Report the LIVE structure: each mount wrangle's cooked points (the
        # placement cloud), which is read LIVE from the root bbox on every cook.
        for mid in res.get("mount_ids", []):
            mw = hou.node(f"{root.path()}/mount_{mid}")
            mw.cook(force=True)
            pts = [list(p.position()) for p in mw.geometry().points()]
            if len(pts) <= 8:
                shown = pts
            else:
                shown = [pts[0], pts[-1], pts[len(pts) // 2]]  # 3 corners
            print(f"  mount '{mid}': {len(pts)} point(s) [live from root bbox]")
            for p in shown:
                print(f"      {_fmt_pos(p)}")
            if len(pts) > 8:
                print(f"      (... + {len(pts) - len(shown)} more grid points)")

        # LIVE demonstration: change a root param, recook (NO rebuild), show the
        # mount points moved automatically — the whole point of M2.
        live_param, new_val, label = {
            "car_showcase": ("length", 8.0, "length 4→8"),
            "bicycle_showcase": ("length", 8.0, "length 4→8"),
            "keyboard_showcase": ("tray_width", 24.0, "tray_width 16→24 (keys relay to fill)"),
            "stairs_showcase": ("base_w", 5.0, "base_w 3→5"),
        }[name]
        before = _first_mount_pts(root, res)
        try:
            root.parm(live_param).set(new_val)
        except Exception:
            pass
        after = _first_mount_pts(root, res)
        if before and after:
            moved = abs(before[0][0] - after[0][0]) > 1e-4 or abs(before[0][1] - after[0][1]) > 1e-4
            print(f"  LIVE: changed {label}, recooked (no rebuild) → "
                  f"first mount point {_fmt_pos(before[0])} → {_fmt_pos(after[0])} "
                  f"{'[MOVED live]' if moved else '[unchanged]'}")

        # Cooked-geometry sanity: total point/prim counts + bounding box.
        out = hou.node(root.path() + "/OUT")
        pts, prims, b = _geo_summary(out)
        print(f"  cooked OUT: {pts} points, {prims} prims")
        print(f"  bbox: x[{b[0]:+.2f}..{b[1]:+.2f}] "
              f"y[{b[2]:+.2f}..{b[3]:+.2f}] z[{b[4]:+.2f}..{b[5]:+.2f}]")

    hou.hipFile.save(hip_path)
    print("\n" + "=" * 72)
    print(f"Saved: {hip_path}")
    print("Open it in the Houdini GUI (File > Open) to look around.")
    print("=" * 72)


if __name__ == "__main__":
    main()
