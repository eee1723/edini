"""Bootstrap the vendored runtime (portable Node + Pi) on a fresh checkout.

Edini bundles its own Node.js and Pi under ``vendor/`` so end-users never
need to install Node/npm globally. That runtime is NOT committed to git
(node.exe is ~30-100MB), so after cloning this repo you run this script once
to materialize it.

What it does:
  1. vendor/node/        — if missing, download a portable Node.js LTS for
                           this platform and extract it.
  2. vendor/node_modules/ — if the Pi package is missing, install it into
                           vendor/ using the vendored npm.

Run from anywhere:
    python scripts/bootstrap_vendor.py
    hython scripts/bootstrap_vendor.py    # Houdini's Python works too
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

# Pinned LTS version known to work with Pi. Bump deliberately and re-test.
NODE_VERSION = "v22.23.0"
PI_PACKAGE = "@earendil-works/pi-coding-agent"
PI_VERSION_RANGE = "^0.79.7"

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "vendor"
VENDOR_NODE = VENDOR / "node"
VENDOR_NODE_MODULES = VENDOR / "node_modules"
VENDOR_PI = VENDOR_NODE_MODULES / "@earendil-works" / "pi-coding-agent"


def _plat_tag() -> tuple[str, str]:
    """Return (node-dir-suffix, archive-ext) for the current platform."""
    s = platform.system()
    m = platform.machine().lower()
    if s == "Windows":
        return ("win-x64", ".zip")
    if s == "Darwin":
        arch = "arm64" if "arm" in m or "aarch64" in m else "x64"
        return (f"darwin-{arch}", ".tar.gz")
    if s == "Linux":
        arch = "arm64" if "arm" in m or "aarch64" in m else "x64"
        return (f"linux-{arch}", ".tar.xz")
    raise RuntimeError(f"unsupported platform: {s}")


def node_exe() -> Path:
    name = "node.exe" if platform.system() == "Windows" else "bin/node"
    return VENDOR_NODE / name


def need_node() -> bool:
    return not node_exe().is_file()


def need_pi() -> bool:
    return not (VENDOR_PI / "dist" / "cli.js").is_file()


def download_portable_node() -> None:
    """Download and extract the portable Node LTS into vendor/node."""
    suffix, ext = _plat_tag()
    url = f"https://nodejs.org/dist/{NODE_VERSION}/node-{NODE_VERSION}-{suffix}{ext}"
    archive = VENDOR / f"node{ext}"
    print(f"Downloading Node {NODE_VERSION} ({suffix})…")
    print(f"  {url}")
    VENDOR.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, archive)
    print("Extracting…")
    if ext == ".zip":
        extract_dir = VENDOR / "_node_extract"
        with zipfile.ZipFile(archive) as z:
            z.extractall(extract_dir)
        inner = next(extract_dir.iterdir())  # node-<ver>-<plat>/
        if VENDOR_NODE.exists():
            shutil.rmtree(VENDOR_NODE)
        shutil.move(str(inner), str(VENDOR_NODE))
        shutil.rmtree(extract_dir, ignore_errors=True)
    else:
        # tar.gz / tar.xz — use system tar (present on macOS/Linux).
        import tarfile
        extract_dir = VENDOR / "_node_extract"
        extract_dir.mkdir(exist_ok=True)
        mode = "r:gz" if ext == ".tar.gz" else "r:xz"
        with tarfile.open(archive, mode) as t:
            t.extractall(extract_dir)
        inner = next(extract_dir.iterdir())
        if VENDOR_NODE.exists():
            shutil.rmtree(VENDOR_NODE)
        shutil.move(str(inner), str(VENDOR_NODE))
        shutil.rmtree(extract_dir, ignore_errors=True)
    archive.unlink(missing_ok=True)

    # Verify it runs.
    r = subprocess.run([str(node_exe()), "--version"], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERROR: downloaded node failed: {r.stderr}", file=sys.stderr)
        sys.exit(1)
    print(f"  Node installed: {r.stdout.strip()}")


def install_pi() -> None:
    """Install Pi into vendor/node_modules using the vendored npm."""
    VENDOR.mkdir(parents=True, exist_ok=True)
    # Ensure vendor/package.json declares the dependency.
    pkg_path = VENDOR / "package.json"
    pkg = {}
    if pkg_path.is_file():
        try:
            pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pkg = {}
    pkg.setdefault("name", "edini-vendor")
    pkg.setdefault("private", True)
    deps = pkg.setdefault("dependencies", {})
    if PI_PACKAGE not in deps:
        deps[PI_PACKAGE] = PI_VERSION_RANGE
    pkg_path.write_text(json.dumps(pkg, indent=2), encoding="utf-8")

    npm = VENDOR_NODE / ("npm.cmd" if platform.system() == "Windows" else "bin/npm")
    if not npm.is_file():
        print(f"ERROR: npm not found at {npm}", file=sys.stderr)
        sys.exit(1)
    # The vendored node must be on PATH so postinstall scripts find `node`.
    env = dict(os.environ)
    node_dir = str(VENDOR_NODE if platform.system() == "Windows" else VENDOR_NODE / "bin")
    env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")
    print(f"Installing {PI_PACKAGE}@{PI_VERSION_RANGE} into vendor/node_modules…")
    r = subprocess.run(
        [str(npm), "install", "--no-audit", "--no-fund"],
        cwd=str(VENDOR), env=env,
    )
    if r.returncode != 0:
        print(f"ERROR: npm install failed (exit {r.returncode})", file=sys.stderr)
        sys.exit(1)
    cli = VENDOR_PI / "dist" / "cli.js"
    print(f"  Pi installed: cli.js at {cli} ({'OK' if cli.is_file() else 'MISSING'})")


def main() -> None:
    print(f"Edini vendor bootstrap — {ROOT}")
    VENDOR.mkdir(parents=True, exist_ok=True)
    if need_node():
        download_portable_node()
    else:
        print(f"Node already present: {node_exe()}")
    if need_pi():
        install_pi()
    else:
        print(f"Pi already present: {VENDOR_PI}")
    print("\nDone. Edini's vendored runtime is ready.")


if __name__ == "__main__":
    main()
