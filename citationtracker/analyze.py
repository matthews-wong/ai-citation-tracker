"""Analysis over stored runs: citation rate, per-query breakdown, and trend.

All functions here are pure — they take loaded run records (see
:mod:`citationtracker.store`) and return plain data structures. No I/O, no
formatting. That keeps the math independently testable and the CLI free to
render however it likes.

A *run* record has this shape::

    {
      "timestamp": "2026-08-04T09:00:00+00:00",
      "target": "example.com",
      "engine": "mock",
      "results": [
        {"query": "...", "engine": "mock", "cited": true, "rank": 2, "citations": [...]},
        ...
      ]
    }
"""

from __future__ import annotations

from typing import Any


def flatten_results(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten per-run result lists into one list, tagging each with run context.

    Each returned result carries the originating run's ``timestamp`` and
    ``target`` so downstream functions can aggregate without re-walking runs.
    """

    out: list[dict[str, Any]] = []
    for run in runs:
        timestamp = run.get("timestamp")
        target = run.get("target")
        for result in run.get("results", []):
            out.append({**result, "timestamp": timestamp, "target": target})
    return out


def citation_rate(results: list[dict[str, Any]]) -> float:
    """Fraction of ``results`` in which the target domain was cited (0.0–1.0).

    Returns ``0.0`` for an empty input so callers never divide by zero.
    """

    if not results:
        return 0.0
    cited = sum(1 for r in results if r.get("cited"))
    return cited / len(results)


def per_query_breakdown(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate results per query across all runs.

    Returns a mapping of query -> ``{cited, total, rate, best_rank}`` where
    ``best_rank`` is the lowest (best) rank the target ever achieved for that
    query, or ``None`` if it was never cited.
    """

    breakdown: dict[str, dict[str, Any]] = {}
    for result in flatten_results(runs):
        query = result.get("query", "")
        entry = breakdown.setdefault(query, {"cited": 0, "total": 0, "_ranks": []})
        entry["total"] += 1
        if result.get("cited"):
            entry["cited"] += 1
            rank = result.get("rank")
            if rank is not None:
                entry["_ranks"].append(rank)

    for entry in breakdown.values():
        entry["rate"] = entry["cited"] / entry["total"] if entry["total"] else 0.0
        ranks = entry.pop("_ranks")
        entry["best_rank"] = min(ranks) if ranks else None
    return breakdown


def trend(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Citation rate per run, ordered chronologically by timestamp.

    Each point is ``{timestamp, rate, count}``. This is the series to plot or
    print to see whether visibility is improving or eroding over time.
    """

    points: list[dict[str, Any]] = []
    for run in sorted(runs, key=lambda r: r.get("timestamp") or ""):
        results = run.get("results", [])
        points.append(
            {
                "timestamp": run.get("timestamp"),
                "rate": citation_rate(results),
                "count": len(results),
            }
        )
    return points


def overall_citation_rate(runs: list[dict[str, Any]]) -> float:
    """Citation rate across every result in every run."""

    return citation_rate(flatten_results(runs))
