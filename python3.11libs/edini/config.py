"""Edini configuration with local settings persistence.

Priority: env vars > settings.json > built-in defaults.
"""
import json
import os
from pathlib import Path
from typing import Any

# config.py is at python3.11libs/edini/config.py
# Project root is 3 levels up: edini/ -> python3.11libs/ -> project root/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Local settings file (gitignored, next to config.py)
SETTINGS_FILE = Path(__file__).resolve().parent / "settings.json"

# Pi executable (from npm global install)
# Houdini may not have npm's bin dir in PATH, so we search for it.
def _find_pi() -> str:
    """Find the pi executable, checking common locations."""
    import shutil
    # 1. Explicit env var
    env_path = os.environ.get("EDINI_PI_PATH")
    if env_path:
        return env_path
    # 2. Check npm global bin (Windows)
    npm_root = os.environ.get("APPDATA", "") + r"\npm"
    for name in ("pi.cmd", "pi"):
        pi_path = os.path.join(npm_root, name)
        if os.path.isfile(pi_path):
            return pi_path
    # 3. Fall back to PATH
    found = shutil.which("pi")
    if found:
        return found
    return "pi"  # last resort

PI_EXECUTABLE = _find_pi()

# Pi extensions directory
PI_EXTENSIONS_DIR = PROJECT_ROOT / "pi-extensions"

# Tool executor HTTP server
TOOL_EXECUTOR_HOST = "127.0.0.1"
TOOL_EXECUTOR_PORT = 9876

# Panel dimensions
PANEL_DEFAULT_WIDTH = 500
PANEL_DEFAULT_HEIGHT = 600

# ---- Defaults (lowest priority) ----
_DEFAULTS: dict[str, Any] = {
    "api_key": "",
    "provider": "deepseek",
    "model_id": "deepseek-chat",
    "theme_color": "cyan",
    "font_scale": 1.0,
    "knowledge_enabled": True,
}

# ---- Env var overrides (highest priority) ----
_ENV_MAP = {
    "api_key": "EDINI_API_KEY",
    "provider": "EDINI_MODEL_PROVIDER",
    "model_id": "EDINI_MODEL_ID",
}


def _load_settings() -> dict[str, Any]:
    """Load settings from local JSON file, falling back to defaults."""
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**_DEFAULTS, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULTS)


def get_settings() -> dict[str, Any]:
    """Get current settings (env overrides file)."""
    settings = _load_settings()
    for key, env_name in _ENV_MAP.items():
        env_val = os.environ.get(env_name)
        if env_val:
            settings[key] = env_val
    return settings


def save_settings(updates: dict[str, Any]) -> None:
    """Merge updates into settings file (atomic write)."""
    current = _load_settings()
    current.update(updates)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2, ensure_ascii=False)
    tmp.replace(SETTINGS_FILE)


def get_pi_env() -> dict[str, str]:
    """Build environment dict for Pi subprocess with current API key."""
    settings = get_settings()
    env = {
        **os.environ,
        "EDINI_TOOL_PORT": str(TOOL_EXECUTOR_PORT),
    }
    # Pass API key as env var so Pi can use it
    api_key = settings.get("api_key", "")
    if api_key:
        env["DEEPSEEK_API_KEY"] = api_key
    return env


def get_pi_command() -> list[str]:
    """Build the Pi subprocess command."""
    return [
        PI_EXECUTABLE,
        "--mode", "rpc",
        "-e", str(PI_EXTENSIONS_DIR / "edini-tools" / "index.ts"),
        "-e", str(PI_EXTENSIONS_DIR / "edini-context" / "index.ts"),
        "-e", str(PI_EXTENSIONS_DIR / "pi-visionizer" / "src" / "index.ts"),
    ]


# ---- Model History (user input memory) ----
_MODEL_HISTORY_FILE = Path(__file__).resolve().parent / "model_history.json"
_MAX_MODEL_HISTORY = 10


def get_model_history() -> list[str]:
    """Return list of previously used model names, newest first."""
    if _MODEL_HISTORY_FILE.exists():
        try:
            with open(_MODEL_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def add_model_history(model_name: str) -> None:
    """Add a model name to history, keeping last 10 unique entries."""
    history = get_model_history()
    if model_name in history:
        history.remove(model_name)
    history.insert(0, model_name)
    history = history[:_MAX_MODEL_HISTORY]
    with open(_MODEL_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
