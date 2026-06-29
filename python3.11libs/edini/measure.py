"""Geometry measurement layer — the core of rooted-modeling.

This module answers ONE question, the question the old declarative pipeline
could not: *"Given a component that has already been built, where exactly does
some feature of it sit in world space?"*

The old pipeline derived every position from a param/skeleton expression DAG.
That works for tube structures (a bike frame is a set of named tube endpoints)
but it CANNOT express the three motivating cases of the new skill:

  - keyboard  → keys sit on a *grid sampled across the top FACE* of the tray
  - building  → doors sit *on a wall, at a height ratio along its length*
  - vehicle   → wheels attach *at corners measured off the already-built body*

In every case the leaf's position is a function of the root's REAL, COOKED
geometry — not of a param. So ``measure`` reads geometry that has already been
built and returns concrete, derived features (points, directions, lengths)
that an assembly step then places leaves onto. Change the root's shape and the
measured features recompute — no human re-syncs numbers.

Design contract
---------------
- Every public function takes an already-cooked ``hou.Geometry`` (or, for
  tests, a ``MockGeometry`` that supports the same subset of the API).
- Every function returns plain Python tuples/lists of floats — never hou
  objects — so the result is JSON-serializable and testable without Houdini.
- The library is deliberately SMALL and named by physical meaning. M0 ships
  bounding-box features (the common case); M1+ will add named anchors and
  face/edge sampling without changing the existing surface.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

__all__ = [
    "MeasureError",
    "measure_bbox",
    "measure_bbox_corner",
    "measure_bbox_face_center",
    "measure_bbox_face_normal",
    "measure_point_on_edge",
    "measure_grid_on_face",
    "measure_array",
    "direction_from_two_points",
    "orient_to_align_y",
]


class MeasureError(ValueError):
    """Raised when a measurement cannot be derived from the given geometry."""


# ── Bounding box ────────────────────────────────────────────────────


def _bbox(geo) -> tuple[float, float, float, float, float, float]:
    """Return the axis-aligned bounding box as interleaved floats
    ``(xmin, xmax, ymin, ymax, zmin, zmax)``.

    Prefers the intrinsic ``bounds`` (fast, exact). Falls back to
    ``boundingBox().minvec()/maxvec()`` (component-major). Raises
    ``MeasureError`` if neither is available or the geometry is empty.
    """
    raw = None
    try:
        raw = geo.intrinsicValue("bounds")
    except Exception:
        raw = None
    if raw is None:
        bb = getattr(geo, "boundingBox", None)
        bb = bb() if callable(bb) else None
        if bb is None:
            raise MeasureError("geometry has no bounds (empty or unavailable)")
        try:
            mn = bb.minvec()
            mx = bb.maxvec()
            raw = (
                float(mn[0]), float(mx[0]),
                float(mn[1]), float(mx[1]),
                float(mn[2]), float(mx[2]),
            )
        except Exception as exc:  # pragma: no cover - defensive
            raise MeasureError(f"could not read bounding box: {exc}") from None
    if raw is None or len(raw) != 6 or not all(math.isfinite(float(c)) for c in raw):
        raise MeasureError(f"geometry bounds are unusable: {raw!r}")
    return tuple(float(c) for c in raw)  # type: ignore[return-value]


def measure_bbox(geo) -> dict[str, list[float]]:
    """Return ``{min, max, size, center}`` of the geometry's bounding box.

    ``size`` is the per-axis extent; ``center`` is the box midpoint. This is
    the foundation every other bbox measurement is expressed against.
    """
    xmin, xmax, ymin, ymax, zmin, zmax = _bbox(geo)
    mn = [xmin, ymin, zmin]
    mx = [xmax, ymax, zmax]
    size = [xmax - xmin, ymax - ymin, zmax - zmin]
    center = [(xmin + xmax) / 2.0, (ymin + ymax) / 2.0, (zmin + zmax) / 2.0]
    return {"min": mn, "max": mx, "size": size, "center": center}


# Corner naming convention: a sign string like "+X-Y+Z" picks the corner at
# (xmax, ymin, zmax). Used by measure_bbox_corner and by the car example
# (four wheels = four bottom corners of the platform).
_AXIS_SIGN = {"+": 1, "-": -1}


def measure_bbox_corner(geo, axes: str) -> tuple[float, float, float]:
    """Return one corner of the bounding box.

    ``axes`` is a 3-char sign string over ``X``/``Y``/``Z``, e.g.
    ``"+X-Y+Z"`` → ``(xmax, ymin, zmax)``. Order of the letters is free;
    each must appear once. This is how the car example picks the four bottom
    corners the wheels sit at — by SIGN, never by hardcoded coordinates.
    """
    parsed = _parse_axes(axes)
    xmin, xmax, ymin, ymax, zmin, zmax = _bbox(geo)
    pool = {"X": (xmin, xmax), "Y": (ymin, ymax), "Z": (zmin, zmax)}
    out = []
    for axis in "XYZ":
        sign = parsed[axis]
        lo, hi = pool[axis]
        out.append(hi if sign > 0 else lo)
    return (out[0], out[1], out[2])


def _parse_axes(axes: str) -> dict[str, int]:
    """Parse "+X-Y+Z" → {"X":+1,"Y":-1,"Z":+1}. Order-independent."""
    if not isinstance(axes, str) or len(axes) != 6:
        raise MeasureError(
            f"axes must be a 6-char string like '+X-Y+Z', got {axes!r}")
    seen: dict[str, int] = {}
    i = 0
    while i < len(axes):
        sign = axes[i]
        if sign not in _AXIS_SIGN:
            raise MeasureError(
                f"axis sign must be '+' or '-', got {sign!r} in {axes!r}")
        if i + 1 >= len(axes):
            raise MeasureError(f"trailing sign with no axis in {axes!r}")
        letter = axes[i + 1]
        if letter not in ("X", "Y", "Z"):
            raise MeasureError(
                f"axis letter must be X/Y/Z, got {letter!r} in {axes!r}")
        if letter in seen:
            raise MeasureError(f"axis {letter!r} repeated in {axes!r}")
        seen[letter] = _AXIS_SIGN[sign]
        i += 2
    missing = {"X", "Y", "Z"} - seen.keys()
    if missing:
        raise MeasureError(f"axes missing {sorted(missing)} in {axes!r}")
    return seen


# ── Faces ───────────────────────────────────────────────────────────


# A bbox face is named by the axis that is EXTREME on it and the sign:
# "+Y" = the top face (ymax), "-X" = the left face (xmin), etc.
def measure_bbox_face_center(geo, face: str) -> tuple[float, float, float]:
    """Return the center of one face of the bounding box.

    ``face`` is a 2-char string: a sign + an axis, e.g. ``"+Y"`` = top face,
    ``"-Y"`` = bottom, ``"-Z"`` = back. The center sits at the extreme of the
    named axis and the midpoint of the other two. This is what the keyboard
    example will use (keys sample the ``+Y`` face of the tray).
    """
    sign, axis = _parse_face(face)
    b = measure_bbox(geo)
    cx, cy, cz = b["center"]
    sx, sy, sz = b["size"]
    if axis == "X":
        x = b["max"][0] if sign > 0 else b["min"][0]
        return (x, cy, cz)
    if axis == "Y":
        y = b["max"][1] if sign > 0 else b["min"][1]
        return (cx, y, cz)
    # Z
    z = b["max"][2] if sign > 0 else b["min"][2]
    return (cx, cy, z)


def measure_bbox_face_normal(geo, face: str) -> tuple[float, float, float]:
    """Return the outward unit normal of one bbox face.

    ``"+Y"`` → ``(0, 1, 0)``, ``"-X"`` → ``(-1, 0, 0)``. A face's normal is
    deterministic for an axis-aligned box; for the M0 car example the wheel's
    spin axis is derived from this (the long edge direction), NOT hardcoded.
    """
    sign, axis = _parse_face(face)
    if axis == "X":
        return (float(sign), 0.0, 0.0)
    if axis == "Y":
        return (0.0, float(sign), 0.0)
    return (0.0, 0.0, float(sign))


def _parse_face(face: str) -> tuple[int, str]:
    if not isinstance(face, str) or len(face) != 2:
        raise MeasureError(
            f"face must be a 2-char string like '+Y' or '-X', got {face!r}")
    sign_ch, axis = face[0], face[1]
    if sign_ch not in _AXIS_SIGN:
        raise MeasureError(f"face sign must be '+' or '-', got {sign_ch!r}")
    if axis not in ("X", "Y", "Z"):
        raise MeasureError(f"face axis must be X/Y/Z, got {axis!r}")
    return _AXIS_SIGN[sign_ch], axis


# ── Edge parametric points ─────────────────────────────────────────


def measure_point_on_edge(
    geo, axes_a: str, axes_b: str, t: float
) -> tuple[float, float, float]:
    """Return a point at parameter ``t`` along a bbox edge.

    The edge runs between corner ``axes_a`` and corner ``axes_b`` (two sign
    strings like ``"+X-Y-Z"``). ``t=0`` is corner A, ``t=1`` is corner B,
    ``t=0.5`` is the midpoint. The two corners must differ on exactly ONE
    axis (a real bbox edge); differing on more is rejected.

    This is how a door can sit "at 30% along the front wall": pick the wall's
    two end corners and ``t=0.3``.
    """
    if not math.isfinite(float(t)):
        raise MeasureError(f"t must be finite, got {t!r}")
    t = float(t)
    if t < 0.0 or t > 1.0:
        raise MeasureError(f"t must be in [0, 1], got {t!r}")
    ca = measure_bbox_corner(geo, axes_a)
    cb = measure_bbox_corner(geo, axes_b)
    diffs = [i for i in range(3) if not math.isclose(ca[i], cb[i], abs_tol=1e-9)]
    if len(diffs) != 1:
        raise MeasureError(
            f"corners {axes_a!r} and {axes_b!r} are not a single bbox edge "
            f"(differ on {len(diffs)} axes)")
    return tuple(ca[i] + (cb[i] - ca[i]) * t for i in range(3))  # type: ignore[return-value]


# ── Multi-point sampling (M1) ──────────────────────────────────────
#
# M0's measurements each return ONE point. The keyboard exposed the gap: a
# face is a 2D region, and placing a GRID of keys on it needs MANY points in
# the face's interior (not just its boundary or center). These two functions
# return LISTS of points, and the assembly builder fans a single leaf out to
# N instances placed at them. Two flavors:
#   - grid_on_face : an M×N lattice across a bbox FACE (keyboard keys, windows
#     on a wall, tiles on a floor). Defined by face + row/col counts + margin.
#   - array        : a 1D/2D/3D lattice along arbitrary directions from an
#     origin point (stair treads, railing balusters, a shelf of books). More
#     general than grid_on_face but asks the caller to name the step directions.


def measure_grid_on_face(
    geo,
    face: str,
    rows: int,
    cols: int,
    margin: float = 0.0,
) -> list[tuple[float, float, float]]:
    """Sample an ``rows × cols`` grid of points across one bbox face.

    ``face`` names the face (``"+Y"`` = top, ``"-Z"`` = front, etc.). The grid
    is laid out in the face's two in-plane axes, with each cell centered and
    ``margin`` inset from the face edges on all sides (so keys don't kiss the
    tray rim). Returns ``rows*cols`` points in row-major order (row 0 first,
    col 0 first within a row). This is how a keyboard lays out its key grid
    on the tray's ``+Y`` face, and how windows tile a building wall.

    The in-plane axes are the two axes OTHER than the face's axis. Row/col
    orientation: rows step along the FIRST in-plane axis (lowest axis index),
    cols along the second. For ``+Y`` that is rows→X, cols→Z.
    """
    rows = int(rows)
    cols = int(cols)
    if rows < 1 or cols < 1:
        raise MeasureError(f"grid needs rows>=1 and cols>=1, got {rows}x{cols}")
    margin = float(margin)
    if margin < 0.0:
        raise MeasureError(f"margin must be >= 0, got {margin}")

    sign, axis = _parse_face(face)
    b = measure_bbox(geo)
    # The two in-plane axes (everything but `axis`), in axis-index order.
    idxs = [i for i in range(3) if "XYZ"[i] != axis]
    if len(idxs) != 2:
        raise MeasureError("a face has exactly two in-plane axes")
    a0, a1 = idxs  # rows step along a0, cols along a1

    # For each in-plane axis, the usable span after margin, and the cell size.
    # Points are placed at cell CENTERS: cell i of N spans
    #   [lo + margin + i*cell, lo + margin + (i+1)*cell], center at +cell/2.
    def cell_centers(lo: float, hi: float, n: int) -> list[float]:
        span = (hi - lo) - 2.0 * margin
        if span <= 0.0:
            raise MeasureError(
                f"margin {margin} leaves no room on the face "
                f"(span {hi - lo} - 2*margin)")
        cell = span / n
        return [lo + margin + cell * (i + 0.5) for i in range(n)]

    centers0 = cell_centers(b["min"][a0], b["max"][a0], rows)
    centers1 = cell_centers(b["min"][a1], b["max"][a1], cols)
    # The face's own axis coordinate (the extreme).
    face_val = b["max"][_axis_index(axis)] if sign > 0 else b["min"][_axis_index(axis)]

    out: list[tuple[float, float, float]] = []
    for r in range(rows):
        for c in range(cols):
            p = [0.0, 0.0, 0.0]
            p[_axis_index(axis)] = face_val
            p[a0] = centers0[r]
            p[a1] = centers1[c]
            out.append((p[0], p[1], p[2]))
    return out


def measure_array(
    origin: Sequence[float],
    count: Sequence[int],
    step: Sequence[Sequence[float]],
) -> list[tuple[float, float, float]]:
    """Sample a 1D/2D/3D lattice of points stepping from ``origin``.

    ``count`` is per-lattice-axis instance counts (e.g. ``[3,1,1]`` = a 1D run
    of 3). ``step`` is the FULL 3D displacement applied per index along each
    lattice axis (parallel to count), so a step can move diagonally — a stair
    tread advances in X AND climbs in Y with one step vector. The lattice is
    centered on ``origin`` (its middle), not anchored at a corner, so it stays
    balanced around its origin for odd/even counts.

    This is how stair treads march up a diagonal, or how railing balusters
    line up. Unlike :func:`measure_grid_on_face` the steps are arbitrary
    vectors (not tied to a bbox face), so an array can climb diagonally.

    ``step`` vectors may carry expressions in the assembly layer (resolved to
    numbers before this function sees them); here they are plain floats.
    """
    if len(origin) != 3:
        raise MeasureError("origin must be a 3-tuple")
    if len(count) != 3 or len(step) != 3:
        raise MeasureError("count and step must each be length 3")
    counts = [int(c) for c in count]
    if any(c < 1 for c in counts):
        raise MeasureError(f"count entries must be >= 1, got {list(counts)}")
    steps = []
    for i, s in enumerate(step):
        if len(s) != 3:
            raise MeasureError(f"step[{i}] must be a 3-vector, got {s!r}")
        steps.append((float(s[0]), float(s[1]), float(s[2])))

    ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])
    # Per lattice axis, the list of scalar multipliers of its step vector,
    # centered so origin sits at the array's middle.
    def axis_multipliers(n: int) -> list[float]:
        if n == 1:
            return [0.0]
        total = n - 1
        return [(-total / 2.0 + i) for i in range(n)]

    m0 = axis_multipliers(counts[0])
    m1 = axis_multipliers(counts[1])
    m2 = axis_multipliers(counts[2])
    out: list[tuple[float, float, float]] = []
    for a in m0:
        for b in m1:
            for c in m2:
                dx = steps[0][0] * a + steps[1][0] * b + steps[2][0] * c
                dy = steps[0][1] * a + steps[1][1] * b + steps[2][1] * c
                dz = steps[0][2] * a + steps[1][2] * b + steps[2][2] * c
                out.append((ox + dx, oy + dy, oz + dz))
    return out


def _axis_index(letter: str) -> int:
    return "XYZ".index(letter)


# ── Directions & orientation ───────────────────────────────────────


def direction_from_two_points(
    a: Sequence[float], b: Sequence[float]
) -> tuple[float, float, float]:
    """Unit direction from point ``a`` to point ``b``.

    The fundamental primitive for "the wheel's axle runs along the platform's
    long edge": measure two opposite corners, take their direction. Length
    zero is rejected (a degenerate edge can't define a direction).
    """
    if len(a) != 3 or len(b) != 3:
        raise MeasureError("points must be 3-tuples")
    dx, dy, dz = float(b[0]) - float(a[0]), float(b[1]) - float(a[1]), float(b[2]) - float(a[2])
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-9:
        raise MeasureError(f"points are coincident: {a!r} == {b!r}")
    return (dx / length, dy / length, dz / length)


def orient_to_align_y(
    direction: Sequence[float],
) -> tuple[float, float, float]:
    """Euler angles (degrees, XYZ) for a Houdini Transform ``r`` parm that
    rotate the geometry's default +Y axis onto ``direction``.

    This is the orientation a Y-axis-built leaf (a torus wheel built facing
    +Y) needs so it actually faces along ``direction``. The caller never
    writes a trig function — they pass a *measured* direction.

    The returned angles are applied by Houdini's xform ``r=(rx,ry,rz)`` in the
    intrinsic order Rx then Ry then Rz (so +Y is tilted by rx, swung by ry,
    then by rz). Since mapping a single axis needs only 2 DOF we set ry=0 and
    solve rx,rz so that the rotation sends (0,1,0) to ``direction``. The
    accompanying :func:`_verify_align_y` asserts this exact contract for every
    direction — geometry, not convention.
    """
    if len(direction) != 3:
        raise MeasureError("direction must be a 3-tuple")
    ux, uy, uz = float(direction[0]), float(direction[1]), float(direction[2])
    norm = math.sqrt(ux * ux + uy * uy + uz * uz)
    if norm < 1e-9:
        raise MeasureError("direction is the zero vector")
    ux, uy, uz = ux / norm, uy / norm, uz / norm

    # Houdini applies Rx then Rz (ry=0) to (0,1,0):
    #   after Rx by φ: (0, cosφ, sinφ)
    #   after Rz by ψ: (-sinψ·cosφ, cosψ·cosφ, sinφ)   [Rz mixes x,y only]
    # Match to (ux,uy,uz):
    #   sinφ = uz                      →  φ = asin(uz)
    #   -sinψ·cosφ = ux                →  ψ = atan2(-ux, uy)
    # (cosφ≥0 for φ in [-90,90], and uy/ux fix the yaw unambiguously.)
    phi = math.asin(max(-1.0, min(1.0, uz)))          # rx
    psi = math.atan2(-ux, uy)                          # rz
    if abs(math.cos(phi)) < 1e-9:
        # uz ≈ ±1: direction is straight up/down; ψ is irrelevant, pick 0.
        psi = 0.0
    return (math.degrees(phi), 0.0, math.degrees(psi))


def _verify_align_y(orient, direction) -> bool:
    """Self-check: does applying the XYZ Euler ``orient`` to +Y yield ``direction``?

    Mirrors Houdini's Transform ``r`` exactly — intrinsic Rx, then Ry, then Rz
    — applied to the +Y basis vector. Used by the test suite as the
    correctness contract for :func:`orient_to_align_y`.
    """
    rx, ry, rz = (math.radians(a) for a in orient)
    ux, uy, uz = (float(c) for c in direction)
    n = math.sqrt(ux * ux + uy * uy + uz * uz)
    ux, uy, uz = ux / n, uy / n, uz / n

    x, y, z = 0.0, 1.0, 0.0
    # Rx: mixes y,z.
    c, s = math.cos(rx), math.sin(rx)
    y, z = y * c - z * s, y * s + z * c
    # Ry: mixes x,z.
    c, s = math.cos(ry), math.sin(ry)
    x, z = x * c + z * s, -x * s + z * c
    # Rz: mixes x,y.
    c, s = math.cos(rz), math.sin(rz)
    x, y = x * c - y * s, x * s + y * c
    return (math.isclose(x, ux, abs_tol=1e-9)
            and math.isclose(y, uy, abs_tol=1e-9)
            and math.isclose(z, uz, abs_tol=1e-9))
