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
        self.assertTrue(result["knowledge_enabled"])

    def test_load_when_missing(self):
        """get_settings returns defaults without file."""
        with patch.object(cfg, "EDINI_SETTINGS_FILE", Path("/nonexistent/settings.json")):
            result = cfg.get_settings()
        self.assertTrue(result["knowledge_enabled"])

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
# TestGetConfiguredProviders
# ═══════════════════════════════════════════════════════════════════════

class TestGetConfiguredProviders(unittest.TestCase):
    """Tests for get_configured_providers() — kind tagging & orphan filter."""

    def _patch_world(self, builtins, auth, models):
        """Patch the data sources get_configured_providers depends on."""
        pi_ai = [{"id": i, "name": i.title()} for i in builtins]

        def fake_status(pid):
            if pid in auth:
                return {"configured": True, "source": "auth.json", "hint": None}
            mp = models.get("providers", {}).get(pid, {})
            if mp.get("apiKey"):
                return {"configured": True, "source": "models.json", "hint": None}
            return {"configured": False, "source": None, "hint": None}

        return (
            patch.object(cfg, "get_pi_ai_providers", return_value=pi_ai),
            patch.object(cfg, "read_pi_auth", return_value=auth),
            patch.object(cfg, "read_pi_models", return_value=models),
            patch.object(cfg, "get_provider_auth_status", side_effect=fake_status),
        )

    def test_orphan_auth_entry_is_filtered(self):
        """Stale auth.json keys not in pi-ai or models.json are dropped."""
        builtins = ["deepseek"]
        auth = {"deepseek": {"type": "api_key", "key": "k"},
                "ali": {"type": "api_key", "key": "k"}}  # orphan
        models = {"providers": {"aliyun": {"apiKey": "k", "name": "Aliyun"}}}
        patches = self._patch_world(builtins, auth, models)
        with patches[0], patches[1], patches[2], patches[3]:
            result = cfg.get_configured_providers()
        ids = [p["id"] for p in result]
        self.assertNotIn("ali", ids)
        self.assertIn("aliyun", ids)
        self.assertIn("deepseek", ids)

    def test_kind_tagging(self):
        """Each result is tagged builtin or custom."""
        builtins = ["deepseek"]
        auth = {"deepseek": {"type": "api_key", "key": "k"},
                "aliyun": {"type": "api_key", "key": "k"}}
        models = {"providers": {"aliyun": {"apiKey": "k", "name": "Aliyun"}}}
        patches = self._patch_world(builtins, auth, models)
        with patches[0], patches[1], patches[2], patches[3]:
            result = cfg.get_configured_providers()
        kinds = {p["id"]: p["kind"] for p in result}
        self.assertEqual(kinds["deepseek"], "builtin")
        self.assertEqual(kinds["aliyun"], "custom")

    def test_builtin_with_models_json_override_stays_builtin(self):
        """A pi-ai built-in id that also appears in models.json is builtin."""
        builtins = ["deepseek"]
        auth = {"deepseek": {"type": "api_key", "key": "k"}}
        models = {"providers": {"deepseek": {"apiKey": "k"}}}
        patches = self._patch_world(builtins, auth, models)
        with patches[0], patches[1], patches[2], patches[3]:
            result = cfg.get_configured_providers()
        ids = [p["id"] for p in result]
        self.assertEqual(ids.count("deepseek"), 1)
        self.assertEqual(result[0]["kind"], "builtin")


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

    def test_loads_project_skills_only(self):
        """Command disables global skills and loads skills from this project."""
        cmd = cfg.get_pi_command()
        self.assertIn("--no-skills", cmd)

        skill_paths = [
            cmd[i + 1] for i, part in enumerate(cmd[:-1])
            if part == "--skill"
        ]
        self.assertFalse(
            any(Path(p).name.lower() == "readme.md" for p in skill_paths),
            skill_paths,
        )
        # Procedural-modeling skills were disabled and moved to
        # _disabled_backup/; grill-me is the remaining active skill.
        self.assertTrue(
            any(Path(p).name == "grill-me" for p in skill_paths),
            skill_paths,
        )

    def test_reports_pi_capabilities(self):
        """Capability inventory lists loaded extensions and project skills."""
        caps = cfg.get_pi_capabilities()
        self.assertTrue(caps["global_skills_disabled"])
        self.assertEqual(caps["project_root"], str(cfg.PROJECT_ROOT))

        extension_names = {e["name"] for e in caps["extensions"]}
        self.assertIn("edini-tools", extension_names)
        self.assertIn("edini-context", extension_names)
        self.assertIn("pi-visionizer", extension_names)

        skill_names = {s["name"] for s in caps["skills"]}
        # Procedural-modeling skills were disabled and moved to
        # _disabled_backup/; grill-me is the remaining active skill.
        self.assertIn("grill-me", skill_names)

    def test_root_pi_package_manifest_declares_edini_capabilities(self):
        """Root package.json groups Edini extensions and project skills."""
        manifest_path = cfg.PROJECT_ROOT / "package.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "edini-pi")
        self.assertTrue(data["private"])
        self.assertIn("pi-package", data["keywords"])

        pi_config = data["pi"]
        self.assertIn("./skills", pi_config["skills"])
        self.assertIn("./pi-extensions/edini-tools/index.ts", pi_config["extensions"])
        self.assertIn("./pi-extensions/edini-context/index.ts", pi_config["extensions"])
        self.assertIn("./pi-extensions/pi-visionizer/src/index.ts", pi_config["extensions"])


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

    def test_vision_env_set_when_configured(self):
        """Vision env vars are injected so pi-visionizer can resolve the model."""
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            data = {"vision_provider": "openai", "vision_model_id": "gpt-4o"}
            settings_path.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(cfg, "EDINI_SETTINGS_FILE", settings_path):
                env = cfg.get_pi_env()
            self.assertEqual(env.get("VISIONIZER_PROVIDER"), "openai")
            self.assertEqual(env.get("VISIONIZER_MODEL_ID"), "gpt-4o")

    def test_vision_env_not_set_when_unconfigured(self):
        """No vision env vars when edini settings have no vision model."""
        with patch.object(cfg, "EDINI_SETTINGS_FILE", Path("/nonexistent/settings.json")):
            env = cfg.get_pi_env()
        self.assertIsNone(env.get("VISIONIZER_PROVIDER"))
        self.assertIsNone(env.get("VISIONIZER_MODEL_ID"))



if __name__ == "__main__":
    unittest.main()
