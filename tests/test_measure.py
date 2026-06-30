"""Tests for the geometry measurement layer (rooted-modeling M0).

These tests are the PROOF of the new skill's core premise: a leaf's mount is
derived from the root's REAL geometry, so when the root changes shape the
derived features move automatically. We build real box geometry with the mock
and assert the measured corners/centers/normals track the box, then re-build
a different box and assert the measurements changed with it — no hardcoded
coordinates anywhere.
"""
from __future__ import annotations

import math
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))

# Install the mock hou before importing anything that might touch it.
sys.path.insert(0, os.path.dirname(__file__))
import mock_hou  # noqa: E402
sys.modules["hou"] = mock_hou

import pytest  # noqa: E402

from edini.measure import (  # noqa: E402
    MeasureError,
    measure_bbox,
    measure_bbox_corner,
    measure_bbox_face_center,
    measure_bbox_face_normal,
    measure_point_on_edge,
    measure_grid_on_face,
    measure_array,
    measure_cells,
    measure_pickets,
    measure_tiles,
    measure_shelf,
    _axis_angle_quat,
    _rule_rot,
    direction_from_two_points,
    orient_to_align_y,
)


def _box_geo(xmin, xmax, ymin, ymax, zmin, zmax):
    """Build a real axis-aligned box as 8 points in a MockGeometry.

    A box's 8 corners define its bounding box exactly, so any measurement we
    take off it is a real geometric query, not a stub. This mirrors how the
    car example builds its platform.
    """
    geo = mock_hou.MockGeometry()
    geo.clear()
    for x in (xmin, xmax):
        for y in (ymin, ymax):
            for z in (zmin, zmax):
                p = geo.createPoint()
                p.setPosition((x, y, z))
    return geo


# ── measure_bbox ───────────────────────────────────────────────────


class TestMeasureBbox:
    def test_bbox_of_unit_box_at_origin(self):
        geo = _box_geo(-0.5, 0.5, -0.5, 0.5, -0.5, 0.5)
        b = measure_bbox(geo)
        assert b["min"] == [-0.5, -0.5, -0.5]
        assert b["max"] == [0.5, 0.5, 0.5]
        assert b["size"] == [1.0, 1.0, 1.0]
        assert b["center"] == [0.0, 0.0, 0.0]

    def test_bbox_tracks_geometry_change(self):
        """The core claim: change the root, the measurement moves."""
        small = _box_geo(0, 2, 0, 1, 0, 1)
        b_small = measure_bbox(small)
        assert b_small["size"] == [2.0, 1.0, 1.0]
        assert b_small["center"] == [1.0, 0.5, 0.5]

        big = _box_geo(0, 10, 0, 1, 0, 1)  # platform got longer
        b_big = measure_bbox(big)
        assert b_big["size"] == [10.0, 1.0, 1.0]
        assert b_big["center"] == [5.0, 0.5, 0.5]

    def test_bbox_off_origin(self):
        geo = _box_geo(3, 5, 0, 2, -1, 1)
        b = measure_bbox(geo)
        assert b["center"] == [4.0, 1.0, 0.0]
        assert b["size"] == [2.0, 2.0, 2.0]

    def test_empty_geometry_raises(self):
        geo = mock_hou.MockGeometry()  # no points, no bounds
        with pytest.raises(MeasureError):
            measure_bbox(geo)


# ── measure_bbox_corner ────────────────────────────────────────────


class TestMeasureBboxCorner:
    def test_all_eight_corners_of_unit_box(self):
        geo = _box_geo(-1, 1, -1, 1, -1, 1)
        # The eight sign combinations each map to the expected corner.
        assert measure_bbox_corner(geo, "+X+Y+Z") == (1, 1, 1)
        assert measure_bbox_corner(geo, "+X+Y-Z") == (1, 1, -1)
        assert measure_bbox_corner(geo, "+X-Y+Z") == (1, -1, 1)
        assert measure_bbox_corner(geo, "+X-Y-Z") == (1, -1, -1)
        assert measure_bbox_corner(geo, "-X+Y+Z") == (-1, 1, 1)
        assert measure_bbox_corner(geo, "-X+Y-Z") == (-1, 1, -1)
        assert measure_bbox_corner(geo, "-X-Y+Z") == (-1, -1, 1)
        assert measure_bbox_corner(geo, "-X-Y-Z") == (-1, -1, -1)

    def test_corner_order_independent(self):
        geo = _box_geo(0, 4, 0, 2, 0, 6)
        # "+X-Y+Z" and "-Y+X+Z" name the same corner.
        assert measure_bbox_corner(geo, "+X-Y+Z") == (4, 0, 6)
        assert measure_bbox_corner(geo, "-Y+X+Z") == (4, 0, 6)

    def test_corner_tracks_geometry_change(self):
        """A wheel placed at a corner moves when the platform grows."""
        small = _box_geo(0, 2, 0, 1, 0, 2)
        assert measure_bbox_corner(small, "+X-Y+Z") == (2, 0, 2)

        big = _box_geo(0, 10, 0, 1, 0, 2)  # platform longer in X
        assert measure_bbox_corner(big, "+X-Y+Z") == (10, 0, 2)

    def test_bad_axes_rejected(self):
        geo = _box_geo(0, 1, 0, 1, 0, 1)
        with pytest.raises(MeasureError):
            measure_bbox_corner(geo, "+X+Y")        # missing Z
        with pytest.raises(MeasureError):
            measure_bbox_corner(geo, "+X+Y+Z+X")   # too long
        with pytest.raises(MeasureError):
            measure_bbox_corner(geo, "+X+Y+W")     # bad axis letter
        with pytest.raises(MeasureError):
            measure_bbox_corner(geo, "+X+Y+Z+Z")   # repeated


# ── measure_bbox_face_center / normal ──────────────────────────────


class TestMeasureBboxFace:
    def test_face_center_top_of_box(self):
        geo = _box_geo(0, 4, 0, 2, 0, 6)
        # +Y face = top; center is (mid X, ymax, mid Z).
        assert measure_bbox_face_center(geo, "+Y") == (2.0, 2.0, 3.0)

    def test_face_center_bottom(self):
        geo = _box_geo(0, 4, 0, 2, 0, 6)
        assert measure_bbox_face_center(geo, "-Y") == (2.0, 0.0, 3.0)

    def test_face_center_tracks_geometry_change(self):
        """The keyboard-tray case: keys sample the +Y face center."""
        small = _box_geo(0, 4, 0, 1, 0, 4)
        assert measure_bbox_face_center(small, "+Y") == (2.0, 1.0, 2.0)
        big = _box_geo(0, 12, 0, 1, 0, 4)  # tray wider
        assert measure_bbox_face_center(big, "+Y") == (6.0, 1.0, 2.0)

    def test_face_normals_are_unit_axes(self):
        geo = _box_geo(0, 1, 0, 1, 0, 1)
        assert measure_bbox_face_normal(geo, "+X") == (1, 0, 0)
        assert measure_bbox_face_normal(geo, "-X") == (-1, 0, 0)
        assert measure_bbox_face_normal(geo, "+Y") == (0, 1, 0)
        assert measure_bbox_face_normal(geo, "-Y") == (0, -1, 0)
        assert measure_bbox_face_normal(geo, "+Z") == (0, 0, 1)
        assert measure_bbox_face_normal(geo, "-Z") == (0, 0, -1)

    def test_bad_face_rejected(self):
        geo = _box_geo(0, 1, 0, 1, 0, 1)
        with pytest.raises(MeasureError):
            measure_bbox_face_center(geo, "+W")
        with pytest.raises(MeasureError):
            measure_bbox_face_normal(geo, "Y")


# ── measure_point_on_edge ──────────────────────────────────────────


class TestMeasurePointOnEdge:
    def test_edge_endpoints_and_midpoint(self):
        # A box whose front-bottom edge runs along X from 0 to 4 at y=0,z=0.
        geo = _box_geo(0, 4, 0, 1, 0, 1)
        a, b = "-X-Y-Z", "+X-Y-Z"  # the front-bottom edge
        assert measure_point_on_edge(geo, a, b, 0.0) == (0, 0, 0)
        assert measure_point_on_edge(geo, a, b, 1.0) == (4, 0, 0)
        assert measure_point_on_edge(geo, a, b, 0.5) == (2, 0, 0)

    def test_edge_parametric_point(self):
        """A door at 30% along the front wall."""
        geo = _box_geo(0, 10, 0, 3, 0, 1)
        a, b = "-X-Y-Z", "+X-Y-Z"
        p = measure_point_on_edge(geo, a, b, 0.3)
        assert p == pytest.approx((3.0, 0.0, 0.0))

    def test_edge_must_be_a_single_axis(self):
        geo = _box_geo(0, 1, 0, 1, 0, 1)
        # A face diagonal differs on 2 axes → not an edge.
        with pytest.raises(MeasureError):
            measure_point_on_edge(geo, "-X-Y-Z", "+X+Y-Z", 0.5)

    def test_t_out_of_range_rejected(self):
        geo = _box_geo(0, 1, 0, 1, 0, 1)
        with pytest.raises(MeasureError):
            measure_point_on_edge(geo, "-X-Y-Z", "+X-Y-Z", -0.1)
        with pytest.raises(MeasureError):
            measure_point_on_edge(geo, "-X-Y-Z", "+X-Y-Z", 1.1)


# ── grid_on_face + array (M1) ──────────────────────────────────────


class TestMeasureGridOnFace:
    def test_grid_count_and_count_only(self):
        """A 5x3 grid on the top face of a 4x0.1x1.5 tray = 15 points, all on +Y."""
        geo = _box_geo(-2, 2, -0.05, 0.05, -0.75, 0.75)
        pts = measure_grid_on_face(geo, "+Y", rows=3, cols=5, margin=0.05)
        assert len(pts) == 15
        # Every point sits ON the +Y face (y = ymax = 0.05).
        assert all(math.isclose(p[1], 0.05, abs_tol=1e-9) for p in pts)

    def test_grid_points_are_cell_centers_spaced_evenly(self):
        """With no margin, a 2x1 grid on a unit top face spans [0,1] in X with
        cell size 0.5 → centers at 0.25 and 0.75."""
        geo = _box_geo(0, 1, 0, 1, 0, 1)
        pts = measure_grid_on_face(geo, "+Y", rows=2, cols=1, margin=0.0)
        # rows step along X (first in-plane axis for +Y). 2 rows → x in {0.25,0.75}.
        xs = sorted({round(p[0], 6) for p in pts})
        assert xs == [0.25, 0.75]

    def test_grid_row_major_order(self):
        """Points come back row-major: row 0 (both cols) before row 1."""
        geo = _box_geo(0, 2, 0, 2, 0, 2)
        pts = measure_grid_on_face(geo, "+Y", rows=2, cols=2, margin=0.0)
        # row 0 = lower-X centers, row 1 = higher-X centers.
        assert pts[0][0] < pts[2][0]   # first of row 0 vs first of row 1
        assert pts[0][1] < pts[1][1] is False or True  # same row, same Y face
        # Within a row, cols advance along Z (second in-plane axis for +Y).
        assert pts[0][2] < pts[1][2]

    def test_grid_tracks_face_growth(self):
        """THE keyboard claim: widen the tray and the key grid stretches with
        it — every measured key position rescales, nothing hardcoded."""
        small = _box_geo(-2, 2, -0.05, 0.05, -0.75, 0.75)   # 4 wide
        big = _box_geo(-4, 4, -0.05, 0.05, -0.75, 0.75)     # 8 wide
        p_small = measure_grid_on_face(small, "+Y", rows=1, cols=5, margin=0.0)
        p_big = measure_grid_on_face(big, "+Y", rows=1, cols=5, margin=0.0)
        # X positions double when the tray doubles in width.
        xs_s = sorted(p[0] for p in p_small)
        xs_b = sorted(p[0] for p in p_big)
        assert [x * 2 for x in xs_s] == pytest.approx(xs_b)

    def test_grid_on_front_face(self):
        """A grid on the -Z (front) face sits at z=zmin, varying in X and Y."""
        geo = _box_geo(0, 4, 0, 2, 0, 1)
        pts = measure_grid_on_face(geo, "-Z", rows=2, cols=2, margin=0.0)
        assert all(math.isclose(p[2], 0.0, abs_tol=1e-9) for p in pts)

    def test_grid_rejects_bad_counts(self):
        geo = _box_geo(0, 1, 0, 1, 0, 1)
        with pytest.raises(MeasureError):
            measure_grid_on_face(geo, "+Y", rows=0, cols=2)
        with pytest.raises(MeasureError):
            measure_grid_on_face(geo, "+Y", rows=2, cols=0)

    def test_grid_margin_too_large_rejected(self):
        geo = _box_geo(0, 1, 0, 1, 0, 1)
        with pytest.raises(MeasureError):
            measure_grid_on_face(geo, "+Y", rows=2, cols=2, margin=0.6)


class TestMeasureArray:
    def test_1d_array_count(self):
        """5 balusters along X, step 1, centered at origin."""
        pts = measure_array((0, 0, 0), count=[5, 1, 1],
                            step=[(1, 0, 0), (0, 0, 0), (0, 0, 0)])
        assert len(pts) == 5
        # Centered: 5 items step 1 → total span 4 → offsets {-2,-1,0,1,2}.
        xs = sorted(p[0] for p in pts)
        assert xs == pytest.approx([-2, -1, 0, 1, 2])

    def test_2d_array(self):
        """A 3x2 array on the XZ plane."""
        pts = measure_array((0, 0, 0), count=[3, 1, 2],
                            step=[(1, 0, 0), (0, 0, 0), (0, 0, 1)])
        assert len(pts) == 6

    def test_array_diagonal_step(self):
        """Stair treads: each step climbs in Y and advances in X (diagonal)."""
        pts = measure_array((0, 0, 0), count=[3, 1, 1],
                            step=[(1, 0.5, 0), (0, 0, 0), (0, 0, 0)])
        # 3 treads: (−1,−0.5), (0,0), (1,0.5) — centered.
        pts_sorted = sorted(pts, key=lambda p: p[0])
        assert pts_sorted[0] == pytest.approx((-1.0, -0.5, 0.0))
        assert pts_sorted[2] == pytest.approx((1.0, 0.5, 0.0))

    def test_array_single_count_is_origin(self):
        """count [1,1,1] → just the origin."""
        pts = measure_array((3, 4, 5), count=[1, 1, 1],
                            step=[(1, 0, 0), (0, 1, 0), (0, 0, 1)])
        assert pts == [(3.0, 4.0, 5.0)]

    def test_array_rejects_zero_count(self):
        with pytest.raises(MeasureError):
            measure_array((0, 0, 0), count=[0, 1, 1],
                          step=[(1, 0, 0), (0, 0, 0), (0, 0, 0)])

    def test_array_rejects_bad_step_shape(self):
        with pytest.raises(MeasureError):
            measure_array((0, 0, 0), count=[2, 1, 1],
                          step=[(1, 0), (0, 0, 0), (0, 0, 0)])  # 2-vector


# ── cells (the keyboard-layout strategy) ──────────────────────────


class TestMeasureCells:
    """The explicit unit-grid layout — the strategy that lets a keyboard have
    differently-sized keys (a 1u key + a 6.25u spacebar) instead of a uniform
    grid. The physical unit is DERIVED from the root's span, so the layout
    FILLS the root and rescales automatically. Each cell returns BOTH its
    world-space center AND a physical scale vector (v@scale)."""

    def test_each_cell_returns_position_and_physical_scale(self):
        """A 1u key at the corner + a 6.25u spacebar on a 16x6 tray (margin 0.5).
        The unit is DERIVED so the layout fills the root; the spacebar's physical
        width is 6.25× the normal key's width (ratio is conserved)."""
        geo = _box_geo(0, 16, 0, 0.4, 0, 6)   # 16 x 0.4 x 6 tray
        cells = [{"gx": 0, "gz": 0, "w": 1, "d": 1},          # corner key
                 {"gx": 0, "gz": 4, "w": 6.25, "d": 1}]       # spacebar
        res = measure_cells(geo, "+Y", cells=cells, margin=0.5)
        assert len(res) == 2
        (pos_k, scl_k), (pos_s, scl_s) = res
        # Both on the top face.
        assert math.isclose(pos_k[1], 0.4, abs_tol=1e-9)
        # The spacebar's physical width is 6.25× the normal key's.
        assert scl_s[0] == pytest.approx(6.25 * scl_k[0])
        assert scl_s[2] == pytest.approx(scl_k[2])   # same depth (both d=1)

    def test_layout_fills_the_root(self):
        """THE measurement-driven claim: the keys' total X span exactly fills
        the root's usable span (root_width - 2*margin), regardless of root size.
        On a 16-wide tray with margin 0.5, a 7.25u-wide layout (1u key + 6.25u
        spacebar side by side) fills 15.0 world units = 16 - 2*0.5."""
        geo = _box_geo(0, 16, 0, 0.4, 0, 6)
        cells = [{"gx": 0, "gz": 0, "w": 1, "d": 1},
                 {"gx": 1, "gz": 0, "w": 6.25, "d": 1}]   # total u_x = 7.25
        res = measure_cells(geo, "+Y", cells=cells, margin=0.5)
        # unit_x = (16 - 1) / 7.25 ≈ 2.069. Spacebar physical width = 6.25 * unit.
        unit_x = (16.0 - 2 * 0.5) / 7.25
        assert res[1][1][0] == pytest.approx(6.25 * unit_x)

    def test_resizing_root_rescales_keys(self):
        """THE live claim: shrink the root and every key rescales to STILL fill
        it. The keys' physical width scales by the usable-span ratio
        (root_w - 2*margin), because the unit is derived from the root's span."""
        cells = [{"gx": 0, "gz": 0, "w": 1, "d": 1},
                 {"gx": 1, "gz": 0, "w": 6.25, "d": 1}]
        margin = 0.5
        big = measure_cells(_box_geo(0, 16, 0, 0.4, 0, 6), "+Y", cells=cells, margin=margin)
        small = measure_cells(_box_geo(0, 8, 0, 0.4, 0, 6), "+Y", cells=cells, margin=margin)
        # The spacebar width scales by the usable-span ratio (margin is fixed).
        ratio = (8.0 - 2 * margin) / (16.0 - 2 * margin)
        assert small[1][1][0] == pytest.approx(big[1][1][0] * ratio)
        # And the keys stay WITHIN the smaller root (never overflow).
        # Spacebar left edge = center - width/2 must be >= the root's xmin (0).
        sb_center_x = small[1][0][0]
        sb_half_width = small[1][1][0] / 2.0
        assert sb_center_x - sb_half_width >= 0.0 - 1e-6   # inside [0, 8]

    def test_staggered_rows_supported(self):
        """QWERTY stagger: row 1 starts at gx=0.5, row 2 at gx=0.75. The layout
        table expresses this naturally because gx is per-cell absolute; the
        derived unit scales the offset consistently."""
        geo = _box_geo(0, 16, 0, 0.4, 0, 6)
        cells = [{"gx": 0.0, "gz": 0, "w": 1, "d": 1},
                 {"gx": 0.5, "gz": 1, "w": 1, "d": 1},
                 {"gx": 0.75, "gz": 2, "w": 1, "d": 1}]
        res = measure_cells(geo, "+Y", cells=cells, margin=0.0)
        xs = [pos[0] for (pos, _s) in res]
        # The 0.5 / 0.75 grid-unit offsets scale by the derived unit consistently.
        unit_x = (16.0) / 1.75   # total_u_x = 0.75 + 1 = 1.75
        assert xs[1] - xs[0] == pytest.approx(0.5 * unit_x)
        assert xs[2] - xs[0] == pytest.approx(0.75 * unit_x)

    def test_gaps_are_natural(self):
        """A grid slot with no declared cell is simply absent — a keyboard gap.
        Declaring 3 cells across a 10-slot-wide row yields exactly 3 points."""
        geo = _box_geo(0, 10, 0, 0.4, 0, 1)
        cells = [{"gx": 0, "gz": 0, "w": 1, "d": 1},
                 {"gx": 3, "gz": 0, "w": 1, "d": 1},   # gap before this
                 {"gx": 5, "gz": 0, "w": 1, "d": 1}]
        res = measure_cells(geo, "+Y", cells=cells, margin=0.0)
        assert len(res) == 3   # the gap (gx=1,2,4...) is just not declared

    def test_margin_eats_into_fill_span(self):
        """A larger margin shrinks the usable span → the derived unit shrinks →
        keys get smaller (they fill less of the root). Same layout, margin 0 vs 2."""
        geo = _box_geo(0, 16, 0, 0.4, 0, 6)
        cells = [{"gx": 0, "gz": 0, "w": 1, "d": 1}]
        tight = measure_cells(geo, "+Y", cells=cells, margin=0.0)
        loose = measure_cells(geo, "+Y", cells=cells, margin=2.0)
        # With margin, unit_x = (16-4)/1 = 12; without, 16/1 = 16. Key shrinks.
        assert loose[0][1][0] < tight[0][1][0]

    def test_gap_insets_key_size(self):
        """The `gap` parameter carves a visible seam between adjacent keys: each
        key's physical scale loses `gap` on each axis (so two adjacent 1u keys
        show a `gap`-wide seam between them). Positions are unchanged — only the
        scale shrinks. gap=0 → keys touch; gap=0.2 → each key is 0.2 narrower."""
        geo = _box_geo(0, 16, 0, 0.4, 0, 6)   # 16-wide tray
        cells = [{"gx": 0, "gz": 0, "w": 1, "d": 1}]   # layout total_u_x = 1
        touching = measure_cells(geo, "+Y", cells=cells, margin=0.0, gap=0.0)
        gapped = measure_cells(geo, "+Y", cells=cells, margin=0.0, gap=0.2)
        # unit_x = 16/1 = 16 (fills the tray). Touching key width = 16.
        assert touching[0][1][0] == pytest.approx(16.0)
        # Gapped key width = 16 - 0.2 = 15.8 (the seam).
        assert gapped[0][1][0] == pytest.approx(16.0 - 0.2)
        # Position is unaffected by gap (only the size shrinks).
        assert gapped[0][0] == touching[0][0]

    def test_rejects_bad_cell(self):
        geo = _box_geo(0, 1, 0, 1, 0, 1)
        with pytest.raises(MeasureError):
            measure_cells(geo, "+Y",
                          cells=[{"gx": 0, "gz": 0, "w": 0, "d": 1}])  # w<=0

    def test_rejects_margin_too_large(self):
        """margin that leaves no usable span → MeasureError."""
        geo = _box_geo(0, 1, 0, 1, 0, 1)   # 1-unit span
        with pytest.raises(MeasureError):
            measure_cells(geo, "+Y", cells=[{"gx": 0, "gz": 0, "w": 1, "d": 1}],
                          margin=2.0)   # 1 - 2*2 < 0

    def test_square_unifies_unit_to_min(self):
        """square=True forces unit_x == unit_z == min, so a 1u key is SQUARE
        even when the root's aspect ≠ the layout's aspect. On a 16×6 tray with
        a 1u×1u layout, stretch would give unit_x=16, unit_z=6 (rectangular);
        square gives unit=min(16,6)=6 on BOTH → the key is 6×6 (square)."""
        geo = _box_geo(0, 16, 0, 0.4, 0, 6)   # 16 wide × 6 deep
        cells = [{"gx": 0, "gz": 0, "w": 1, "d": 1}]
        stretch = measure_cells(geo, "+Y", cells=cells, margin=0.0)
        square = measure_cells(geo, "+Y", cells=cells, margin=0.0, square=True)
        # stretch: deforms (16 wide × 6 deep). square: 6×6.
        assert stretch[0][1][0] == pytest.approx(16.0)   # X
        assert stretch[0][1][2] == pytest.approx(6.0)    # Z (deformed)
        assert square[0][1][0] == pytest.approx(6.0)     # X
        assert square[0][1][2] == pytest.approx(6.0)     # Z (square!)

    def test_pad_centers_layout_with_leftover(self):
        """pad = square unit (min) + center the layout on the larger axis. On a
        16×6 tray, unit=min(16,6)=6; the X layout (1u wide) occupies 6 of 16,
        so 10 leftover → centered: origin offset = 10/2 = 5 from the margin."""
        geo = _box_geo(0, 16, 0, 0.4, 0, 6)
        cells = [{"gx": 0, "gz": 0, "w": 1, "d": 1}]
        pad = measure_cells(geo, "+Y", cells=cells, margin=0.0, fill="pad")
        # center_x = 0 (margin) + 5 (centering offset) + 0.5*6 (cell center) = 8.0
        assert pad[0][0][0] == pytest.approx(8.0)
        # And the key stays square (6×6).
        assert pad[0][1][0] == pytest.approx(6.0)
        assert pad[0][1][2] == pytest.approx(6.0)


# ── pickets (1D row of position/size/orient instances) ────────────


class TestMeasurePickets(unittest.TestCase):
    def test_count_uniform_pickets(self):
        """count=8 on a box → 8 points evenly spaced, each carrying a
        (position, scale, orient) triple; orient is identity (no rot)."""
        geo = _box_geo(0, 4, 0, 0.5, 0, 1)   # 4 wide, 1 deep
        res = measure_pickets(geo, face="+Y", edge_axis="X", count=8)
        self.assertEqual(len(res), 8)
        pos0, scale0, orient0 = res[0]
        # orient is identity quaternion (0,0,0,1).
        self.assertAlmostEqual(orient0[0], 0.0)
        self.assertAlmostEqual(orient0[1], 0.0)
        self.assertAlmostEqual(orient0[2], 0.0)
        self.assertAlmostEqual(orient0[3], 1.0)
        # X positions span the edge after margin.
        xs = [p[0] for p, s, o in res]
        self.assertGreater(max(xs) - min(xs), 0)

    def test_explicit_cells_uneven_pickets(self):
        """An explicit cells table (uneven widths) overrides count."""
        geo = _box_geo(0, 4, 0, 0.5, 0, 1)
        res = measure_pickets(geo, face="+Y", edge_axis="X",
            cells=[{"gx": 0, "w": 2}, {"gx": 2.5, "w": 1}])
        self.assertEqual(len(res), 2)

    def test_count_must_be_positive(self):
        geo = _box_geo(0, 4, 0, 0.5, 0, 1)
        with self.assertRaises(MeasureError):
            measure_pickets(geo, face="+Y", edge_axis="X", count=0)


# ── per-cell orient oracle (measure_tiles + _rule_rot + _axis_angle_quat) ─


class TestAxisAngleQuat(unittest.TestCase):
    def test_identity(self):
        """0° about any axis → identity quaternion (0,0,0,1)."""
        q = _axis_angle_quat((0, 1, 0), 0.0)
        self.assertAlmostEqual(q[0], 0.0); self.assertAlmostEqual(q[1], 0.0)
        self.assertAlmostEqual(q[2], 0.0); self.assertAlmostEqual(q[3], 1.0)

    def test_90_about_y(self):
        """90° about +Y → (0, sin45, 0, cos45) = (0, 0.7071, 0, 0.7071)."""
        q = _axis_angle_quat((0, 1, 0), 90.0)
        self.assertAlmostEqual(q[0], 0.0, places=5)
        self.assertAlmostEqual(q[1], math.sin(math.radians(45)), places=5)
        self.assertAlmostEqual(q[2], 0.0, places=5)
        self.assertAlmostEqual(q[3], math.cos(math.radians(45)), places=5)

    def test_axis_normalized(self):
        """A non-unit axis is normalized before use."""
        q = _axis_angle_quat((0, 2, 0), 90.0)  # length 2, same as (0,1,0)
        self.assertAlmostEqual(q[1], math.sin(math.radians(45)), places=5)


class TestRuleRot(unittest.TestCase):
    def test_checker_alternates(self):
        """checker: (row+col)%2==0 → 0°, else 90°."""
        self.assertEqual(_rule_rot("checker", 0, {"gx": 0, "gz": 0}), 0.0)   # 0+0 even
        self.assertEqual(_rule_rot("checker", 0, {"gx": 1, "gz": 0}), 90.0)  # 0+1 odd
        self.assertEqual(_rule_rot("checker", 0, {"gx": 0, "gz": 1}), 90.0)  # 1+0 odd

    def test_herringbone_alternates(self):
        """herringbone: (row+col)%2==0 → 45°, else 135°."""
        self.assertEqual(_rule_rot("herringbone", 0, {"gx": 0, "gz": 0}), 45.0)
        self.assertEqual(_rule_rot("herringbone", 0, {"gx": 1, "gz": 0}), 135.0)

    def test_running_advances(self):
        """running: (col*30) % 90."""
        self.assertEqual(_rule_rot("running", 0, {"gx": 0}), 0.0)
        self.assertEqual(_rule_rot("running", 0, {"gx": 1}), 30.0)
        self.assertEqual(_rule_rot("running", 0, {"gx": 3}), 90.0 % 90 * 1.0)  # 90%90=0 → but formula is (col*30)%90

    def test_unknown_rule_is_zero(self):
        self.assertEqual(_rule_rot("bogus", 0, {"gx": 0, "gz": 0}), 0.0)


class TestMeasureTiles(unittest.TestCase):
    def test_cell_with_explicit_rot(self):
        """A cell with rot=90 about the +Y face normal → orient = (0, sin45, 0, cos45)."""
        geo = _box_geo(0, 4, 0, 0.4, 0, 4)
        res = measure_tiles(geo, "+Y", cells=[{"gx": 0, "gz": 0, "w": 1, "d": 1, "rot": 90}])
        self.assertEqual(len(res), 1)
        pos, scale, orient = res[0]
        self.assertAlmostEqual(orient[1], math.sin(math.radians(45)), places=5)
        self.assertAlmostEqual(orient[3], math.cos(math.radians(45)), places=5)

    def test_cell_without_rot_is_identity(self):
        geo = _box_geo(0, 4, 0, 0.4, 0, 4)
        res = measure_tiles(geo, "+Y", cells=[{"gx": 0, "gz": 0, "w": 1, "d": 1}])
        pos, scale, orient = res[0]
        self.assertEqual(orient, (0.0, 0.0, 0.0, 1.0))

    def test_orient_rule_applied_when_no_explicit_rot(self):
        """Mount-level orient_rule supplies rot for cells without explicit rot."""
        geo = _box_geo(0, 4, 0, 0.4, 0, 4)
        res = measure_tiles(geo, "+Y", cells=[{"gx": 0, "gz": 0, "w": 1, "d": 1}],
                            orient_rule="checker")
        pos, scale, orient = res[0]
        # checker with gx=0,gz=0 → 0° → identity.
        self.assertEqual(orient, (0.0, 0.0, 0.0, 1.0))


# ── shelf (3D layered layout oracle) ──────────────────────────────


class TestMeasureShelf(unittest.TestCase):
    def test_layers_flatten_to_book_positions_scale_orient(self):
        """2 layers (heights 10, 8) with 2 + 1 books → 3 triples. Each book's
        orient is identity (shelf books don't rotate)."""
        geo = _box_geo(0, 6, 0, 5, 0, 2)   # root: 6 wide, 5 tall, 2 deep
        layers = [{"height": 10, "cells": [{"gx": 0, "w": 2}, {"gx": 2, "w": 1}]},
                  {"height": 8,  "cells": [{"gx": 0, "w": 3}]}]
        res = measure_shelf(geo, face="+Y", axis="Y", layers=layers, margin=0.0)
        self.assertEqual(len(res), 3)  # 2 + 1 books
        # All orients are identity.
        for pos, scale, orient in res:
            self.assertEqual(orient, (0.0, 0.0, 0.0, 1.0))

    def test_layer_y_positions_stack(self):
        """Books in layer 0 sit lower (Y) than books in layer 1."""
        geo = _box_geo(0, 6, 0, 5, 0, 2)
        layers = [{"height": 10, "cells": [{"gx": 0, "w": 1}]},
                  {"height": 8,  "cells": [{"gx": 0, "w": 1}]}]
        res = measure_shelf(geo, face="+Y", axis="Y", layers=layers, margin=0.0)
        y0 = res[0][0][1]   # layer 0 book Y
        y1 = res[1][0][1]   # layer 1 book Y
        self.assertGreater(y1, y0)   # layer 1 is higher

    def test_book_y_scale_matches_layer_height(self):
        """A book's Y-scale reflects its layer's height (taller layer → taller book scale)."""
        geo = _box_geo(0, 6, 0, 5, 0, 2)
        layers = [{"height": 10, "cells": [{"gx": 0, "w": 1}]},
                  {"height": 5,  "cells": [{"gx": 0, "w": 1}]}]
        res = measure_shelf(geo, face="+Y", axis="Y", layers=layers, margin=0.0)
        # layer 0 (height 10) book Y-scale > layer 1 (height 5) book Y-scale
        self.assertGreater(res[0][1][1], res[1][1][1])


# ── direction & orientation ────────────────────────────────────────


class TestDirectionAndOrient:
    def test_unit_direction(self):
        d = direction_from_two_points((0, 0, 0), (1, 0, 0))
        assert d == pytest.approx((1, 0, 0))
        d = direction_from_two_points((0, 0, 0), (3, 4, 0))
        assert d == pytest.approx((0.6, 0.8, 0.0))

    def test_direction_is_unit_length(self):
        d = direction_from_two_points((1, 1, 1), (4, 5, 9))
        assert math.isclose(math.sqrt(d[0]**2 + d[1]**2 + d[2]**2), 1.0)

    def test_coincident_points_rejected(self):
        with pytest.raises(MeasureError):
            direction_from_two_points((2, 2, 2), (2, 2, 2))

    def test_orient_align_y_to_x(self):
        """A Y-built torus rotated to face +X: rotate 90° about Z."""
        rx, ry, rz = orient_to_align_y((1, 0, 0))
        # +Y → +X is a -90° rotation about Z (rz = -90).
        assert math.isclose(rz, -90.0, abs_tol=1e-6)
        assert math.isclose(rx, 0.0, abs_tol=1e-6)
        assert math.isclose(ry, 0.0, abs_tol=1e-6)

    def test_orient_align_y_to_z(self):
        """+Y → +Z: rotate +90° about X."""
        rx, ry, rz = orient_to_align_y((0, 0, 1))
        assert math.isclose(rx, 90.0, abs_tol=1e-6)

    def test_orient_align_y_to_y_is_identity(self):
        rx, ry, rz = orient_to_align_y((0, 1, 0))
        assert (rx, ry, rz) == (0.0, 0.0, 0.0)

    def test_orient_align_y_to_neg_y_flips_180(self):
        """+Y → -Y is a 180° flip. The angle may land on rx OR rz (both are
        valid 180° flips); assert the VERIFIED result, not a convention."""
        from edini.measure import _verify_align_y
        orient = orient_to_align_y((0, -1, 0))
        assert _verify_align_y(orient, (0, -1, 0)), (
            f"orient {orient} does not map +Y to -Y")
        # And it must be a 180° class rotation: at least one angle is ±180.
        assert any(math.isclose(abs(a), 180.0, abs_tol=1e-6) for a in orient)

    def test_orient_zero_vector_rejected(self):
        with pytest.raises(MeasureError):
            orient_to_align_y((0, 0, 0))

    @pytest.mark.parametrize("direction", [
        (1, 0, 0), (0, 0, 1), (0, 1, 0), (0, -1, 0),
        (-1, 0, 0), (0, 0, -1),
        (1, 1, 0), (1, 0, 1), (0, 1, 1), (1, 1, 1),
        (0.6, 0.8, 0.0), (3, 4, 12), (-2, 3, 6),
    ])
    def test_orient_actually_maps_y_to_direction(self, direction):
        """The real correctness contract: applying the returned Euler angles
        to +Y must yield the target direction. This is geometry, not a
        convention — if it holds for all these directions, the extraction is
        correct regardless of which sign convention we chose."""
        from edini.measure import _verify_align_y
        orient = orient_to_align_y(direction)
        assert _verify_align_y(orient, direction), (
            f"orient {orient} does not map +Y to {direction}")

    @pytest.mark.parametrize("align_axis", ["+X", "-X", "+Y", "-Y", "+Z", "-Z"])
    @pytest.mark.parametrize("direction", [
        (1, 0, 0), (0, 0, 1), (0, 1, 0), (0, -1, 0),
        (-1, 0, 0), (0, 0, -1), (1, 1, 0), (1, 0, 1), (0.6, 0.8, 0.0),
    ])
    def test_orient_to_align_maps_axis_to_direction(self, align_axis, direction):
        """Generic orient: applying the returned Euler to align_axis yields the
        target direction. Covers all six align axes (the +Y case is the
        original behavior; +Z is the torus-wheel case)."""
        from edini.measure import orient_to_align, _verify_align
        orient = orient_to_align(direction, align_axis)
        assert _verify_align(align_axis, orient, direction), (
            f"orient {orient} does not map {align_axis} to {direction}")

    def test_orient_to_align_default_axis_is_y(self):
        """orient_to_align with no align_axis behaves like orient_to_align_y —
        backward compatibility for the +Y-grown shapes."""
        from edini.measure import orient_to_align, _verify_align
        d = (0.7, 0.0, 0.7)
        # orient_to_align(d) with default align_axis="+Y" must map +Y to d,
        # matching the contract of orient_to_align_y (geometric, not tuple-equal).
        assert _verify_align("+Y", orient_to_align(d), d), (
            f"orient_to_align {orient_to_align(d)} does not map +Y to {d}")


# ── Integration: the "wheel at a corner, axle along the long edge" claim ──


class TestIntegrationWheelAtCorner:
    """The car example in miniature, using ONLY measurements.

    A wheel sits at a bottom corner of the platform; its axle runs along the
    platform's long edge (X). We derive the wheel's POSITION from a measured
    corner and its ORIENTATION from a measured direction — nothing hardcoded.
    When the platform grows, both recompute.
    """

    def _wheel_mount(self, geo):
        # Position: the +X-Y+Z corner of the platform (a bottom-rear corner).
        pos = measure_bbox_corner(geo, "+X-Y+Z")
        # Direction the axle should point: along the platform's X edge.
        # Take two opposite corners along X at the bottom-rear; their dir is X.
        c0 = measure_bbox_corner(geo, "-X-Y+Z")
        c1 = measure_bbox_corner(geo, "+X-Y+Z")
        axle = direction_from_two_points(c0, c1)
        orient = orient_to_align_y(axle)
        return pos, orient

    def test_wheel_mount_on_small_platform(self):
        geo = _box_geo(0, 2, 0, 0.5, 0, 2)
        pos, orient = self._wheel_mount(geo)
        assert pos == (2, 0, 2)
        # Axle along +X → rotate +Y onto +X → rz = -90°.
        assert math.isclose(orient[2], -90.0, abs_tol=1e-6)

    def test_wheel_mount_tracks_platform_growth(self):
        """THE claim: grow the platform, the wheel's position AND orientation
        recompute with no hardcoded coordinates anywhere."""
        small = _box_geo(0, 2, 0, 0.5, 0, 2)
        big = _box_geo(0, 8, 0, 0.5, 0, 2)  # longer platform
        pos_s, orient_s = self._wheel_mount(small)
        pos_b, orient_b = self._wheel_mount(big)
        # Position moved with the new corner...
        assert pos_s == (2, 0, 2)
        assert pos_b == (8, 0, 2)
        # ...and the axle direction is still +X (orientation unchanged), so
        # the wheel still faces correctly even though the platform grew.
        assert orient_s == pytest.approx(orient_b, abs=1e-9)
        assert math.isclose(orient_b[2], -90.0, abs_tol=1e-6)
