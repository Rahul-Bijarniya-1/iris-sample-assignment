"""
The harvester is reachable in two ways — `main.py transnetbw` and
`python -m app.transnetbw.cli` — and never runs as a side effect of
`main.py all`: a full pipeline run must not make live requests to a source
it was not asked to harvest.

The CLI is the scheduler-facing contract, so its exit codes are tested
against a real (scratch) database.
"""

import json

import pytest

from app.runners.pipeline_runner import PipelineRunner
from app.transnetbw import cli
from tests.conftest import scratch_url


def test_transnetbw_is_an_available_command():
    assert "transnetbw" in PipelineRunner().commands


def test_no_phase_of_the_full_pipeline_runs_the_harvester(monkeypatch):
    runner = PipelineRunner()

    calls: list[str] = []

    for method in runner.commands.values():
        name = method.__name__
        monkeypatch.setattr(runner, name, lambda name=name: calls.append(name), raising=False)

    for phase in (runner.phase_1, runner.phase_2, runner.phase_3, runner.phase_4):
        phase()

    assert calls, "the phases ran no steps at all; the recorder is not wired"
    assert "transnetbw" not in calls


def test_harvest_without_a_database_is_refused(monkeypatch, capsys):
    monkeypatch.delenv("TRANSNETBW_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir("/")  # no .env to fall back on

    exit_code = cli.main(["harvest", "--offline", "--fixtures", _fixtures(), "--no-report"])

    assert exit_code == 1
    assert "no database" in capsys.readouterr().err.lower()


def _fixtures() -> str:
    from pathlib import Path

    return str(Path(__file__).resolve().parents[1] / "fixtures" / "transnetbw")


@pytest.mark.integration
def test_an_offline_harvest_exits_0_and_prints_its_status(migrated_database, capsys):
    exit_code = cli.main(
        [
            "harvest",
            "--offline",
            "--fixtures",
            _fixtures(),
            "--database-url",
            scratch_url(migrated_database),
            "--no-report",
        ]
    )

    out = capsys.readouterr().out

    assert exit_code == 0
    assert "SUCCEEDED" in out
    assert "inserted 14" in out


@pytest.mark.integration
def test_log_json_emits_one_parseable_event_per_line(migrated_database, capsys):
    exit_code = cli.main(
        [
            "harvest",
            "--offline",
            "--fixtures",
            _fixtures(),
            "--database-url",
            scratch_url(migrated_database),
            "--no-report",
            "--log-json",
        ]
    )

    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]

    assert exit_code == 0
    assert {"record", "issue", "run_finished"} <= {event["event"] for event in events}
    assert events[-1]["event"] == "run_finished"
    assert events[-1]["exit_code"] == 0
