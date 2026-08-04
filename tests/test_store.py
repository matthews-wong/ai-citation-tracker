"""Store tests — append/load round-trip on a temp file (no shared state)."""

from __future__ import annotations

from citationtracker.store import append_run, load_runs


def test_load_missing_returns_empty(tmp_path):
    assert load_runs(tmp_path / "nope.json") == []


def test_append_then_load_round_trip(tmp_path):
    path = tmp_path / "runs.json"
    run = {
        "timestamp": "2026-08-04T09:00:00+00:00",
        "target": "example.com",
        "engine": "mock",
        "results": [{"query": "a", "engine": "mock", "cited": True, "rank": 1, "citations": ["example.com"]}],
    }
    append_run(run, path)
    append_run({**run, "timestamp": "2026-08-05T09:00:00+00:00"}, path)

    loaded = load_runs(path)
    assert len(loaded) == 2
    assert loaded[0]["target"] == "example.com"
    assert loaded[1]["timestamp"] == "2026-08-05T09:00:00+00:00"


def test_append_creates_parent_dir(tmp_path):
    path = tmp_path / "nested" / "dir" / "runs.json"
    append_run({"timestamp": "t", "target": "x", "engine": "mock", "results": []}, path)
    assert path.exists()
    assert load_runs(path)[0]["target"] == "x"
