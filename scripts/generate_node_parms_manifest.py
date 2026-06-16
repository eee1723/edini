#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate the bundled node-params manifest (C-station).

Run this ONCE per Houdini major version inside a real Houdini Python Shell
(or hython) to (re)build ``python3.11libs/edini/data/node_parms_manifest.json``.
The committed file pins the exact parm names/types/menu tokens for that
Houdini version so that:

  * ``houdini_node_parms`` queries are zero-cost and offline-accurate, and
  * ``_validate_recipe`` can reject misspelled postprocess parm names at build
    time.

Usage (inside Houdini Python Shell):
    import sys; sys.path.insert(0, r"E:\\edini\\python3.11libs")
    from edini.node_utils import generate_node_parms_manifest
    import json, os
    out = os.path.join(r"E:\\edini\\python3.11libs\\edini\\data",
                       "node_parms_manifest.json")
    m = generate_node_parms_manifest("Sop")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)
    print("wrote", out, "with", len(m["node_types"]), "node types")

Or from hython on the command line:
    hython scripts/generate_node_parms_manifest.py [--category Sop] [--out PATH]
"""
import argparse
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the node-params manifest from a live Houdini.")
    parser.add_argument("--category", default="Sop",
                        help="NodeType category to dump (default: Sop)")
    # Default output sits next to the edini package data dir.
    default_out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "python3.11libs", "edini", "data", "node_parms_manifest.json")
    parser.add_argument("--out", default=default_out,
                        help=f"Output JSON path (default: {default_out})")
    args = parser.parse_args()

    try:
        import hou  # noqa: F401
    except ImportError:
        print("ERROR: this script must run inside Houdini (hython) — "
              "the `hou` module is not available.", file=sys.stderr)
        return 2

    # Make the edini package importable.
    pkg_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "python3.11libs")
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)

    from edini.node_utils import generate_node_parms_manifest

    manifest = generate_node_parms_manifest(args.category)
    count = len(manifest.get("node_types", {}))
    excluded = manifest.get("excluded_namespaces", [])

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    os.replace(tmp, args.out)  # atomic on both Windows and POSIX

    print(f"Wrote {args.out}")
    print(f"  Houdini version: {manifest.get('houdini_version')}")
    print(f"  Category:        {args.category}")
    print(f"  Node types:      {count}")
    print(f"  Excluded NS:     {', '.join(excluded) if excluded else '(none)'}")

    # Quick sanity spot-checks on a few nodes agents use most.
    nts = manifest.get("node_types", {})
    for probe in ("normal", "attribpromote", "copytopoints", "polybevel"):
        if probe in nts:
            names = [p["name"] for p in nts[probe].get("parms", [])]
            print(f"  {probe}: {len(names)} parms, e.g. {names[:6]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
