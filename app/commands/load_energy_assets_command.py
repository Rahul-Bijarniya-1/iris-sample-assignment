from sqlalchemy.orm import Session

from app.config.paths import DataPaths
from app.loaders.energy_asset_loader import EnergyAssetLoader


class LoadEnergyAssetsCommand:
    """
    Loads transformed MaStR energy assets into PostgreSQL.

    Input:
        <paths>/processed/mastr/power_generation.json

    The input location comes from DataPaths so a staged pipeline run reads
    the file it just produced under data/runs/<run_id>/ instead of whatever
    happens to be sitting in the flat data/ workspace.
    """

    INPUT_FILENAME = "power_generation.json"

    def __init__(
        self,
        session: Session,
        paths: DataPaths | None = None,
    ):

        self.paths = paths or DataPaths()

        self.input_file = (
            self.paths.mastr_processed
            / self.INPUT_FILENAME
        )

        self.loader = EnergyAssetLoader(
            session
        )

    def execute(self):

        return self.loader.load(
            self.input_file
        )
