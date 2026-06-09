"""Tests for knowledge deduplication logic."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python3.11libs'))

import unittest
from edini.ui.dedup import jaccard_similarity, find_similar, classify_items


class TestJaccard(unittest.TestCase):
    def test_identical(self):
        self.assertAlmostEqual(jaccard_similarity("hello world", "hello world"), 1.0)

    def test_no_overlap(self):
        self.assertAlmostEqual(jaccard_similarity("aaa", "bbb"), 0.0)

    def test_partial_overlap(self):
        score = jaccard_similarity("hou API error", "hou API warning")
        self.assertGreater(score, 0.3)
        self.assertLess(score, 1.0)

    def test_chinese_chars(self):
        score = jaccard_similarity("避坑Hou主线程", "避坑Hou多线程")
        self.assertGreater(score, 0.3)

    def test_empty_both(self):
        self.assertAlmostEqual(jaccard_similarity("", ""), 1.0)

    def test_empty_one(self):
        self.assertAlmostEqual(jaccard_similarity("hello", ""), 0.0)


class TestFindSimilar(unittest.TestCase):
    def setUp(self):
        self.existing = [
            {"id": "a1", "title": "hou.BoundingBox 没有 size 方法"},
            {"id": "b2", "title": "Wrangle批量操作用AttribTransfer"},
        ]

    def test_find_exact_match(self):
        result = find_similar("hou.BoundingBox 没有 size 方法", self.existing)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "a1")

    def test_find_near_match(self):
        result = find_similar("hou.BoundingBox 没有 size 方法 新发现", self.existing)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "a1")

    def test_near_match_low_threshold(self):
        # 3 shared tokens out of 9 union = 0.33, below default 0.5
        result = find_similar("hou.BoundingBox 缺少 size", self.existing)
        self.assertIsNone(result)
        # But with lower threshold it matches
        result = find_similar("hou.BoundingBox 缺少 size", self.existing, threshold=0.3)
        self.assertIsNotNone(result)

    def test_no_match(self):
        result = find_similar("完全无关的标题xyz", self.existing)
        self.assertIsNone(result)


class TestClassifyItems(unittest.TestCase):
    def test_new_item(self):
        items = [{"type": "rule", "title": "全新的知识", "content": "内容"}]
        result = classify_items(items, [], [])
        self.assertEqual(result[0]["_action"], "new")

    def test_merge_item(self):
        existing = [{"id": "x1", "title": "hou.BoundingBox 没有 size"}]
        items = [{"type": "rule", "title": "hou.BoundingBox 没有 size 方法", "content": "更新"}]
        result = classify_items(items, existing, [])
        self.assertEqual(result[0]["_action"], "merge")
        self.assertEqual(result[0]["_merge_target"]["id"], "x1")


if __name__ == "__main__":
    unittest.main()
