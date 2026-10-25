"""
The insolvency slice must be runnable, and must stay out of `main.py all`.

It is a fixture-only vertical slice with no database or network dependency.
Folding it into a phase would make `all` write audit artefacts as a side
effect and would couple a self-contained deliverable to the geospatial
pipeline's failure modes.
"""

from app.runners.pipeline_runner import PipelineRunner


PHASES = ("phase_1", "phase_2", "phase_3", "phase_4")


def test_insolvency_is_an_available_command():
    assert "insolvency" in PipelineRunner().commands


def test_insolvency_is_not_run_by_any_phase(monkeypatch):
    """
    `main.py all` must not trigger it.
    """

    runner = PipelineRunner()

    called: list[str] = []

    for name in runner.commands:

        attribute = name.replace("-", "_")

        if not hasattr(runner, attribute):
            continue

        monkeypatch.setattr(
            runner,
            attribute,
            (lambda n=attribute: lambda: called.append(n))(),
            raising=False,
        )

    for phase in PHASES:
        getattr(runner, phase)()

    assert "insolvency" not in called, (
        "insolvency ran as part of `all`; it is an explicit-only command"
    )
