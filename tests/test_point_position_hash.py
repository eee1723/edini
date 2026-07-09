"""The point-position hash probe for verify_parametric (P2, 2026-07-09).

Context: ``verify_parametric`` used a bbox-only proxy, which false-negatived
shape params (bevel rounding, sticker_size) as 'dead params' — they move
points WITHOUT moving the bbox. That drove agents to hand-edit
``__edini_state`` to shrink the verified set. The fix adds a point-position
hash as a second probe: any real geometric change moves a point → hash
changes. This tests the hash's load-bearing guarantees directly, with a fake
geo (no hou needed).
"""
import math
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))
if "hou" not in sys.modules:
    sys.modules["hou"] = types.ModuleType("hou")

from edini.verify import _point_position_hash  # noqa: E402


class _V:
    """Minimal stand-in for hou.Vector3: indexing + subtraction + length."""
    def __init__(self, x, y, z):
        self.v = (x, y, z)

    def __getitem__(self, i):
        return self.v[i]

    def __sub__(self, o):
        return _V(self.v[0] - o.v[0], self.v[1] - o.v[1], self.v[2] - o.v[2])

    def length(self):
        return math.sqrt(sum(c * c for c in self.v))


class _BB:
    def __init__(self, mn, mx):
        self._mn = _V(*mn)
        self._mx = _V(*mx)

    def minvec(self):
        return self._mn

    def maxvec(self):
        return self._mx


class _Pt:
    def __init__(self, *args):
        if len(args) == 1:
            a = args[0]
            self._pos = a if isinstance(a, _V) else _V(*a)
        else:
            self._pos = _V(*args)

    def position(self):
        return self._pos


class _Geo:
    def __init__(self, pts, mn=(-1, -1, -1), mx=(1, 1, 1)):
        self._pts = pts
        self._bb = _BB(mn, mx)

    def points(self):
        return self._pts

    def boundingBox(self):
        return self._bb


def _box_corners(s=0.5):
    """The 8 corners of a box — the pre-bevel geometry."""
    return [_Pt(x, y, z) for x in (-s, s) for y in (-s, s) for z in (-s, s)]


class TestPointPositionHash(unittest.TestCase):

    def test_deterministic(self):
        """Same geometry → same hash, every call."""
        g = _Geo(_box_corners())
        self.assertEqual(_point_position_hash(g), _point_position_hash(g))

    def test_detects_a_moved_point(self):
        """Moving one point changes the hash — the core sensitivity."""
        base = _box_corners()
        moved = _box_corners()
        moved[0] = _Pt(0.5, 0.5, 0.4)   # one corner nudged
        self.assertNotEqual(
            _point_position_hash(_Geo(base)),
            _point_position_hash(_Geo(moved)))

    def test_order_insensitive(self):
        """Reordering the point list must NOT change the hash (ops may emit
        points in a different order across a perturbation)."""
        import random
        pts = _box_corners()
        shuffled = pts[:]
        random.seed(7)
        random.shuffle(shuffled)
        self.assertEqual(
            _point_position_hash(_Geo(pts)),
            _point_position_hash(_Geo(shuffled)))

    def test_catches_bbox_preserving_change(self):
        """THE regression: a bevel/sticker-size change moves interior points
        but leaves the bbox identical. The bbox-only proxy missed this; the
        hash must catch it."""
        # Pre-bevel: 8 box corners at +-0.5. bbox = [-0.5, 0.5].
        before = _Geo(_box_corners(0.5), mn=(-0.5,)*3, mx=(0.5,)*3)
        # Post-bevel: corners unchanged at +-0.5 (bbox identical) but bevel
        # inserts new rounded-edge vertices INSIDE the bbox.
        post = _box_corners(0.5) + [_Pt(0.5, 0.0, 0.0), _Pt(-0.5, 0.0, 0.0),
                                    _Pt(0.0, 0.5, 0.0), _Pt(0.0, -0.5, 0.0)]
        after = _Geo(post, mn=(-0.5,)*3, mx=(0.5,)*3)
        # bbox is byte-identical (the old proxy's only signal):
        self.assertEqual(before.boundingBox().minvec()[0],
                         after.boundingBox().minvec()[0])
        # ...yet the hash sees the change:
        self.assertNotEqual(_point_position_hash(before),
                            _point_position_hash(after))

    def test_identical_geometry_hashes_equal(self):
        """A truly dead param (broken ch()) produces identical geometry → the
        hash must NOT change (no false 'passed')."""
        a = _Geo(_box_corners())
        b = _Geo(_box_corners())  # same points, fresh objects
        self.assertEqual(_point_position_hash(a), _point_position_hash(b))


if __name__ == "__main__":
    unittest.main()
