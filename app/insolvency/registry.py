"""
The corporate registry a notice is matched against.

A small, self-contained fixture: the brief's scope limit rules out a live
registry integration, and the matching logic is what is under test.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.insolvency.notice import Address


@dataclass(frozen=True)
class Company:

    registry_id: str
    name: str
    address: Address
    legal_form: str | None = None


class CompanyRegistry:
    """
    Lookup by stable identifier, and by name for candidate generation.

    Name lookup returns every company sharing a name. Collisions are real —
    the fixture contains two "Rheinmetall Logistik GmbH" at different
    addresses — and collapsing them would hide exactly the ambiguity the
    resolver has to surface.
    """

    def __init__(self, companies: list[Company]):

        self.companies = companies

        self._by_registry_id = {
            company.registry_id: company for company in companies
        }

    @classmethod
    def load(cls, file_path: str | Path) -> "CompanyRegistry":

        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(
                f"Registry fixture not found: {file_path}"
            )

        with file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        companies = []

        for raw in payload.get("companies", []):

            address = raw.get("address") or {}

            companies.append(
                Company(
                    registry_id=raw["registry_id"],
                    name=raw["name"],
                    legal_form=raw.get("legal_form"),
                    address=Address(
                        street=address.get("street"),
                        postal_code=address.get("postal_code"),
                        city=address.get("city"),
                    ),
                )
            )

        return cls(companies)

    # ------------------------------------------------------------------

    def by_registry_id(self, registry_id: str | None) -> Company | None:

        if not registry_id:
            return None

        return self._by_registry_id.get(registry_id.strip())

    def __len__(self) -> int:
        return len(self.companies)
