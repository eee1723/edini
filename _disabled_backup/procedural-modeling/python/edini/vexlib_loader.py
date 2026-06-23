"""VEX library loader — makes the ``vexlib/*.vfl`` functions truly callable.

Why this module exists
----------------------
The skill ships three ``.vfl`` files (skeleton/sections/attribs) under
``skills/procedural-modeling/scripts/vexlib/``. Two failure modes prevented
them from ever being used in practice:

1. ``harness._make_wrangle`` only injected an ``#include`` directive when the
   snippet happened to mention *exactly* ``make_polyline`` or ``make_circle``
   — the other ~13 functions were silently ignored.
2. The emitted ``#include <vexlib/foo.vfl>`` relies on ``HOUDINI_VEX_PATH``
   being set in the *process environment* before Houdini starts. Setting it
   at runtime from Python (after the VEX compiler cached its search paths)
   is unreliable, so the include silently failed to resolve.

This module fixes both:

* :func:`expand_vexlib` reads the real ``.vfl`` source and **inlines** only
  the files whose functions the snippet actually calls. Inline expansion does
  not depend on the environment, so it always works. This is the primary
  path used by the harness.
* :func:`ensure_vex_path` / :func:`vexlib_dir` still register
  ``HOUDINI_VEX_PATH`` so that hand-written ``#include`` directives authored
  directly in a wrangle continue to resolve.

The function→file map is derived from the actual source (each function is
declared as ``<ret> <name>(``), not hard-coded, so adding a new function to a
``.vfl`` automatically makes it injectable.
"""
from __future__ import annotations

import os
import re
import threading
from functools import lru_cache

# ── Location ──────────────────────────────────────────────────────────────
# python3.11libs/edini/vexlib_loader.py
#   → python3.11libs/  (pardir 1: up from edini/)
#   → <repo root>/     (pardir 2: up from python3.11libs/)
_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
VEXLIB_DIR = os.path.join(
    _REPO_ROOT, "skills", "procedural-modeling", "scripts", "vexlib"
)

# .vfl files in load order (later files may depend on earlier ones, e.g.
# sections.vfl calls make_closed_polyline from skeleton.vfl).
_VFL_FILES = ("skeleton.vfl", "sections.vfl", "attribs.vfl")

# ── Function → file discovery ─────────────────────────────────────────────
# Matches a VEX function declaration header. VEX uses two declaration forms:
#   int[] make_polyline(const int geohandle; const vector positions[])
#   void set_orient_from_tangent(...)
# The regex captures the function name (an identifier) right after the return
# type, which itself ends in ) ] or is a bare word (void/int/float/...).
_FUNC_DECL_RE = re.compile(
    r"""
    ^                        # start of line
    (?:[A-Za-z_][\w\[\]\s]*?)  # return type (greedy-min, may be "int[]")
    \s+                      # whitespace before name
    ([A-Za-z_]\w*)           # group(1): function name
    \s*\(                    # opening paren of the parameter list
    """,
    re.VERBOSE | re.MULTILINE,
)

# Once a function name appears as a *call* we look for ``name(`` not preceded
# by a word char (so ``len(...)`` won't match ``my_len``).
def _call_pattern(func_name: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(func_name)}\s*\(")


@lru_cache(maxsize=1)
def _function_index() -> dict[str, str]:
    """Map every declared function name → the .vfl file that defines it.

    Cached because the .vfl files do not change during a session. The map is
    rebuilt automatically on the first call of each interpreter session.
    """
    index: dict[str, str] = {}
    for vfl in _VFL_FILES:
        path = os.path.join(VEXLIB_DIR, vfl)
        if not os.path.isfile(path):
            # Missing file — skip silently; callers handle empty results.
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                src = fh.read()
        except OSError:
            continue
        for m in _FUNC_DECL_RE.finditer(src):
            name = m.group(1)
            # First declaration wins; files are ordered skeleton→sections→attribs
            # so dependency direction is respected if a name were duplicated.
            index.setdefault(name, vfl)
    return index


def known_functions() -> set[str]:
    """All function names exported across the vexlib .vfl files."""
    return set(_function_index())


def used_vexlib_functions(snippet: str) -> list[str]:
    """Return the sorted list of vexlib functions *called* in ``snippet``.

    A function is "used" if it is invoked as ``name(...)`` somewhere in the
    code (not just mentioned in a comment). Declarations inside the snippet
    itself are ignored: only calls to functions defined in the library count.
    """
    if not snippet:
        return []
    used: list[str] = []
    for fname in _function_index():
        if _call_pattern(fname).search(snippet):
            used.append(fname)
    return sorted(used)


def _needed_files(used: list[str]) -> list[str]:
    """Resolve the (ordered, de-duplicated) set of .vfl files to inline.

    Order follows ``_VFL_FILES`` so dependencies resolve: skeleton before
    sections (sections call make_closed_polyline) before attribs.
    """
    files_for_used = {_function_index()[f] for f in used}
    return [vfl for vfl in _VFL_FILES if vfl in files_for_used]


@lru_cache(maxsize=8)
def _file_source(vfl: str) -> str:
    """Read and cache a single .vfl file's source."""
    with open(os.path.join(VEXLIB_DIR, vfl), "r", encoding="utf-8") as fh:
        return fh.read()


def expand_vexlib(snippet: str) -> str:
    """Inline the vexlib sources a snippet needs, in front of it.

    This is the reliable primary path: no ``HOUDINI_VEX_PATH`` dependency,
    no include-resolution ambiguity. Only the files whose functions are
    actually called are prepended (keeps wrangle snippets small).

    If the snippet already contains an ``#include`` we assume the author
    wrote it deliberately and leave the snippet untouched (the include path
    is still registered via :func:`ensure_vex_path` for resolution).
    """
    if not snippet:
        return snippet
    # Respect an explicit hand-written include — don't double-inject.
    if "#include" in snippet:
        return snippet
    used = used_vexlib_functions(snippet)
    if not used:
        return snippet
    parts = [
        f"// ── vexlib inline ({', '.join(_needed_files(used))}) "
        f"— auto-injected by vexlib_loader ──"
    ]
    for vfl in _needed_files(used):
        parts.append(_file_source(vfl))
    parts.append(snippet)
    return "\n".join(parts)


# ── Environment registration (for hand-written #include directives) ───────
_path_registered = False
_lock = threading.Lock()


def ensure_vex_path() -> bool:
    """Ensure ``HOUDINI_VEX_PATH`` covers the vexlib parent directory.

    ``#include <vexlib/skeleton.vfl>`` resolves against the *parent* of the
    ``vexlib`` folder, so we register ``.../scripts`` (the parent of
    ``vexlib``). This runs at import time and is idempotent.

    Returns True if the path is (now) present, False if vexlib is missing or
    it could not be set. Note: VEX caches search paths at process start, so
    this primarily helps when edini is imported before the first VEX compile
    (the common case, since edini loads as a Houdini Python package).
    """
    global _path_registered
    if _path_registered:
        return True
    with _lock:
        if _path_registered:
            return True
        scripts_dir = os.path.dirname(VEXLIB_DIR)
        if not os.path.isdir(VEXLIB_DIR):
            _path_registered = True
            return False
        current = os.environ.get("HOUDINI_VEX_PATH", "")
        # De-dup: don't append the same dir twice across re-imports.
        parts = [p for p in current.split(os.pathsep) if p]
        if scripts_dir not in parts:
            parts.append(scripts_dir)
            os.environ["HOUDINI_VEX_PATH"] = os.pathsep.join(parts)
        _path_registered = True
        return True


# Register eagerly on import so hand-written includes resolve too.
ensure_vex_path()
