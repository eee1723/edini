# VEXlib — Procedural Skeleton Function Library

VEX functions for generating **skeletons** (points, polylines, attributes) that
feed into native SOPs (Sweep, PolyExtrude, Copy-to-Points). The functions never
produce closed geometry — closedness is guaranteed by downstream nodes.

## How to use (from a wrangle)

```vex
// In an Attribute Wrangle set to Run Over: Detail (Numbers).
// Include the library:
#include <vexlib/skeleton.vfl>
#include <vexlib/sections.vfl>
#include <vexlib/attribs.vfl>

// Then call functions directly:
int path[] = make_stair_path(0, chi("steps"), chf("tread"), chf("riser"),
                             {0,0,0}, {1,0,0});
```

> **IMPORTANT:** All skeleton/section functions must run in a wrangle with
> **Run Over: Detail (Numbers)**. Otherwise addpoint/addprim multiplies
> geometry per-element.

## Function Index

### Skeleton Generators (`skeleton.vfl`)

| Function | Signature | Returns | Description |
|---|---|---|---|
| `make_polyline` | `(geohandle; positions[])` | `int[]` point_ids | Open polyline through given world positions |
| `make_closed_polyline` | `(geohandle; positions[])` | `int[]` point_ids | Closed loop (last→first) |
| `make_helix` | `(geohandle; n; radius; height; turns)` | `int[]` point_ids | Helical path for spiral stairs, springs |
| `make_stair_path` | `(geohandle; n; tread; riser; start; direction)` | `int[]` point_ids | Stair-step path (treads + risers) |
| `make_grid` | `(geohandle; rows; cols; sx; sy; stagger; origin; plane)` | `int[]` point_ids | 2D grid with optional stagger |

### Section Generators (`sections.vfl`)

| Function | Signature | Returns | Description |
|---|---|---|---|
| `make_rect_section` | `(geohandle; width; height; plane)` | `int[]` point_ids | Rectangular closed contour |
| `make_circle_section` | `(geohandle; radius; sides; plane; offset)` | `int[]` point_ids | Regular N-gon closed contour |
| `make_tapered_section` | `(geohandle; radii[]; plane; offset)` | `int[]` point_ids | Variable-radius N-gon |
| `make_arc_path` | `(geohandle; n; radius; start_deg; end_deg; plane; offset)` | `int[]` point_ids | Circular arc open polyline |
| `make_gear_profile` | `(geohandle; teeth; outer_r; inner_r; plane; offset)` | `int[]` point_ids | Toothed gear/chainring closed contour |

### Attribute Writers (`attribs.vfl`)

| Function | Signature | Description |
|---|---|---|
| `set_orient_from_tangent` | `(geohandle; ptnum; tangent; up)` | Write @orient quaternion from tangent+up |
| `set_component_id_by_range` | `(geohandle; cid; min; max)` | Assign @component_id to prims by centroid bbox |
| `set_component_id_by_index` | `(geohandle; prefix; start; per_id)` | Assign @component_id by sequential index |
| `set_scale_along_curve` | `(geohandle; ptnum; base; peak; mode)` | Write @pscale ramp along @curveu |
| `set_instance_attrs` | `(geohandle; ptnum; P; fwd; up; scale)` | Write all Copy-to-Points attrs at once |

## VEXlib Iron Rules

1. **Run Over: Detail** — all make_* functions MUST run in Detail mode (addpoint/addprim in Point mode duplicates geometry per point).
2. **ch() for parameters** — always use `chf("name")` / `chi("name")` for sizing, never hardcode numbers. This auto-creates UI sliders.
3. **Skeletons only** — these functions produce points and polylines, never closed geometry. Closedness is the job of Sweep (`endcaptype=1`), PolyExtrude (`output_back=1`), Cap, etc.
4. **Return point_ids** — every make_* function returns `int[]` so downstream code can wire vertices.
