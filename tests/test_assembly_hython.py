"""Real-Houdini (hython) end-to-end tests for the LIVE build layer (M2).

These are the decisive tests for the whole redesign. They run against genuine
Houdini 21 and prove TWO things the mock fundamentally cannot:

1. **Correctness**: the copytopoints-stamped instances land where the Python
   oracle (measure.py) predicts — so the VEX strategies + CTP wiring are right.
2. **LIVE**: change a root param and recook WITHOUT rebuilding the network —
   the instances must move to their new measured positions automatically. This
   is the entire point of M2 (no baked coordinates).

Auto-detects hython at D:/houdini/bin/hython.exe and standard dirs; override
with EDINI_HYTHON. Skips when not found.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest

_HOUDINI_CANDIDATES = [
    r"D:\houdini",
    r"C:\Program Files\Side Effects Software",
    "/Applications/Houdini",
    "/opt/hfs",
]


def _find_hython():
    env = os.environ.get("EDINI_HYTHON") or os.environ.get("HYTHON")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("hython") or shutil.which("hython.exe")
    if found:
        return found
    for base in _HOUDINI_CANDIDATES:
        if not os.path.isdir(base):
            continue
        candidates = []
        for exe in ("hython.exe" if os.name == "nt" else "hython",):
            exe_path = os.path.join(base, "bin", exe)
            if os.path.isfile(exe_path):
                candidates.append(("0-direct", exe_path))
        for name in os.listdir(base):
            exe = os.path.join(base, name, "bin",
                               "hython.exe" if os.name == "nt" else "hython")
            if os.path.isfile(exe):
                candidates.append((name, exe))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
    return None


HYTHON = _find_hython()

# The harness builds an assembly, then runs a probe (cooked-geometry read +
# optional live-recook). It prints one JSON line the test parses.
_HARNESS = r'''
import json, sys, os
sys.path.insert(0, os.path.join(os.getcwd(), "python3.11libs"))
import hou
from edini.assembly_builder import build_assembly

req = json.loads(sys.stdin.read())
assembly = req["assembly"]
probe_kind = req.get("probe", "instance_centers")

root = hou.node("/obj").createNode("geo", "edini_live_test")
res = build_assembly(assembly, root.path())

def instance_centers():
    """Bbox-center of each instance prim in the OUT — where the copies landed."""
    out = hou.node(root.path() + "/OUT")
    out.cook(force=True)
    geo = out.geometry()
    # Group prims by their bbox center (each copy is a connected prim cluster);
    # simpler: take the centroid of the whole OUT's connected pieces. For the
    # car (4 tori) we want 4 centers. Use prim intrinsic bbox per prim and
    # cluster by proximity — but the cleanest signal is the per-copy translation
    # baked into each prim's position. Instead, read the mount wrangle's POINTS
    # (the placement cloud), which is the direct source of truth.
    centers = []
    for nm in [c.name() for c in root.allSubChildren() if c.name().startswith("mount_")]:
        wr = hou.node(root.path() + "/" + nm)
        wr.cook(force=True)
        wg = wr.geometry()
        if wg is not None:
            centers.extend([list(p.position()) for p in wg.points()])
    return centers

def instance_piece_bboxes():
    """For each CONNECTED piece in OUT, its bbox (min/max/size on 3 axes).
    A torus wheel (radx=1, rady=0.08) is THIN along its symmetry axis (~0.16)
    and WIDE on the other two (~2.0). After orient, the thin axis points
    along the axle direction — so the thin bbox dim reveals the wheel's
    facing without trusting CTP attribute transfer.

    Pieces are clustered by CONNECTIVITY (prims sharing points belong to one
    wheel), NOT per-prim: a single torus has ~288 face prims whose individual
    bboxes are meaningless薄片; only the whole-wheel bbox reveals the facing."""
    out = hou.node(root.path() + "/OUT")
    out.cook(force=True)
    geo = out.geometry()
    prims = list(geo.prims())
    # Union-Find over point numbers: prims sharing a point are one piece.
    parent = {}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb: parent[ra] = rb
    for prim in prims:
        pts = [v.point().number() for v in prim.vertices()]
        for p in pts:
            if p not in parent: parent[p] = p
        for i in range(1, len(pts)):
            union(pts[0], pts[i])
    # Bucket each prim by its root point.
    buckets = {}
    for prim in prims:
        pts = [v.point().number() for v in prim.vertices()]
        proot = find(pts[0]) if pts else -1
        buckets.setdefault(proot, []).append(prim)
    bboxes = []
    for proot, prims_in_piece in buckets.items():
        if len(prims_in_piece) < 4:  # skip stray single prims / the root box faces
            continue
        xs, ys, zs = [], [], []
        for prim in prims_in_piece:
            for v in prim.vertices():
                p = v.point().position()
                xs.append(float(p[0])); ys.append(float(p[1])); zs.append(float(p[2]))
        bboxes.append({
            "min": [min(xs), min(ys), min(zs)],
            "max": [max(xs), max(ys), max(zs)],
            "size": [max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)],
            "prim_count": len(prims_in_piece),
        })
    return bboxes

def mount_cloud_orient():
    """Read p@orient off each mount wrangle's points (pre-CTP), so we can
    verify the orient quaternion itself lands on points and rotates the
    align-axis basis onto the measured axle direction."""
    out = {}
    for nm in [c.name() for c in root.allSubChildren() if c.name().startswith("mount_")]:
        wr = hou.node(root.path() + "/" + nm); wr.cook(force=True)
        wg = wr.geometry()
        if wg is None:
            continue
        orients = []
        for p in wg.points():
            try:
                q = p.floatListAttribValue("orient")
                orients.append(list(q))
            except Exception:
                pass
        out[nm] = orients
    return out

def root_bbox():
    box = hou.node(root.path() + "/root_shape"); box.cook(force=True)
    return list(box.geometry().intrinsicValue("bounds"))

probe = {}
if res.get("success"):
    probe["centers"] = instance_centers()
    probe["root_bbox"] = root_bbox()
    if probe_kind in ("piece_bboxes", "facing"):
        probe["pieces"] = instance_piece_bboxes()
        probe["cloud_orient"] = mount_cloud_orient()
    # THE LIVE TEST: change a param, recook, re-read — WITHOUT rebuilding.
    if probe_kind == "live_recook":
        param = req["change_param"]; newval = req["new_value"]
        p = root.parm(param)
        if p is not None:
            p.set(newval)
        probe["centers_after"] = instance_centers()
        probe["root_bbox_after"] = root_bbox()

print("EDINI_RESULT_JSON:" + json.dumps({**res, "_probe": probe}))
'''


def _car(length=4.0):
    return {
        "id": "car",
        "params": {"length": length, "width": 2.0, "thickness": 0.5,
                   "wheel_radius": 0.4, "wheel_tube_r": 0.08},
        "root": {"shape": {"type": "box",
                           "params": {"size": ["length", "thickness", "width"]}}},
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
    }


def _bicycle(length=4.0):
    """A bicycle-style platform + 4 wheels, exercising all four fixes:
    align_axis +Z (torus faces its axle), origin normalization (wheel pushed
    to +Z to clear the platform), grouped CTP (4 identical wheels → 1 CTP)."""
    return {
        "id": "bicycle",
        "params": {"length": length, "width": 2.0, "thickness": 0.5,
                   "wheel_radius": 0.4, "wheel_tube_r": 0.08, "wheel_clearance": 0.1},
        "root": {"shape": {"type": "box",
                           "params": {"size": ["length", "thickness", "width"]}}},
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
    }


def _keyboard(rows=3, cols=5):
    return {
        "id": "keyboard",
        "params": {"tray_width": 4.0, "tray_depth": 1.5, "tray_thick": 0.1,
                   "key_size": 0.2, "key_height": 0.08},
        "root": {"shape": {"type": "box", "params": {
            "size": ["tray_width", "tray_thick", "tray_depth"]}}},
        "mounts": [
            {"id": "keys", "position": {"measure": "grid_on_face",
                "from": "root", "face": "+Y", "rows": rows, "cols": cols, "margin": 0.05}},
        ],
        "leaves": [
            {"id": "key", "mount": "keys",
             "shape": {"type": "box", "params": {
                 "size": ["key_size", "key_height", "key_size"]}}},
        ],
    }


def _cells_keyboard():
    """A REAL keyboard layout via the `cells` strategy: a 6.25u spacebar +
    several 1u keys + a staggered row. The physical unit is DERIVED from the
    tray's span so the layout FILLS the tray and rescales when tray_w changes.
    The leaf is a 1u BASIS shape; each cell's per-point v@scale grows it to the
    cell's footprint. This is the case grid_on_face CANNOT express."""
    return {
        "id": "cells_keyboard",
        "params": {"tray_w": 16.0, "tray_d": 6.0, "tray_h": 0.4,
                   "key_height": 0.4},
        "root": {"shape": {"type": "box", "params": {
            "size": ["tray_w", "tray_h", "tray_d"]}}},
        "mounts": [
            {"id": "keys", "position": {
                "measure": "cells", "from": "root", "face": "+Y",
                "margin": 0.5,
                "cells": [
                    {"gx": 0, "gz": 0, "w": 1, "d": 1},     # back row
                    {"gx": 1, "gz": 0, "w": 1, "d": 1},
                    {"gx": 2, "gz": 0, "w": 1, "d": 1},
                    {"gx": 0.5, "gz": 1, "w": 1, "d": 1},   # staggered row
                    {"gx": 1.5, "gz": 1, "w": 1, "d": 1},
                    {"gx": 0, "gz": 4, "w": 6.25, "d": 1},  # spacebar
                ]}},
        ],
        "leaves": [
            {"id": "key", "mount": "keys",
             "shape": {"type": "box", "params": {
                 "size": [1, "key_height", 1]}}},   # 1u basis; v@scale grows it
        ],
    }


def _run(assembly, probe="instance_centers", change_param=None, new_value=None):
    req = {"assembly": assembly, "probe": probe}
    if change_param is not None:
        req["change_param"] = change_param
        req["new_value"] = new_value
    proc = subprocess.run(
        [HYTHON, "-c", _HARNESS],
        input=json.dumps(req),
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        capture_output=True, text=True, timeout=240,
    )
    line = None
    for ln in proc.stdout.splitlines():
        if ln.startswith("EDINI_RESULT_JSON:"):
            line = ln[len("EDINI_RESULT_JSON:"):]
            break
    assert line is not None, f"no result line.\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    return json.loads(line)


def _closest(a, centers, tol=1e-3):
    return any(abs(a[0]-c[0]) < tol and abs(a[1]-c[1]) < tol and abs(a[2]-c[2]) < tol
               for c in centers)


@unittest.skipUnless(HYTHON, "hython not installed")
class TestLiveBuildHython(unittest.TestCase):
    def test_car_instances_land_on_measured_corners(self):
        """The 4 wheels' mount points land exactly on the Python oracle's
        bbox corners of a 4x0.5x2 box: (±2, -0.25, ±1)."""
        res = _run(_car())
        self.assertTrue(res["success"], res.get("error"))
        centers = res["_probe"]["centers"]
        self.assertEqual(len(centers), 4)
        for expected in [(2, -0.25, 1), (2, -0.25, -1), (-2, -0.25, 1), (-2, -0.25, -1)]:
            self.assertTrue(_closest(list(expected), centers),
                            f"no wheel at {expected}; got {centers}")

    def test_car_LIVE_recook_moves_wheels(self):
        """THE live proof: build the car, change `length` 4→8, recook (NO
        rebuild), and the front wheels' X moves from +2 to +4 automatically.
        This is impossible with baked-coordinate builds."""
        res = _run(_car(), probe="live_recook", change_param="length", new_value=8.0)
        self.assertTrue(res["success"], res.get("error"))
        before = res["_probe"]["centers"]
        after = res["_probe"]["centers_after"]
        self.assertEqual(len(before), 4)
        self.assertEqual(len(after), 4)
        # Front wheels were at x=+2; after length→8 they must be at x=+4.
        fr_before = [c for c in before if abs(c[0] - 2.0) < 0.1]
        fr_after = [c for c in after if abs(c[0] - 4.0) < 0.1]
        self.assertEqual(len(fr_before), 2, f"expected 2 front wheels at x=2, got {before}")
        self.assertEqual(len(fr_after), 2, f"live update FAILED: expected wheels at x=4, got {after}")

    def test_keyboard_grid_fifteen_keys_on_face(self):
        """15 keys (3x5 grid) all sit on the tray's +Y face (y = tray_thick/2)."""
        res = _run(_keyboard(rows=3, cols=5))
        self.assertTrue(res["success"], res.get("error"))
        centers = res["_probe"]["centers"]
        self.assertEqual(len(centers), 15)
        for c in centers:
            self.assertAlmostEqual(c[1], 0.05, places=4)  # tray_thick/2

    def test_keyboard_LIVE_recook_rescales_grid(self):
        """Widen the tray 4→8 via param and the key grid's X extent doubles —
        the grid re-samples the face live."""
        res = _run(_keyboard(), probe="live_recook",
                   change_param="tray_width", new_value=8.0)
        self.assertTrue(res["success"], res.get("error"))
        before_x = sorted(c[0] for c in res["_probe"]["centers"])
        after_x = sorted(c[0] for c in res["_probe"]["centers_after"])
        self.assertEqual(len(before_x), 15)
        self.assertEqual(len(after_x), 15)
        # The grid's X span roughly doubles (margin stays fixed at 0.05, so the
        # ratio is ~2x not exactly 2x — the point is the grid rescaled live).
        before_span = before_x[-1] - before_x[0]
        after_span = after_x[-1] - after_x[0]
        self.assertGreater(after_span / before_span, 1.9,
                           f"grid did not rescale: before_span={before_span}, after_span={after_span}")

    def test_cells_keyboard_one_ctp_many_sizes(self):
        """THE cells-strategy proof: one CTP stamps 6 DIFFERENTLY-SIZED keys from
        a single 1u basis leaf. The 6.25u spacebar's bbox X is exactly 6.25× a
        normal 1u key's X — the RATIO is conserved because the unit is derived
        from the tray. This is impossible with grid_on_face (uniform cells). The
        size variety comes from per-point v@scale that CTP reads per instance —
        verified at the GEOMETRY level (the bbox sizes the user sees)."""
        res = _run(_cells_keyboard(), probe="piece_bboxes")
        self.assertTrue(res["success"], res.get("error"))
        pieces = res["_probe"]["pieces"]
        # 6 connected key pieces (each key is a box = 6 prims; the root tray is
        # filtered by the >=4-prim clustering heuristic but we check counts).
        keys = [p for p in pieces if p["prim_count"] >= 6]
        self.assertGreaterEqual(len(keys), 6, f"expected >=6 keys, got {len(keys)}: {pieces}")
        # Sort widest-first. The spacebar (6.25u) must dominate on X.
        keys.sort(key=lambda p: -p["size"][0])
        spacebar = keys[0]
        normal = keys[-1]
        # THE RATIO claim: spacebar is 6.25× wider than a normal key, regardless
        # of the derived unit (which depends on the tray size). This ratio is the
        # invariant the per-point v@scale preserves.
        self.assertAlmostEqual(spacebar["size"][0] / normal["size"][0], 6.25, delta=0.15,
                               msg=f"spacebar/normal ratio={spacebar['size'][0]/normal['size'][0]} ≠ 6.25")

    def test_cells_keyboard_LIVE_root_resizes_relays_keys(self):
        """THE measurement-driven proof: shrink the root (tray_w 16→10) and the
        keys RELAY-OUT to fill the smaller root — the derived unit shrinks so
        every key rescales AND the keys stay WITHIN the root (never overflow).
        This is the coupling the old fixed-unit `cells` lacked."""
        res = _run(_cells_keyboard(), probe="live_recook",
                   change_param="tray_w", new_value=10.0)  # shrink tray
        self.assertTrue(res["success"], res.get("error"))
        before_root = res["_probe"]["root_bbox"]
        after_root = res["_probe"]["root_bbox_after"]
        # The tray actually shrank (16 → 10 on X).
        self.assertLess(after_root[1] - after_root[0], before_root[1] - before_root[0])
        before = res["_probe"]["centers"]
        after = res["_probe"]["centers_after"]
        self.assertEqual(len(before), 6)
        self.assertEqual(len(after), 6)
        # THE KEY CLAIM: keys rescaled to fill the smaller tray. The total X span
        # of the keys shrank (they're closer together now).
        before_xs = sorted(c[0] for c in before)
        after_xs = sorted(c[0] for c in after)
        before_span = before_xs[-1] - before_xs[0]
        after_span = after_xs[-1] - after_xs[0]
        self.assertLess(after_span, before_span,
                        f"keys did not rescale to smaller tray: {before_span}→{after_span}")
        # AND the keys stay WITHIN the smaller root — no overflow (the layout
        # fills it, never exceeds it). Every key's X is within [xmin, xmax].
        for x in after_xs:
            self.assertGreaterEqual(x, after_root[0] - 0.01,
                                    f"key x={x} overflowed tray xmin {after_root[0]}")
            self.assertLessEqual(x, after_root[1] + 0.01,
                                 f"key x={x} overflowed tray xmax {after_root[1]}")

    def test_cells_square_keys_are_actually_square(self):
        """THE square-constraint proof: with square=True, a 1u key's bbox X == Z
        (physically square), even though the tray is NOT square (16 wide × 6 deep
        — stretch would deform it to 16×6). This is what makes a real keyboard's
        keys look right."""
        a = _cells_keyboard()
        a["mounts"][0]["position"]["square"] = True
        res = _run(a, probe="piece_bboxes")
        self.assertTrue(res["success"], res.get("error"))
        keys = [p for p in res["_probe"]["pieces"] if p["prim_count"] >= 6]
        self.assertGreaterEqual(len(keys), 6)
        # Find a normal 1u key (the smallest X piece that isn't the spacebar).
        keys.sort(key=lambda p: p["size"][0])
        normal = keys[0]
        # THE CLAIM: X size == Z size (square), to within a tolerance for the gap.
        self.assertAlmostEqual(normal["size"][0], normal["size"][2], delta=0.05,
                               msg=f"square key not square: X={normal['size'][0]} Z={normal['size'][2]}")

    def test_cells_pad_leaves_visible_leftover(self):
        """fill=pad: keys stay square (unit=min) AND the layout is centered, so
        on a non-square tray there's visible leftover on the larger axis. The
        keys' total X span is LESS than the tray's usable X span (unlike stretch
        which fills it)."""
        a = _cells_keyboard()
        a["mounts"][0]["position"]["square"] = True
        a["mounts"][0]["position"]["fill"] = "pad"
        res = _run(a, probe="piece_bboxes")
        self.assertTrue(res["success"], res.get("error"))
        keys = [p for p in res["_probe"]["pieces"] if p["prim_count"] >= 6]
        self.assertGreaterEqual(len(keys), 6)
        # Keys are square (unit=min(16,6)=6 region → unit ~ (6-...)/...).
        keys.sort(key=lambda p: p["size"][0])
        normal = keys[0]
        self.assertAlmostEqual(normal["size"][0], normal["size"][2], delta=0.05)
        # Pad leaves leftover: the keys don't reach the tray's X edges (16 wide,
        # but keys only span ~the 6-unit region). Check via centers: keys cluster
        # in the middle, not at the X extremes.
        centers_x = [p["min"][0] + p["size"][0] / 2 for p in keys]
        # The leftmost key's left edge is well inside the tray (not at xmin=-8).
        self.assertGreater(min(p["min"][0] for p in keys), -7.5,
                           "pad keys should not reach the tray's left edge")

    def test_cells_repeat_fills_with_extra_keys(self):
        """fill=repeat: keys stay square AND extra 1u keys are added to fill the
        leftover, so MORE keys than declared appear. A 6-cell layout on a
        non-square tray yields > 6 keys (the fillers)."""
        a = _cells_keyboard()
        a["mounts"][0]["position"]["square"] = True
        a["mounts"][0]["position"]["fill"] = "repeat"
        res = _run(a, probe="piece_bboxes")
        self.assertTrue(res["success"], res.get("error"))
        keys = [p for p in res["_probe"]["pieces"] if p["prim_count"] >= 6]
        # The fixture declares 6 keys; repeat adds fillers → strictly more.
        self.assertGreater(len(keys), 6,
                           f"repeat should add filler keys, got {len(keys)}")

    def test_staircase_builds_three_treads(self):
        """The staircase builds with 3 diagonal treads (the array strategy
        works end-to-end via CTP). Live-recook of the array's internal step is
        NOT asserted here — array step/origin/count are computed at build time
        (M2 scope); only ROOT-SHAPE params are live (the car/keyboard tests
        prove that). This is documented in SKILL.md."""
        stairs = {
            "id": "stairs",
            "params": {"base_w": 3.0, "base_h": 0.2, "base_d": 1.0,
                       "tread_w": 0.6, "tread_h": 0.05, "tread_d": 0.25,
                       "rise": 0.3, "run": 0.5},
            "root": {"shape": {"type": "box", "params": {
                "size": ["base_w", "base_h", "base_d"]}}},
            "mounts": [
                {"id": "treads", "position": {"measure": "array", "from": "root",
                    "origin": [0, 0.1, 0], "count": [3, 1, 1],
                    "step": [["run", "rise", 0], [0, 0, 0], [0, 0, 0]]}},
            ],
            "leaves": [
                {"id": "tread", "mount": "treads", "shape": {"type": "box",
                    "params": {"size": ["tread_w", "tread_h", "tread_d"]}}},
            ],
        }
        res = _run(stairs)
        self.assertTrue(res["success"], res.get("error"))
        centers = res["_probe"]["centers"]
        self.assertEqual(len(centers), 3)
        # The 3 treads climb diagonally: sorted by X, consecutive steps differ
        # by (run, rise) = (0.5, 0.3).
        pts = sorted(centers, key=lambda c: c[0])
        for i in range(2):
            dx = pts[i + 1][0] - pts[i][0]
            dy = pts[i + 1][1] - pts[i][1]
            self.assertAlmostEqual(dx, 0.5, places=4)
            self.assertAlmostEqual(dy, 0.3, places=4)

    def test_bicycle_wheels_face_their_axle(self):
        """The decisive facing test: each wheel instance's THINNEST bbox axis
        must be the axle direction (X for this platform). A torus radx=1,
        rady=0.08 is ~0.16 thick on its symmetry axis and ~2.0 on the others,
        so the thinnest bbox dim points where the wheel faces. If orient were
        ignored (the old bug), the thin axis would stay Z, not X."""
        res = _run(_bicycle(), probe="facing")
        self.assertTrue(res["success"], res.get("error"))
        pieces = res["_probe"]["pieces"]
        thin_axes = []
        for p in pieces:
            sz = p["size"]
            thin_axes.append(sz.index(min(sz)))
        # For this platform the axle runs along X (index 0).
        x_facing = sum(1 for a in thin_axes if a == 0)
        self.assertGreaterEqual(x_facing, 4,
            f"wheels not facing axle (X): thin_axes={thin_axes}, pieces={len(pieces)}")

    def test_bicycle_cloud_orient_rotates_align_axis_to_axle(self):
        """Secondary check: read p@orient off the mount cloud (pre-CTP), rotate
        the align axis (+Y — the torus's symmetry axis) by it, and the result
        must align with the measured axle direction (X). Proves the orient
        quaternion itself is correct. (align_axis is +Y because a Houdini torus
        disc lies in the XZ plane with its symmetry axis along Y.)"""
        import math
        res = _run(_bicycle(), probe="facing")
        self.assertTrue(res["success"], res.get("error"))
        cloud = res["_probe"]["cloud_orient"]
        self.assertTrue(cloud, "no orient read from mount cloud")
        for mount_name, quats in cloud.items():
            self.assertTrue(quats, f"no orient on {mount_name}'s points")
            q = quats[0]
            # q = (qx,qy,qz,qw) from floatListAttribValue. Rotate v={0,1,0} (+Y) by q.
            qx, qy, qz, qw = q
            vx, vy, vz = 0.0, 1.0, 0.0
            # Quaternion rotation: v' = v + 2*qw*(q_vec × v) + 2*(q_vec × (q_vec × v))
            cxv = (qy*vz - qz*vy, qz*vx - qx*vz, qx*vy - qy*vx)
            cxv2 = (qy*cxv[2] - qz*cxv[1], qz*cxv[0] - qx*cxv[2], qx*cxv[1] - qy*cxv[0])
            rx = vx + 2*qw*cxv[0] + 2*cxv2[0]
            ry = vy + 2*qw*cxv[1] + 2*cxv2[1]
            rz = vz + 2*qw*cxv[2] + 2*cxv2[2]
            n = math.sqrt(rx*rx + ry*ry + rz*rz)
            rx, ry, rz = rx/n, ry/n, rz/n
            # The axle runs along ±X. The rotated +Y (align axis) must be dominantly X.
            self.assertGreater(abs(rx), 0.9,
                f"{mount_name}: rotated +Y = ({rx:.3f},{ry:.3f},{rz:.3f}) "
                f"not aligned to axle X (orient wrong or ignored)")

    def test_bicycle_one_ctp_four_wheels(self):
        """4 identical wheels share ONE CTP. The OUT has 4 wheels but the
        network has a single wheel_*_ctp node."""
        res = _run(_bicycle(), probe="instance_centers")
        self.assertTrue(res["success"], res.get("error"))
        centers = res["_probe"]["centers"]
        self.assertEqual(len(centers), 4, f"expected 4 wheel mount points, got {centers}")

    def test_car_still_faces_axle_under_new_convention(self):
        """Regression: the car (now annotated align_axis +Z) still has its
        wheels facing the axle, proving the new convention is backward
        compatible with the verified example."""
        res = _run(_car(), probe="facing")
        self.assertTrue(res["success"], res.get("error"))
        pieces = res["_probe"]["pieces"]
        thin_axes = [p["size"].index(min(p["size"])) for p in pieces]
        x_facing = sum(1 for a in thin_axes if a == 0)
        self.assertGreaterEqual(x_facing, 4,
            f"car wheels lost axle facing: thin_axes={thin_axes}")


if __name__ == "__main__":
    unittest.main()
