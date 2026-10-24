



from __future__ import annotations

import argparse

from app.runners.run_context import RunContext

from app.runners.country_runner import (
    run_country,
)

from app.runners.market_runner import (
    run_markets,
)

from app.runners.facility_runner import (
    run_facilities,
)

from app.runners.merge_runner import (
    run_merge,
)

from app.runners.transform_runner import (
    run_transform,
)

from app.runners.facility_geo_transform_runner import (
    run as run_facility_geo_transform,
)

from app.runners.facility_load_runner import (
    run as run_facility_load,
)

# ==========================================================
# OVERPASS
# ==========================================================

from app.runners.overpass_runner import (
    run as run_overpass,
)

from app.runners.overpass_parser_runner import (
    run as run_overpass_parser,
)

from app.runners.overpass_transform_runner import (
    run as run_overpass_transform,
)

# ==========================================================
# MASTR
# ==========================================================

from app.runners.mastr_runner import (
    run as run_mastr,
)

from app.runners.mastr_parser_runner import (
    run as run_mastr_parser,
)

from app.runners.mastr_transform_runner import (
    run as run_mastr_transform,
)

from app.runners.energy_asset_load_runner import (
    run as run_energy_asset_load,
)

# ==========================================================
# POWER
# ==========================================================

from app.runners.power_enricher_runner import (
    run as run_power_enricher,
)

# ==========================================================
# BORIS
# ==========================================================

from app.runners.boris_runner import (
    BorisRunner,
)

from app.runners.boris_enricher_runner import (
    run as run_boris_enricher,
)

# ==========================================================
# SITE SCORE
# ==========================================================

from app.runners.site_score_runner import (
    run as run_site_score,
)

# ==========================================================
# NEWS
# ==========================================================

from app.runners.news_runner import (
    run as run_news,
)

from app.runners.entity_matcher_runner import (
    run as run_entity_matcher,
)

from app.runners.news_intelligence_runner import (
    run as run_news_intelligence,
)

from app.runners.news_loader_runner import (
    run as run_news_loader,
)

# ==========================================================
# BUSINESS INTELLIGENCE
# ==========================================================

from app.runners.land_value_runner import (
    run as run_land_values,
)

from app.runners.power_infrastructure_runner import (
    run as run_power_infrastructure,
)

from app.runners.osm_infrastructure_runner import (
    run as run_osm_infrastructure,
)


class PipelineRunner:
    """
    Main IRIS Core ETL pipeline runner.

    Responsibilities:

        - Parse CLI arguments
        - Select the country
        - Execute individual pipeline commands
        - Execute the complete ETL pipeline
        - Create an isolated RunContext for `all`
        - Pass RunContext-specific DataPaths to migrated runners
        - Stop the pipeline when a required phase fails
        - Mark successful and failed runs
        - Promote successful runs to data/current

    Individual commands executed outside `all` continue
    to use their default DataPaths.

    When executing `all`, every migrated component receives:

        self.run_context.paths
    """

    def __init__(
        self,
        country_code: str = "DE",
    ):

        self.country_code = (
            country_code.upper()
        )

        self.run_context: RunContext | None = None

        self.commands = {

            "country": self.country,

            "markets": self.markets,

            "facilities": self.facilities,

            "merge": self.merge,

            "transform": self.transform,

            "facility-geo-transform": (
                self.facility_geo_transform
            ),

            "facility-load": (
                self.facility_load
            ),

            "overpass": self.overpass,

            "overpass-parse": (
                self.overpass_parse
            ),

            "overpass-transform": (
                self.overpass_transform
            ),

            "mastr": self.mastr,

            "mastr-parse": (
                self.mastr_parse
            ),

            "mastr-transform": (
                self.mastr_transform
            ),

            "energy-asset-load": (
                self.energy_asset_load
            ),

            "power-enricher": (
                self.power_enricher
            ),

            "boris-transform": (
                self.boris_transform
            ),

            "boris-enricher": (
                self.boris_enricher
            ),

            "site-score": (
                self.site_score
            ),

            "news": self.news,

            "entity-matcher": (
                self.entity_matcher
            ),

            "news-load": (
                self.news_load
            ),

            "news-intelligence": (
                self.news_intelligence
            ),

            "land-values": (
                self.land_values
            ),

            "power-infrastructure": (
                self.power_infrastructure
            ),

            "osm-infrastructure": (
                self.osm_infrastructure
            ),

            "all": self.run_all,
        }

    # ======================================================
    # CLI
    # ======================================================

    def run(self):

        parser = argparse.ArgumentParser(
            description="IRIS Core ETL Pipeline"
        )

        parser.add_argument(
            "command",
            choices=self.commands.keys(),
            help="Pipeline command to execute",
        )

        parser.add_argument(
            "--country",
            default="DE",
            help="ISO country code (default: DE)",
        )

        args = parser.parse_args()

        self.country_code = (
            args.country.upper()
        )

        print(
            f"Country: "
            f"{self.country_code}"
        )

        print(
            f"Command: "
            f"{args.command}"
        )

        print("=" * 60)

        self.commands[
            args.command
        ]()

    # ======================================================
    # RUN CONTEXT
    # ======================================================

    def create_run_context(self):

        self.run_context = (
            RunContext()
        )

        self.run_context.initialize()

        print(
            f"Run ID      : "
            f"{self.run_context.run_id}"
        )

        print(
            f"Run Root    : "
            f"{self.run_context.run_root}"
        )

        print(
            f"Raw Root    : "
            f"{self.run_context.paths.raw}"
        )

        print(
            f"Processed   : "
            f"{self.run_context.paths.processed}"
        )

        print("--------------------------------")

    # ======================================================
    # PATH HELPER
    # ======================================================

    def get_paths(self):

        """
        Return the current RunContext paths when running
        the complete pipeline.

        Individual commands without a RunContext use
        their default DataPaths internally.
        """

        if self.run_context is None:

            return None

        return self.run_context.paths

    # ======================================================
    # INDIVIDUAL COMMANDS
    # ======================================================

    def country(self):

        print(
            "▶ Running Country Scraper..."
        )

        paths = self.get_paths()

        if paths:

            run_country(
                country_code=self.country_code,
                paths=paths,
            )

        else:

            run_country(
                country_code=self.country_code,
            )

    # ======================================================

    def markets(self):

        print(
            "▶ Running Market Scraper..."
        )

        paths = self.get_paths()

        if paths:

            run_markets(
                country_code=self.country_code,
                paths=paths,
            )

        else:

            run_markets(
                country_code=self.country_code,
            )

    # ======================================================

    def facilities(self):

        print(
            "▶ Running Facility Scraper..."
        )

        paths = self.get_paths()

        if paths:

            run_facilities(
                country_code=self.country_code,
                paths=paths,
            )

        else:

            run_facilities(
                country_code=self.country_code,
            )

    # ======================================================

    def merge(self):

        print(
            "▶ Running Facility Merger..."
        )

        paths = self.get_paths()

        if paths:

            run_merge(
                paths=paths,
            )

        else:

            run_merge()

    # ======================================================

    def transform(self):

        print(
            "▶ Running Facility Transformer..."
        )

        paths = self.get_paths()

        if paths:

            run_transform(
                paths=paths,
            )

        else:

            run_transform()

    # ======================================================

    def facility_geo_transform(self):

        print(
            "▶ Running Facility Geo Transformer..."
        )

        paths = self.get_paths()

        if paths:

            run_facility_geo_transform(
                paths=paths,
            )

        else:

            run_facility_geo_transform()

    # ======================================================
    # FACILITY LOAD
    # ======================================================

    def facility_load(self):

        print(
            "▶ Loading Facilities..."
        )

        paths = self.get_paths()

        if paths:

            run_facility_load(
                paths=paths,
            )

        else:

            run_facility_load()

    # ======================================================
    # OVERPASS
    # ======================================================

    def overpass(self):

        print(
            "▶ Running Overpass Scraper..."
        )

        paths = self.get_paths()

        if paths:

            run_overpass(
                country_code=self.country_code,
                paths=paths,
            )

        else:

            run_overpass(
                country_code=self.country_code,
            )

    # ======================================================

    def overpass_parse(self):

        print(
            "▶ Running Overpass Parser..."
        )

        paths = self.get_paths()

        if paths:

            run_overpass_parser(
                paths=paths,
            )

        else:

            run_overpass_parser()

    # ======================================================

    def overpass_transform(self):

        print(
            "▶ Running Overpass Transformer..."
        )

        paths = self.get_paths()

        if paths:

            run_overpass_transform(
                paths=paths,
            )

        else:

            run_overpass_transform()

    # ======================================================
    # MASTR
    # ======================================================

    def mastr(self):

        print(
            "▶ Running MaStR Scraper..."
        )

        paths = self.get_paths()

        if paths:

            run_mastr(
                paths=paths,
            )

        else:

            run_mastr()

    # ======================================================

    def mastr_parse(self):

        print(
            "▶ Running MaStR Parser..."
        )

        paths = self.get_paths()

        if paths:

            run_mastr_parser(
                paths=paths,
            )

        else:

            run_mastr_parser()

    # ======================================================

    def mastr_transform(self):

        print(
            "▶ Running MaStR Transformer..."
        )

        paths = self.get_paths()

        if paths:

            run_mastr_transform(
                country_code=self.country_code,
                paths=paths,
            )

        else:

            run_mastr_transform(
                country_code=self.country_code,
            )

    # ======================================================

    def energy_asset_load(self):

        print(
            "▶ Loading Energy Assets..."
        )

        paths = self.get_paths()

        if paths:

            run_energy_asset_load(
                paths=paths,
            )

        else:

            run_energy_asset_load()

    # ======================================================
    # POWER
    # ======================================================

    def power_enricher(self):

        print(
            "▶ Running Power Enricher..."
        )

        paths = self.get_paths()

        if paths:

            run_power_enricher(
                paths=paths,
            )

        else:

            run_power_enricher()

    # ======================================================
    # BORIS
    # ======================================================

    def boris_transform(self):

        print(
            "▶ Running BORIS Transformer..."
        )

        paths = self.get_paths()

        if paths:

            BorisRunner(
                paths=paths,
            ).run()

        else:

            BorisRunner().run()

    # ======================================================

    def boris_enricher(self):

        print(
            "▶ Running BORIS Enricher..."
        )

        paths = self.get_paths()

        if paths:

            run_boris_enricher(
                paths=paths,
            )

        else:

            run_boris_enricher()

    # ======================================================
    # SITE SCORE
    # ======================================================

    def site_score(self):

        print(
            "▶ Running Site Scoring..."
        )

        paths = self.get_paths()

        if paths:

            run_site_score(
                paths=paths,
            )

        else:

            run_site_score()

    # ======================================================
    # NEWS
    # ======================================================

    def news(self):

        print(
            "▶ Running News Fetcher..."
        )

        paths = self.get_paths()

        if paths:

            run_news(
                paths=paths,
            )

        else:

            run_news()

    # ======================================================

    def entity_matcher(self):

        print(
            "▶ Running Entity Matcher..."
        )

        paths = self.get_paths()

        if paths:

            run_entity_matcher(
                paths=paths,
            )

        else:

            run_entity_matcher()

    # ======================================================

    def news_load(self):

        print(
            "▶ Loading News Intelligence..."
        )

        paths = self.get_paths()

        if paths:

            run_news_loader(
                paths=paths,
            )

        else:

            run_news_loader()

    # ======================================================

    def news_intelligence(self):

        print(
            "▶ Running News Intelligence..."
        )

        paths = self.get_paths()

        if paths:

            run_news_intelligence(
                paths=paths,
            )

        else:

            run_news_intelligence()

    # ======================================================
    # LAND
    # ======================================================

    def land_values(self):

        print(
            "▶ Loading Land Values..."
        )

        paths = self.get_paths()

        if paths:

            run_land_values(
                paths=paths,
            )

        else:

            run_land_values()

    # ======================================================
    # POWER INFRASTRUCTURE
    # ======================================================

    def power_infrastructure(self):

        print(
            "▶ Loading Power Infrastructure..."
        )

        paths = self.get_paths()

        if paths:

            run_power_infrastructure(
                paths=paths,
            )

        else:

            run_power_infrastructure()

    # ======================================================
    # OSM INFRASTRUCTURE
    # ======================================================

    def osm_infrastructure(self):

        print(
            "▶ Loading OSM Infrastructure..."
        )

        paths = self.get_paths()

        if paths:

            result = run_osm_infrastructure(
                paths=paths,
                country_code=self.country_code,
            )

        else:

            result = run_osm_infrastructure(
                country_code=self.country_code,
            )

        print(
            f"OSM Infrastructure Result: "
            f"{result}"
        )

        return result

    # ======================================================
    # COMPLETE PIPELINE
    # ======================================================

    def run_all(self):

        print("=" * 70)

        print(
            "IRIS Core ETL Pipeline"
        )

        print("=" * 70)

        print(
            f"Country Code: "
            f"{self.country_code}"
        )

        print("=" * 70)

        # --------------------------------------------------
        # Create isolated run workspace
        # --------------------------------------------------

        self.create_run_context()

        try:

            # ==============================================
            # PHASE 1
            # ==============================================

            self.phase_1()

            # ==============================================
            # PHASE 2
            # ==============================================

            self.phase_2()

            # ==============================================
            # PHASE 3
            # ==============================================

            self.phase_3()

            # ==============================================
            # PHASE 4
            # ==============================================

            self.phase_4()

        except KeyboardInterrupt:

            print("\n")

            print("=" * 70)

            print(
                "PIPELINE INTERRUPTED"
            )

            print("=" * 70)

            if self.run_context:

                self.run_context.mark_failed(
                    KeyboardInterrupt(
                        "Pipeline interrupted by user."
                    )
                )

                print(
                    f"Run ID   : "
                    f"{self.run_context.run_id}"
                )

                print(
                    f"Run Root : "
                    f"{self.run_context.run_root}"
                )

                print(
                    "Current production data "
                    "was not promoted."
                )

            print("=" * 70)

            raise

        except Exception as exc:

            print("\n")

            print("=" * 70)

            print(
                "PIPELINE FAILED"
            )

            print("=" * 70)

            print(
                f"Country : "
                f"{self.country_code}"
            )

            print(
                f"Error   : "
                f"{type(exc).__name__}: {exc}"
            )

            if self.run_context:

                self.run_context.mark_failed(
                    exc
                )

                print(
                    f"Run ID   : "
                    f"{self.run_context.run_id}"
                )

                print(
                    f"Run Root : "
                    f"{self.run_context.run_root}"
                )

                print(
                    "Current production data "
                    "was not promoted."
                )

            print("=" * 70)

            raise

        # --------------------------------------------------
        # SUCCESS
        # --------------------------------------------------

        if self.run_context:

            self.run_context.mark_success()

            print("\n")

            print("=" * 70)

            print(
                "PROMOTING RUN TO CURRENT"
            )

            print("=" * 70)

            self.run_context.promote_to_current()

        print("\n")

        print("=" * 70)

        print(
            "PIPELINE COMPLETED SUCCESSFULLY"
        )

        print("=" * 70)

        if self.run_context:

            print(
                f"Run ID   : "
                f"{self.run_context.run_id}"
            )

            print(
                f"Run Root : "
                f"{self.run_context.run_root}"
            )

            print(
                f"Current  : "
                f"{self.run_context.current_root}"
            )

        print("=" * 70)

    # ======================================================
    # PHASE 1
    # ======================================================

    def phase_1(self):

        print(
            "\n[Phase 1] Data Acquisition"
        )

        self.country()

        self.markets()

        self.facilities()

        self.merge()

        self.transform()

        self.facility_geo_transform()

        self.facility_load()

        print(
            "\n[Phase 1] Completed"
        )

    # ======================================================
    # PHASE 2
    # ======================================================

    def phase_2(self):

        print(
            "\n[Phase 2] Infrastructure"
        )

        self.overpass()

        self.overpass_parse()

        self.overpass_transform()

        self.mastr()

        self.mastr_parse()

        self.mastr_transform()

        self.boris_transform()

        self.energy_asset_load()

        print(
            "\n[Phase 2] Completed"
        )

    # ======================================================
    # PHASE 3
    # ======================================================

    def phase_3(self):

        print(
            "\n[Phase 3] Spatial Intelligence"
        )

        self.power_enricher()

        self.boris_enricher()

        self.site_score()

        print(
            "\n[Phase 3] Completed"
        )

    # ======================================================
    # PHASE 4
    # ======================================================

    def phase_4(self):

        print(
            "\n[Phase 4] Business Intelligence"
        )

        self.news()

        self.entity_matcher()

        self.news_load()

        self.news_intelligence()

        self.land_values()

        self.power_infrastructure()

        self.osm_infrastructure()

        print(
            "\n[Phase 4] Completed"
        )


# ==========================================================
# MODULE ENTRY POINT
# ==========================================================

if __name__ == "__main__":

    PipelineRunner().run()
