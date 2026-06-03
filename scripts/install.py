"""Edini installation script for Houdini.

Registers the Edini package so Houdini can import it.
Run with Houdini's Python (hython):

    hython scripts/install.py

Or from within Houdini's Python Shell:

    exec(open(r'F:/zz/Edini/scripts/install.py').read())
"""
from __future__ import annotations

import os
import sys
import json
from pathlib import Path


def get_edini_root() -> Path:
    """Get the Edini project root (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


def get_houdini_packages_dir() -> Path | None:
    """Find Houdini's packages directory."""
    candidates = [
        Path(os.environ.get("HOUDINI_USER_PREF_DIR", "")) / "packages",
        Path.home() / "Documents" / "houdini21.0" / "packages",
        Path.home() / "Documents" / "houdini21.5" / "packages",
    ]

    # Try via hou module if available (running inside Houdini)
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
    """Install Edini to Houdini's packages directory."""
    root = get_edini_root()
    packages_dir = get_houdini_packages_dir()

    if packages_dir is None:
        print("ERROR: Could not find Houdini packages directory.")
        print("Please set HOUDINI_USER_PREF_DIR or manually install.")
        sys.exit(1)

    packages_dir.mkdir(parents=True, exist_ok=True)
    package_file = packages_dir / "edini.json"

    with open(package_file, "w") as f:
        json.dump({
            "env": [{"PYTHONPATH": str(root)}],
            "path": str(root),
        }, f, indent=2)

    print(f"✅ Edini installed!")
    print(f"   Package file: {package_file}")
    print(f"   Project root: {root}")
    print()
    print("Next steps:")
    print("  1. Restart Houdini")
    print("  2. Run: scripts/setup_pi.bat")
    print("  3. Set API key: set ANTHROPIC_API_KEY=sk-ant-...")
    print()
    print("In Houdini Python Shell:")
    print("  from edini import createPanel")
    print("  panel = createPanel()")
    print("  panel.show()")


if __name__ == "__main__":
    install()
