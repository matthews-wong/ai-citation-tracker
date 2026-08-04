"""Analysis tests — citation-rate math, per-query breakdown, and trend."""

from __future__ import annotations

from citationtracker.analyze import (
    citation_rate,
    flatten_results,
    overall_citation_rate,
    per_query_breakdown,
    trend,
)


def _run(timestamp, target, results):
    return {"timestamp": timestamp, "target": target, "engine": "mock", "results": results}


def _res(query, cited, rank=None):
    return {"query": query, "engine": "mock", "cited": cited, "rank": rank}


def test_citation_rate_basic():
    results = [_res("a", True, 1), _res("b", False), _res("c", True, 3), _res("d", False)]
    assert citation_rate(results) == 0.5


def test_citation_rate_empty_is_zero():
    assert citation_rate([]) == 0.0


def test_citation_rate_all_cited():
    assert citation_rate([_res("a", True, 1), _res("b", True, 2)]) == 1.0


def test_flatten_tags_run_context():
    runs = [_run("t1", "example.com", [_res("a", True, 1)])]
    flat = flatten_results(runs)
    assert flat[0]["timestamp"] == "t1"
    assert flat[0]["target"] == "example.com"
    assert flat[0]["query"] == "a"


def test_overall_citation_rate_across_runs():
    runs = [
        _run("t1", "example.com", [_res("a", True, 1), _res("b", False)]),
        _run("t2", "example.com", [_res("a", True, 2), _res("b", True, 4)]),
    ]
    # 3 cited out of 4 total.
    assert overall_citation_rate(runs) == 0.75


def test_per_query_breakdown_math_and_best_rank():
    runs = [
        _run("t1", "example.com", [_res("a", True, 3), _res("b", False)]),
        _run("t2", "example.com", [_res("a", True, 1), _res("b", False)]),
    ]
    breakdown = per_query_breakdown(runs)

    assert breakdown["a"]["cited"] == 2
    assert breakdown["a"]["total"] == 2
    assert breakdown["a"]["rate"] == 1.0
    assert breakdown["a"]["best_rank"] == 1  # min of ranks 3 and 1

    assert breakdown["b"]["cited"] == 0
    assert breakdown["b"]["total"] == 2
    assert breakdown["b"]["rate"] == 0.0
    assert breakdown["b"]["best_rank"] is None


def test_trend_is_chronological_with_rates():
    runs = [
        _run("2026-08-02", "example.com", [_res("a", False), _res("b", False)]),
        _run("2026-08-01", "example.com", [_res("a", True, 1), _res("b", True, 2)]),
    ]
    points = trend(runs)
    assert [p["timestamp"] for p in points] == ["2026-08-01", "2026-08-02"]
    assert points[0]["rate"] == 1.0
    assert points[1]["rate"] == 0.0
    assert points[0]["count"] == 2
