from app.commands.load_energy_assets_command import (
    LoadEnergyAssetsCommand,
)
from app.config.paths import DataPaths
from app.database.session import SessionLocal


def run(
    paths: DataPaths | None = None,
):
    """
    Load transformed MaStR energy assets into the database.

    When called from `all`, the pipeline provides the current
    RunContext-specific DataPaths.

    When called independently, the default data/ workspace is used.
    """

    session = SessionLocal()

    try:

        command = LoadEnergyAssetsCommand(
            session,
            paths=paths,
        )

        return command.execute()

    finally:

        session.close()
