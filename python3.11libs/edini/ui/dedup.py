"""Deduplication logic for knowledge entries.

Uses Jaccard similarity on tokenized titles to detect near-duplicates.
"""

import re
from typing import Any

_SIMILARITY_THRESHOLD = 0.5


def _tokenize(text: str) -> set[str]:
    """Tokenize text into a set of lowercase words (Chinese char = 1 token)."""
    tokens: set[str] = set()
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            tokens.add(ch)
    for word in re.findall(r'[a-zA-Z0-9]+', text.lower()):
        tokens.add(word)
    return tokens


def jaccard_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity between two strings."""
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def find_similar(
    title: str,
    existing: list[dict[str, Any]],
    threshold: float = _SIMILARITY_THRESHOLD,
) -> dict[str, Any] | None:
    """Find the most similar existing entry to the given title."""
    best_score = 0.0
    best_match = None
    for item in existing:
        score = jaccard_similarity(title, item.get("title", ""))
        if score > best_score and score >= threshold:
            best_score = score
            best_match = item
    return best_match


def classify_items(
    new_items: list[dict[str, Any]],
    existing_rules: list[dict[str, Any]],
    existing_entries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Classify each new item as 'new' or 'merge'."""
    all_existing = existing_rules + existing_entries
    results = []
    for item in new_items:
        match = find_similar(item.get("title", ""), all_existing)
        annotated = dict(item)
        if match:
            annotated["_action"] = "merge"
            annotated["_merge_target"] = match
            annotated["_similarity"] = jaccard_similarity(
                item.get("title", ""), match.get("title", ""))
        else:
            annotated["_action"] = "new"
        results.append(annotated)
    return results
