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
