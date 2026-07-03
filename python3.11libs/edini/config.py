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

# Edini skills directory (optional, user-curated)
EDINI_SKILLS_DIR = PROJECT_ROOT / "skills"

PI_EXTENSION_ENTRIES = (
    {
        "name": "edini-tools",
        "description": "Houdini scene and node operation tools",
        "path": PI_EXTENSIONS_DIR / "edini-tools" / "index.ts",
    },
    {
        "name": "edini-context",
        "description": "Houdini context and knowledge injection",
        "path": PI_EXTENSIONS_DIR / "edini-context" / "index.ts",
    },
    {
        "name": "pi-visionizer",
        "description": "Vision support for text-only models",
        "path": PI_EXTENSIONS_DIR / "pi-visionizer" / "src" / "index.ts",
    },
)

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
    # Names of project skills (under EDINI_SKILLS_DIR) the user has toggled off
    # in Settings → Pi Capabilities. Filtered out of `--skill` args at pi spawn,
    # so a change takes effect after a pi restart.
    "disabled_skills": [],
    # Visual verification (capture_review + describe_image) on/off. Currently
    # disabled by default — the vision-driven verify loop added noise/false
    # positives during modeling. Toggle to True to re-enable once the visual
    # verification workflow is reworked. Read by get_pi_env() as
    # EDINI_VISUAL_VERIFICATION so the TS extensions can gate themselves.
    "visual_verification_enabled": False,
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

    Vision model selection IS passed via env vars: pi-visionizer reads
    VISIONIZER_PROVIDER / VISIONIZER_MODEL_ID as its config source
    (a session entry set via /visionizer-model still takes priority).
    The API key is resolved by pi's model registry from models.json,
    so only provider + model id are needed here.
    """
    env = {
        **os.environ,
        "EDINI_TOOL_PORT": str(TOOL_EXECUTOR_PORT),
    }
    settings = _load_edini_settings()
    vision_provider = settings.get("vision_provider", "")
    vision_model = settings.get("vision_model_id", "")
    if vision_provider and vision_model:
        env["VISIONIZER_PROVIDER"] = vision_provider
        env["VISIONIZER_MODEL_ID"] = vision_model
    # Visual verification gate (capture_review + describe_image). The TS
    # extensions (edini-context, edini-tools, pi-visionizer) read this env to
    # decide whether to inject verify rules / register the vision tools.
    env["EDINI_VISUAL_VERIFICATION"] = (
        "true" if settings.get("visual_verification_enabled") else "false"
    )
    return env


def _read_skill_frontmatter(skill_path: Path) -> dict[str, str]:
    """Read the YAML-like front matter from a skill markdown file."""
    try:
        text = skill_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}

    data: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip("\"'")
    return data


def _discover_skill_records() -> list[dict[str, Any]]:
    """Discover project skills with metadata for command building and UI."""
    records: list[dict[str, Any]] = []
    if not EDINI_SKILLS_DIR.is_dir():
        return records

    # Root-level .md files -> individual skills. README.md is documentation.
    for f in sorted(EDINI_SKILLS_DIR.iterdir()):
        if f.is_file() and f.suffix == ".md" and f.name.lower() != "readme.md":
            meta = _read_skill_frontmatter(f)
            records.append({
                "name": meta.get("name") or f.stem,
                "description": meta.get("description", ""),
                "path": str(f),
                "entry": str(f),
                "exists": f.is_file(),
                "source": "project",
            })

    # Subdirectories with SKILL.md -> named skills.
    for d in sorted(EDINI_SKILLS_DIR.iterdir()):
        skill_file = d / "SKILL.md"
        if d.is_dir() and skill_file.is_file():
            meta = _read_skill_frontmatter(skill_file)
            records.append({
                "name": meta.get("name") or d.name,
                "description": meta.get("description", ""),
                "path": str(d),
                "entry": str(skill_file),
                "exists": skill_file.is_file(),
                "source": "project",
            })

    # Honor user-disabled skills (Settings → Pi Capabilities toggles). A
    # disabled name is dropped here so BOTH `get_pi_command` (no `--skill`) and
    # `get_pi_capabilities` (hidden from the table) reflect the toggle from a
    # single filter point.
    disabled = set(_load_edini_settings().get("disabled_skills", []))
    if disabled:
        records = [r for r in records if r["name"] not in disabled]

    return records


def _discover_skills() -> list[str]:
    """Find skills curated under EDINI_SKILLS_DIR.

    Returns a flat list of ``--skill <path>`` arguments.
    Each immediate subdirectory containing ``SKILL.md`` is one skill.
    Root-level ``*.md`` files are also treated as individual skills
    (matching Pi's discovery convention).
    """
    args: list[str] = []
    for record in _discover_skill_records():
        args.extend(["--skill", record["path"]])
    return args


def get_pi_capabilities() -> dict[str, Any]:
    """Return the Pi extensions and skills Edini will load."""
    extensions = []
    for item in PI_EXTENSION_ENTRIES:
        path = item["path"]
        extensions.append({
            "name": item["name"],
            "description": item["description"],
            "path": str(path),
            "exists": path.is_file(),
            "source": "project",
        })

    package_path = PROJECT_ROOT / "package.json"
    package_info = {
        "path": str(package_path),
        "exists": package_path.is_file(),
        "name": "",
        "description": "",
    }
    if package_path.is_file():
        try:
            data = json.loads(package_path.read_text(encoding="utf-8"))
            package_info["name"] = data.get("name", "")
            package_info["description"] = data.get("description", "")
        except (json.JSONDecodeError, OSError):
            package_info["description"] = "Unable to parse package.json"

    return {
        "project_root": str(PROJECT_ROOT),
        "global_skills_disabled": True,
        "skills_dir": str(EDINI_SKILLS_DIR),
        "extensions": extensions,
        "skills": _discover_skill_records(),
        "package": package_info,
    }


def get_pi_command() -> list[str]:
    """Build the Pi subprocess command.

    Uses ``--no-skills`` to skip global skill loading and ``--skill`` to
    load only skills curated under this Edini project.
    """
    cmd = [
        PI_EXECUTABLE,
        "--mode", "rpc",
        "--approve",
        "--no-skills",
    ]
    for item in PI_EXTENSION_ENTRIES:
        cmd.extend(["-e", str(item["path"])])
    cmd.extend(_discover_skills())
    return cmd


# ═══════════════════════════════════════════════════════════════════════
# Pi-AI Data Bridge (auto-synced provider/model data)
# ═══════════════════════════════════════════════════════════════════════

_BRIDGE_SCRIPT = Path(__file__).resolve().parent / "pi_data_bridge.mjs"
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
        if isinstance(entry, dict) and entry.get("type") == "oauth":
            return {"configured": True, "source": "auth.json (oauth)",
                    "hint": "订阅登录 (OAuth)"}
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
    """Return configured providers grouped by origin.

    - ``kind="builtin"``: pi-ai built-in providers that have auth.
    - ``kind="custom"``: user-defined providers in models.json that have auth.
      Orphan auth.json entries (key present, no matching built-in or
      models.json provider) are ignored so stale leftovers don't pollute
      the list.
    """
    all_providers = get_pi_ai_providers()
    pi_ai_ids = {p["id"] for p in all_providers}
    models_providers = read_pi_models().get("providers", {})

    result: list[dict] = []
    for p in all_providers:
        status = get_provider_auth_status(p["id"])
        if status["configured"]:
            result.append({
                "id": p["id"], "name": p["name"],
                "source": status["source"], "hint": status["hint"],
                "kind": "builtin",
            })
    for pid in sorted(models_providers.keys()):
        if pid in pi_ai_ids:
            continue
        status = get_provider_auth_status(pid)
        if status["configured"]:
            pdata = models_providers[pid]
            result.append({
                "id": pid,
                "name": pdata.get("name", pid),
                "source": status["source"],
                "hint": status["hint"],
                "kind": "custom",
            })
    return result
