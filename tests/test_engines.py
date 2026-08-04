"""Engine tests — MockEngine determinism and target detection (offline only)."""

from __future__ import annotations

from citationtracker.engines import (
    MockEngine,
    build_engine,
    detect_domain,
    domain_of,
)


def test_mock_engine_is_deterministic():
    """Two engines with the same pool and seed always agree."""
    pool = ["example.com", "wikipedia.org", "reddit.com", "g2.com"]
    a = MockEngine(domains=pool)
    b = MockEngine(domains=pool)

    for query in ["best crm", "top note apps", "seo tools"]:
        assert a.answer(query).citations == b.answer(query).citations


def test_mock_engine_citation_count_in_range():
    """The mock cites between 3 and 5 sources (or the pool size if smaller)."""
    engine = MockEngine()
    for query in ["one", "two", "three", "a longer query here"]:
        k = len(engine.answer(query).citations)
        assert 3 <= k <= 5


def test_mock_engine_different_seed_can_differ():
    pool = ["example.com", "wikipedia.org", "reddit.com", "g2.com", "forbes.com"]
    a = MockEngine(domains=pool, seed="one")
    b = MockEngine(domains=pool, seed="two")
    # At least one query should rank differently across seeds.
    assert any(
        a.answer(q).citations != b.answer(q).citations
        for q in ["alpha", "beta", "gamma", "delta"]
    )


def test_domain_of_normalizes():
    assert domain_of("https://www.Example.com/page?x=1") == "example.com"
    assert domain_of("user:pass@Example.com:8080") == "example.com"
    assert domain_of("example.com") == "example.com"


def test_detect_domain_matches_and_ranks():
    citations = ["wikipedia.org", "https://www.example.com/x", "reddit.com"]
    cited, rank = detect_domain(citations, "example.com")
    assert cited is True
    assert rank == 2


def test_detect_domain_matches_subdomain():
    cited, rank = detect_domain(["blog.example.com"], "example.com")
    assert cited is True
    assert rank == 1


def test_detect_domain_absent():
    cited, rank = detect_domain(["wikipedia.org", "reddit.com"], "example.com")
    assert cited is False
    assert rank is None


def test_build_engine_folds_target_into_pool():
    engine = build_engine("mock", "mybrand.com", mock_domains=["wikipedia.org"])
    # Across enough queries the target should surface at least once.
    surfaced = any(
        detect_domain(engine.answer(q).citations, "mybrand.com")[0]
        for q in [f"query {i}" for i in range(20)]
    )
    assert surfaced


def test_build_engine_unknown_name():
    import pytest

    with pytest.raises(ValueError):
        build_engine("nope", "example.com")
