"""Edini installation script for Houdini.

Registers Edini as a Houdini package so it appears in the menu bar.
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path


def get_edini_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_houdini_packages_dir() -> Path | None:
    candidates = [
        Path(os.environ.get("HOUDINI_USER_PREF_DIR", "")) / "packages",
        Path.home() / "Documents" / "houdini21.0" / "packages",
        Path.home() / "Documents" / "houdini21.5" / "packages",
    ]
    try:
        import hou
        prefs = hou.getenv("HOUDINI_USER_PREF_DIR") or hou.homeHoudiniDirectory()
        candidates.insert(0, Path(prefs) / "packages")
    except ImportError:
        pass
    for d in candidates:
        if d.exists() and d.is_dir():
            return d
    return None


def install() -> None:
    root = get_edini_root()
    packages_dir = get_houdini_packages_dir()

    if packages_dir is None:
        print("ERROR: Could not find Houdini packages directory.")
        print("Please set HOUDINI_USER_PREF_DIR or manually install.")
        sys.exit(1)

    packages_dir.mkdir(parents=True, exist_ok=True)
    package_file = packages_dir / "edini.json"

    path_forward = str(root).replace("\\", "/")

    with open(package_file, "w") as f:
        json.dump({
            "env": [
                {"EDINI_PATH": path_forward}
            ],
            "path": "$EDINI_PATH",
            "houdini": {
                "python3.11libs": "$EDINI_PATH/python3.11libs"
            }
        }, f, indent=2)

    print(f"Edini installed!")
    print(f"  Package file: {package_file}")
    print(f"  Project root: {root}")
    print()
    print("Next steps:")
    print("  1. Restart Houdini")
    print("  2. Menu: Edini > Open Chat Panel")
    print("  3. Or run: scripts/setup_pi.bat")


if __name__ == "__main__":
    install()
