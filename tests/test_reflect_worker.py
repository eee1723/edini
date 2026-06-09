"""Tests for ReflectWorker."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python3.11libs'))

import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from edini.ui.reflect_worker import ReflectWorker, _PROVIDER_URLS


class TestProviderUrls(unittest.TestCase):
    def test_known_providers_have_urls(self):
        for p in ["deepseek", "openai", "qwen", "zai-coding-cn"]:
            self.assertIn(p, _PROVIDER_URLS)

    def test_unknown_provider_no_url(self):
        w = ReflectWorker("", "unknown_provider", "model", "key")
        self.assertIsNone(w._resolve_url())

    def test_custom_base_url(self):
        w = ReflectWorker("", "custom", "model", "key",
                          base_url="https://example.com/v1")
        self.assertEqual(w._resolve_url(), "https://example.com/v1/chat/completions")


class TestReadConversation(unittest.TestCase):
    def test_read_jsonl(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl',
                                         delete=False, encoding='utf-8') as f:
            f.write(json.dumps({"role": "user", "content": "hello"}) + "\n")
            f.write(json.dumps({"role": "assistant", "content": "world"}) + "\n")
            path = f.name
        try:
            w = ReflectWorker(path, "deepseek", "model", "key")
            text = w._read_conversation()
            self.assertIn("hello", text)
            self.assertIn("world", text)
        finally:
            os.unlink(path)

    def test_missing_file(self):
        w = ReflectWorker("/nonexistent/file.jsonl", "deepseek", "model", "key")
        self.assertEqual(w._read_conversation(), "")

    def test_multipart_content(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl',
                                         delete=False, encoding='utf-8') as f:
            f.write(json.dumps({
                "role": "user",
                "content": [
                    {"type": "text", "text": "part1"},
                    {"type": "text", "text": "part2"},
                ]
            }) + "\n")
            path = f.name
        try:
            w = ReflectWorker(path, "deepseek", "model", "key")
            text = w._read_conversation()
            self.assertIn("part1", text)
            self.assertIn("part2", text)
        finally:
            os.unlink(path)


class TestParseResponse(unittest.TestCase):
    def test_valid_json(self):
        w = ReflectWorker("", "deepseek", "model", "key")
        items = w._parse_response('[{"type":"rule","category":"避坑","title":"test","content":"desc","tags":[]}]')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "test")

    def test_empty_array(self):
        w = ReflectWorker("", "deepseek", "model", "key")
        items = w._parse_response('[]')
        self.assertEqual(len(items), 0)


class TestCallApi(unittest.TestCase):
    @patch("edini.ui.reflect_worker.urllib.request.urlopen")
    def test_successful_call(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "[]"}}]
        }).encode("utf-8")
        mock_resp.__enter__ = lambda s: mock_resp
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        w = ReflectWorker("", "deepseek", "deepseek-chat", "sk-test")
        result = w._call_api("test prompt")
        self.assertEqual(result, "[]")


if __name__ == "__main__":
    unittest.main()
