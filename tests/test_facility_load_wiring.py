"""
Facility loading must be reachable from the pipeline.

FacilityLoader is the only code path that writes iris_core.facilities, so if
no pipeline command or phase calls it, a fully successful `main.py all` still
leaves the facilities table empty and the dashboard has nothing to render.
"""

from pathlib import Path

from app.commands.load_facilities_command import LoadFacilitiesCommand
from app.config.paths import DataPaths
from app.runners.pipeline_runner import PipelineRunner


PHASE_1_STEPS = (
    "country",
    "markets",
    "facilities",
    "merge",
    "transform",
    "facility_geo_transform",
    "facility_load",
)


def test_facility_load_is_an_available_command():
    """
    `main.py facility-load` must exist so the step can be run on its own.
    """

    assert "facility-load" in PipelineRunner().commands


def test_phase_1_loads_facilities_after_transforming_them(monkeypatch):
    """
    The full pipeline must load facilities, and only after the clean JSON
    they are read from has been produced.
    """

    runner = PipelineRunner()

    calls: list[str] = []

    def recorder(step: str):
        return lambda: calls.append(step)

    for step in PHASE_1_STEPS:
        monkeypatch.setattr(runner, step, recorder(step), raising=False)

    runner.phase_1()

    assert "facility_load" in calls, (
        "phase_1 never loads facilities into the database; it ran: "
        f"{calls}"
    )

    assert calls.index("facility_load") > calls.index("transform"), (
        "facilities must be loaded after `transform` writes "
        f"facilities_clean.json; order was {calls}"
    )


def test_load_command_reads_from_the_supplied_data_paths(tmp_path):
    """
    A staged run writes to data/runs/<run_id>/processed/..., so the command
    must resolve its input through DataPaths rather than a fixed path.
    """

    command = LoadFacilitiesCommand(
        session=object(),
        paths=DataPaths(tmp_path),
    )

    assert command.input_file == (
        tmp_path
        / "processed"
        / "datacentermap"
        / "facilities_clean.json"
    )


def test_load_command_defaults_to_the_flat_data_workspace():
    """
    Run on its own with no RunContext, the command keeps using data/.
    """

    command = LoadFacilitiesCommand(session=object())

    assert command.input_file == Path(
        "data/processed/datacentermap/facilities_clean.json"
    )
