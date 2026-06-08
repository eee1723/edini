"""Edini configuration with pi-native config file integration.

Model/provider/API-key configuration is managed via pi's standard files:
  ~/.pi/agent/auth.json    — API keys
  ~/.pi/agent/models.json  — custom provider/model definitions
  ~/.pi/agent/settings.json — default provider/model/thinking

Edini's own settings.json stores only UI preferences (theme, font, knowledge).
"""
import json
import os
from pathlib import Path
from typing import Any

# config.py is at python3.11libs/edini/config.py
# Project root is 3 levels up: edini/ -> python3.11libs/ -> project root/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Pi agent config files (shared with pi CLI) ──────────────────────
PI_AGENT_DIR = Path.home() / ".pi" / "agent"
PI_AUTH_FILE = PI_AGENT_DIR / "auth.json"
PI_MODELS_FILE = PI_AGENT_DIR / "models.json"
PI_SETTINGS_FILE = PI_AGENT_DIR / "settings.json"

# Edini's own local settings (theme, font, knowledge — NOT provider/model/key)
EDINI_SETTINGS_FILE = Path(__file__).resolve().parent / "settings.json"

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


# ═══════════════════════════════════════════════════════════════════════
# Pi Config File Helpers
# ═══════════════════════════════════════════════════════════════════════

def _atomic_write_json(path: Path, data: dict) -> None:
    """Write JSON to file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def read_pi_auth() -> dict:
    """Read ~/.pi/agent/auth.json. Returns {} if missing or invalid."""
    if PI_AUTH_FILE.exists():
        try:
            with open(PI_AUTH_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def read_pi_models() -> dict:
    """Read ~/.pi/agent/models.json. Returns {} if missing or invalid."""
    if PI_MODELS_FILE.exists():
        try:
            with open(PI_MODELS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def read_pi_settings() -> dict:
    """Read ~/.pi/agent/settings.json. Returns {} if missing or invalid."""
    if PI_SETTINGS_FILE.exists():
        try:
            with open(PI_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def write_pi_auth(data: dict) -> None:
    """Overwrite ~/.pi/agent/auth.json."""
    _atomic_write_json(PI_AUTH_FILE, data)


def write_pi_models(data: dict) -> None:
    """Overwrite ~/.pi/agent/models.json."""
    _atomic_write_json(PI_MODELS_FILE, data)


def write_pi_settings(data: dict) -> None:
    """Overwrite ~/.pi/agent/settings.json."""
    _atomic_write_json(PI_SETTINGS_FILE, data)


# ═══════════════════════════════════════════════════════════════════════
# Edini UI Settings (theme, font, knowledge only)
# ═══════════════════════════════════════════════════════════════════════

_EDINI_DEFAULTS: dict[str, Any] = {
    "theme_color": "cyan",
    "font_scale": 1.0,
    "knowledge_enabled": True,
    "vision_provider": "",
    "vision_model_id": "",
}


def _load_edini_settings() -> dict[str, Any]:
    """Load Edini's own UI settings (not provider/model)."""
    if EDINI_SETTINGS_FILE.exists():
        try:
            with open(EDINI_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**_EDINI_DEFAULTS, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_EDINI_DEFAULTS)


def get_settings() -> dict[str, Any]:
    """Get Edini UI settings."""
    return _load_edini_settings()


def save_settings(updates: dict[str, Any]) -> None:
    """Merge updates into Edini settings file."""
    current = _load_edini_settings()
    current.update(updates)
    _atomic_write_json(EDINI_SETTINGS_FILE, current)


# ═══════════════════════════════════════════════════════════════════════
# Legacy Migration
# ═══════════════════════════════════════════════════════════════════════

def migrate_legacy_settings() -> str | None:
    """Migrate old api_key/provider/model_id to pi config files.
    Returns migration message or None if nothing to migrate.
    """
    old = _load_edini_settings()
    old_key = old.get("api_key", "")
    old_provider = old.get("provider", "")
    old_model = old.get("model_id", "")

    if not old_key or not old_provider:
        return None

    # Write API key to auth.json
    auth = read_pi_auth()
    if old_provider not in auth:
        auth[old_provider] = {"type": "api_key", "key": old_key}
        write_pi_auth(auth)

    # Write default model to pi settings.json
    pi_settings = read_pi_settings()
    if "defaultProvider" not in pi_settings:
        pi_settings["defaultProvider"] = old_provider
        pi_settings["defaultModel"] = old_model
        write_pi_settings(pi_settings)

    # Remove legacy keys from edini settings
    old.pop("api_key", None)
    old.pop("provider", None)
    old.pop("model_id", None)
    old.pop("vision_api_key", None)
    _atomic_write_json(EDINI_SETTINGS_FILE, old)

    return f"✅ Migrated: {old_provider}/{old_model} → ~/.pi/agent/"


# ═══════════════════════════════════════════════════════════════════════
# Pi Subprocess
# ═══════════════════════════════════════════════════════════════════════

def get_pi_env() -> dict[str, str]:
    """Build environment dict for Pi subprocess.

    Pi reads ~/.pi/agent/auth.json itself on startup, so no API key
    injection via env vars is needed.
    """
    env = {
        **os.environ,
        "EDINI_TOOL_PORT": str(TOOL_EXECUTOR_PORT),
    }
    # Pass vision config for pi-visionizer backward compat during transition.
    settings = get_settings()
    vision_provider = settings.get("vision_provider", "")
    vision_model = settings.get("vision_model_id", "")
    if vision_provider and vision_model:
        env["VISIONIZER_PROVIDER"] = vision_provider
        env["VISIONIZER_MODEL_ID"] = vision_model
    return env


def get_pi_command() -> list[str]:
    """Build the Pi subprocess command."""
    cmds = [
        PI_EXECUTABLE,
        "--mode", "rpc",
        "-e", str(PI_EXTENSIONS_DIR / "edini-tools" / "index.ts"),
        "-e", str(PI_EXTENSIONS_DIR / "edini-context" / "index.ts"),
        "-e", str(PI_EXTENSIONS_DIR / "pi-visionizer" / "src" / "index.ts"),
    ]
    # Add 智谱 extension if it exists
    zhipu_ext = PI_EXTENSIONS_DIR / "edini-zhipu" / "index.ts"
    if zhipu_ext.exists():
        cmds.extend(["-e", str(zhipu_ext)])
    return cmds


# ═══════════════════════════════════════════════════════════════════════
# Model History (user input memory)
# ═══════════════════════════════════════════════════════════════════════

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
