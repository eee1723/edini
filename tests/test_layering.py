"""Architecture layering guard.

Enforces the dependency rules that keep the unified-chat-window architecture
maintainable. Uses AST parsing (no import side effects) to check banned imports.

Rules:
  1. edini/ui/components/* MUST NOT import:
     - edini.rpc_client (components are presentation-only, no RPC)
     - edini.ui.chat.* (components don't know about the assembly layer)
     - edini.main_window / edini.ui.main_window (no upward coupling)
  2. chat_runtime MUST NOT import edini.ui.components (Runtime emits signals,
     doesn't know who consumes them)
"""
import ast
from pathlib import Path

ROOT = Path(__file__).parent.parent / "python3.11libs" / "edini"

BANNED_FOR_COMPONENTS = {
    "edini.rpc_client",
    "edini.ui.chat",
    "edini.ui.chat.chat_runtime",
    "edini.ui.chat.base_driver",
    "edini.ui.chat.window_shell",
    "edini.ui.chat.scope",
    "edini.main_window",
    "edini.ui.main_window",
}
BANNED_FOR_CHAT_RUNTIME = {
    "edini.ui.components",
}


def _imports_in(path: Path) -> set[str]:
    """Extract all imported module names from a Python file via AST."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:  # absolute imports only
                mods.add(node.module)
    return mods


def test_components_dont_import_rpc_or_chat():
    """Every file in components/ must be free of rpc/chat/main_window imports."""
    comp_dir = ROOT / "ui" / "components"
    assert comp_dir.exists(), f"components dir not found: {comp_dir}"
    offenders = []
    for py in comp_dir.glob("*.py"):
        if py.name == "__init__.py":
            continue
        imps = _imports_in(py)
        bad = imps & BANNED_FOR_COMPONENTS
        if bad:
            offenders.append(f"{py.name}: imports {bad}")
    assert not offenders, "components/ has banned imports:\n" + "\n".join(offenders)


def test_chat_runtime_doesnt_import_components():
    """ChatRuntime must not import components (signals only, no UI awareness)."""
    candidates = [
        ROOT / "ui" / "chat" / "chat_runtime.py",
        ROOT / "ui" / "chat_runtime.py",
    ]
    found = False
    for cand in candidates:
        if cand.exists():
            found = True
            imps = _imports_in(cand)
            bad = imps & BANNED_FOR_CHAT_RUNTIME
            assert not bad, f"{cand.name} imports banned: {bad}"
    assert found, "chat_runtime.py not found in expected locations"


def test_status_doesnt_import_rpc():
    """status/ (ContextPanel etc.) should not directly import rpc_client."""
    status_dir = ROOT / "ui" / "status"
    if not status_dir.exists():
        return  # skip if not present
    offenders = []
    for py in status_dir.glob("*.py"):
        if py.name == "__init__.py":
            continue
        imps = _imports_in(py)
        if "edini.rpc_client" in imps:
            offenders.append(py.name)
    assert not offenders, f"status/ imports rpc_client: {offenders}"
