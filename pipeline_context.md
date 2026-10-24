> **STALE — do not use as a reference.**
>
> This file is a generated snapshot of a few source files, not documentation,
> and it has drifted badly from the code. `pipeline_runner.py` appears here at
> ~290 lines against ~1180 live; `facility_runner` appears as a bare function
> where the live version is a class with per-market caching and request
> pacing; the paths are Windows-style from another machine.
>
> For how the pipeline works, read the "Data Pipeline" section of README.md.
> For the authoritative behaviour of any step, read `app/runners/`.

==============================
FILE: app\runners\pipeline_runner.py
==============================

import argparse

from app.runners.country_runner import run_country
from app.runners.market_runner import run_markets
from app.runners.facility_runner import run_facilities
from app.runners.merge_runner import run_merge
from app.runners.transform_runner import run_transform
from app.runners.facility_geo_transform_runner import (
    run as run_facility_geo_transform,
)
from app.runners.overpass_runner import run as run_overpass
from app.runners.overpass_parser_runner import run as run_overpass_parser
from app.runners.overpass_transform_runner import (
    run as run_overpass_transform,
)
from app.runners.mastr_runner import run as run_mastr
from app.runners.mastr_parser_runner import run as run_mastr_parser
from app.runners.mastr_transform_runner import (
    run as run_mastr_transform,
)
from app.runners.power_enricher_runner import run as run_power_enricher
from app.runners.boris_runner import BorisRunner
from app.runners.boris_enricher_runner import run as run_boris_enricher
from app.runners.site_score_runner import run as run_site_score
from app.runners.news_runner import run as run_news
from app.runners.entity_matcher_runner import run as run_entity_matcher
from app.runners.news_intelligence_runner import (
    run as run_news_intelligence,
)
from app.runners.land_value_runner import run as run_land_values
from app.runners.power_infrastructure_runner import (
    run as run_power_infrastructure,
)


class PipelineRunner:
    """
    Main application runner.

    Responsible for:
    - Parsing CLI arguments
    - Selecting the country
    - Executing individual commands
    - Executing the full ETL pipeline
    """

    def __init__(
        self,
        country_code: str = "DE",
    ):
        self.country_code = country_code.upper()

        self.commands = {
            "country": self.country,
            "markets": self.markets,
            "facilities": self.facilities,
            "merge": self.merge,
            "transform": self.transform,
            "facility-geo-transform": self.facility_geo_transform,
            "overpass": self.overpass,
            "overpass-parse": self.overpass_parse,
            "overpass-transform": self.overpass_transform,
            "mastr": self.mastr,
            "mastr-parse": self.mastr_parse,
            "mastr-transform": self.mastr_transform,
            "power-enricher": self.power_enricher,
            "boris-transform": self.boris_transform,
            "boris-enricher": self.boris_enricher,
            "site-score": self.site_score,
            "news": self.news,
            "entity-matcher": self.entity_matcher,
            "news-intelligence": self.news_intelligence,
            "land-values": self.land_values,
            "power-infrastructure": self.power_infrastructure,
            "all": self.run_all,
        }

    # =====================================================
    # CLI
    # =====================================================

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

        self.country_code = args.country.upper()

        print(
            f"Country: {self.country_code}"
        )

        self.commands[args.command]()

    # =====================================================
    # Individual Commands
    # =====================================================

    def country(self):
        print("▶ Running Country Scraper...")
        run_country(
            country_code=self.country_code
        )

    def markets(self):
        print("▶ Running Market Scraper...")
        run_markets(
            country_code=self.country_code
        )

    def facilities(self):
        print("▶ Running Facility Scraper...")
        run_facilities(
            country_code=self.country_code
        )

    def merge(self):
        print("▶ Running Facility Merger...")
        run_merge()

    def transform(self):
        print("▶ Running Facility Transformer...")
        run_transform()

    def facility_geo_transform(self):
        print("▶ Running Facility Geo Transformer...")
        run_facility_geo_transform()

    def overpass(self):
        print("▶ Running Overpass Scraper...")
        run_overpass(
            country_code=self.country_code
        )

    def overpass_parse(self):
        print("▶ Running Overpass Parser...")
        run_overpass_parser()

    def overpass_transform(self):
        print("▶ Running Overpass Transformer...")
        run_overpass_transform()

    def mastr(self):
        print("▶ Running MaStR Scraper...")
        run_mastr()

    def mastr_parse(self):
        print("▶ Running MaStR Parser...")
        run_mastr_parser()

    def mastr_transform(self):
        print("▶ Running MaStR Transformer...")
        run_mastr_transform(
            country_code=self.country_code
        )

    def power_enricher(self):
        print("▶ Running Power Enricher...")
        run_power_enricher()

    def boris_transform(self):
        print("▶ Running BORIS Transformer...")
        BorisRunner().run()

    def boris_enricher(self):
        print("▶ Running BORIS Enricher...")
        run_boris_enricher()

    def site_score(self):
        print("▶ Running Site Scoring...")
        run_site_score()

    def news(self):
        print("▶ Running News Fetcher...")
        run_news()

    def entity_matcher(self):
        print("▶ Running Entity Matcher...")
        run_entity_matcher()

    def news_intelligence(self):
        print("▶ Running News Intelligence...")
        run_news_intelligence()

    def land_values(self):
        print("▶ Loading Land Values...")
        run_land_values()

    def power_infrastructure(self):
        print("▶ Loading Power Infrastructure...")
        run_power_infrastructure()

    # =====================================================
    # Complete Pipeline
    # =====================================================

    def run_all(self):

        print("=" * 70)
        print("IRIS Core ETL Pipeline")
        print("=" * 70)
        print(
            f"Country Code: {self.country_code}"
        )
        print("=" * 70)

        self.phase_1()

        self.phase_2()

        self.phase_3()

        self.phase_4()

        print("\n" + "=" * 70)
        print("Pipeline Completed Successfully")
        print("=" * 70)

    # =====================================================
    # Phases
    # =====================================================

    def phase_1(self):

        print("\n[Phase 1] Data Acquisition")

        self.country()
        self.markets()
        self.facilities()
        self.merge()
        self.transform()
        self.facility_geo_transform()

    def phase_2(self):

        print("\n[Phase 2] Infrastructure")

        self.overpass()
        self.overpass_parse()
        self.overpass_transform()

        self.mastr()
        self.mastr_parse()
        self.mastr_transform()

        self.boris_transform()

    def phase_3(self):

        print("\n[Phase 3] Spatial Intelligence")

        self.power_enricher()
        self.boris_enricher()
        self.site_score()

    def phase_4(self):

        print("\n[Phase 4] Business Intelligence")

        self.news()
        self.entity_matcher()
        self.news_intelligence()
        self.land_values()
        self.power_infrastructure()


==============================
FILE: app\runners\facility_runner.py
==============================

import json

from app.scrapers.datacentermap.facility_scraper import (
    FacilityScraper,
)


def run_facilities(
    country_code: str = "DE",
):
    country_code = country_code.upper()

    markets_file = (
        f"data/processed/datacentermap/"
        f"{country_code.lower()}_markets.json"
    )

    with open(
        markets_file,
        encoding="utf-8",
    ) as f:

        markets = json.load(f)

    scraper = FacilityScraper()

    for market in markets:

        slug = market.get("slug")

        if not slug:
            continue

        try:

            scraper.scrape_market(
                slug
            )

        except Exception as e:

            print(
                f"Failed {slug}: {e}"
            )

    print(
        "Facility scraping completed."
    )


==============================
FILE: app\parsers\facility_parser.py
==============================

import json
from pathlib import Path

from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from app.database.models.facility import Facility


class FacilityParser:
    """
    Parses facility JSON files into Facility entities.
    """

    def parse(self, file_path: str | Path) -> list[Facility]:

        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(file_path)

        with file_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        facilities: list[Facility] = []

        for item in data:

            latitude = item.get("latitude")
            longitude = item.get("longitude")

            geometry = None

            if latitude is not None and longitude is not None:

                geometry = from_shape(
                    Point(longitude, latitude),
                    srid=4326,
                )

            company = item.get("company") or "Unknown"

            name = item.get("name") or "Unnamed Facility"

            address = item.get("address")

            city = item.get("city")

            postal_code = item.get("postal_code")

            country = item.get("country")

            website = item.get("website")

            facility = Facility(

                company=company,

                name=name,

                address=address,

                city=city,

                postal_code=postal_code,

                country=country,

                website=website,

                latitude=latitude,

                longitude=longitude,

                geometry=geometry,
            )

            facilities.append(facility)

        return facilities


==============================
FILE: app\transformers\facility_transformer.py
==============================

from pathlib import Path
import json


class FacilityTransformer:

    INPUT_FILE = Path("data/processed/datacentermap/facilities.json")
    OUTPUT_FILE = Path("data/processed/datacentermap/facilities_clean.json")

    def transform(self):

        with open(self.INPUT_FILE, encoding="utf-8") as f:
            facilities = json.load(f)

        cleaned = []

        seen = set()

        for facility in facilities:

            company = self._clean_text(facility.get("company"))
            name = self._clean_text(facility.get("name"))
            city = self._clean_text(facility.get("city"))
            address = self._clean_text(facility.get("address"))
            country = self._clean_text(facility.get("country"))

            latitude = self._to_float(facility.get("latitude"))
            longitude = self._to_float(facility.get("longitude"))

            website = self._normalize_url(facility.get("website"))

            duplicate_key = (
                company,
                name,
                city,
                latitude,
                longitude,
            )

            if duplicate_key in seen:
                continue

            seen.add(duplicate_key)

            cleaned.append(
                {
                    "company": company,
                    "name": name,
                    "city": city,
                    "country": country,
                    "address": address,
                    "postal_code": self._clean_text(
                        facility.get("postal_code")
                    ),
                    "latitude": latitude,
                    "longitude": longitude,
                    "website": website,
                }
            )

        self.OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(self.OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, indent=2, ensure_ascii=False)

        print(f"✅ Cleaned {len(cleaned)} facilities.")
        print(f"📁 Saved to {self.OUTPUT_FILE}")

    def _clean_text(self, value):

        if value is None:
            return None

        value = str(value).strip()

        if value == "":
            return None

        return value

    def _to_float(self, value):

        if value in (None, "", "null"):
            return None

        try:
            return float(value)
        except Exception:
            return None

    def _normalize_url(self, url):

        url = self._clean_text(url)

        if not url:
            return None

        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        return url.lower()


==============================
FILE: app\loaders\facility_loader.py
==============================

from pathlib import Path
import logging
import time

from sqlalchemy.orm import Session

from app.database.repositories.facility_repository import FacilityRepository
from app.parsers.facility_parser import FacilityParser


logger = logging.getLogger(__name__)


class FacilityLoader:
    """
    Loads facility data into PostgreSQL.

    Workflow:
        Read JSON
            ↓
        Parse facilities
            ↓
        Remove duplicates
            ↓
        Persist to database
            ↓
        Return import statistics
    """

    def __init__(self, session: Session):
        self.repository = FacilityRepository(session)
        self.parser = FacilityParser()

    def _deduplicate(self, facilities: list):
        """
        Remove duplicate facilities based on (company, name).
        """

        unique = {}
        duplicates = 0

        for facility in facilities:

            key = (
                facility.company,
                facility.name,
            )

            if key in unique:
                duplicates += 1
                continue

            unique[key] = facility

        logger.info("Removed %s duplicate facilities", duplicates)

        return list(unique.values()), duplicates

    def load(self, file_path: str | Path) -> dict:

        start_time = time.perf_counter()

        logger.info("Reading facility file...")

        parsed_facilities = self.parser.parse(file_path)

        logger.info(
            "Parsed %s facilities",
            len(parsed_facilities),
        )

        facilities, duplicates = self._deduplicate(parsed_facilities)

        logger.info(
            "Importing %s unique facilities",
            len(facilities),
        )

        self.repository.create_many(facilities)

        elapsed = round(
            time.perf_counter() - start_time,
            2,
        )

        logger.info("Facility import completed.")

        return {
            "processed": len(parsed_facilities),
            "inserted": len(facilities),
            "duplicates_removed": duplicates,
            "failed": 0,
            "execution_time": elapsed,
        }


==============================
FILE: app\mergers\facility_merger.py
==============================

from pathlib import Path

from app.scrapers.datacentermap.facility_parser import FacilityParser


class FacilityMerger:

    def merge(self):

        parser = FacilityParser()

        facility_dir = Path("data/raw/datacentermap/facilities")

        all_facilities = []

        for file in facility_dir.glob("*.json"):

            slug = file.stem

            try:
                print(f"Parsing {slug}")

                facilities = parser.parse(slug)

                all_facilities.extend(facilities)

            except Exception as e:
                print(f"❌ Failed parsing {slug}: {e}")

        print(f"\nMerged {len(all_facilities)} facilities.")

        return all_facilities
