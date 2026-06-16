"""
tests/test_tools.py

Pytest tests for each FitFindr tool, covering both success and failure modes.
Run with:
    pytest tests/
"""

import sys
import os

# Ensure the project root is on the path so imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools import (
    create_fit_card,
    estimate_price_fairness,
    search_listings,
    suggest_outfit,
)
from utils.data_loader import get_empty_wardrobe, get_example_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0
    # Every result must be a dict with required fields
    for item in results:
        assert "title" in item
        assert "price" in item
        assert "id" in item


def test_search_empty_results():
    # Impossible query — must return [] without raising
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_price_filter():
    max_p = 30.0
    results = search_listings("jacket", size=None, max_price=max_p)
    assert isinstance(results, list)
    assert all(item["price"] <= max_p for item in results)


def test_search_size_filter():
    results = search_listings("tee", size="M", max_price=None)
    assert isinstance(results, list)
    # All results must have "m" somewhere in their size string
    for item in results:
        assert "m" in item["size"].lower()


def test_search_results_sorted_by_relevance():
    # A very specific query should return the most relevant item first
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert len(results) > 0
    # The top result should contain at least one of the keywords in its tags/title
    top = results[0]
    combined = (top["title"] + " ".join(top.get("style_tags", []))).lower()
    assert any(kw in combined for kw in ["vintage", "graphic", "tee", "graphic tee"])


def test_search_no_size_filter_returns_more_than_with_filter():
    all_results = search_listings("tee", size=None, max_price=None)
    filtered = search_listings("tee", size="XL", max_price=None)
    assert len(all_results) >= len(filtered)


def test_search_description_only():
    # No size or price filter — should still work
    results = search_listings("denim jacket")
    assert isinstance(results, list)
    assert len(results) > 0


# ── suggest_outfit ────────────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert results, "Need a search result for this test"
    item = results[0]
    suggestion = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 20  # Should be a real suggestion, not empty


def test_suggest_outfit_empty_wardrobe():
    # Must return a useful string — not crash, not return ""
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert results, "Need a search result for this test"
    item = results[0]
    suggestion = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(suggestion, str)
    assert len(suggestion) > 20


def test_suggest_outfit_empty_wardrobe_no_exception():
    # Explicit guard: calling with empty wardrobe must never raise
    results = search_listings("flannel shirt", size=None, max_price=None)
    assert results
    try:
        result = suggest_outfit(results[0], get_empty_wardrobe())
        assert isinstance(result, str)
        assert result  # non-empty
    except Exception as e:
        raise AssertionError(f"suggest_outfit raised with empty wardrobe: {e}")


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_empty_outfit_returns_error_string():
    # Empty outfit must return a descriptive error string, NOT raise
    results = search_listings("vintage tee", size=None, max_price=50)
    assert results
    result = create_fit_card("", results[0])
    assert isinstance(result, str)
    assert "error" in result.lower() or "cannot" in result.lower() or "missing" in result.lower()


def test_create_fit_card_whitespace_outfit_returns_error_string():
    results = search_listings("vintage tee", size=None, max_price=50)
    assert results
    result = create_fit_card("   ", results[0])
    assert isinstance(result, str)
    assert "error" in result.lower() or "cannot" in result.lower() or "missing" in result.lower()


def test_create_fit_card_returns_string():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert results
    outfit = "Pair with baggy jeans and chunky sneakers for a streetwear look."
    card = create_fit_card(outfit, results[0])
    assert isinstance(card, str)
    assert len(card) > 20


def test_create_fit_card_no_exception_on_empty():
    # Must not raise under any circumstances for empty outfit
    results = search_listings("cardigan", size=None, max_price=None)
    assert results
    try:
        result = create_fit_card("", results[0])
        assert isinstance(result, str)
    except Exception as e:
        raise AssertionError(f"create_fit_card raised on empty outfit: {e}")


# ── estimate_price_fairness (stretch) ─────────────────────────────────────────

def test_estimate_price_fairness_returns_string():
    results = search_listings("vintage graphic tee", size=None, max_price=None)
    assert results
    assessment = estimate_price_fairness(results[0])
    assert isinstance(assessment, str)
    assert len(assessment) > 10


def test_estimate_price_fairness_no_exception():
    results = search_listings("jeans", size=None, max_price=None)
    assert results
    try:
        result = estimate_price_fairness(results[0])
        assert isinstance(result, str)
    except Exception as e:
        raise AssertionError(f"estimate_price_fairness raised: {e}")


def test_estimate_price_fairness_contains_price_info():
    results = search_listings("jacket", size=None, max_price=None)
    assert results
    assessment = estimate_price_fairness(results[0])
    # Should mention a dollar amount
    assert "$" in assessment or "price" in assessment.lower()
