"""Local JSON persistence for tracking runs.

The store is a single JSON file holding an array of *run* records. Each run is
one invocation of ``track`` and captures the target domain, a UTC timestamp, the
engine used, and the per-query results. Keeping every run (rather than
overwriting) is what makes trend analysis over time possible.

The format is intentionally plain JSON so it is easy to inspect, diff, and load
without this package. ``append_run`` is read-modify-write: fine for the local,
single-writer workflow this tool targets.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: Default on-disk location, relative to the current working directory.
DEFAULT_STORE_PATH = Path("data") / "runs.json"


def load_runs(path: str | Path = DEFAULT_STORE_PATH) -> list[dict[str, Any]]:
    """Load all run records from ``path``.

    Returns an empty list when the file does not exist yet, so callers can treat
    a fresh install and an empty history identically.
    """

    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Store at {p} is corrupt: expected a JSON array of runs.")
    return data


def append_run(run: dict[str, Any], path: str | Path = DEFAULT_STORE_PATH) -> None:
    """Append a single ``run`` record to the store, creating it if needed."""

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    runs = load_runs(p)
    runs.append(run)
    with p.open("w", encoding="utf-8") as fh:
        json.dump(runs, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
