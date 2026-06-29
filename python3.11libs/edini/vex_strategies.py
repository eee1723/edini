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
// the high end down so indices stay valid as we delete.
int __n = npoints(geoself());
for (int __i = __n - 1; __i >= 0; __i--) { removepoint(geoself(), __i); }
""".strip()

# bbox_corner: one point at a chosen corner. cx/cy/cz ∈ {0,1} pick min/max.
_VEX_BBOX_CORNER = _VEX_CLEAR + r"""
vector mn = getbbox_min(0);
vector mx = getbbox_max(0);
vector p = set(lerp(mn.x, mx.x, chi("cx")),
               lerp(mn.y, mx.y, chi("cy")),
               lerp(mn.z, mx.z, chi("cz")));
int pt = addpoint(0, p);
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
int pt = addpoint(0, p);
""".strip()

# bbox_center: one point at the bbox midpoint.
_VEX_BBOX_CENTER = _VEX_CLEAR + r"""
int pt = addpoint(0, getbbox_center(0));
""".strip()

# point_on_edge: lerp between two corners (each by its own cx/cy/cz) at t∈[0,1].
# The two corners must differ on exactly one axis (validated on the Python side).
_VEX_POINT_ON_EDGE = _VEX_CLEAR + r"""
vector mn = getbbox_min(0);
vector mx = getbbox_max(0);
vector a = set(lerp(mn.x, mx.x, chi("cax")), lerp(mn.y, mx.y, chi("cay")), lerp(mn.z, mx.z, chi("caz")));
vector b = set(lerp(mn.x, mx.x, chi("cbx")), lerp(mn.y, mx.y, chi("cby")), lerp(mn.z, mx.z, chi("cbz")));
int pt = addpoint(0, lerp(a, b, ch("t")));
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
        addpoint(0, p);
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
            addpoint(0, p);
        }
    }
}
""".strip()


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
vector __mn = getbbox_min(0);
vector __mx = getbbox_max(0);
vector __da = set(lerp(__mn.x, __mx.x, {dax}), lerp(__mn.y, __mx.y, {day}), lerp(__mn.z, __mx.z, {daz}));
vector __db = set(lerp(__mn.x, __mx.x, {dbx}), lerp(__mn.y, __mx.y, {dby}), lerp(__mn.z, __mx.z, {dbz}));
vector __dir = normalize(__db - __da);
vector4 __q = dihedral({{{ax},{ay},{az}}}, __dir);
for (int __i = 0; __i < npoints(geoself()); __i++) {{
    setpointattrib(geoself(), "orient", __i, __q, "set");
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


# ── Public: turn a mount position spec into (snippet, spare_parms) ──


def build_mount_vex(mount_position: dict) -> tuple[str, dict[str, Any]]:
    """Resolve a mount's ``position`` spec into a VEX snippet + spare parms.

    Returns ``(snippet, parms)`` where ``snippet`` is the full detail-wrangle
    body (position strategy + optional orient fragment) and ``parms`` is a
    dict of spare-parm name → value to install on the wrangle node.

    The snippet reads the root bbox LIVE (getbbox_min/max on input 0), so the
    same node re-cooks correctly when a root param changes — the defining
    property of the live build layer. Nothing here is a baked coordinate.
    """
    if not isinstance(mount_position, dict):
        raise VexStrategyError("mount position must be an object")
    kind = mount_position.get("measure")
    snippets: dict[str, str] = {
        "bbox_corner": _VEX_BBOX_CORNER,
        "bbox_face_center": _VEX_BBOX_FACE_CENTER,
        "bbox_center": _VEX_BBOX_CENTER,
        "point_on_edge": _VEX_POINT_ON_EDGE,
        "grid_on_face": _VEX_GRID_ON_FACE,
        "array": _VEX_ARRAY,
    }
    if kind not in snippets:
        raise VexStrategyError(f"no VEX strategy for measure {kind!r}")

    parms: dict[str, Any] = {}
    body = snippets[kind]

    # Per-kind selector resolution (sign-string → numeric ch() values).
    if kind == "bbox_corner":
        parms.update(_corner_selectors(mount_position["axes"]))
    elif kind == "bbox_face_center":
        parms.update(_face_selector(mount_position["face"]))
    elif kind == "point_on_edge":
        # _corner_selectors returns {cx,cy,cz}; prefix with ca/cb but drop the
        # leading c so VEX sees cax/cay/caz, cbx/cby/cbz (matching the template).
        sa = _corner_selectors(mount_position["axes_a"])
        sb = _corner_selectors(mount_position["axes_b"])
        parms.update({f"ca{a[1:]}": v for a, v in sa.items()})  # cx→ax → cax
        parms.update({f"cb{a[1:]}": v for a, v in sb.items()})  # cx→bx → cbx
        parms["t"] = float(mount_position.get("t", 0.5))
    elif kind == "grid_on_face":
        parms.update(_face_selector(mount_position["face"]))
        parms["rows"] = int(mount_position.get("rows", 1))
        parms["cols"] = int(mount_position.get("cols", 1))
        parms["margin"] = float(mount_position.get("margin", 0.0))
    elif kind == "array":
        # count + step arrive as numbers/exprs in the spec; the builder resolves
        # expressions to concrete values before installing them. Here we pass
        # them through; the caller (_install_array_parms) resolves exprs.
        count = mount_position.get("count", [1, 1, 1])
        step = mount_position.get("step", [[0, 0, 0]] * 3)
        parms["countx"] = int(count[0]); parms["county"] = int(count[1]); parms["countz"] = int(count[2])
        # origin + step are vectors — installed via parmTuple by the builder.
        parms["_origin"] = mount_position.get("origin")
        parms["_step0"] = step[0]; parms["_step1"] = step[1]; parms["_step2"] = step[2]

    snippet = body
    return snippet, parms


__all__ = ["VexStrategyError", "build_mount_vex", "_orient_fragment",
           "_corner_selectors", "_face_selector"]
