"""
Energy asset loading must be reachable from the pipeline.

EnergyAssetLoader is the only code path that writes iris_core.energy_assets,
so if no pipeline command or phase calls it, a fully successful `main.py all`
still leaves the energy_assets table empty even though the MaStR chain has
already produced the file it would read.

This is the same defect as the facilities one covered by
test_facility_load_wiring.py.
"""

from pathlib import Path

from app.commands.load_energy_assets_command import (
    LoadEnergyAssetsCommand,
)
from app.config.paths import DataPaths
from app.runners.pipeline_runner import PipelineRunner


PHASE_2_STEPS = (
    "overpass",
    "overpass_parse",
    "overpass_transform",
    "mastr",
    "mastr_parse",
    "mastr_transform",
    "boris_transform",
    "energy_asset_load",
)


def test_energy_asset_load_is_an_available_command():
    """
    `main.py energy-asset-load` must exist so the step can be run on its own.
    """

    assert "energy-asset-load" in PipelineRunner().commands


def test_phase_2_loads_energy_assets_after_transforming_them(monkeypatch):
    """
    The full pipeline must load energy assets, and only after the processed
    JSON they are read from has been produced.
    """

    runner = PipelineRunner()

    calls: list[str] = []

    def recorder(step: str):
        return lambda: calls.append(step)

    for step in PHASE_2_STEPS:
        monkeypatch.setattr(runner, step, recorder(step), raising=False)

    runner.phase_2()

    assert "energy_asset_load" in calls, (
        "phase_2 never loads energy assets into the database; it ran: "
        f"{calls}"
    )

    assert calls.index("energy_asset_load") > calls.index("mastr_transform"), (
        "energy assets must be loaded after `mastr-transform` writes "
        f"power_generation.json; order was {calls}"
    )


def test_load_command_reads_from_the_supplied_data_paths(tmp_path):
    """
    A staged run writes to data/runs/<run_id>/processed/..., so the command
    must resolve its input through DataPaths rather than a fixed path.
    """

    command = LoadEnergyAssetsCommand(
        session=object(),
        paths=DataPaths(tmp_path),
    )

    assert command.input_file == (
        tmp_path
        / "processed"
        / "mastr"
        / "power_generation.json"
    )


def test_load_command_defaults_to_the_flat_data_workspace():
    """
    Run on its own with no RunContext, the command keeps using data/.
    """

    command = LoadEnergyAssetsCommand(session=object())

    assert command.input_file == Path(
        "data/processed/mastr/power_generation.json"
    )
