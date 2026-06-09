"""Edini configuration with pi-native config file integration.

Model/provider/API-key configuration is managed via pi's standard files:
  ~/.pi/agent/auth.json    — API keys
  ~/.pi/agent/models.json  — custom provider/model definitions
  ~/.pi/agent/settings.json — default provider/model/thinking

Edini's own settings.json stores only UI preferences (knowledge).
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# Project root (parent of the top-level edini/ directory).
# Handles both paths: edini/config.py and python3.11libs/edini/config.py
_config_dir = Path(__file__).resolve().parent
if _config_dir.name == "edini" and _config_dir.parent.name == "python3.11libs":
    PROJECT_ROOT = _config_dir.parent.parent  # python3.11libs/edini → up 2 levels
else:
    PROJECT_ROOT = _config_dir.parent         # edini/ → up 1 level (top-level package)

# ── Pi agent config files (shared with pi CLI) ──────────────────────
PI_AGENT_DIR = Path.home() / ".pi" / "agent"
PI_AUTH_FILE = PI_AGENT_DIR / "auth.json"
PI_MODELS_FILE = PI_AGENT_DIR / "models.json"
PI_SETTINGS_FILE = PI_AGENT_DIR / "settings.json"

# Edini's own local settings (knowledge — NOT provider/model/key)
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
# Edini UI Settings (knowledge only)
# ═══════════════════════════════════════════════════════════════════════

_EDINI_DEFAULTS: dict[str, Any] = {
    "knowledge_enabled": True,
    "reflection_provider": "",
    "reflection_model": "",
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
    return {
        **os.environ,
        "EDINI_TOOL_PORT": str(TOOL_EXECUTOR_PORT),
    }


def get_pi_command() -> list[str]:
    """Build the Pi subprocess command."""
    return [
        PI_EXECUTABLE,
        "--mode", "rpc",
        "-e", str(PI_EXTENSIONS_DIR / "edini-tools" / "index.ts"),
        "-e", str(PI_EXTENSIONS_DIR / "edini-context" / "index.ts"),
        "-e", str(PI_EXTENSIONS_DIR / "pi-visionizer" / "src" / "index.ts"),
    ]


# ═══════════════════════════════════════════════════════════════════════
# Pi-AI Data Bridge (auto-synced provider/model data)
# ═══════════════════════════════════════════════════════════════════════

_BRIDGE_SCRIPT = Path(__file__).resolve().parent / "pi_data_bridge.js"
_providers_cache: list[dict] | None = None
_models_cache: dict[str, list[dict]] = {}
_vision_models_cache: list[dict] | None = None


def _run_bridge(*args: str) -> Any:
    cmd = ["node", str(_BRIDGE_SCRIPT)] + list(args)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass
    return None


def get_pi_ai_providers() -> list[dict]:
    global _providers_cache
    if _providers_cache is None:
        _providers_cache = _run_bridge("providers") or []
    return _providers_cache


def get_pi_ai_models(provider: str) -> list[dict]:
    if provider not in _models_cache:
        data = _run_bridge("models", provider) or []
        _models_cache[provider] = data
    return _models_cache[provider]


def get_pi_ai_vision_models() -> list[dict]:
    global _vision_models_cache
    if _vision_models_cache is None:
        _vision_models_cache = _run_bridge("vision-models") or []
    return _vision_models_cache


def get_provider_auth_status(provider: str) -> dict:
    auth = read_pi_auth()
    if provider in auth:
        entry = auth[provider]
        if isinstance(entry, dict) and entry.get("type") == "api_key":
            key = entry.get("key", "")
            hint = key[:8] + "..." + key[-4:] if len(key) > 12 else key
            return {"configured": True, "source": "auth.json", "hint": hint}
    models = read_pi_models()
    prov_config = models.get("providers", {}).get(provider, {})
    if prov_config.get("apiKey"):
        return {"configured": True, "source": "models.json",
                "hint": prov_config["apiKey"][:20] + "..."}
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY", "google": "GEMINI_API_KEY",
        "mistral": "MISTRAL_API_KEY", "groq": "GROQ_API_KEY",
        "cerebras": "CEREBRAS_API_KEY", "xai": "XAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY", "nvidia": "NVIDIA_API_KEY",
        "fireworks": "FIREWORKS_API_KEY", "together": "TOGETHER_API_KEY",
        "huggingface": "HF_TOKEN", "zai": "ZAI_API_KEY",
        "zai-coding-cn": "ZAI_CODING_CN_API_KEY",
        "opencode": "OPENCODE_API_KEY",
        "kimi-coding": "KIMI_API_KEY",
        "minimax": "MINIMAX_API_KEY", "minimax-cn": "MINIMAX_CN_API_KEY",
        "xiaomi": "XIAOMI_API_KEY",
    }
    env_var = env_map.get(provider, "")
    if env_var and os.environ.get(env_var):
        return {"configured": True, "source": "env", "hint": env_var}
    return {"configured": False, "source": None, "hint": None}


def get_configured_providers() -> list[dict]:
    all_providers = get_pi_ai_providers()
    extra_ids = set()
    for p in read_pi_auth().keys():
        extra_ids.add(p)
    for p in read_pi_models().get("providers", {}).keys():
        extra_ids.add(p)
    result = []
    for p in all_providers:
        status = get_provider_auth_status(p["id"])
        if status["configured"]:
            result.append({
                "id": p["id"], "name": p["name"],
                "source": status["source"], "hint": status["hint"],
            })
    pi_ai_ids = {p["id"] for p in all_providers}
    for pid in sorted(extra_ids - pi_ai_ids):
        status = get_provider_auth_status(pid)
        if status["configured"]:
            display = read_pi_models().get("providers", {}).get(pid, {})
            result.append({
                "id": pid,
                "name": display.get("name", pid),
                "source": status["source"],
                "hint": status["hint"],
            })
    return result
