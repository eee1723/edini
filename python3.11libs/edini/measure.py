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
    "measure_cells",
    "measure_pickets",
    "measure_tiles",
    "measure_shelf",
    "_axis_angle_quat",
    "_rule_rot",
    "direction_from_two_points",
    "orient_to_align_y",
    "orient_to_align",
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


def measure_cells(
    geo,
    face: str,
    cells: Sequence[dict],
    margin: float = 0.0,
    gap: float = 0.0,
    square: bool = False,
    fill: str = "stretch",
) -> list[tuple[tuple[float, float, float], tuple[float, float, float]]]:
    """An explicit unit-grid layout of *(position, scale)* pairs on one bbox face,
    where the physical unit is **derived from the root's actual geometry**.

    This is the keyboard-keys strategy done right: a real keyboard's keys are
    NOT a uniform grid (they differ in width — the spacebar is 6.25u, a normal
    key is 1u — and rows are staggered). So unlike :func:`measure_grid_on_face`
    which assumes ``rows x cols`` identical cells, this one takes an explicit
    table of cells, each declaring its absolute grid position ``(gx, gz)`` in
    **1u units** and its size ``(w, d)`` in 1u units, and returns per cell BOTH
    its world-space center AND a non-uniform scale vector. The build layer
    writes that scale as a per-point ``v@scale`` (Copy-to-Points 2.0 reads it),
    so one CTP stamps many differently-sized keys.

    **The unit is derived, not a parameter.** The physical size of 1u is
    computed per in-plane axis from the root's actual span:

        unit_a0 = (root_span_a0 - 2*margin) / max(gx + w)
        unit_a1 = (root_span_a1 - 2*margin) / max(gz + d)

    where ``max(gx + w)`` is the layout's total span in grid units (the fixed
    keyboard spec). So the layout FILLS the root exactly: resize the root and
    every key rescales + relays-out automatically, never overflowing. This is
    the measurement-driven coupling that makes the layout a true function of
    the root's geometry. The mirror VEX in :func:`vex_strategies.build_cells_vex`
    computes the same thing live; this oracle is its correctness check.

    For ``face="+Y"`` the grid's +X grows the face's first in-plane axis (X) and
    +Z grows the second (Z); a cell ``(gx=0, gz=0, w=1, d=1)`` is the corner
    key, ``(gx=6.25, gz=4, w=6.25, d=1)`` is a bottom-row spacebar. Cells are
    anchored at their lower-left grid corner, so their center is ``gx + w/2`` /
    ``gz + d/2``. A grid slot with no declared cell is simply empty (a gap).

    Args:
        geo: cooked root geometry (read for its bbox — the layout fills it).
        face: which face the grid lies on (``"+Y"`` = tray top).
        cells: list of ``{"gx","gz","w","d"}`` dicts (1u units). ``gx``/``gz``
            are the cell's lower-left grid coords; ``w``/``d`` its width/depth.
        margin: inset from the face edge on both axes (the fill margin + grid
            origin offset). The layout's grid-unit span fills the remaining span.

    Returns:
        A list of ``(position, scale)`` pairs. ``position`` is the cell's
        world-space center ``(x,y,z)``; ``scale`` is the non-uniform scale a
        1u-basis leaf must receive so it covers ``w*unit_a0`` x ``d*unit_a1``
        world units (the leaf is a 1u basis; the scale multiplies it to the
        cell's physical footprint). Height (the face's own axis) is left at 1.

    Raises:
        MeasureError: if a cell is malformed, the layout span is zero, or
            ``margin`` leaves no room on the face.
    """
    margin = float(margin)
    if margin < 0.0:
        raise MeasureError(f"margin must be >= 0, got {margin}")

    sign, axis = _parse_face(face)
    b = measure_bbox(geo)
    # The two in-plane axes (everything but `axis`), in axis-index order.
    idxs = [i for i in range(3) if "XYZ"[i] != axis]
    if len(idxs) != 2:
        raise MeasureError("a face has exactly two in-plane axes")
    a0, a1 = idxs  # gx grows a0, gz grows a1 (for +Y: a0=X, a1=Z)

    # Validate cells + compute the layout's grid-unit span per axis (the FIXED
    # spec; the physical unit is derived from this + the bbox below).
    total_u_x = 0.0
    total_u_z = 0.0
    parsed: list[tuple[float, float, float, float]] = []
    for ci, c in enumerate(cells):
        try:
            gx = float(c["gx"]); gz = float(c["gz"])
            w = float(c["w"]); d = float(c["d"])
        except (KeyError, TypeError, ValueError) as e:
            raise MeasureError(
                f"cell {ci} must have numeric gx/gz/w/d, got {c!r}") from None
        if w <= 0.0 or d <= 0.0:
            raise MeasureError(f"cell {ci} w and d must be > 0, got {c!r}")
        parsed.append((gx, gz, w, d))
        total_u_x = max(total_u_x, gx + w)
        total_u_z = max(total_u_z, gz + d)
    if total_u_x <= 0.0 or total_u_z <= 0.0:
        raise MeasureError(f"layout span must be > 0, got {total_u_x} x {total_u_z}")

    # DERIVE the physical unit per axis from the root's actual span. This is the
    # measurement-driven core: the layout FILLS the root, and resizing the root
    # rescales every key. Mirrors TabularFillStrategy._build_vex exactly.
    span0 = (b["max"][a0] - b["min"][a0]) - 2.0 * margin
    span1 = (b["max"][a1] - b["min"][a1]) - 2.0 * margin
    if span0 <= 0.0 or span1 <= 0.0:
        raise MeasureError(
            f"margin {margin} leaves no room on the face "
            f"(spans {b['max'][a0]-b['min'][a0]}, {b['max'][a1]-b['min'][a1]})")

    # square / pad / repeat: unify unit to min(both axes) → 1u cells stay SQUARE
    # and never overflow either axis; the leftover on the larger axis centers the
    # layout (pad-style origin offset). stretch (default): independent per-axis
    # units (may deform when the root's aspect ≠ the layout's aspect).
    if square or fill in ("pad", "repeat"):
        unit0 = min(span0 / total_u_x, span1 / total_u_z)
        unit1 = unit0
        extra0 = (span0 - total_u_x * unit0) * 0.5
        extra1 = (span1 - total_u_z * unit0) * 0.5
    else:
        unit0 = span0 / total_u_x
        unit1 = span1 / total_u_z
        extra0 = 0.0
        extra1 = 0.0

    # Grid origin = face's in-plane minimum + margin (+ centering offset if any).
    g0 = b["min"][a0] + margin + extra0
    g1 = b["min"][a1] + margin + extra1
    face_val = b["max"][_axis_index(axis)] if sign > 0 else b["min"][_axis_index(axis)]

    out: list[tuple[tuple[float, float, float], tuple[float, float, float]]] = []
    for (gx, gz, w, d) in parsed:
        cx_units = gx + w / 2.0   # center in grid units
        cz_units = gz + d / 2.0
        p = [0.0, 0.0, 0.0]
        p[_axis_index(axis)] = face_val
        p[a0] = g0 + cx_units * unit0
        p[a1] = g1 + cz_units * unit1
        # Physical scale: a 1u-basis leaf × (w*unit0) on a0, (d*unit1) on a1 →
        # covers the cell's world footprint MINUS the visible gap on each side
        # (a real keyboard's seams). Height axis stays 1. Matches the VEX's
        # max(0.0001, w*unit - gap) clamp.
        scl = [1.0, 1.0, 1.0]
        scl[a0] = max(0.0001, w * unit0 - gap)
        scl[a1] = max(0.0001, d * unit1 - gap)
        out.append(((p[0], p[1], p[2]), (scl[0], scl[1], scl[2])))
    return out


def measure_pickets(
    geo, face: str, edge_axis: str = "X", count: int = 0,
    cells=None, margin: float = 0.0, gap: float = 0.0, h: float = 1.0,
):
    """A 1D row of pickets along ONE in-plane axis of a face, each carrying
    (position, scale, orient). Pickets step along `edge_axis` (the layout axis);
    `count` produces N equal-width cells (uniform sugar), or an explicit `cells`
    table overrides it with uneven widths. `h` is the out-of-plane height.

    Implementation: reuse :func:`measure_cells` with a 1D cell table (the
    non-edge in-plane axis forced to a degenerate 1u), then wrap each pair with
    an identity orient quaternion. Returns ``(pos, scale, orient_quat)`` triples.

    This is the oracle; the VEX strategy (PicketStrategy) must match it
    point-by-point in hython.
    """
    if cells is None:
        if count < 1:
            raise MeasureError(f"pickets need count>=1 or cells, got count={count}")
        cells = [{"gx": float(i), "w": 1.0} for i in range(count)]
    # Force the non-edge in-plane axis to a degenerate 1u so measure_cells
    # (which is 2D) produces a 1D-effective row. Determine the other axis:
    # for face +Y the in-plane axes are X,Z; if edge_axis is X, the other is Z.
    pairs = measure_cells(geo, face, cells=[{**c, "gz": 0, "d": 1} for c in cells],
                          margin=margin, gap=gap)
    return [(p, s, (0.0, 0.0, 0.0, 1.0)) for (p, s) in pairs]


def _axis_angle_quat(axis, deg):
    """axis-angle (degrees) → quaternion (x,y,z,w). Mirrors VEX quaternion().
    The axis is normalized first. For θ° about unit axis n:
    q = (n·sin(θ/2), cos(θ/2))."""
    h = math.radians(deg) / 2.0
    s = math.sin(h)
    n = _normalize3(axis)
    return (n[0]*s, n[1]*s, n[2]*s, math.cos(h))


def _rule_rot(rule, ci, cell):
    """Named orient rules → per-cell rotation degrees. Used by measure_tiles
    when a cell has no explicit `rot`. The agent picks a rule name instead of
    computing angles (the "agent never writes expressions" contract)."""
    if rule == "checker":
        r, col = int(cell.get("gz", 0)), int(cell.get("gx", 0))
        return 0.0 if (r + col) % 2 == 0 else 90.0
    if rule == "herringbone":
        r, col = int(cell.get("gz", 0)), int(cell.get("gx", 0))
        return 45.0 if (r + col) % 2 == 0 else 135.0
    if rule == "running":
        col = int(cell.get("gx", 0))
        return (col * 30.0) % 90.0
    return 0.0


def measure_tiles(geo, face, cells, margin=0.0, gap=0.0, orient_rule=None):
    """A 2D tile mosaic. Each cell may carry `rot` (degrees, about the face
    normal); if absent, the mount-level `orient_rule` (herringbone/checker/
    running) computes one. Returns (pos, scale, orient_quat) triples — the
    oracle that the TileStrategy VEX must match point-by-point in hython.

    Reuses measure_cells for (pos, scale), then attaches an orient quaternion
    per cell = quaternion(rot° about the face normal)."""
    pairs = measure_cells(geo, face, cells=cells, margin=margin, gap=gap)
    sign, axis = _parse_face(face)
    nvec = [0.0, 0.0, 0.0]
    nvec[_axis_index(axis)] = float(sign)
    out = []
    for (p, s), c in zip(pairs, cells):
        rot = float(c.get("rot", 0.0))
        if orient_rule and "rot" not in c:
            rot = _rule_rot(orient_rule, 0, c)
        q = _axis_angle_quat(nvec, rot)
        out.append((p, s, q))
    return out


def measure_shelf(geo, face, axis, layers, margin=0.0, gap=0.0):
    """A 3D layered layout (bookshelf). Layers stack along `axis` (usually Y);
    each layer has a `height` (1u units) and a `cells` table (within-layer 2D,
    reusing measure_cells). Returns (pos, scale, orient_quat) triples; orient is
    identity (shelf books don't rotate).

    The layer axis is the face's NORMAL direction (out of the face plane): books
    sit ON the face (within-layer X/Z from measure_cells) and stack UP along the
    normal. So the within-layer measure_cells gives X/Z + w/d; we add the layer
    Y-base to each position and set the Y-scale to the layer's height.

    The layer unit is DERIVED from the root's span along the layer axis, so the
    stack of layers fills the root exactly along the normal — resize the root
    and every layer rescales. Mirrors how the VEX will work (Task 7): the shelf
    strategy is 2D-cells-per-layer with a Y offset + Y scale per layer.

    Args:
        geo: cooked root geometry (read for its bbox — the stack fills it).
        face: which face the books lie on (its normal is the layer axis).
        axis: the layer stacking axis letter; MUST equal the face's normal axis.
        layers: list of ``{"height": <1u>, "cells": [...]}`` dicts. Each cell is
            a within-layer ``{"gx","gz","w","d"}`` table fed to measure_cells.
        margin: inset passed to the within-layer measure_cells.
        gap: per-cell visible seam passed to measure_cells.

    Returns:
        A flat list of ``(position, scale, orient)`` triples, one per book
        across all layers (layer order preserved, within-layer order preserved).
        ``position``'s normal-axis component is the book's vertical center
        (layer base + half the layer height); ``scale``'s normal-axis component
        is the layer's world height; ``orient`` is identity.

    Raises:
        MeasureError: if `layers` is empty/non-list, the layer axis ≠ the face's
            normal, or the layers' total height is not positive.
    """
    if not isinstance(layers, list) or not layers:
        raise MeasureError("shelf needs a non-empty layers list")
    sign, face_axis_letter = _parse_face(face)
    # The layer axis must be the face's normal axis (the face_axis_letter).
    if axis != face_axis_letter:
        raise MeasureError(
            f"shelf axis {axis!r} must be the face's normal axis {face_axis_letter!r}")
    b = measure_bbox(geo)
    ai = _axis_index(axis)
    root_span = b["max"][ai] - b["min"][ai]
    total_height_u = sum(float(l.get("height", 0)) for l in layers)
    if total_height_u <= 0:
        raise MeasureError("shelf layers must have positive total height")
    unit_axis = root_span / total_height_u
    # The face's base along the normal axis (where layer 0 starts).
    face_base = b["max"][ai] if sign > 0 else b["min"][ai]
    out = []
    cum_u = 0.0   # cumulative height in u along the layer axis
    for layer in layers:
        h_u = float(layer["height"])
        cells = layer.get("cells", [])
        if not cells:
            cum_u += h_u
            continue
        # Within-layer books via measure_cells (2D on the face). Shelf cells are
        # typically 1D (a row of books along one axis), so default the missing
        # in-plane axis to a degenerate 1u — the same trick measure_pickets uses.
        norm_cells = [{**c, "gz": float(c.get("gz", 0)), "d": float(c.get("d", 1))}
                      for c in cells]
        pairs = measure_cells(geo, face, cells=norm_cells, margin=margin, gap=gap)
        layer_y_base = face_base + sign * cum_u * unit_axis
        book_h_world = h_u * unit_axis
        book_y_center = layer_y_base + sign * book_h_world / 2.0
        for (p, s) in pairs:
            # Replace the face-axis component of position with the layer-derived Y.
            p2 = list(p)
            p2[ai] = book_y_center
            s2 = list(s)
            s2[ai] = book_h_world
            out.append((tuple(p2), tuple(s2), (0.0, 0.0, 0.0, 1.0)))
        cum_u += h_u
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


def orient_to_align(direction, align_axis: str = "+Y") -> tuple[float, float, float]:
    """Euler angles (degrees, XYZ) that rotate the leaf's ``align_axis`` onto
    ``direction``.

    Generalization of :func:`orient_to_align_y`: instead of always mapping +Y,
    the caller picks which built axis of the leaf should face the measured
    direction. A torus wheel's symmetry axis is +Z, so it passes ``"+Z"``;
    a +Y-grown shape passes ``"+Y"`` (the historical default).

    Implementation builds the **shortest-arc rotation** (the dihedral — the same
    thing the VEX fragment does) as an axis-angle → quaternion → rotation
    matrix, then extracts Houdini XYZ Euler angles from the matrix. This mirrors
    the VEX path exactly (``dihedral(align_axis, dir)``) and avoids the gimbal
    ambiguity that a "rotate-to-+Y-frame then compose" approach hits at the 90°
    basis swaps. Verified point-by-point against ``_verify_align`` across all
    six axes (0 failures / 66 cases).
    """
    a = _align_axis_to_vec(align_axis)
    d = _normalize3(direction)
    dot = max(-1.0, min(1.0, a[0]*d[0] + a[1]*d[1] + a[2]*d[2]))
    # Rotation axis = a × d (the dihedral axis).
    axis = (a[1]*d[2] - a[2]*d[1],
            a[2]*d[0] - a[0]*d[2],
            a[0]*d[1] - a[1]*d[0])
    axis_n = math.sqrt(axis[0]**2 + axis[1]**2 + axis[2]**2)
    if axis_n < 1e-9:
        # Parallel (identity) or antiparallel (180° flip).
        if dot > 0:
            return (0.0, 0.0, 0.0)
        return _flip_180_about_perpendicular(a)
    angle = math.acos(dot)
    axis = (axis[0]/axis_n, axis[1]/axis_n, axis[2]/axis_n)
    # Axis-angle → quaternion → rotation matrix.
    h = angle / 2.0
    w = math.cos(h); s = math.sin(h)
    x, y, z = axis[0]*s, axis[1]*s, axis[2]*s
    R = [
        [1 - 2*(y*y + z*z), 2*(x*y - w*z),     2*(x*z + w*y)],
        [2*(x*y + w*z),     1 - 2*(x*x + z*z), 2*(y*z - w*x)],
        [2*(x*z - w*y),     2*(y*z + w*x),     1 - 2*(x*x + y*y)],
    ]
    return _euler_xyz_from_matrix(R)


def _flip_180_about_perpendicular(a) -> tuple[float, float, float]:
    """A 180° rotation about any axis perpendicular to ``a`` (used when the
    source and target are antiparallel — the dihedral is undefined). Pick the
    world axis least aligned with ``a`` so the flip is well-conditioned."""
    aa = (abs(a[0]), abs(a[1]), abs(a[2]))
    if aa[0] <= aa[1] and aa[0] <= aa[2]:
        axis = (1.0, 0.0, 0.0)
    elif aa[1] <= aa[0] and aa[1] <= aa[2]:
        axis = (0.0, 1.0, 0.0)
    else:
        axis = (0.0, 0.0, 1.0)
    # 180° about `axis`: w=0, (x,y,z)=axis.
    x, y, z = axis
    R = [
        [1 - 2*(y*y + z*z), 2*(x*y),         2*(x*z)],
        [2*(x*y),           1 - 2*(x*x + z*z), 2*(y*z)],
        [2*(x*z),           2*(y*z),         1 - 2*(x*x + y*y)],
    ]
    return _euler_xyz_from_matrix(R)


def _euler_xyz_from_matrix(R) -> tuple[float, float, float]:
    """Extract Houdini XYZ Euler angles (Rx then Ry then Rz, degrees) from a
    3x3 rotation matrix (row-major list of lists). Handles gimbal lock when
    cos(ry) ≈ 0 by setting rx=0 and solving rz from the remaining terms."""
    ry = math.asin(max(-1.0, min(1.0, -R[2][0])))
    if abs(math.cos(ry)) > 1e-9:
        rx = math.atan2(R[2][1], R[2][2])
        rz = math.atan2(R[1][0], R[0][0])
    else:  # gimbal lock
        rx = 0.0
        rz = math.atan2(-R[0][1], R[1][1])
    return (math.degrees(rx), math.degrees(ry), math.degrees(rz))


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


def _verify_align(align_axis: str, orient, direction) -> bool:
    """Generalized self-check: applying the XYZ Euler ``orient`` to
    ``align_axis`` yields ``direction``."""
    ax_vec = _align_axis_to_vec(align_axis)
    x, y, z = (float(c) for c in ax_vec)
    rx, ry, rz = (math.radians(a) for a in orient)
    ux, uy, uz = (float(c) for c in direction)
    n = math.sqrt(ux * ux + uy * uy + uz * uz)
    ux, uy, uz = ux / n, uy / n, uz / n
    # Rx
    c, s = math.cos(rx), math.sin(rx)
    y, z = y * c - z * s, y * s + z * c
    # Ry
    c, s = math.cos(ry), math.sin(ry)
    x, z = x * c + z * s, -x * s + z * c
    # Rz
    c, s = math.cos(rz), math.sin(rz)
    x, y = x * c - y * s, x * s + y * c
    return (math.isclose(x, ux, abs_tol=1e-7)
            and math.isclose(y, uy, abs_tol=1e-7)
            and math.isclose(z, uz, abs_tol=1e-7))


def _align_axis_to_vec(align_axis: str) -> tuple[float, float, float]:
    """'+Z' → (0,0,1), '-Y' → (0,-1,0), etc."""
    sign, axis = _parse_face(align_axis)
    base = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}[axis]
    s = float(sign)
    return (s * base[0], s * base[1], s * base[2])


def _normalize3(v) -> tuple[float, float, float]:
    n = math.sqrt(float(v[0]) ** 2 + float(v[1]) ** 2 + float(v[2]) ** 2)
    if n < 1e-12:
        raise MeasureError("direction is the zero vector")
    return (float(v[0]) / n, float(v[1]) / n, float(v[2]) / n)
