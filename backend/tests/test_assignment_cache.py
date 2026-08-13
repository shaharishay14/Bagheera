"""Tests for the in-memory per-slide assignment cache.

Pure Python — no ML deps. Records are plain tuples/lists standing in for the
real `(coords, cluster_labels, qq, mixture_probs, patch_size)` numpy records.
"""
from __future__ import annotations

import pytest

from app.services import assignment_cache


@pytest.fixture(autouse=True)
def _clean_cache():
    """Start every test with an empty cache and restore the cap afterward."""
    assignment_cache.clear()
    original_cap = assignment_cache.MAX_ENTRIES
    yield
    assignment_cache.clear()
    assignment_cache.MAX_ENTRIES = original_cap


def _rec(tag):
    # A fake record shaped like the real 5-tuple, but with opaque placeholders.
    return (f"coords-{tag}", f"labels-{tag}", f"qq-{tag}", f"pi-{tag}", 256)


def test_put_get_roundtrip():
    rec = _rec("a")
    assignment_cache.put("model-1", "slideA", rec)
    assert assignment_cache.get("model-1", "slideA") == rec


def test_get_miss_returns_none():
    assert assignment_cache.get("model-1", "nope") is None
    # A different key from a stored one is still a miss.
    assignment_cache.put("model-1", "slideA", _rec("a"))
    assert assignment_cache.get("model-1", "slideB") is None


def test_lru_eviction_past_cap():
    assignment_cache.MAX_ENTRIES = 3
    for i in range(3):
        assignment_cache.put("m", f"slide{i}", _rec(i))
    # All three present.
    for i in range(3):
        assert assignment_cache.get("m", f"slide{i}") is not None

    # Touch slide0 so it becomes most-recently-used; slide1 is now LRU.
    assert assignment_cache.get("m", "slide0") is not None

    # Insert a 4th → evicts the least-recently-used (slide1).
    assignment_cache.put("m", "slide3", _rec(3))
    assert assignment_cache.get("m", "slide1") is None
    assert assignment_cache.get("m", "slide0") is not None
    assert assignment_cache.get("m", "slide2") is not None
    assert assignment_cache.get("m", "slide3") is not None


def test_per_model_slide_isolation():
    # Same slide_stem under two different model_ids are independent entries.
    rec1 = _rec("m1")
    rec2 = _rec("m2")
    assignment_cache.put("model-1", "sharedSlide", rec1)
    assignment_cache.put("model-2", "sharedSlide", rec2)

    assert assignment_cache.get("model-1", "sharedSlide") == rec1
    assert assignment_cache.get("model-2", "sharedSlide") == rec2
    assert rec1 != rec2


def test_get_or_compute_calls_compute_only_on_miss():
    calls = {"n": 0}

    def compute():
        calls["n"] += 1
        return _rec("computed")

    # First call: miss → compute runs once.
    first = assignment_cache.get_or_compute("model-1", "slideA", compute)
    assert calls["n"] == 1
    assert first == _rec("computed")

    # Subsequent calls: hit → compute NOT re-run.
    second = assignment_cache.get_or_compute("model-1", "slideA", compute)
    assert calls["n"] == 1
    assert second == first

    # A different key misses and computes again.
    assignment_cache.get_or_compute("model-1", "slideB", compute)
    assert calls["n"] == 2


def test_clear_model_drops_only_that_model():
    assignment_cache.put("model-1", "s1", _rec("11"))
    assignment_cache.put("model-1", "s2", _rec("12"))
    assignment_cache.put("model-2", "s1", _rec("21"))

    removed = assignment_cache.clear_model("model-1")
    assert removed == 2

    assert assignment_cache.get("model-1", "s1") is None
    assert assignment_cache.get("model-1", "s2") is None
    # model-2's entry survives.
    assert assignment_cache.get("model-2", "s1") is not None


def test_clear_model_no_entries_returns_zero():
    assignment_cache.put("model-1", "s1", _rec("11"))
    assert assignment_cache.clear_model("model-nope") == 0
    assert assignment_cache.get("model-1", "s1") is not None
