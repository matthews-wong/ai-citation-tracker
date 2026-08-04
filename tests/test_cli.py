"""CLI tests — track + report end to end on the offline MockEngine."""

from __future__ import annotations

import textwrap

from click.testing import CliRunner

from citationtracker.cli import main


def _write_config(tmp_path, target="example.com"):
    config = tmp_path / "config.yaml"
    config.write_text(
        textwrap.dedent(
            f"""
            target: {target}
            queries:
              - best crm
              - top note apps
              - seo tools
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return config


def test_track_then_report(tmp_path):
    config = _write_config(tmp_path)
    store = tmp_path / "runs.json"
    runner = CliRunner()

    track_result = runner.invoke(
        main, ["track", "-c", str(config), "-s", str(store)]
    )
    assert track_result.exit_code == 0, track_result.output
    assert "MOCK engine" in track_result.output
    assert store.exists()

    report_result = runner.invoke(
        main, ["report", "-c", str(config), "-s", str(store)]
    )
    assert report_result.exit_code == 0, report_result.output
    assert "Citation report for example.com" in report_result.output
    assert "Overall citation rate:" in report_result.output


def test_track_is_deterministic_across_invocations(tmp_path):
    config = _write_config(tmp_path)
    store_a = tmp_path / "a.json"
    store_b = tmp_path / "b.json"
    runner = CliRunner()

    out_a = runner.invoke(main, ["track", "-c", str(config), "-s", str(store_a)])
    out_b = runner.invoke(main, ["track", "-c", str(config), "-s", str(store_b)])

    # The per-query "cited @#N / not cited" lines must be identical.
    lines_a = [ln for ln in out_a.output.splitlines() if ln.startswith("  '")]
    lines_b = [ln for ln in out_b.output.splitlines() if ln.startswith("  '")]
    assert lines_a == lines_b


def test_report_without_runs_errors(tmp_path):
    config = _write_config(tmp_path)
    store = tmp_path / "empty.json"
    runner = CliRunner()

    result = runner.invoke(main, ["report", "-c", str(config), "-s", str(store)])
    assert result.exit_code != 0
    assert "No runs found" in result.output


def test_missing_config_errors(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        main, ["track", "-c", str(tmp_path / "missing.yaml"), "-s", str(tmp_path / "s.json")]
    )
    assert result.exit_code != 0
    assert "Config not found" in result.output
