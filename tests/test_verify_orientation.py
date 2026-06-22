"""Tests for orientation_math (pure PCA helpers) and verify_orientation flow."""
import importlib
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "python3.11libs"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest

# Pure math — no hou dependency at all
from edini.orientation_math import (
    AXIS_VECTORS,
    KIND_EIGEN_RANK,
    compute_covariance,
    jacobi_eigen_3x3,
    axis_angle_between,
    dominant_axis_name,
    flip_to_hemisphere,
    rotate_vector_by_quaternion,
    LOCAL_AXIS_VECTORS,
)


def _ring_points(n=32, center=(0, 0, 0), radius=1.0, plane="YZ"):
    pts = []
    for i in range(n):
        theta = 2.0 * math.pi * i / n
        c, s = math.cos(theta), math.sin(theta)
        if plane == "YZ":
            p = (center[0], center[1] + radius * c, center[2] + radius * s)
        elif plane == "XZ":
            p = (center[0] + radius * c, center[1], center[2] + radius * s)
        elif plane == "XY":
            p = (center[0] + radius * c, center[1] + radius * s, center[2])
        else:
            raise ValueError(plane)
        pts.append(p)
    return pts


def _tube_points(n=32, start=(0, 0, 0), direction=(1, 0, 0),
                 length=5.0, radius=0.1):
    pts = []
    dx, dy, dz = direction
    mag = math.sqrt(dx * dx + dy * dy + dz * dz)
    dx, dy, dz = dx / mag, dy / mag, dz / mag
    if abs(dx) < 0.9:
        u = (0, 1, 0)
    else:
        u = (0, 0, 1)
    ux = u[0] - (u[0] * dx + u[1] * dy + u[2] * dz) * dx
    uy = u[1] - (u[0] * dx + u[1] * dy + u[2] * dz) * dy
    uz = u[2] - (u[0] * dx + u[1] * dy + u[2] * dz) * dz
    um = math.sqrt(ux * ux + uy * uy + uz * uz)
    ux, uy, uz = ux / um, uy / um, uz / um
    vx = dy * uz - dz * uy
    vy = dz * ux - dx * uz
    vz = dx * uy - dy * ux
    for i in range(n):
        t = i / (n - 1)
        cx = start[0] + dx * length * t
        cy = start[1] + dy * length * t
        cz = start[2] + dz * length * t
        theta = 2.0 * math.pi * (i % 8) / 8
        pts.append((
            cx + radius * (ux * math.cos(theta) + vx * math.sin(theta)),
            cy + radius * (uy * math.cos(theta) + vy * math.sin(theta)),
            cz + radius * (uz * math.cos(theta) + vz * math.sin(theta)),
        ))
    return pts


# ---------------------------------------------------------------------------
# Pure math tests
# ---------------------------------------------------------------------------

class TestCovariance(unittest.TestCase):
    def test_centroid_of_unit_ring_at_origin(self):
        pts = _ring_points(64, radius=1.0)
        cov, centroid = compute_covariance(pts)
        for c in centroid:
            self.assertAlmostEqual(c, 0.0, places=6)

    def test_covariance_diagonal_for_axis_aligned(self):
        pts = [(-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0)]
        cov, _ = compute_covariance(pts)
        self.assertAlmostEqual(cov[0][0], 0.5, places=6)
        self.assertAlmostEqual(cov[1][1], 0.5, places=6)
        self.assertAlmostEqual(cov[2][2], 0.0, places=6)
        self.assertAlmostEqual(cov[0][1], 0.0, places=6)


class TestJacobiEigen(unittest.TestCase):
    def test_diagonal_matrix_unchanged(self):
        cov = [[3.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 1.0]]
        eigs, vecs = jacobi_eigen_3x3(cov)
        self.assertAlmostEqual(eigs[0], 1.0, places=6)
        self.assertAlmostEqual(eigs[1], 2.0, places=6)
        self.assertAlmostEqual(eigs[2], 3.0, places=6)

    def test_returns_ascending_eigenvalues(self):
        cov = [[5.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 3.0]]
        eigs, _ = jacobi_eigen_3x3(cov)
        self.assertEqual(eigs, sorted(eigs))

    def test_eigenvectors_orthonormal(self):
        cov = [[2.0, 1.0, 0.0], [1.0, 2.0, 0.5], [0.0, 0.5, 1.5]]
        eigs, vecs = jacobi_eigen_3x3(cov)
        for v in vecs:
            mag = math.sqrt(sum(c * c for c in v))
            self.assertAlmostEqual(mag, 1.0, places=5)
        for i in range(3):
            for j in range(i + 1, 3):
                dot = sum(vecs[i][k] * vecs[j][k] for k in range(3))
                self.assertAlmostEqual(dot, 0.0, places=5)

    def test_ring_in_YZ_plane_smallest_eigenvalue_along_X(self):
        pts = _ring_points(64, plane="YZ", radius=1.0)
        cov, _ = compute_covariance(pts)
        eigs, vecs = jacobi_eigen_3x3(cov)
        dom = dominant_axis_name(vecs[0])
        self.assertEqual(dom, "X")

    def test_ring_in_XY_plane_smallest_eigenvalue_along_Z(self):
        pts = _ring_points(64, plane="XY", radius=1.0)
        cov, _ = compute_covariance(pts)
        eigs, vecs = jacobi_eigen_3x3(cov)
        dom = dominant_axis_name(vecs[0])
        self.assertEqual(dom, "Z")

    def test_tube_along_X_largest_eigenvalue_along_X(self):
        pts = _tube_points(64, direction=(1, 0, 0), length=5.0, radius=0.05)
        cov, _ = compute_covariance(pts)
        eigs, vecs = jacobi_eigen_3x3(cov)
        dom = dominant_axis_name(vecs[2])
        self.assertIn(dom, ("X", "-X"))

    def test_tube_along_Z_largest_eigenvalue_along_Z(self):
        pts = _tube_points(64, direction=(0, 0, 1), length=5.0, radius=0.05)
        cov, _ = compute_covariance(pts)
        eigs, vecs = jacobi_eigen_3x3(cov)
        dom = dominant_axis_name(vecs[2])
        self.assertIn(dom, ("Z", "-Z"))


class TestAxisAngleBetween(unittest.TestCase):
    def test_parallel_vectors_zero_angle(self):
        angle, q = axis_angle_between((1, 0, 0), (1, 0, 0))
        self.assertAlmostEqual(angle, 0.0, places=4)
        self.assertAlmostEqual(q[3], 1.0, places=4)

    def test_perpendicular_X_to_Y(self):
        angle, q = axis_angle_between((1, 0, 0), (0, 1, 0))
        self.assertAlmostEqual(angle, 90.0, places=2)
        self.assertAlmostEqual(q[2], math.sin(math.radians(45)), places=3)
        self.assertAlmostEqual(q[3], math.cos(math.radians(45)), places=3)

    def test_180_degree_flip(self):
        # Default unsigned: 180° apart = same axis line = 0°
        angle_u, _ = axis_angle_between((1, 0, 0), (-1, 0, 0))
        self.assertAlmostEqual(angle_u, 0.0, places=2)
        # Signed: true 180°
        angle_s, _ = axis_angle_between((1, 0, 0), (-1, 0, 0), signed=True)
        self.assertAlmostEqual(angle_s, 180.0, places=2)


class TestDominantAxisName(unittest.TestCase):
    def test_pure_X(self):
        self.assertEqual(dominant_axis_name((1, 0, 0)), "X")
        self.assertEqual(dominant_axis_name((-1, 0, 0)), "-X")

    def test_dominant_with_components(self):
        self.assertEqual(dominant_axis_name((0.9, 0.1, 0.1)), "X")
        self.assertEqual(dominant_axis_name((0.1, 0.9, 0.1)), "Y")
        self.assertEqual(dominant_axis_name((0.1, 0.1, 0.9)), "Z")


class TestFlipToHemisphere(unittest.TestCase):
    def test_no_flip_when_same_hemisphere(self):
        self.assertEqual(flip_to_hemisphere((1, 0, 0), (1, 0, 0)), (1, 0, 0))

    def test_flip_when_opposite_hemisphere(self):
        self.assertEqual(flip_to_hemisphere((-1, 0, 0), (1, 0, 0)), (1, 0, 0))

    def test_no_flip_for_orthogonal(self):
        # Dot = 0 → keep as-is (boundary case)
        self.assertEqual(flip_to_hemisphere((0, 1, 0), (1, 0, 0)), (0, 1, 0))


class TestRotateVectorByQuaternion(unittest.TestCase):
    """B-station pure-math core: deterministic local→world axis derivation."""

    def test_identity_quaternion_leaves_vector_unchanged(self):
        v = rotate_vector_by_quaternion((1, 0, 0), (0, 0, 0, 1))
        self.assertAlmostEqual(v[0], 1.0, places=6)
        self.assertAlmostEqual(v[1], 0.0, places=6)
        self.assertAlmostEqual(v[2], 0.0, places=6)

    def test_90deg_around_Z_maps_X_to_Y(self):
        # q = (0,0,sin45,cos45) rotates X→Y
        import math
        s = math.sin(math.radians(45))
        c = math.cos(math.radians(45))
        v = rotate_vector_by_quaternion((1, 0, 0), (0, 0, s, c))
        self.assertAlmostEqual(v[0], 0.0, places=5)
        self.assertAlmostEqual(v[1], 1.0, places=5)
        self.assertAlmostEqual(v[2], 0.0, places=5)

    def test_90deg_around_X_maps_Y_to_Z(self):
        import math
        s = math.sin(math.radians(45))
        c = math.cos(math.radians(45))
        v = rotate_vector_by_quaternion((0, 1, 0), (s, 0, 0, c))
        self.assertAlmostEqual(v[0], 0.0, places=5)
        self.assertAlmostEqual(v[1], 0.0, places=5)
        self.assertAlmostEqual(v[2], 1.0, places=5)

    def test_180deg_around_Z_maps_X_to_negative_X(self):
        import math
        s = math.sin(math.radians(90))
        c = math.cos(math.radians(90))
        v = rotate_vector_by_quaternion((1, 0, 0), (0, 0, s, c))
        self.assertAlmostEqual(v[0], -1.0, places=5)
        self.assertAlmostEqual(v[1], 0.0, places=5)

    def test_local_axis_vectors_table_present(self):
        self.assertEqual(LOCAL_AXIS_VECTORS["Y"], (0.0, 1.0, 0.0))
        self.assertEqual(LOCAL_AXIS_VECTORS["-X"], (-1.0, 0.0, 0.0))

    def test_unit_quaternion_preserves_vector_length(self):
        import math
        # Fully normalized: axis (1,1,1)/sqrt(3), angle 30°
        inv3 = 1.0 / math.sqrt(3.0)
        s = math.sin(math.radians(30))
        c = math.cos(math.radians(30))
        q = (s * inv3, s * inv3, s * inv3, c)
        v = rotate_vector_by_quaternion((3, 0, 0), q)
        mag = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
        self.assertAlmostEqual(mag, 3.0, places=4)


# ---------------------------------------------------------------------------
# Full verify_orientation flow with mocked hou geometry
# ---------------------------------------------------------------------------

class TestVerifyOrientationFlow(unittest.TestCase):
    """Verify the orchestrating function works end-to-end with mock geometry."""

    def setUp(self):
        # Install mock hou before importing node_utils
        self.prev_hou = sys.modules.get("hou")
        self.prev_edini = {
            n: m for n, m in sys.modules.items() if n.startswith("edini")
        }
        from tests.mock_hou import create_mock_hou, MockNode
        self.prev_hou_ref = MockNode._hou_ref
        self.mock_hou = create_mock_hou()
        sys.modules["hou"] = self.mock_hou
        for mod_name in list(sys.modules):
            if mod_name.startswith("edini"):
                del sys.modules[mod_name]
        self.nu = importlib.import_module("edini.node_utils")

    def tearDown(self):
        from tests.mock_hou import MockNode
        for mod_name in list(sys.modules):
            if mod_name.startswith("edini"):
                del sys.modules[mod_name]
        sys.modules.update(self.prev_edini)
        if self.prev_hou is not None:
            sys.modules["hou"] = self.prev_hou
        else:
            sys.modules.pop("hou", None)
        MockNode._hou_ref = self.prev_hou_ref

    def _build_bike_geo(self, wheel_axle="X", handle_long="Z"):
        """Build a bike geo with wheel + handlebar components.

        Stage-5 (decision 3): the PCA fallback path was removed, so prims now
        MUST carry a baked edini_world_axis. We bake it from the construction
        params: the wheel's radial axis is its axle (the plane normal), the
        handlebar's long axis is its direction. This keeps the tests' detection
        semantics intact — when the baked axis matches expected_axis the check
        passes; when it disagrees the check fails with the detected axis —
        while exercising the construction path instead of PCA."""
        from tests.mock_hou import MockGeometry
        geo = MockGeometry()
        geo.clear()
        geo.addAttrib("prim", "component_id", "")
        geo.addAttrib("prim", "edini_world_axis", (0.0, 0.0, 0.0))

        wheel_axis_vec = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[wheel_axle]
        wheel_plane = {"X": "YZ", "Y": "XZ", "Z": "XY"}[wheel_axle]
        for p in _ring_points(32, center=(0, 1, 0), radius=0.5, plane=wheel_plane):
            pt = geo.createPoint(); pt.setPosition(p)
            prim = geo.createPolygon(); prim.addVertex(pt)
            prim.setAttribValue("component_id", "wheel_front")
            prim.setAttribValue("edini_world_axis", wheel_axis_vec)

        handle_dir = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[handle_long]
        for p in _tube_points(32, start=(0, 2, 0), direction=handle_dir,
                              length=2.0, radius=0.05):
            pt = geo.createPoint(); pt.setPosition(p)
            prim = geo.createPolygon(); prim.addVertex(pt)
            prim.setAttribValue("component_id", "handlebar")
            prim.setAttribValue("edini_world_axis", handle_dir)

        return geo

    def _patch_node(self, geo):
        from tests.mock_hou import MockNode
        node = MockNode("/obj/bike/OUT", "OUT", parent=None)
        node.geometry = lambda: geo
        self.mock_hou.node = lambda p: node if p == "/obj/bike/OUT" else None

    def test_correctly_oriented_bike_passes(self):
        geo = self._build_bike_geo(wheel_axle="X", handle_long="Z")
        self._patch_node(geo)
        result = self.nu.verify_orientation("/obj/bike/OUT", [
            {"component_id": "wheel_front", "kind": "radial",
             "expected_axis": "X", "tolerance_deg": 15},
            {"component_id": "handlebar", "kind": "elongated",
             "expected_axis": "Z", "tolerance_deg": 15},
        ])
        self.assertTrue(result["success"], msg=result)
        self.assertEqual(result["passed"], 2)
        self.assertEqual(result["failed"], 0)

    def test_laying_flat_wheel_detected(self):
        geo = self._build_bike_geo(wheel_axle="Y", handle_long="Z")
        self._patch_node(geo)
        result = self.nu.verify_orientation("/obj/bike/OUT", [
            {"component_id": "wheel_front", "kind": "radial",
             "expected_axis": "X", "tolerance_deg": 15},
        ])
        self.assertTrue(result["success"])
        self.assertEqual(result["failed"], 1)
        chk = result["checks"][0]
        self.assertFalse(chk["passed"])
        self.assertEqual(chk["detected_axis"], "Y")
        self.assertGreater(chk["angle_error_deg"], 75)
        self.assertIn("quaternion", chk.get("hint", "").lower())

    def test_parallel_handlebar_detected(self):
        geo = self._build_bike_geo(wheel_axle="X", handle_long="X")
        self._patch_node(geo)
        result = self.nu.verify_orientation("/obj/bike/OUT", [
            {"component_id": "handlebar", "kind": "elongated",
             "expected_axis": "Z", "tolerance_deg": 15},
        ])
        self.assertEqual(result["failed"], 1)
        chk = result["checks"][0]
        self.assertIn(chk["detected_axis"], ("X", "-X"))
        self.assertGreater(chk["angle_error_deg"], 75)

    def test_missing_component_id_attr(self):
        from tests.mock_hou import MockGeometry
        geo = MockGeometry()
        geo.clear()
        pt = geo.createPoint(); pt.setPosition((1, 0, 0))
        prim = geo.createPolygon(); prim.addVertex(pt)
        self._patch_node(geo)
        result = self.nu.verify_orientation("/obj/bike/OUT", [
            {"component_id": "wheel_front", "kind": "radial",
             "expected_axis": "X"},
        ])
        self.assertFalse(result["success"])
        self.assertIn("component_id", result["error"])

    def test_unknown_component_id_lists_available(self):
        geo = self._build_bike_geo(wheel_axle="X", handle_long="Z")
        self._patch_node(geo)
        result = self.nu.verify_orientation("/obj/bike/OUT", [
            {"component_id": "nonexistent", "kind": "radial",
             "expected_axis": "X"},
        ])
        self.assertTrue(result["success"])
        self.assertEqual(result["failed"], 1)
        chk = result["checks"][0]
        self.assertIn("Available:", chk.get("error", ""))
        self.assertIn("wheel_front", chk["error"])
        self.assertIn("handlebar", chk["error"])

    def test_invalid_kind_rejected(self):
        geo = self._build_bike_geo()
        self._patch_node(geo)
        result = self.nu.verify_orientation("/obj/bike/OUT", [
            {"component_id": "wheel_front", "kind": "weird",
             "expected_axis": "X"},
        ])
        self.assertEqual(result["failed"], 1)
        self.assertIn("Unknown kind", result["checks"][0]["error"])


class TestVerifyOrientationConstructionPath(unittest.TestCase):
    """B-station: when edini_world_axis is baked on prims, verify_orientation
    uses the deterministic construction axis and SKIPS PCA (method=construction)."""

    def setUp(self):
        self.prev_hou = sys.modules.get("hou")
        self.prev_edini = {
            n: m for n, m in sys.modules.items() if n.startswith("edini")
        }
        from tests.mock_hou import create_mock_hou, MockNode
        self.prev_hou_ref = MockNode._hou_ref
        self.mock_hou = create_mock_hou()
        sys.modules["hou"] = self.mock_hou
        for mod_name in list(sys.modules):
            if mod_name.startswith("edini"):
                del sys.modules[mod_name]
        self.nu = importlib.import_module("edini.node_utils")

    def tearDown(self):
        from tests.mock_hou import MockNode
        for mod_name in list(sys.modules):
            if mod_name.startswith("edini"):
                del sys.modules[mod_name]
        sys.modules.update(self.prev_edini)
        if self.prev_hou is not None:
            sys.modules["hou"] = self.prev_hou
        else:
            sys.modules.pop("hou", None)
        MockNode._hou_ref = self.prev_hou_ref

    def _build_geo_with_world_axis(self, world_axis):
        """Build a minimal geo whose wheel prims carry edini_world_axis.
        Point positions are deliberately a RING in the YZ plane (PCA would
        detect X) so we can prove the construction axis OVERRIDES PCA."""
        from tests.mock_hou import MockGeometry
        geo = MockGeometry()
        geo.clear()
        geo.addAttrib("prim", "component_id", "")
        # declare the attrib so findPrimAttrib sees it
        geo.addAttrib("prim", "edini_world_axis", (0.0, 0.0, 0.0))
        # ring in YZ plane → PCA radial axis = X. We bake world_axis="Y"
        # to assert the construction authority overrides this.
        for p in _ring_points(32, center=(0, 0, 0), radius=1.0, plane="YZ"):
            pt = geo.createPoint(); pt.setPosition(p)
            prim = geo.createPolygon(); prim.addVertex(pt)
            prim.setAttribValue("component_id", "wheel_front")
            prim.setAttribValue("edini_world_axis", tuple(world_axis))
        return geo

    def _patch_node(self, geo):
        from tests.mock_hou import MockNode
        node = MockNode("/obj/bike/OUT", "OUT", parent=None)
        node.geometry = lambda: geo
        self.mock_hou.node = lambda p: node if p == "/obj/bike/OUT" else None

    def test_construction_axis_overrides_pca(self):
        """edini_world_axis=Y but PCA would say X. Construction wins."""
        geo = self._build_geo_with_world_axis((0.0, 1.0, 0.0))
        self._patch_node(geo)
        result = self.nu.verify_orientation("/obj/bike/OUT", [
            {"component_id": "wheel_front", "kind": "radial",
             "expected_axis": "Y", "tolerance_deg": 15},
        ])
        self.assertTrue(result["success"], msg=result)
        self.assertEqual(result["passed"], 1)
        chk = result["checks"][0]
        self.assertEqual(chk["method"], "construction")
        self.assertEqual(chk["detected_axis"], "Y")
        self.assertTrue(chk["passed"])

    def test_construction_mismatch_fails_with_deterministic_hint(self):
        """Baked axis X, expected Z → fails, hint says fix recipe not quaternion."""
        geo = self._build_geo_with_world_axis((1.0, 0.0, 0.0))
        self._patch_node(geo)
        result = self.nu.verify_orientation("/obj/bike/OUT", [
            {"component_id": "wheel_front", "kind": "radial",
             "expected_axis": "Z", "tolerance_deg": 15},
        ])
        self.assertEqual(result["failed"], 1)
        chk = result["checks"][0]
        self.assertFalse(chk["passed"])
        self.assertEqual(chk["method"], "construction")
        # hint must say this is deterministic (NOT a post-hoc quaternion fix)
        self.assertIn("construction", chk["hint"].lower())

    def test_pca_crosscheck_warning_when_divergent(self):
        """Construction says Y, PCA estimates X (the ring) → crosscheck warning
        present but the check still PASSES (construction is authoritative)."""
        geo = self._build_geo_with_world_axis((0.0, 1.0, 0.0))
        self._patch_node(geo)
        result = self.nu.verify_orientation("/obj/bike/OUT", [
            {"component_id": "wheel_front", "kind": "radial",
             "expected_axis": "Y", "tolerance_deg": 15},
        ])
        chk = result["checks"][0]
        self.assertIn("pca_crosscheck", chk)
        # ring in YZ → PCA radial = X → divergence from Y is ~90°
        self.assertGreater(chk["pca_crosscheck"]["divergence_deg"], 75)
        self.assertIn("warning", chk["pca_crosscheck"])

    def test_no_world_axis_now_rejected(self):
        """Decision 3 (single-path design): prims WITHOUT edini_world_axis FAIL.
        The PCA fallback path was removed (it misclassifies elongated cylinders
        → the hub 90° bug). With no estimation path left, a prim without a
        baked axis fails outright and points at the fix: build via
        build_procedural_asset (bakes edini_world_axis from construction_axis)
        or remove the assert. This replaces the old
        'no world axis falls back to PCA / backward compat' test — that
        property was explicitly retired by decision 3."""
        from tests.mock_hou import MockGeometry
        geo = MockGeometry()
        geo.clear()
        geo.addAttrib("prim", "component_id", "")
        for p in _ring_points(32, center=(0, 0, 0), radius=1.0, plane="YZ"):
            pt = geo.createPoint(); pt.setPosition(p)
            prim = geo.createPolygon(); prim.addVertex(pt)
            prim.setAttribValue("component_id", "wheel_front")
        self._patch_node(geo)
        result = self.nu.verify_orientation("/obj/bike/OUT", [
            {"component_id": "wheel_front", "kind": "radial",
             "expected_axis": "X", "tolerance_deg": 15},
        ])
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["passed"], 0)
        chk = result["checks"][0]
        self.assertEqual(chk["method"], "no_axis")
        self.assertFalse(chk["passed"])
        self.assertIn("edini_world_axis", chk["error"])


if __name__ == "__main__":
    unittest.main()
