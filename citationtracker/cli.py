"""Command-line interface wiring engines, store, and analysis together.

Two commands:

* ``track`` — ask each configured query to an engine (``mock`` by default,
  fully offline), detect whether the target domain was cited and at what rank,
  and append the run to the JSON store.
* ``report`` — load stored runs for the target and print the overall citation
  rate, a per-query breakdown, and the rate trend across runs.

Configuration (target domain + tracked queries) lives in a YAML file; see
``config.example.yaml``. The CLI does no analysis math itself — it delegates to
:mod:`citationtracker.analyze` so the numbers stay independently testable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
import yaml

from .analyze import overall_citation_rate, per_query_breakdown, trend
from .engines import EngineUnavailable, build_engine, detect_domain
from .store import DEFAULT_STORE_PATH, append_run, load_runs

DEFAULT_CONFIG_PATH = "config.example.yaml"


def load_config(path: str | Path) -> dict[str, Any]:
    """Load and validate the YAML config (target domain + tracked queries)."""

    p = Path(path)
    if not p.exists():
        raise click.ClickException(
            f"Config not found: {p}. Copy config.example.yaml and edit it."
        )
    with p.open("r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}

    target = config.get("target")
    queries = config.get("queries")
    if not target:
        raise click.ClickException(f"Config {p} is missing a 'target' domain.")
    if not queries:
        raise click.ClickException(f"Config {p} is missing a non-empty 'queries' list.")
    return config


def _fmt_pct(rate: float) -> str:
    return f"{rate * 100:.0f}%"


@click.group()
@click.version_option(package_name="ai-citation-tracker")
def main() -> None:
    """Track whether your domain is cited by AI answer engines, over time.

    The default engine is a deterministic, fully offline MOCK — its results are
    illustrative and involve no real answer-engine calls. See the README for
    plugging in a real provider.
    """


@main.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    help="Path to the YAML config (target domain + tracked queries).",
)
@click.option(
    "-e",
    "--engine",
    "engine_name",
    default="mock",
    show_default=True,
    type=click.Choice(["mock", "claude"]),
    help="Answer engine to query. 'mock' is offline and deterministic.",
)
@click.option(
    "-s",
    "--store",
    "store_path",
    default=str(DEFAULT_STORE_PATH),
    show_default=True,
    help="Path to the JSON run store.",
)
def track(config_path: str, engine_name: str, store_path: str) -> None:
    """Run every tracked query through ENGINE and record whether TARGET was cited."""

    config = load_config(config_path)
    target = config["target"]
    queries = config["queries"]
    mock_domains = config.get("mock_domains")

    try:
        engine = build_engine(engine_name, target, mock_domains=mock_domains)
    except EngineUnavailable as exc:
        raise click.ClickException(str(exc)) from exc

    if engine_name == "mock":
        click.echo(
            "Using the MOCK engine: results are deterministic and illustrative, "
            "with no real answer-engine calls."
        )

    results: list[dict[str, Any]] = []
    for query in queries:
        try:
            answer = engine.answer(query)
        except EngineUnavailable as exc:
            raise click.ClickException(str(exc)) from exc
        cited, rank = detect_domain(answer.citations, target)
        results.append(
            {
                "query": query,
                "engine": engine.name,
                "cited": cited,
                "rank": rank,
                "citations": answer.citations,
            }
        )
        status = f"cited @#{rank}" if cited else "not cited"
        click.echo(f"  {query!r}: {status}")

    run = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target": target,
        "engine": engine.name,
        "results": results,
    }
    append_run(run, store_path)

    cited_count = sum(1 for r in results if r["cited"])
    click.echo(
        f"Recorded run for {target}: cited in {cited_count}/{len(results)} queries "
        f"({_fmt_pct(cited_count / len(results))}). Store: {store_path}"
    )


@main.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    default=DEFAULT_CONFIG_PATH,
    show_default=True,
    help="Path to the YAML config (used to select the target domain).",
)
@click.option(
    "-s",
    "--store",
    "store_path",
    default=str(DEFAULT_STORE_PATH),
    show_default=True,
    help="Path to the JSON run store.",
)
def report(config_path: str, store_path: str) -> None:
    """Print citation rate, per-query breakdown, and trend for TARGET."""

    config = load_config(config_path)
    target = config["target"]

    all_runs = load_runs(store_path)
    runs = [run for run in all_runs if run.get("target") == target]
    if not runs:
        raise click.ClickException(
            f"No runs found for {target} in {store_path}. Run 'track' first."
        )

    click.echo(f"Citation report for {target} ({len(runs)} run(s))")
    click.echo(f"Overall citation rate: {_fmt_pct(overall_citation_rate(runs))}")

    click.echo("\nPer-query breakdown:")
    breakdown = per_query_breakdown(runs)
    for query in sorted(breakdown):
        entry = breakdown[query]
        rank = entry["best_rank"]
        rank_str = f"best #{rank}" if rank is not None else "never cited"
        click.echo(
            f"  {_fmt_pct(entry['rate']):>4}  ({entry['cited']}/{entry['total']}, {rank_str})  {query}"
        )

    click.echo("\nTrend (rate per run, oldest first):")
    for point in trend(runs):
        click.echo(f"  {point['timestamp']}  {_fmt_pct(point['rate']):>4}  (n={point['count']})")


if __name__ == "__main__":  # pragma: no cover
    main()
