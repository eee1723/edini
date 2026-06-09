"""Unit tests for edini/config.py — config file read/write, migration, env.

config.py is pure Python (no hou dependency).
Run: pytest tests/test_config.py -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# ── Import setup ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))

# Force reimport so we get a clean module
for _mod in list(sys.modules):
    if _mod.startswith("edini"):
        del sys.modules[_mod]

import edini.config as cfg


# ═══════════════════════════════════════════════════════════════════════
# TestAtomicWriteJson
# ═══════════════════════════════════════════════════════════════════════

class TestAtomicWriteJson(unittest.TestCase):
    """Tests for _atomic_write_json()."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)

    def test_writes_valid_json(self):
        """Writes valid JSON that round-trips correctly."""
        path = Path(self.tmpdir.name) / "out.json"
        data = {"hello": "world", "num": 42}
        cfg._atomic_write_json(path, data)
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded, data)

    def test_creates_parent_dirs(self):
        """Creates intermediate directories if they don't exist."""
        path = Path(self.tmpdir.name) / "a" / "b" / "c" / "file.json"
        cfg._atomic_write_json(path, {"x": 1})
        self.assertTrue(path.exists())
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"x": 1})

    def test_overwrites_existing(self):
        """Overwrites an existing file with new content."""
        path = Path(self.tmpdir.name) / "overwrite.json"
        cfg._atomic_write_json(path, {"v": 1})
        cfg._atomic_write_json(path, {"v": 2})
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["v"], 2)

    def test_unicode_values(self):
        """Handles unicode strings correctly."""
        path = Path(self.tmpdir.name) / "unicode.json"
        data = {"name": "智谱清言", "emoji": "🧪"}
        cfg._atomic_write_json(path, data)
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["name"], "智谱清言")
        self.assertEqual(loaded["emoji"], "🧪")


# ═══════════════════════════════════════════════════════════════════════
# TestReadPiAuth
# ═══════════════════════════════════════════════════════════════════════

class TestReadPiAuth(unittest.TestCase):
    """Tests for read_pi_auth()."""

    def test_missing_file_returns_empty(self):
        """Returns {} when auth file doesn't exist."""
        with patch.object(cfg, "PI_AUTH_FILE", Path("/nonexistent/auth.json")):
            result = cfg.read_pi_auth()
        self.assertEqual(result, {})

    def test_valid_file(self):
        """Returns parsed dict from valid auth.json."""
        with tempfile.TemporaryDirectory() as tmp:
            auth_path = Path(tmp) / "auth.json"
            data = {"anthropic": {"type": "api_key", "key": "sk-test123"}}
            auth_path.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(cfg, "PI_AUTH_FILE", auth_path):
                result = cfg.read_pi_auth()
            self.assertEqual(result, data)

    def test_corrupt_json_returns_empty(self):
        """Returns {} when file contains invalid JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            auth_path = Path(tmp) / "auth.json"
            auth_path.write_text("{invalid json!!!", encoding="utf-8")
            with patch.object(cfg, "PI_AUTH_FILE", auth_path):
                result = cfg.read_pi_auth()
            self.assertEqual(result, {})


# ═══════════════════════════════════════════════════════════════════════
# TestReadPiModels
# ═══════════════════════════════════════════════════════════════════════

class TestReadPiModels(unittest.TestCase):
    """Tests for read_pi_models()."""

    def test_missing_file_returns_empty(self):
        """Returns {} when models file doesn't exist."""
        with patch.object(cfg, "PI_MODELS_FILE", Path("/nonexistent/models.json")):
            result = cfg.read_pi_models()
        self.assertEqual(result, {})

    def test_valid_file(self):
        """Returns parsed dict from valid models.json."""
        with tempfile.TemporaryDirectory() as tmp:
            models_path = Path(tmp) / "models.json"
            data = {"providers": {"myprov": {"name": "My Provider"}}}
            models_path.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(cfg, "PI_MODELS_FILE", models_path):
                result = cfg.read_pi_models()
            self.assertEqual(result, data)


# ═══════════════════════════════════════════════════════════════════════
# TestReadPiSettings
# ═══════════════════════════════════════════════════════════════════════

class TestReadPiSettings(unittest.TestCase):
    """Tests for read_pi_settings()."""

    def test_missing_file_returns_empty(self):
        """Returns {} when settings file doesn't exist."""
        with patch.object(cfg, "PI_SETTINGS_FILE", Path("/nonexistent/settings.json")):
            result = cfg.read_pi_settings()
        self.assertEqual(result, {})


# ═══════════════════════════════════════════════════════════════════════
# TestWritePiAuth
# ═══════════════════════════════════════════════════════════════════════

class TestWritePiAuth(unittest.TestCase):
    """Tests for write_pi_auth()."""

    def test_writes_data(self):
        """Writes auth data that can be read back."""
        with tempfile.TemporaryDirectory() as tmp:
            auth_path = Path(tmp) / "auth.json"
            data = {"openai": {"type": "api_key", "key": "sk-abc"}}
            with patch.object(cfg, "PI_AUTH_FILE", auth_path):
                cfg.write_pi_auth(data)
                result = cfg.read_pi_auth()
            self.assertEqual(result, data)


# ═══════════════════════════════════════════════════════════════════════
# TestEdiniSettings
# ═══════════════════════════════════════════════════════════════════════

class TestEdiniSettings(unittest.TestCase):
    """Tests for _load_edini_settings / get_settings / save_settings."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.settings_path = Path(self.tmpdir.name) / "settings.json"

    def test_defaults_when_no_file(self):
        """Returns defaults when settings file doesn't exist."""
        with patch.object(cfg, "EDINI_SETTINGS_FILE", self.settings_path):
            result = cfg.get_settings()
        self.assertEqual(result["theme_color"], "cyan")
        self.assertEqual(result["font_scale"], 1.0)
        self.assertTrue(result["knowledge_enabled"])

    def test_load_when_missing(self):
        """get_settings returns defaults without file."""
        with patch.object(cfg, "EDINI_SETTINGS_FILE", Path("/nonexistent/settings.json")):
            result = cfg.get_settings()
        self.assertIn("theme_color", result)
        self.assertEqual(result["theme_color"], "cyan")

    def test_save_and_load(self):
        """save_settings persists and get_settings returns merged values."""
        with patch.object(cfg, "EDINI_SETTINGS_FILE", self.settings_path):
            cfg.save_settings({"theme_color": "dark", "font_scale": 1.5})
            result = cfg.get_settings()
        self.assertEqual(result["theme_color"], "dark")
        self.assertEqual(result["font_scale"], 1.5)
        # Defaults preserved for unmodified keys
        self.assertTrue(result["knowledge_enabled"])


# ═══════════════════════════════════════════════════════════════════════
# TestLegacyMigration
# ═══════════════════════════════════════════════════════════════════════

class TestLegacyMigration(unittest.TestCase):
    """Tests for migrate_legacy_settings()."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.settings_path = Path(self.tmpdir.name) / "settings.json"
        self.auth_path = Path(self.tmpdir.name) / "auth.json"
        self.pi_settings_path = Path(self.tmpdir.name) / "pi_settings.json"

    def test_no_migration_needed(self):
        """Returns None when no legacy keys present."""
        with patch.object(cfg, "EDINI_SETTINGS_FILE", self.settings_path):
            # Fresh defaults have no api_key/provider
            result = cfg.migrate_legacy_settings()
        self.assertIsNone(result)

    def test_migrates_legacy_keys(self):
        """Migrates api_key/provider/model_id to pi config files."""
        legacy_data = {
            "api_key": "sk-test-key-123456",
            "provider": "anthropic",
            "model_id": "claude-sonnet-4-20250514",
            "theme_color": "dark",
        }
        self.settings_path.write_text(json.dumps(legacy_data), encoding="utf-8")

        with patch.object(cfg, "EDINI_SETTINGS_FILE", self.settings_path), \
             patch.object(cfg, "PI_AUTH_FILE", self.auth_path), \
             patch.object(cfg, "PI_SETTINGS_FILE", self.pi_settings_path):
            msg = cfg.migrate_legacy_settings()

        self.assertIsNotNone(msg)
        self.assertIn("anthropic", msg)

        # Auth file should have the key
        auth = json.loads(self.auth_path.read_text(encoding="utf-8"))
        self.assertIn("anthropic", auth)
        self.assertEqual(auth["anthropic"]["key"], "sk-test-key-123456")

        # Pi settings should have default provider/model
        pi_s = json.loads(self.pi_settings_path.read_text(encoding="utf-8"))
        self.assertEqual(pi_s["defaultProvider"], "anthropic")
        self.assertEqual(pi_s["defaultModel"], "claude-sonnet-4-20250514")

        # Edini settings should have legacy keys removed
        edini = json.loads(self.settings_path.read_text(encoding="utf-8"))
        self.assertNotIn("api_key", edini)
        self.assertNotIn("provider", edini)
        self.assertNotIn("model_id", edini)
        # Non-legacy keys preserved
        self.assertEqual(edini["theme_color"], "dark")


# ═══════════════════════════════════════════════════════════════════════
# TestGetPiCommand
# ═══════════════════════════════════════════════════════════════════════

class TestGetPiCommand(unittest.TestCase):
    """Tests for get_pi_command()."""

    def test_rpc_mode(self):
        """Command includes --mode rpc."""
        cmd = cfg.get_pi_command()
        self.assertIn("--mode", cmd)
        idx = cmd.index("--mode")
        self.assertEqual(cmd[idx + 1], "rpc")

    def test_includes_extensions(self):
        """Command includes edini-tools and edini-context extensions."""
        cmd = cfg.get_pi_command()
        cmd_str = " ".join(cmd)
        self.assertIn("edini-tools", cmd_str)
        self.assertIn("edini-context", cmd_str)
        self.assertIn("pi-visionizer", cmd_str)


# ═══════════════════════════════════════════════════════════════════════
# TestGetPiEnv
# ═══════════════════════════════════════════════════════════════════════

class TestGetPiEnv(unittest.TestCase):
    """Tests for get_pi_env()."""

    def test_includes_tool_port(self):
        """Env dict includes EDINI_TOOL_PORT."""
        with patch.object(cfg, "EDINI_SETTINGS_FILE", Path("/nonexistent/settings.json")):
            env = cfg.get_pi_env()
        self.assertIn("EDINI_TOOL_PORT", env)
        self.assertEqual(env["EDINI_TOOL_PORT"], str(cfg.TOOL_EXECUTOR_PORT))

    def test_preserves_env(self):
        """Env dict includes existing environment variables."""
        with patch.object(cfg, "EDINI_SETTINGS_FILE", Path("/nonexistent/settings.json")):
            env = cfg.get_pi_env()
        # Should contain at least PATH
        self.assertIn("PATH", env)

    def test_vision_env_when_configured(self):
        """Sets VISIONIZER env vars when vision provider/model configured."""
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            data = {"vision_provider": "openai", "vision_model_id": "gpt-4o"}
            settings_path.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(cfg, "EDINI_SETTINGS_FILE", settings_path):
                env = cfg.get_pi_env()
            self.assertEqual(env.get("VISIONIZER_PROVIDER"), "openai")
            self.assertEqual(env.get("VISIONIZER_MODEL_ID"), "gpt-4o")


# ═══════════════════════════════════════════════════════════════════════
# TestModelHistory
# ═══════════════════════════════════════════════════════════════════════

class TestModelHistory(unittest.TestCase):
    """Tests for get_model_history / add_model_history."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.history_path = Path(self.tmpdir.name) / "model_history.json"

    def test_empty_history(self):
        """Returns [] when history file doesn't exist."""
        with patch.object(cfg, "_MODEL_HISTORY_FILE", self.history_path):
            result = cfg.get_model_history()
        self.assertEqual(result, [])

    def test_add_and_retrieve(self):
        """Adds a model and retrieves it."""
        with patch.object(cfg, "_MODEL_HISTORY_FILE", self.history_path):
            cfg.add_model_history("claude-sonnet-4-20250514")
            result = cfg.get_model_history()
        self.assertEqual(result, ["claude-sonnet-4-20250514"])

    def test_dedup_and_order(self):
        """Most recent entry is first, duplicates removed."""
        with patch.object(cfg, "_MODEL_HISTORY_FILE", self.history_path):
            cfg.add_model_history("model-a")
            cfg.add_model_history("model-b")
            cfg.add_model_history("model-a")  # duplicate
            result = cfg.get_model_history()
        self.assertEqual(result, ["model-a", "model-b"])


if __name__ == "__main__":
    unittest.main()
