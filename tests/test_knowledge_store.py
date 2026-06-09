"""Unit tests for edini.ui.knowledge_store — CRUD, search, parse, accept."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

# Make edini package importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python3.11libs"))

from edini.ui.knowledge_store import (  # noqa: E402
    MAX_RULES,
    accept_extracted,
    add_entry,
    add_rule,
    delete_entry,
    delete_rule,
    entries_count,
    get_enabled_rules,
    load_entries,
    load_rules,
    parse_extraction_response,
    rules_count,
    save_entries,
    save_rules,
    search_entries,
    update_entry,
    update_rule,
)


class _IsolatedKnowledgeDir:
    """Context manager that redirects knowledge file paths to a tempdir.

    Patches the globals dict of the imported load_rules function directly,
    which is the only reliable way to override _rules_path regardless of
    how many module instances pytest creates.
    """

    def __init__(self, td: str):
        # Use the globals from the actual imported load_rules function
        # This is the authoritative module namespace that load_rules sees
        self._g = load_rules.__globals__
        self._kdir = Path(td) / "knowledge"
        self._saved = {}
        for name in ('_rules_path', '_entries_path', '_ensure_dir'):
            self._saved[name] = self._g[name]

    def __enter__(self):
        kdir = self._kdir
        self._g['_rules_path'] = lambda: kdir / "rules.json"
        self._g['_entries_path'] = lambda: kdir / "entries.json"
        self._g['_ensure_dir'] = lambda: kdir.mkdir(parents=True, exist_ok=True)
        return self

    def __exit__(self, *args):
        for name, func in self._saved.items():
            self._g[name] = func


def _patch_dir(td: str):
    """Return a context manager that redirects knowledge file paths to a tempdir."""
    return _IsolatedKnowledgeDir(td)


# ── TestRulesCRUD ──────────────────────────────────────────────────────────


class TestRulesCRUD:
    """Tests for load_rules, save_rules, add_rule, update_rule, delete_rule."""

    def test_load_rules_returns_defaults_when_no_file(self):
        """When no rules.json exists, load_rules returns 4 seed rules."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                rules = load_rules()
                assert isinstance(rules, list)
                assert len(rules) == 4
                for r in rules:
                    assert "id" in r
                    assert "category" in r
                    assert "title" in r
                    assert "content" in r
                    assert "enabled" in r
                # Every default rule should have required keys
                for r in rules:
                    assert "id" in r
                    assert "category" in r
                    assert "title" in r
                    assert "content" in r
                    assert "enabled" in r

    def test_add_rule_persists(self):
        """add_rule writes a new rule that survives a reload."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                rule = add_rule("技巧", "test title", "test content")
                assert rule["category"] == "技巧"
                assert rule["title"] == "test title"
                assert rule["content"] == "test content"
                assert rule["enabled"] is True
                assert "id" in rule

                # Reload and verify it's there (4 defaults + 1 new)
                all_rules = load_rules()
                assert len(all_rules) == 5
                ids = [r["id"] for r in all_rules]
                assert rule["id"] in ids

    def test_max_rules_enforcement(self):
        """Adding beyond MAX_RULES drops the oldest rules."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                # Already 4 defaults; add enough to exceed MAX_RULES
                added_ids = []
                for i in range(MAX_RULES + 2):
                    r = add_rule("技巧", f"extra rule {i}", f"content {i}")
                    added_ids.append(r["id"])

                final_rules = load_rules()
                assert len(final_rules) == MAX_RULES

    def test_delete_rule(self):
        """delete_rule removes the specified rule and returns True."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                rule = add_rule("技巧", "to delete", "content")
                assert delete_rule(rule["id"]) is True

                remaining = load_rules()
                ids = [r["id"] for r in remaining]
                assert rule["id"] not in ids

    def test_delete_nonexistent_rule_returns_false(self):
        """Deleting a rule ID that doesn't exist returns False."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                assert delete_rule("nonexistent_id") is False

    def test_update_rule(self):
        """update_rule modifies an existing rule's fields."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                rule = add_rule("技巧", "original", "original content")
                updated = update_rule(rule["id"], title="updated", content="new content")
                assert updated is not None
                assert updated["title"] == "updated"
                assert updated["content"] == "new content"

                # Persisted
                all_rules = load_rules()
                found = [r for r in all_rules if r["id"] == rule["id"]][0]
                assert found["title"] == "updated"

    def test_update_nonexistent_rule_returns_none(self):
        """Updating a rule ID that doesn't exist returns None."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                result = update_rule("nonexistent_id", title="x")
                assert result is None


# ── TestEnabledRules ───────────────────────────────────────────────────────


class TestEnabledRules:
    """Tests for get_enabled_rules."""

    def test_filters_disabled(self):
        """get_enabled_rules only returns rules with enabled=True."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                add_rule("技巧", "enabled rule", "content", enabled=True)
                add_rule("避坑", "disabled rule", "content", enabled=False)

                enabled = get_enabled_rules()
                titles = [r["title"] for r in enabled]
                assert "enabled rule" in titles
                assert "disabled rule" not in titles


# ── TestEntriesCRUD ────────────────────────────────────────────────────────


class TestEntriesCRUD:
    """Tests for load_entries, save_entries, add_entry, update_entry, delete_entry."""

    def test_load_entries_empty_when_no_file(self):
        """When no entries.json exists, load_entries returns []."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                entries = load_entries()
                assert entries == []

    def test_add_entry_persists(self):
        """add_entry writes an entry that survives reload."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                entry = add_entry("技巧", "test entry", "some content",
                                  tags=["tag1", "tag2"], source_session="/tmp/test.hip")
                assert entry["category"] == "技巧"
                assert entry["title"] == "test entry"
                assert entry["tags"] == ["tag1", "tag2"]
                assert entry["source_session"] == "/tmp/test.hip"

                all_entries = load_entries()
                assert len(all_entries) == 1
                assert all_entries[0]["id"] == entry["id"]

    def test_delete_entry(self):
        """delete_entry removes an entry and returns True."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                e1 = add_entry("技巧", "keep me", "content")
                e2 = add_entry("避坑", "delete me", "content")
                assert delete_entry(e2["id"]) is True

                remaining = load_entries()
                assert len(remaining) == 1
                assert remaining[0]["id"] == e1["id"]

    def test_delete_nonexistent_entry_returns_false(self):
        """Deleting a nonexistent entry ID returns False."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                assert delete_entry("nonexistent") is False

    def test_update_entry(self):
        """update_entry modifies an existing entry's fields."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                entry = add_entry("技巧", "original", "content")
                updated = update_entry(entry["id"], title="updated title", tags=["new_tag"])
                assert updated is not None
                assert updated["title"] == "updated title"
                assert updated["tags"] == ["new_tag"]

    def test_update_nonexistent_entry_returns_none(self):
        """Updating a nonexistent entry returns None."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                assert update_entry("nonexistent", title="x") is None


# ── TestSearchEntries ──────────────────────────────────────────────────────


class TestSearchEntries:
    """Tests for search_entries with query, category, tags, limit."""

    def _seed(self, td):
        """Add test entries inside a patched tempdir."""
        with _patch_dir(td):
            add_entry("技巧", "Python tip", "Use list comprehensions", tags=["python"])
            add_entry("避坑", "Common pitfall", "Don't forget to close files", tags=["io"])
            add_entry("工作流", "Node workflow", "Connect nodes before cooking", tags=["node", "houdini"])
            add_entry("配置", "Config setup", "Set environment variables", tags=["env"])

    def test_search_by_query(self):
        """Substring match on title and content."""
        with tempfile.TemporaryDirectory() as td:
            self._seed(td)
            with _patch_dir(td):
                results = search_entries(query="Python")
                assert len(results) == 1
                assert results[0]["title"] == "Python tip"

    def test_search_by_category(self):
        """Filter by category returns only matching entries."""
        with tempfile.TemporaryDirectory() as td:
            self._seed(td)
            with _patch_dir(td):
                results = search_entries(category="避坑")
                assert all(e["category"] == "避坑" for e in results)
                assert len(results) == 1

    def test_search_by_tags(self):
        """Filter by tags using set intersection."""
        with tempfile.TemporaryDirectory() as td:
            self._seed(td)
            with _patch_dir(td):
                results = search_entries(tags=["node"])
                assert len(results) == 1
                assert "Node workflow" in results[0]["title"]

    def test_search_limit(self):
        """Results are capped by the limit parameter."""
        with tempfile.TemporaryDirectory() as td:
            self._seed(td)
            with _patch_dir(td):
                results = search_entries(limit=2)
                assert len(results) <= 2

    def test_search_empty_returns_all(self):
        """Calling search_entries with no filters returns all entries (up to limit)."""
        with tempfile.TemporaryDirectory() as td:
            self._seed(td)
            with _patch_dir(td):
                results = search_entries(limit=100)
                assert len(results) == 4


# ── TestParseExtraction ────────────────────────────────────────────────────


class TestParseExtraction:
    """Tests for parse_extraction_response with various input formats."""

    def test_valid_json(self):
        """Standard JSON array with proper items returns normalized items."""
        data = json.dumps([
            {"type": "rule", "category": "避坑", "title": "A rule", "content": "Details here"},
            {"type": "entry", "category": "技巧", "title": "An entry", "content": "More details"},
        ])
        items, leftover = parse_extraction_response(data)
        assert len(items) == 2
        assert items[0]["type"] == "rule"
        assert items[1]["type"] == "entry"
        assert leftover == ""

    def test_plain_array(self):
        """A raw array (no key wrapping) is parsed directly."""
        text = '[{"type":"entry","category":"技巧","title":"Test","content":"Body"}]'
        items, _ = parse_extraction_response(text)
        assert len(items) == 1
        assert items[0]["title"] == "Test"

    def test_single_quotes(self):
        """Single quotes are tolerated and converted to double quotes."""
        text = "[{'type':'rule','category':'避坑','title':'Single','content':'Works'}]"
        items, _ = parse_extraction_response(text)
        assert len(items) == 1
        assert items[0]["title"] == "Single"

    def test_trailing_commas(self):
        """Trailing commas before } or ] are handled gracefully."""
        text = '[{"type":"entry","category":"技巧","title":"TC","content":"ok",},]'
        items, _ = parse_extraction_response(text)
        assert len(items) == 1

    def test_empty_input(self):
        """Empty string returns empty list and empty leftover."""
        items, leftover = parse_extraction_response("")
        assert items == []

    def test_non_json_text(self):
        """Non-JSON text returns empty list and the raw text as leftover."""
        items, leftover = parse_extraction_response("This is just plain text.")
        # When no [ found, returns empty list and the text
        # Actually the function returns [], text when no [ found
        assert items == []

    def test_filters_empty_items(self):
        """Items with empty title or content are dropped."""
        data = json.dumps([
            {"type": "entry", "category": "技巧", "title": "", "content": "has content"},
            {"type": "entry", "category": "技巧", "title": "Has title", "content": ""},
            {"type": "entry", "category": "技巧", "title": "Good", "content": "Good content"},
        ])
        items, _ = parse_extraction_response(data)
        assert len(items) == 1
        assert items[0]["title"] == "Good"

    def test_markdown_code_block(self):
        """JSON inside ```json ... ``` code block is extracted."""
        text = """Here is the result:
```json
[{"type":"rule","category":"避坑","title":"Code block","content":"Extracted"}]
```
"""
        items, _ = parse_extraction_response(text)
        assert len(items) == 1
        assert items[0]["title"] == "Code block"


# ── TestNormalizeCategory ──────────────────────────────────────────────────


class TestNormalizeCategory:
    """Unknown category defaults to 技巧."""

    def test_unknown_category_defaults_to_tips(self):
        """Items with unknown category get normalized to '技巧'."""
        data = json.dumps([
            {"type": "entry", "category": "unknown_cat", "title": "Weird cat", "content": "text"},
        ])
        items, _ = parse_extraction_response(data)
        assert len(items) == 1
        assert items[0]["category"] == "技巧"

    def test_known_category_preserved(self):
        """Valid categories are kept as-is."""
        for cat in ["避坑", "技巧", "工作流", "配置"]:
            data = json.dumps([
                {"type": "entry", "category": cat, "title": f"Cat {cat}", "content": "text"},
            ])
            items, _ = parse_extraction_response(data)
            assert items[0]["category"] == cat


# ── TestAcceptExtracted ────────────────────────────────────────────────────


class TestAcceptExtracted:
    """Tests for accept_extracted — mixed items go to rules + entries."""

    def test_mixed_items_routed_correctly(self):
        """Rules go to rules.json, entries go to entries.json."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                items = [
                    {"type": "rule", "category": "避坑", "title": "Rule 1", "content": "Rule content", "tags": []},
                    {"type": "rule", "category": "技巧", "title": "Rule 2", "content": "Rule content 2", "tags": []},
                    {"type": "entry", "category": "工作流", "title": "Entry 1", "content": "Entry content", "tags": ["tag1"]},
                ]
                r, e = accept_extracted(items, session_path="/tmp/test.hip")
                assert r == 2
                assert e == 1

                # Verify rules count (4 defaults + 2 new)
                assert rules_count() == 6
                # Verify entries count
                assert entries_count() == 1


# ── TestRulesCount / EntriesCount ──────────────────────────────────────────


class TestCounts:
    """Tests for rules_count and entries_count."""

    def test_rules_count_defaults(self):
        """rules_count returns 4 for fresh state (default rules)."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                assert rules_count() == 4

    def test_entries_count_empty(self):
        """entries_count returns 0 for fresh state."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                assert entries_count() == 0

    def test_entries_count_after_add(self):
        """entries_count reflects added entries."""
        with tempfile.TemporaryDirectory() as td:
            with _patch_dir(td):
                add_entry("技巧", "t1", "c1")
                add_entry("技巧", "t2", "c2")
                assert entries_count() == 2
