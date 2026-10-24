from sqlalchemy.orm import Session

from app.config.paths import DataPaths
from app.loaders.facility_loader import FacilityLoader


class LoadFacilitiesCommand:
    """
    Loads cleaned Data Center Map facilities into PostgreSQL.

    Input:
        <paths>/processed/datacentermap/facilities_clean.json

    The input location comes from DataPaths so a staged pipeline run reads
    the file it just produced under data/runs/<run_id>/ instead of whatever
    happens to be sitting in the flat data/ workspace.
    """

    INPUT_FILENAME = "facilities_clean.json"

    def __init__(
        self,
        session: Session,
        paths: DataPaths | None = None,
    ):

        self.paths = paths or DataPaths()

        self.input_file = (
            self.paths.datacentermap_processed
            / self.INPUT_FILENAME
        )

        self.loader = FacilityLoader(
            session
        )

    def execute(self):

        return self.loader.load(
            self.input_file
        )
