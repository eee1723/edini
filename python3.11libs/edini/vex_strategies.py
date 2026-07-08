"""VEX strategy library — pre-built, pre-tested VEX per measurement primitive.

This is the heart of the **live** build layer (M2). Instead of measuring the
root once and baking concrete coordinates into Transform nodes (which then
never update when a param changes), each mount becomes an ``attribwrangle``
running one of these strategies. The wrangle reads the root's bbox live via
``getbbox_min/max`` and emits point(s) carrying ``@P``, ``p@orient`` (a
quaternion), and ``@pscale``. A downstream Copy-to-Points stamps the leaf
shape onto those points. Change a root param → the bbox re-cooks → the wrangle
re-runs → the points move → the copies re-stamp. Zero baked coordinates.

Why pre-built VEX and not LLM-authored VEX
------------------------------------------
This project's history: LLM-authored VEX was the #1 failure mode of the old
procedural pipeline (high error rate). The fix is the OPPOSITE of asking the
LLM to write VEX: **we write and test each strategy once**, the agent only
chooses ``measure: "grid_on_face"`` + parameters. The agent never writes a
line of VEX. Correctness is ours to guarantee, and we do it two ways:
  1. hython: each strategy cooks against real Houdini 21.
  2. Python oracle: ``measure.py`` computes the expected point set; the test
     compares it to the VEX output point-by-point. (measure.py is kept as the
     oracle, NOT as the build path.)

Sign-string resolution
----------------------
The mount spec uses human-friendly sign-strings (``"+X-Y+Z"`` corner,
``"+Y"`` face). VEX has no clean string parser, so Python resolves each
sign-string to numeric selectors and injects them as ``ch()``-driven spare
parms on the wrangle (``cx/cy/cz`` 0/1 for corner min/max choice,
``face_axis/face_sign`` for face). The VEX stays clean and parameter-driven.

Orientation
-----------
Copy-to-Points 2.0 reads ``p@orient`` (a quaternion) as its canonical
instance-orientation attribute. Every strategy that needs facing emits it via
``dihedral({0,1,0}, normalize(dir))`` — the one-line VEX equivalent of
``measure.orient_to_align_y``, computing the shortest-arc rotation that maps
the leaf's built +Y axis onto the measured direction. ``@orient`` is preferred
over ``@N``+``@up`` (which is the Sweep convention) precisely because CTP
reads it directly and unambiguously.
"""
from __future__ import annotations

from typing import Any

from edini.measure import _parse_axes, _parse_face


class VexStrategyError(ValueError):
    """Raised when a mount spec cannot be turned into a VEX strategy."""


class VexStrategy:
    """Base contract for a measurement strategy.

    Subclasses implement :meth:`build` to turn a mount ``position`` spec into a
    ``(snippet, parms)`` pair. The snippet is a detail-wrangle body that MUST
    begin with :data:`_VEX_CLEAR` (so the orient fragment can be appended) and
    MUST emit every point via ``append(__newpts, addpoint(...))``. ``parms`` is
    a dict of spare-parm name → value the builder installs on the wrangle node.
    """

    def build(self, position_spec: dict) -> tuple[str, dict[str, Any]]:
        raise NotImplementedError


# ── Sign-string → numeric selector resolution ──────────────────────


def _corner_selectors(axes: str) -> dict[str, int]:
    """Resolve "+X-Y+Z" → {"cx":1,"cy":0,"cz":1} (1=max, 0=min per axis).

    This is the bridge from the human sign-string to the VEX ``ch("cx")``
    selector. ``lerp(min, max, cx)`` reproduces ``hi if sign>0 else lo``.
    """
    parsed = _parse_axes(axes)  # {"X":+1,"Y":-1,"Z":+1} — validates too
    return {
        "cx": 1 if parsed["X"] > 0 else 0,
        "cy": 1 if parsed["Y"] > 0 else 0,
        "cz": 1 if parsed["Z"] > 0 else 0,
    }


def _face_selector(face: str) -> dict[str, int]:
    """Resolve "+Y" → {"face_axis":1, "face_sign":1} (axis 0/1/2 = X/Y/Z)."""
    sign, axis = _parse_face(face)
    return {"face_axis": "XYZ".index(axis), "face_sign": 1 if sign > 0 else -1}


# ── VEX templates ──────────────────────────────────────────────────
#
# Each template is a detail-wrangle body. It reads the root's bbox from input 0
# and emits point(s). The FIRST line clears the input geometry's points so the
# wrangle OUTPUT is only the freshly-emitted mount points (a detail wrangle
# otherwise passes through the box's 8 corner points). Position comes from
# getbbox_min/max arithmetic; orient from dihedral; pscale from a ch() the
# builder sets. Numeric selectors arrive as ch() values the builder installs as
# spare parms, so the SAME node re-cooks correctly when a param changes — the
# bbox is read live, nothing is baked.
#
# The clear idiom: collect every existing point id and remove it. Using
# expandpointid + foreach(removepoint) is the portable H21 way to drop all
# incoming points while keeping the detail (so addpoint has somewhere to write).

_VEX_CLEAR = r"""
// Drop the input geometry's points — the wrangle output is ONLY the emitted
// mount points (otherwise the source box's corners pass through). Remove from
// the high end down so indices stay valid as we delete. Also declare the
// __newpts[] array that EVERY addpoint in this wrangle appends its returned
// point number to — the orient fragment (appended below) writes onto THESE
// points, NOT on a npoints() range: in a detail wrangle npoints() does NOT
// reflect points addpoint'd during the same cook, so a range loop would miss
// them and leave their orient at the default identity quaternion.
int __n = npoints(geoself());
for (int __i = __n - 1; __i >= 0; __i--) { removepoint(geoself(), __i); }
int __newpts[];
""".strip()

# bbox_corner: one point at a chosen corner. cx/cy/cz ∈ {0,1} pick min/max.
_VEX_BBOX_CORNER = _VEX_CLEAR + r"""
vector mn = getbbox_min(0);
vector mx = getbbox_max(0);
vector p = set(lerp(mn.x, mx.x, chi("cx")),
               lerp(mn.y, mx.y, chi("cy")),
               lerp(mn.z, mx.z, chi("cz")));
append(__newpts, addpoint(0, p));
""".strip()

# bbox_face_center: one point at the center of a face. face_axis∈{0,1,2},
# face_sign∈{-1,+1}. The face's own axis takes the extreme; the other two take
# the bbox midpoint.
_VEX_BBOX_FACE_CENTER = _VEX_CLEAR + r"""
vector ctr = getbbox_center(0);
vector mn = getbbox_min(0);
vector mx = getbbox_max(0);
int fa = chi("face_axis");
float fs = ch("face_sign");
vector p = ctr;
p[fa] = (fs > 0) ? mx[fa] : mn[fa];
append(__newpts, addpoint(0, p));
""".strip()

# bbox_center: one point at the bbox midpoint.
_VEX_BBOX_CENTER = _VEX_CLEAR + r"""
append(__newpts, addpoint(0, getbbox_center(0)));
""".strip()

# point_on_edge: lerp between two corners (each by its own cx/cy/cz) at t∈[0,1].
# The two corners must differ on exactly one axis (validated on the Python side).
_VEX_POINT_ON_EDGE = _VEX_CLEAR + r"""
vector mn = getbbox_min(0);
vector mx = getbbox_max(0);
vector a = set(lerp(mn.x, mx.x, chi("cax")), lerp(mn.y, mx.y, chi("cay")), lerp(mn.z, mx.z, chi("caz")));
vector b = set(lerp(mn.x, mx.x, chi("cbx")), lerp(mn.y, mx.y, chi("cby")), lerp(mn.z, mx.z, chi("cbz")));
append(__newpts, addpoint(0, lerp(a, b, ch("t"))));
""".strip()

# grid_on_face: an rows×cols lattice of cell centers on a face. margin-inset,
# row-major (rows step along the first in-plane axis, cols along the second).
# This is the keyboard keys / wall-windows strategy.
_VEX_GRID_ON_FACE = _VEX_CLEAR + r"""
vector mn = getbbox_min(0);
vector mx = getbbox_max(0);
int   fa = chi("face_axis");
float fs = ch("face_sign");
int   rows = chi("rows");
int   cols = chi("cols");
float m = ch("margin");

// in-plane axes: the two axes other than fa, in index order (a0 < a1).
int a0 = -1, a1 = -1, seen = 0;
for (int i = 0; i < 3; i++) { if (i != fa) { if (seen == 0) a0 = i; else a1 = i; seen++; } }

float face_val = (fs > 0) ? mx[fa] : mn[fa];
float span0 = (mx[a0] - mn[a0]) - 2 * m;
float span1 = (mx[a1] - mn[a1]) - 2 * m;
float cell0 = span0 / rows;
float cell1 = span1 / cols;
for (int r = 0; r < rows; r++) {
    for (int c = 0; c < cols; c++) {
        vector p = {0, 0, 0};
        p[fa] = face_val;
        p[a0] = mn[a0] + m + cell0 * (r + 0.5);
        p[a1] = mn[a1] + m + cell1 * (c + 0.5);
        append(__newpts, addpoint(0, p));
    }
}
""".strip()

# array: a centered lattice stepping from an origin by per-axis 3D vectors.
# count[3] + step[3 vectors]. Diagonal steps allowed (stairs climb X+Y). The
# multiplier (i-(n-1)/2) centers the array on the origin — mirrors measure.py.
_VEX_ARRAY = _VEX_CLEAR + r"""
vector origin = chv("origin");
int   nx = chi("countx"), ny = chi("county"), nz = chi("countz");
vector s0 = chv("step0"), s1 = chv("step1"), s2 = chv("step2");
for (int i = 0; i < nx; i++) {
    float a = (nx == 1) ? 0.0 : (i - (nx - 1) / 2.0);
    for (int j = 0; j < ny; j++) {
        float b = (ny == 1) ? 0.0 : (j - (ny - 1) / 2.0);
        for (int k = 0; k < nz; k++) {
            float c = (nz == 1) ? 0.0 : (k - (nz - 1) / 2.0);
            vector p = origin + a * s0 + b * s1 + c * s2;
            append(__newpts, addpoint(0, p));
        }
    }
}
""".strip()


# by_name: pick a SEMANTIC marker point that the root component's generator
# already emitted at a REAL geometric location (not a bbox derivation).
#
# This is the cure for the "bbox_face_center on a merged mesh ≠ real dropout"
# failure (session log 2, road bike frame). A root generator (e.g. the frame's
# Python SOP) emits a point tagged @name="head_tube_top" at the ACTUAL head-tube
# top coordinate; the downstream anchor uses measure:"by_name" + marker:"head_tube_top"
# to pick THAT exact point. Change frame_scale → the generator re-cooks → the
# marker moves with the real geometry → the anchor follows. Truly parametric,
# unlike bbox_face_center which tracks the merged-mesh hull.
#
# Unlike the bbox strategies, this does NOT begin with _VEX_CLEAR. It must
# PRESERVE the named input point's position. So it captures the matched point's
# P (+ orient, if the generator supplied one) in a single scan, drops ALL input
# points, then re-emits ONLY the marker. __newpts is declared so the orient
# fragment and the builder's @name tag still apply to the re-emitted point.
_VEX_BY_NAME = r"""
int __n = npoints(geoself());
string __marker = chs("marker");
vector __pos = {0, 0, 0};
vector4 __ori = {0, 0, 0, 1};   // identity quaternion default
int __has_ori = 0;
int __found = 0;
for (int __i = 0; __i < __n; __i++) {
    string __nm = pointattrib(geoself(), "name", __i, 0);
    if (__nm == __marker && !__found) {
        __pos = pointattrib(geoself(), "P", __i, 0);
        // Preserve a generator-supplied orient if present (identity otherwise).
        int __nh = hasattrib(geoself(), "point", "orient");
        if (__nh) {
            __ori = pointattrib(geoself(), "orient", __i, 0);
            __has_ori = 1;
        }
        __found = 1;
    }
}
// Clear all input points, then re-emit ONLY the matched marker.
for (int __i = __n - 1; __i >= 0; __i--) { removepoint(geoself(), __i); }
int __newpts[];
if (__found) {
    int __pt = addpoint(geoself(), __pos);
    if (__has_ori) {
        setpointattrib(geoself(), "orient", __pt, __ori, "set");
    }
    append(__newpts, __pt);
} else {
    // FAIL FAST: a zero-match is almost always a typo'd marker or a generator
    // that forgot to emit @name=<marker>. Emitting zero points silently would
    // leave the agent unable to tell "marker not found" from "upstream empty"
    // (session-logs-analysis finding 3 audit). error() makes this surface via
    // node.errors(), which inspect_health / verify_parametric already read.
    error(sprintf("by_name anchor: marker '%s' not found in upstream geometry (typo? generator did not emit @name=%s?)\n", __marker, __marker));
}
""".strip()


# cells: an explicit unit-grid layout where each cell has its OWN size, and
# every size + position is DERIVED live from the root's actual geometry.
#
# Unlike grid_on_face (N identical cells), this is the keyboard-keys strategy
# done right: the agent declares a table of {gx,gz,w,d} cells in 1u units, and
# the strategy emits one point per cell — each carrying a non-uniform v@scale
# (w on the first in-plane axis, d on the second). Copy-to-Points 2.0 reads
# v@scale per instance, so ONE CTP stamps many differently-sized keys (a 1u
# key + a 6.25u spacebar from a single 1u leaf shape).
#
# MEASUREMENT-DRIVEN COUPLING (the key property): the physical size of 1u is
# NOT a free parameter. It is DERIVED live in VEX from the root's actual span:
#     unit_x = (root_span_x - 2*margin) / layout_total_u_x
# where layout_total_u_x = max(gx+w) is the layout's span in grid units (the
# fixed keyboard spec, baked at build). So scaling the root → unit re-derives →
# every key rescales AND relays-out to FILL the root exactly, never overflowing.
# This is what makes the cells layout a true function of the root's geometry,
# not a free parameter the user must keep in sync.
#
# The layout TABLE (which keys, which sizes) is baked at build (mirrors array
# step). margin is a live spare (the grid-origin inset + fill margin). face +
# in-plane axes are resolved by Python (face_axis/face_sign spares) and the
# per-cell code is LOOP-UNROLLED by the builder below (VEX has no JSON parser;
# Python walks the cells table and emits one block per cell, with gx/gz/w/d
# inlined as literals — exactly how the orient fragment inlines its selectors).
class TabularFillStrategy(VexStrategy):
    """Table-driven (position, size) layouts that FILL a region of the root.

    The layout is an explicit table of cells (the schema is defined by the
    subclass — :class:`CellsStrategy` uses ``{gx,gz,w,d}``). This base class
    encodes the table as VEX **array literals** (the data) and runs a single
    compact **loop** over them (the code), so the generated VEX is ~30 lines
    regardless of cell count. It derives the per-axis physical unit from the
    root's actual span (measurement-driven: the layout FILLS the root and
    rescales when the root resizes), writes a per-point ``v@scale`` so one CTP
    stamps many differently-sized instances, and applies the shape constraint
    + fill mode.

    Shape constraint (``square``): when true, the per-axis unit is unified to
    ``min(unit_a0, unit_a1)`` so a 1u cell is physically SQUARE (no axis
    stretching). This matches a real keyboard's 1u = 19mm in both X and Z.

    Fill mode (``fill``): how to handle non-divisible leftover space.
      - ``stretch`` (default): unit = span/total_u per axis (independent; may
        deform when square=False, or underfill one axis when square=True).
      - ``pad``: unit = min(both axes); leftover space stays empty on the
        larger axis (the grid origin centers the layout). Keys stay square.
      - ``repeat``: like pad for the unit, but the builder PRE-EXPANDS the cell
        table (Python layer) with extra 1u cells to fill the leftover — so the
        VEX loop is unchanged, only fed a longer table.

    Subclasses provide :meth:`_parse_table` (spec → validated (centers, sizes)
    arrays) and :meth:`_table_totals` (the layout's grid-unit span per axis).
    """

    def build(self, position_spec: dict) -> tuple[str, dict[str, Any]]:
        cells = position_spec.get("cells")
        if not isinstance(cells, list) or not cells:
            raise VexStrategyError("cells strategy needs a non-empty 'cells' list")
        square = bool(position_spec.get("square", False))
        fill = str(position_spec.get("fill", "stretch"))
        if fill not in ("stretch", "pad", "repeat"):
            raise VexStrategyError(
                f"cells.fill must be stretch|pad|repeat, got {fill!r}")

        gx_vals, gz_vals, w_vals, d_vals = self._parse_table(cells)
        total_u_x, total_u_z = self._table_totals(gx_vals, gz_vals, w_vals, d_vals)

        # Resolve face → face_axis/face_sign (same selector as grid_on_face).
        # _resolve_face reads basis.face (new) or the legacy face field, so the
        # existing 2D cells spec (which uses bare `face`) is unchanged.
        face = self._resolve_face(position_spec)
        fparms = _face_selector(face)
        parms: dict[str, Any] = {"face_axis": fparms["face_axis"],
                                 "face_sign": fparms["face_sign"]}
        # margin + gap are live spares (grid inset + visible seam). square/fill
        # are baked into the VEX template choice below (not live spares): they
        # change the structure of the unit-derivation, not a runtime value.
        parms["_margin"] = position_spec.get("margin", 0.0)
        parms["_gap"] = position_spec.get("gap", 0.0)

        snippet = self._build_vex(gx_vals, gz_vals, w_vals, d_vals,
                                  total_u_x, total_u_z, square, fill)
        return snippet, parms

    # ── Subclass hooks ───────────────────────────────────────────────
    def _parse_table(self, cells: list[dict]
                     ) -> tuple[list[float], list[float], list[float], list[float]]:
        """Validate the cell table → (gx[], gz[], w[], d[]) value lists."""
        raise NotImplementedError

    def _table_totals(self, gx, gz, w, d) -> tuple[float, float]:
        """The layout's grid-unit span per in-plane axis (max gx+w, max gz+d)."""
        return (max(gx_ + w_ for gx_, w_ in zip(gx, w)),
                max(gz_ + d_ for gz_, d_ in zip(gz, d)))

    # ── Spec field resolution (new in M-tabular-fill) ────────────────
    @staticmethod
    def _resolve_face(position_spec: dict) -> str:
        """Resolve the face string from `basis.face` (new) or the legacy bare
        `face` field. The bare `face` path is unchanged so existing 2D cells
        specs produce byte-identical VEX."""
        basis = position_spec.get("basis")
        if isinstance(basis, dict) and isinstance(basis.get("face"), str):
            return basis["face"]
        face = position_spec.get("face")
        if isinstance(face, str):
            return face
        raise VexStrategyError(
            "position needs a face: give basis.face or a bare face field")

    # ── VEX generation ───────────────────────────────────────────────
    @staticmethod
    def _arr(vals) -> str:
        """Format a Python list as a VEX array-LITERAL body: {a, b, c};"""
        return "{" + ", ".join(repr(v) for v in vals) + "};"

    def _build_vex(self, gx_vals, gz_vals, w_vals, d_vals,
                   total_u_x, total_u_z, square, fill) -> str:
        """Generate the compact-loop VEX for the given table + constraints.

        The unit-derivation block depends on (square, fill): stretch uses the
        per-axis units independently; square/pad unify them to min. The loop
        body is shared (data/code decoupled). Mirrors measure.measure_cells.
        """
        # The unit-derivation block. stretch (no square): independent per-axis
        # units (may deform when the root's aspect ≠ the layout's aspect).
        # square / pad / repeat: unify unit to min(unit0, unit1) so 1u cells stay
        # SQUARE and never overflow either axis; the leftover space on the larger
        # axis is split to CENTER the layout (pad-style). repeat additionally
        # pre-expands the table (builder layer) so the leftover gets filled.
        if square or fill in ("pad", "repeat"):
            unit_block = (
                "float __u0raw = __span0 / " + repr(total_u_x) + ";\n"
                "float __u1raw = __span1 / " + repr(total_u_z) + ";\n"
                "// square/pad/repeat: unify unit to min → 1u cells stay square,\n"
                "// never overflow. Leftover on the larger axis centers the layout.\n"
                "float __u0 = min(__u0raw, __u1raw);\n"
                "float __u1 = __u0;\n"
                "float __extra0 = (__span0 - " + repr(total_u_x) + " * __u0) * 0.5;\n"
                "float __extra1 = (__span1 - " + repr(total_u_z) + " * __u0) * 0.5;\n"
                "float __g0 = __mn[__a0] + __m + __extra0;\n"
                "float __g1 = __mn[__a1] + __m + __extra1;\n"
            )
        else:
            unit_block = (
                "float __u0 = __span0 / " + repr(total_u_x) + ";\n"
                "float __u1 = __span1 / " + repr(total_u_z) + ";\n"
                "float __g0 = __mn[__a0] + __m;\n"
                "float __g1 = __mn[__a1] + __m;\n"
            )

        cx = [gx + w / 2.0 for gx, w in zip(gx_vals, w_vals)]
        cz = [gz + d / 2.0 for gz, d in zip(gz_vals, d_vals)]

        # Per-cell orient (tiles strategy): only emitted when the strategy
        # carries a non-trivial `rot` per cell. CellsStrategy/PicketStrategy
        # never set _rot_vals, so this produces NOTHING for them — keeping the
        # 2D `cells` VEX byte-identical (the Task-1 regression gate). The gate
        # requires a non-empty list matching the cell count AND at least one
        # non-zero rotation (all-zero rot is a no-op orient, so we omit it and
        # the VEX stays identical to the cells strategy for that case too).
        rot_vals = getattr(self, "_rot_vals", None)
        has_rot = (isinstance(rot_vals, list) and len(rot_vals) == len(cx)
                   and any(abs(float(r)) > 1e-12 for r in rot_vals))
        rot_decl = ("float __rot[] = " + self._arr(rot_vals)
                    if has_rot else "")
        rot_block = (
            "    // per-cell orient: rotate `rot` degrees about the face normal\n"
            "    // → quaternion (POINT class via setpointattrib, so CTP reads it).\n"
            "    vector __nvec = {0, 0, 0}; __nvec[__fa] = __fs;\n"
            "    vector4 __qrot = quaternion(radians(__rot[__ci]), __nvec);\n"
            "    setpointattrib(geoself(), \"orient\", __pt, __qrot, \"set\");\n"
            if has_rot else "")

        # Per-cell shelf 3D (ShelfStrategy only): when self._shelf_layers is set
        # (a per-cell [(gy, h), ...] list — set ONLY by ShelfStrategy._parse_table,
        # never by cells/pickets/tiles), emit the layer arrays + a fragment that
        # OVERRIDES each point's face-axis P with the layer-derived center and
        # the face-axis scale with the layer height. This is how a 3D bookshelf
        # reuses the 2D TabularFill loop: layers are flattened into cells, the
        # loop places each in-plane (X/Z), and this fragment lifts each onto its
        # layer along the face normal (Y). Mirrors measure.measure_shelf:
        #   unit_axis = face_span / total_layer_u;
        #   layer N base = face_base + sign * cum_u_before_N * unit_axis;
        #   book center = base + sign * (h*unit)/2.
        # cells/pickets/tiles leave _shelf_layers unset → getattr returns None →
        # NO shelf fragment → byte-identical VEX preserved (Task-1 gate).
        shelf_layers = getattr(self, "_shelf_layers", None)
        has_shelf = (isinstance(shelf_layers, list) and len(shelf_layers) == len(cx))
        if has_shelf:
            layer_gy = [gy for gy, _h in shelf_layers]
            layer_h = [h for _gy, h in shelf_layers]
            total_layer_u = max(gy + h for gy, h in shelf_layers)
            shelf_decl = (
                "float __layer_gy[] = " + self._arr(layer_gy)
                + "float __layer_h[] = " + self._arr(layer_h)
                + "float __u_axis = (__mx[__fa] - __mn[__fa]) / "
                + repr(total_layer_u) + ";"
            )
            shelf_block = (
                "    // shelf 3D: override the face-axis P with the layer-derived\n"
                "    // center, and the face-axis scale with the layer height. The\n"
                "    // in-plane axes (X/Z) keep the 2D cells placement/scale.\n"
                "    float __ly_base = __faceval + __fs * __layer_gy[__ci] * __u_axis;\n"
                "    float __lh = __layer_h[__ci] * __u_axis;\n"
                "    vector __p2 = __p; __p2[__fa] = __ly_base + __fs * __lh / 2.0;\n"
                "    setpointattrib(geoself(), \"P\", __pt, __p2, \"set\");\n"
                "    vector __s2 = __scl; __s2[__fa] = __lh;\n"
                "    setpointattrib(geoself(), \"scale\", __pt, __s2, \"set\");\n"
            )
        else:
            shelf_decl = ""
            shelf_block = ""

        # Per-cell out-of-plane HEIGHT (BlockStrategy only): when
        # self._block_h_vals is set (a per-cell height list — set ONLY by
        # BlockStrategy._parse_table, never by cells/pickets/tiles/shelf), emit
        # a __block_h[] array + a fragment that OVERRIDES each point's face-axis
        # scale with the block's height. The unit is DERIVED from the root's
        # face-axis span / max(h) (the tallest block fills the root's height),
        # mirroring how the in-plane units derive from the in-plane spans. This
        # is the synthesis: BlockStrategy = TileStrategy (rot → orient) + this
        # height fragment. The two fragments are independent (orient writes
        # p@orient; height writes the face-axis scale component) so they compose
        # cleanly. cells/pickets/tiles/shelf leave _block_h_vals unset → None →
        # NO block fragment → byte-identical VEX preserved (Task-1 gate).
        block_h_vals = getattr(self, "_block_h_vals", None)
        has_block_h = (isinstance(block_h_vals, list) and len(block_h_vals) == len(cx)
                       and any(abs(float(h)) > 1e-12 for h in block_h_vals))
        if has_block_h:
            total_h_u = max(float(h) for h in block_h_vals)
            block_decl = (
                "float __block_h[] = " + self._arr(block_h_vals)
                + "float __u_h = (__mx[__fa] - __mn[__fa]) / "
                + repr(total_h_u) + ";"
            )
            block_block = (
                "    // block height: override the face-axis scale with the\n"
                "    // block's height (out-of-plane, derived from the root's\n"
                "    // face-axis span / max height so the tallest fills it).\n"
                "    vector __s3 = __scl; __s3[__fa] = __block_h[__ci] * __u_h;\n"
                "    setpointattrib(geoself(), \"scale\", __pt, __s3, \"set\");\n"
            )
        else:
            block_decl = ""
            block_block = ""

        snippet = _VEX_CLEAR + r"""
vector __mn = getbbox_min(0);
vector __mx = getbbox_max(0);
int   __fa = chi("face_axis");
float __fs = ch("face_sign");
float __m  = ch("margin");
float __gap = ch("gap");               // visible gap between adjacent keys (world units)
// in-plane axes: the two axes other than __fa, in index order (a0 < a1).
int __a0 = -1, __a1 = -1, __seen = 0;
for (int __i = 0; __i < 3; __i++) { if (__i != __fa) { if (__seen == 0) __a0 = __i; else __a1 = __i; __seen++; } }
float __faceval = (__fs > 0) ? __mx[__fa] : __mn[__fa];
// THE MEASUREMENT-DRIVEN CORE: per-axis unit DERIVED from root span, so the
// layout FILLS the root and rescales live.
float __span0 = (__mx[__a0] - __mn[__a0]) - 2 * __m;
float __span1 = (__mx[__a1] - __mn[__a1]) - 2 * __m;
""" + unit_block + r"""
// The layout table — one line per field. Position is the cell CENTER in grid
// units (gx + w/2), precomputed in Python so the loop stays branch-free.
float __cx[] = """ + self._arr(cx) + r"""
float __cz[] = """ + self._arr(cz) + r"""
float __cw[] = """ + self._arr(w_vals) + r"""
float __cd[] = """ + self._arr(d_vals) + rot_decl + shelf_decl + block_decl + r"""
// ONE loop over every cell. Position = grid center × derived unit; scale =
// physical size (w*u0) with the gap inset so adjacent keys show a visible seam.
// (Unique loop vars __ci/__ncell avoid clashing with the clear loop's __n/__i.)
int __ncell = len(__cx);
for (int __ci = 0; __ci < __ncell; __ci++) {
    vector __p = {0, 0, 0};
    __p[__fa] = __faceval;
    __p[__a0] = __g0 + __cx[__ci] * __u0;
    __p[__a1] = __g1 + __cz[__ci] * __u1;
    int __pt = addpoint(geoself(), __p);
    append(__newpts, __pt);
    // physical size = grid units × derived unit, minus the visible gap on each
    // side (so a 1u key is u0-gap wide; the layout still fills the root).
    vector __scl = {1, 1, 1};
    __scl[__a0] = max(0.0001, __cw[__ci] * __u0 - __gap);
    __scl[__a1] = max(0.0001, __cd[__ci] * __u1 - __gap);
    setpointattrib(geoself(), "scale", __pt, __scl, "set");
""" + shelf_block + block_block + rot_block + r"""}
""".strip()
        return snippet


# ── Spec pre-expansion (internalized builder-layer sugar) ──────────
#
# Three tabular-fill strategies accept a higher-level spec that expands into
# the canonical {gx,gz,w,d} cells table the VEX loop consumes. These expansions
# used to live in assembly_builder.py (the retired rooted-modeling builder
# layer); they are internalized HERE so each strategy is SELF-SUFFICIENT — call
# build_mount_vex directly and the sugar resolves. No external builder needed.
# (assembly_builder retired 2026-07-08; see docs/superpowers/plans/
#  2026-07-08-procedural-agent-refactor.md Phase 0a.)


def _expand_repeat_cells(cells: list[dict]) -> list[dict]:
    """Extend a cells table with 1u filler cells (the ``fill=repeat`` mode).

    ``repeat`` keeps cells SQUARE (unit = min, like pad) but FILLS the leftover
    space on the larger axis by auto-adding 1u cells. The VEX loop is unchanged
    — it just receives a longer table.

    The layout's grid-unit span is ``max(gx+w)`` / ``max(gz+d)``. With unit=min,
    the smaller axis fills exactly; the larger axis has leftover grid units. We
    extend the layout's declared span so both axes match the LARGER one, filling
    the now-empty grid slots with 1u cells (skipping any slot already occupied
    by a declared cell). Result: square keys, no gaps.
    """
    if not cells:
        return cells
    total_u_x = max(float(c["gx"]) + float(c["w"]) for c in cells)
    total_u_z = max(float(c["gz"]) + float(c["d"]) for c in cells)
    target = max(total_u_x, total_u_z)   # fill both axes to the larger span

    # Occupancy grid (integer slots) of declared cells.
    occupied: set[tuple[int, int]] = set()
    for c in cells:
        gx, gz = int(float(c["gx"])), int(float(c["gz"]))
        w, d = int(float(c["w"])), int(float(c["d"]))
        for ix in range(gx, gx + w):
            for iz in range(gz, gz + d):
                occupied.add((ix, iz))

    out = list(cells)
    for ix in range(int(target)):
        for iz in range(int(target)):
            if (ix, iz) not in occupied:
                out.append({"gx": float(ix), "gz": float(iz), "w": 1, "d": 1})
    return out


def _expand_pickets_count(position_spec: dict) -> dict:
    """Expand a pickets ``count`` into an explicit equal-width cells table.

    count=N → N cells of width 1 at gx=0,1,...,N-1. The VEX loop is unchanged;
    only fed a generated table.
    """
    if "count" not in position_spec:
        return position_spec
    count = int(position_spec["count"])
    if count < 1:
        raise VexStrategyError(f"pickets count must be >= 1, got {count}")
    cells = [{"gx": float(i), "w": 1.0} for i in range(count)]
    out = {k: v for k, v in position_spec.items() if k != "count"}
    out["cells"] = cells
    return out


def _expand_shelf_layers(position_spec: dict) -> dict:
    """Flatten a shelf ``layers`` table into a cells list carrying per-cell
    layer info (for the VEX strategy). Each cell gets its layer's gy (cumulative
    u) and h (layer height) injected, so the inherited TabularFill loop can
    place it in 3D. The layer axis comes from basis.face's normal.
    """
    layers = position_spec.get("layers")
    if not isinstance(layers, list):
        return position_spec
    out_spec = {k: v for k, v in position_spec.items() if k != "layers"}
    flat_cells = []
    cum = 0.0
    for layer in layers:
        h = float(layer.get("height", 0))
        for c in layer.get("cells", []):
            cell = dict(c)
            cell["__layer_gy"] = cum      # layer's base in u (consumed by strategy)
            cell["__layer_h"] = h          # layer height in u
            flat_cells.append(cell)
        cum += h
    out_spec["cells"] = flat_cells
    return out_spec


class CellsStrategy(TabularFillStrategy):
    """The gx/gz/w/d keyboard-layout schema.

    Each cell declares its lower-left grid coords (gx, gz) and size (w, d) in
    1u units. This is the keyboard-keys strategy: a real keyboard's keys differ
    in width (spacebar 6.25u, normal 1u) and rows are staggered. The leaf shape
    is a 1u BASIS box; the per-point v@scale grows it to each cell's footprint.
    """

    def build(self, position_spec: dict) -> tuple[str, dict[str, Any]]:
        # fill=repeat sugar (internalized): extend the cells table with 1u
        # filler cells to fill the leftover space on the larger axis. The VEX
        # loop is unchanged — only fed a longer table. Makes the strategy
        # self-sufficient — no external builder needs to pre-expand.
        if position_spec.get("fill") == "repeat":
            spec = dict(position_spec)
            spec["cells"] = _expand_repeat_cells(spec.get("cells", []))
            return super().build(spec)
        return super().build(position_spec)

    def _parse_table(self, cells: list[dict]
                     ) -> tuple[list[float], list[float], list[float], list[float]]:
        """Validate the {gx,gz,w,d} cell table → value lists."""
        gx_vals: list[float] = []
        gz_vals: list[float] = []
        w_vals: list[float] = []
        d_vals: list[float] = []
        for ci, c in enumerate(cells):
            try:
                gx_vals.append(float(c["gx"])); gz_vals.append(float(c["gz"]))
                w_vals.append(float(c["w"])); d_vals.append(float(c["d"]))
            except (KeyError, TypeError, ValueError) as e:
                raise VexStrategyError(
                    f"cell {ci} must have numeric gx/gz/w/d, got {c!r}") from None
        return gx_vals, gz_vals, w_vals, d_vals


class PicketStrategy(TabularFillStrategy):
    """The 1D picket/fence schema. Each cell declares {gx, w}. Reuses the
    TabularFill 2D loop with the 2nd axis degenerate (gz=0, d=1) — exactly as
    measure_pickets does — so the inherited _build_vex produces a 1D-effective
    row (all points share the same z). The `count`→cells sugar is expanded by
    build() via _expand_pickets_count (internalized) before parsing."""

    def build(self, position_spec: dict) -> tuple[str, dict[str, Any]]:
        # count→cells sugar (internalized): count=N becomes N equal-width 1u
        # cells. Makes the strategy self-sufficient — no external builder needs
        # to pre-expand.
        spec = (_expand_pickets_count(position_spec)
                if "count" in position_spec else position_spec)
        return super().build(spec)

    def _parse_table(self, cells):
        gx_vals, w_vals = [], []
        for ci, c in enumerate(cells):
            try:
                gx_vals.append(float(c["gx"])); w_vals.append(float(c["w"]))
            except (KeyError, TypeError, ValueError):
                raise VexStrategyError(
                    f"picket cell {ci} needs numeric gx/w, got {c!r}") from None
        # 2nd axis degenerate (gz=0, d=1) → 1D-effective row via the inherited 2D loop.
        return gx_vals, [0.0]*len(gx_vals), w_vals, [1.0]*len(gx_vals)


class TileStrategy(TabularFillStrategy):
    """The 2D tile-mosaic schema. Cells carry {gx,gz,w,d, rot?}. rot (degrees)
    rotates each tile about the face normal → per-cell p@orient (CTP reads it).
    A mount-level `orient` rule (herringbone/checker/running) supplies rot for
    cells without explicit rot. The rule is applied HERE (Python layer) before
    _parse_table, so the VEX just sees a __rot[] array."""

    def build(self, position_spec: dict) -> tuple[str, dict[str, Any]]:
        # Apply the named orient rule: inject rot into cells that lack it.
        spec = dict(position_spec)
        rule = spec.get("orient")
        if isinstance(rule, str):
            from edini.measure import _rule_rot
            cells = [dict(c) for c in spec.get("cells", [])]
            for ci, c in enumerate(cells):
                if "rot" not in c:
                    c["rot"] = _rule_rot(rule, ci, c)
            spec["cells"] = cells
        return super().build(spec)

    def _parse_table(self, cells):
        gx, gz, w, d, rot = [], [], [], [], []
        for ci, c in enumerate(cells):
            try:
                gx.append(float(c["gx"])); gz.append(float(c["gz"]))
                w.append(float(c["w"])); d.append(float(c["d"]))
            except (KeyError, TypeError, ValueError) as e:
                raise VexStrategyError(
                    f"cell {ci} must have numeric gx/gz/w/d, got {c!r}") from None
            rot.append(float(c.get("rot", 0.0)))
        self._rot_vals = rot   # signals _build_vex to emit per-cell orient
        return gx, gz, w, d


class ShelfStrategy(TabularFillStrategy):
    """The 3D bookshelf schema. Layers stack along the face's NORMAL axis; each
    layer has a height (1u) + within-layer cells (a row of books, defaulting the
    2nd in-plane axis to a degenerate 1u — the same trick measure_pickets uses).

    build() flattens layers first (via _expand_shelf_layers), then the inherited
    TabularFill loop places each flattened cell in-plane (X/Z). _parse_table
    extracts the per-cell layer info (__layer_gy/__layer_h, injected by the
    expander) and stores it as self._shelf_layers, which SIGNALS _build_vex to
    append the shelf 3D fragment — that overrides each point's face-axis P with
    the layer-derived center and the face-axis scale with the layer height. So
    the 3D stack is a 2D loop + a per-point face-axis override (mirror of
    measure.measure_shelf). cells/pickets/tiles leave _shelf_layers unset, so
    the base _build_vex emits NO shelf fragment for them (byte-identical)."""

    def build(self, position_spec: dict) -> tuple[str, dict[str, Any]]:
        # Flatten layers into a single cells table (carrying per-cell __layer_gy
        # / __layer_h) BEFORE the inherited build parses the table. The expander
        # is internalized above (_expand_shelf_layers) so the strategy is
        # self-sufficient when called directly (e.g. from tests).
        spec = (_expand_shelf_layers(position_spec)
                if "layers" in position_spec else position_spec)
        return super().build(spec)

    def _parse_table(self, cells):
        gx, gz, w, d, gy, h = [], [], [], [], [], []
        for ci, c in enumerate(cells):
            try:
                gx.append(float(c["gx"])); w.append(float(c["w"]))
            except (KeyError, TypeError, ValueError) as e:
                raise VexStrategyError(
                    f"shelf cell {ci} needs numeric gx/w, got {c!r}") from None
            # The within-layer 2nd in-plane axis defaults to a degenerate 1u
            # (a row of books along ONE in-plane axis), like measure_pickets.
            gz.append(float(c.get("gz", 0))); d.append(float(c.get("d", 1)))
            # Per-cell layer info injected by _expand_shelf_layers:
            # __layer_gy = the layer's cumulative-u base; __layer_h = its height.
            gy.append(float(c.get("__layer_gy", 0)))
            h.append(float(c.get("__layer_h", 1)))
        self._shelf_layers = list(zip(gy, h))   # signals _build_vex shelf fragment
        return gx, gz, w, d


class BlockStrategy(TabularFillStrategy):
    """The 2D city-blocks schema — the SYNTHESIS layout (④). Cells carry
    {gx,gz,w,d, h?, rot?}: a 2D footprint (in-plane, via the cells loop) + an
    out-of-plane HEIGHT (h, along the face normal) + optional per-cell ROTATION
    (rot → p@orient, exactly as tiles). This composes the mechanisms built for
    tiles (rot → ``_rot_vals``) and a new height fragment (``_block_h_vals``);
    the two fragments are independent (orient vs face-axis scale) and stack
    cleanly. ``build()`` first applies the named orient rule (if any), exactly
    as TileStrategy does, then inherits the rest.

    The unit for height is DERIVED from the root's face-axis span / max(h) so
    the tallest block fills the root's height (mirroring the in-plane unit
    derivation). Empty grid slots (parks/streets) are simply undeclared cells."""

    def build(self, position_spec: dict) -> tuple[str, dict[str, Any]]:
        # Apply the named orient rule (mirrors TileStrategy.build): inject rot
        # into cells lacking it, so the VEX just sees a __rot[] array.
        spec = dict(position_spec)
        rule = spec.get("orient")
        if isinstance(rule, str):
            from edini.measure import _rule_rot
            cells = [dict(c) for c in spec.get("cells", [])]
            for ci, c in enumerate(cells):
                if "rot" not in c:
                    c["rot"] = _rule_rot(rule, ci, c)
            spec["cells"] = cells
        return super().build(spec)

    def _parse_table(self, cells):
        gx, gz, w, d, rot, h = [], [], [], [], [], []
        for c in cells:
            gx.append(float(c["gx"])); gz.append(float(c["gz"]))
            w.append(float(c["w"])); d.append(float(c["d"]))
            rot.append(float(c.get("rot", 0.0)))
            h.append(float(c.get("h", 0.0)))
        self._rot_vals = rot        # signals orient fragment (Task 5 mechanism)
        self._block_h_vals = h      # signals the height fragment (new)
        return gx, gz, w, d


# Module-level singleton dispatched to by build_mount_vex.
_CELLS_STRATEGY = CellsStrategy()
_PICKET_STRATEGY = PicketStrategy()
_TILE_STRATEGY = TileStrategy()
_SHELF_STRATEGY = ShelfStrategy()
_BLOCK_STRATEGY = BlockStrategy()


def build_cells_vex(cells: list[dict]) -> tuple[str, dict[str, Any]]:
    """Build the cells strategy's VEX. Returns ``(snippet, {})``.

    Backward-compatible wrapper: delegates to :class:`CellsStrategy`. Kept so
    existing callers (and tests) that pass a bare cells list still work; new
    code should use ``build_mount_vex`` with a full position spec (which
    dispatches through the strategy registry and resolves face/margin/gap).
    """
    snippet, _parms = _CELLS_STRATEGY.build(
        {"measure": "cells", "face": "+Y", "cells": cells})
    return snippet, {}


# ── Orient injection ───────────────────────────────────────────────
#
# When a mount declares an orient spec (two measured points → a direction), the
# builder appends this fragment to the strategy's VEX so EVERY emitted point
# carries the same @orient quaternion. The direction is computed from two
# resolved corners (da/ db with their own selectors) and @orient is set on
# each point via setpointattrib. Because CTP reads @orient, the leaf's built
# +Y faces along the measured direction.
#
# Per-instance orient (different facing per grid cell) is a later milestone;
# M2 applies one orient per mount, shared by all its points.

def _orient_fragment(orient_spec: dict, align_axis: str = "+Y") -> str:
    """Build the @orient-setting VEX fragment for a mount's orient spec.

    Reads two resolved corners (da/db with their own cX selectors), computes
    the unit direction, and writes the orient quaternion onto EVERY point via
    ``setpointattrib`` — NOT a bare ``p@orient =`` — because this fragment runs
    inside a **detail** wrangle (it must, to ``addpoint`` the mount points), and
    a bare ``p@orient =`` in a detail wrangle becomes a *detail* attribute,
    which ``copytopoints::2.0`` silently ignores. Writing through
    ``setpointattrib`` forces it onto each POINT, where CTP reads it.

    ``align_axis`` (default "+Y") selects which axis of the leaf shape is mapped
    onto the measured direction: ``p@orient = dihedral(<align_axis>, dir)``.
    A torus wheel's symmetry axis is +Z, so it passes ``"+Z"``; a +Y-grown
    shape keeps the default. Returns "" if no orient spec.
    """
    if not isinstance(orient_spec, dict):
        return ""
    from_a = orient_spec.get("from_a")
    from_b = orient_spec.get("from_b")
    if not (isinstance(from_a, dict) and isinstance(from_b, dict)):
        return ""
    sa = _corner_selectors(from_a.get("axes", "-X-Y-Z"))
    sb = _corner_selectors(from_b.get("axes", "+X-Y-Z"))
    ax, ay, az = align_axis_to_vec(align_axis)
    axis_label = align_axis  # e.g. "+Y"
    return r"""
// --- orient: map leaf's {axis_label} onto the direction between two measured corners ---
// Written via setpointattrib so the attribute is POINT-class (CTP-readable),
// not detail-class (a bare orient export here would be silently ignored).
// Iterates __newpts (the array every addpoint in this wrangle appended to),
// NOT npoints(): in a detail wrangle npoints() does not reflect points created
// by addpoint during the same cook, so a range loop would miss them.
vector __mn = getbbox_min(0);
vector __mx = getbbox_max(0);
vector __da = set(lerp(__mn.x, __mx.x, {dax}), lerp(__mn.y, __mx.y, {day}), lerp(__mn.z, __mx.z, {daz}));
vector __db = set(lerp(__mn.x, __mx.x, {dbx}), lerp(__mn.y, __mx.y, {dby}), lerp(__mn.z, __mx.z, {dbz}));
vector __dir = normalize(__db - __da);
vector4 __q = dihedral({{{ax},{ay},{az}}}, __dir);
foreach (int __ptnum; __newpts) {{
    setpointattrib(geoself(), "orient", __ptnum, __q, "set");
}}
""".format(
        dax=sa["cx"], day=sa["cy"], daz=sa["cz"],
        dbx=sb["cx"], dby=sb["cy"], dbz=sb["cz"],
        ax=ax, ay=ay, az=az,
        axis_label=axis_label,
    ).strip()


def align_axis_to_vec(align_axis: str) -> tuple[float, float, float]:
    """Resolve an align-axis sign-string to a unit vector.

    "+Y" → (0,1,0), "-Z" → (0,0,-1), etc. The leaf's this axis is rotated onto
    the measured direction by ``dihedral``. Default "+Y" preserves the original
    semantics (a +Y-grown shape faces the measured direction). Components are
    ints (0/±1) so the injected VEX reads as the idiomatic ``{0,1,0}`` literal.
    """
    sign, axis = _parse_face(align_axis)
    base = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}[axis]
    s = int(sign)
    return (s * base[0], s * base[1], s * base[2])


# ── Strategy class hierarchy ───────────────────────────────────────
#
# Three layers, each a strict superset of the one above:
#
#   VexStrategy            — the contract every measurement kind satisfies:
#                            build(spec) -> (snippet, parms). The snippet MUST
#                            begin with _VEX_CLEAR (so __newpts exists for an
#                            appended orient fragment) and emit points via
#                            append(__newpts, addpoint()).
#   ├─ StaticTemplateStrategy — the 6 fixed-template kinds (bbox_corner,
#   │                           grid_on_face, array, ...). Parameterized by a
#   │                           template constant + a selector-resolver fn, so
#   │                           one class replaces the build_mount_vex lookup
#   │                           table + if/elif chain.
#   └─ TabularFillStrategy — table-driven (position,size) layouts that FILL a
#       │                     region. Encodes the layout table as VEX array
#       │                     literals + a single compact loop (data/code
#       │                     decoupled — ~30 lines regardless of cell count),
#       │                     derives the per-axis unit from the root's span,
#       │                     writes per-point v@scale, and applies the shape
#       │                     constraint (square) + fill mode (pad/repeat/stretch).
#       └─ CellsStrategy — the gx/gz/w/d keyboard-layout schema. Future
#                          bookshelf/city-block layouts inherit the same
#                          TabularFill base and just override the schema.


class StaticTemplateStrategy(VexStrategy):
    """A measurement kind backed by a fixed VEX template + a selector resolver.

    Encapsulates the 6 static kinds (bbox_corner, bbox_face_center, bbox_center,
    point_on_edge, grid_on_face, array). Each differs only in (a) which template
    constant it uses and (b) how it resolves the spec's sign-strings/counts into
    the ``ch()``/``chi()`` spare values the template reads. Parameterizing those
    two collapses the old build_mount_vex lookup-table + per-kind if/elif chain
    into a registry of instances.
    """

    def __init__(self, template: str, resolver):
        self._template = template
        self._resolver = resolver  # (spec) -> dict[str, Any] of spare parms

    def build(self, position_spec: dict) -> tuple[str, dict[str, Any]]:
        parms = self._resolver(position_spec)
        return self._template, parms


# Per-kind selector resolvers. Each turns the human spec (sign-strings, counts)
# into the numeric spare-parm values its template reads via ch()/chi().
def _resolve_bbox_corner(spec: dict) -> dict[str, Any]:
    return _corner_selectors(spec["axes"])


def _resolve_bbox_face_center(spec: dict) -> dict[str, Any]:
    return _face_selector(spec["face"])


def _resolve_bbox_center(spec: dict) -> dict[str, Any]:
    return {}   # no parameters — reads getbbox_center directly


def _resolve_point_on_edge(spec: dict) -> dict[str, Any]:
    # _corner_selectors returns {cx,cy,cz}; prefix with ca/cb but drop the
    # leading c so VEX sees cax/cay/caz, cbx/cby/cbz (matching the template).
    sa = _corner_selectors(spec["axes_a"])
    sb = _corner_selectors(spec["axes_b"])
    parms = {f"ca{a[1:]}": v for a, v in sa.items()}   # cx→ax → cax
    parms.update({f"cb{a[1:]}": v for a, v in sb.items()})  # cx→bx → cbx
    parms["t"] = float(spec.get("t", 0.5))
    return parms


def _resolve_grid_on_face(spec: dict) -> dict[str, Any]:
    parms = _face_selector(spec["face"])
    parms["rows"] = int(spec.get("rows", 1))
    parms["cols"] = int(spec.get("cols", 1))
    parms["margin"] = float(spec.get("margin", 0.0))
    return parms


def _resolve_array(spec: dict) -> dict[str, Any]:
    # count + step arrive as numbers/exprs in the spec; the builder resolves
    # expressions to concrete values before installing them. Pass them through;
    # the caller (_install_wrangle_parms) resolves the _-prefixed vector specs.
    count = spec.get("count", [1, 1, 1])
    step = spec.get("step", [[0, 0, 0]] * 3)
    parms: dict[str, Any] = {
        "countx": int(count[0]), "county": int(count[1]), "countz": int(count[2]),
        "_origin": spec.get("origin"),
        "_step0": step[0], "_step1": step[1], "_step2": step[2],
    }
    return parms


def _resolve_by_name(spec: dict) -> dict[str, Any]:
    # by_name picks a marker point the root generator emitted at a real
    # geometric location. The only selector is the marker's @name string.
    # Unlike bbox strategies, marker is a STRING spare parm (chs), not int.
    marker = spec.get("marker")
    if not marker or not isinstance(marker, str):
        raise VexStrategyError(
            "by_name measure requires a 'marker' string (the @name of the "
            "point the root generator emitted). Example: "
            '{"measure":"by_name","marker":"head_tube_top","name":"head_tube"}')
    if not marker.replace("_", "").isalnum():
        raise VexStrategyError(
            f"by_name marker {marker!r} must be a legal @name token "
            f"(letters/digits/underscores)")
    return {"_marker": marker}


# The static-strategy registry. build_mount_vex dispatches through this.
_STATIC_STRATEGIES: dict[str, StaticTemplateStrategy] = {
    "bbox_corner":      StaticTemplateStrategy(_VEX_BBOX_CORNER, _resolve_bbox_corner),
    "bbox_face_center": StaticTemplateStrategy(_VEX_BBOX_FACE_CENTER, _resolve_bbox_face_center),
    "bbox_center":      StaticTemplateStrategy(_VEX_BBOX_CENTER, _resolve_bbox_center),
    "point_on_edge":    StaticTemplateStrategy(_VEX_POINT_ON_EDGE, _resolve_point_on_edge),
    "grid_on_face":     StaticTemplateStrategy(_VEX_GRID_ON_FACE, _resolve_grid_on_face),
    "array":            StaticTemplateStrategy(_VEX_ARRAY, _resolve_array),
    # by_name: unlike the bbox strategies, this preserves a marker point the
    # root generator emitted at a REAL geometric location — truly parametric
    # against the actual shape, not the bbox hull. See _VEX_BY_NAME docstring.
    "by_name":          StaticTemplateStrategy(_VEX_BY_NAME, _resolve_by_name),
}


# ── Public: turn a mount position spec into (snippet, spare_parms) ──


def build_mount_vex(mount_position: dict) -> tuple[str, dict[str, Any]]:
    """Resolve a mount's ``position`` spec into a VEX snippet + spare parms.

    Dispatches to the matching :class:`VexStrategy` (static template or the
    cells tabular-fill strategy). Returns ``(snippet, parms)`` where ``snippet``
    is the full detail-wrangle body (position strategy + optional orient
    fragment appended separately by the builder) and ``parms`` is a dict of
    spare-parm name → value to install on the wrangle node.

    The snippet reads the root bbox LIVE (getbbox_min/max on input 0), so the
    same node re-cooks correctly when a root param changes — the defining
    property of the live build layer. Nothing here is a baked coordinate.
    """
    if not isinstance(mount_position, dict):
        raise VexStrategyError("mount position must be an object")
    kind = mount_position.get("measure")

    # cells: dispatch to the CellsStrategy (a TabularFillStrategy). It builds
    # its snippet dynamically (the layout table is encoded into the VEX).
    if kind == "cells":
        return _CELLS_STRATEGY.build(mount_position)

    # pickets: the 1D fence/baluster strategy. Dispatches to PicketStrategy,
    # which reuses the 2D TabularFill loop with the 2nd axis degenerate (the
    # count→cells expansion happens in the builder layer before this runs).
    if kind == "pickets":
        return _PICKET_STRATEGY.build(mount_position)

    # tiles: the 2D tile-mosaic strategy. Dispatches to TileStrategy, which
    # applies the named orient rule (herringbone/checker/running) at the Python
    # layer, then reuses the TabularFill loop + emits a per-cell __rot[] array
    # → setpointattrib "orient" (POINT-class, CTP-readable) inside the loop.
    if kind == "tiles":
        return _TILE_STRATEGY.build(mount_position)

    # shelf: the 3D bookshelf strategy. Dispatches to ShelfStrategy, which
    # flattens layers into a cells table (carrying per-cell __layer_gy/__layer_h),
    # reuses the TabularFill loop in-plane, and appends a shelf fragment that
    # overrides each point's face-axis P/scale with the layer-derived values.
    # The layer flattening (_expand_shelf_layers) is internalized so the
    # strategy is self-sufficient when called directly.
    if kind == "shelf":
        return _SHELF_STRATEGY.build(mount_position)

    if kind == "blocks":
        return _BLOCK_STRATEGY.build(mount_position)

    static = _STATIC_STRATEGIES.get(kind)
    if static is None:
        raise VexStrategyError(f"no VEX strategy for measure {kind!r}")
    return static.build(mount_position)


__all__ = ["VexStrategy", "StaticTemplateStrategy", "TabularFillStrategy",
           "CellsStrategy", "PicketStrategy", "TileStrategy", "ShelfStrategy",
           "BlockStrategy",
           "VexStrategyError", "build_mount_vex", "build_cells_vex",
           "_orient_fragment", "_corner_selectors", "_face_selector"]
