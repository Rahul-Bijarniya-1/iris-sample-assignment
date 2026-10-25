"""
Conservative entity resolution: notice -> registered company.

The governing rule, and the reason this task exists: legal insolvency must
never be inferred from name similarity alone. A false match asserts in
writing that a solvent company is insolvent, which is far more damaging than
leaving a true match for a human to confirm. Every tie-break therefore
favours "needs review".

Decision order:

  1. Stable identifier present and known -> authoritative match.
  2. Otherwise, name candidates above a high similarity floor, then:
     - address conflicts  -> disqualified, no match at all
     - address agrees     -> auto-match
     - address unknown    -> flagged for review, never auto-matched
     - several candidates -> flagged for review, never auto-matched

Nothing here states anything about a debtor's property. An insolvency notice
is a court record, not an indication that a site is for sale or available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from difflib import SequenceMatcher
from enum import Enum

from app.insolvency.notice import Address, Notice
from app.insolvency.registry import Company, CompanyRegistry


class MatchMethod(Enum):

    REGISTRY_ID = "registry_id"
    NAME_ADDRESS = "name_address"
    NONE = "none"


# A name must be near-identical before it is even considered. This is a
# candidate filter, not a match: address evidence still decides.
NAME_SIMILARITY_FLOOR = 0.92

# Confidence at or above which a match may be applied without a human.
AUTO_MATCH_THRESHOLD = 0.90

CONFIDENCE_REGISTRY_ID = 1.0
CONFIDENCE_NAME_AND_POSTCODE = 0.95
CONFIDENCE_NAME_AND_CITY = 0.75
CONFIDENCE_NAME_ONLY = 0.50
CONFIDENCE_AMBIGUOUS = 0.40
CONFIDENCE_NONE = 0.0


@dataclass
class CandidateCompany:
    """
    A registry company considered for one notice, with why it was considered.
    """

    registry_id: str
    name: str
    name_similarity: float
    address_agreement: bool | None
    address_conflict: bool

    def to_dict(self) -> dict:
        return {
            "registry_id": self.registry_id,
            "name": self.name,
            "name_similarity": round(self.name_similarity, 4),
            "address_agreement": self.address_agreement,
            "address_conflict": self.address_conflict,
        }


@dataclass
class MatchResult:
    """
    The outcome for one notice.

    `auto_matched` is the only field a downstream consumer should act on
    without a human. `human_review` marks everything a reviewer should see.
    """

    notice_id: str
    entity_name: str
    registry_id: str | None
    method: MatchMethod
    confidence: float
    rationale: str
    human_review: bool
    notice_is_active: bool
    notice_status: str
    address_agreement: bool | None = None
    as_of: date | None = None
    resolved_at: datetime | None = None
    candidates: list[CandidateCompany] = field(default_factory=list)

    @property
    def auto_matched(self) -> bool:
        return (
            self.registry_id is not None
            and self.confidence >= AUTO_MATCH_THRESHOLD
        )

    def to_dict(self) -> dict:
        return {
            "notice_id": self.notice_id,
            "entity_name": self.entity_name,
            "registry_id": self.registry_id,
            "method": self.method.value,
            "confidence": round(self.confidence, 4),
            "auto_matched": self.auto_matched,
            "human_review": self.human_review,
            "address_agreement": self.address_agreement,
            "notice_is_active": self.notice_is_active,
            "notice_status": self.notice_status,
            "rationale": self.rationale,
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "resolved_at": (
                self.resolved_at.isoformat()
                if self.resolved_at
                else None
            ),
            "candidates": [c.to_dict() for c in self.candidates],
        }


class EntityResolver:

    def __init__(self, registry: CompanyRegistry):
        self.registry = registry

    # ------------------------------------------------------------------

    def resolve(self, notice: Notice) -> MatchResult:

        base = {
            "notice_id": notice.notice_id,
            "entity_name": notice.entity_name,
            "notice_is_active": notice.is_active,
            "notice_status": notice.status.value,
            "as_of": notice.published_on,
            "resolved_at": datetime.now(timezone.utc),
        }

        # 1. Stable identifier wins outright.
        by_id = self.registry.by_registry_id(notice.entity_registry_id)

        if by_id is not None:

            return MatchResult(
                registry_id=by_id.registry_id,
                method=MatchMethod.REGISTRY_ID,
                confidence=CONFIDENCE_REGISTRY_ID,
                human_review=False,
                address_agreement=self._agrees(
                    notice.entity_address, by_id.address
                ),
                rationale=(
                    f"Matched on registry identifier "
                    f"{by_id.registry_id}, published in the notice."
                ),
                candidates=[self._candidate(notice, by_id)],
                **base,
            )

        # An identifier was given but is unknown to the registry: do not
        # fall back to name matching, which would quietly contradict it.
        if notice.entity_registry_id:

            return MatchResult(
                registry_id=None,
                method=MatchMethod.NONE,
                confidence=CONFIDENCE_NONE,
                human_review=True,
                rationale=(
                    f"Notice cites registry identifier "
                    f"{notice.entity_registry_id}, which is absent from the "
                    f"registry. Not matched by name, because an unknown "
                    f"identifier is a provenance problem rather than a "
                    f"naming one."
                ),
                candidates=[],
                **base,
            )

        # 2. Name candidates, then let address evidence decide.
        candidates = self._name_candidates(notice)

        if not candidates:

            return MatchResult(
                registry_id=None,
                method=MatchMethod.NONE,
                confidence=CONFIDENCE_NONE,
                human_review=False,
                rationale=(
                    "No registry company's name is close enough to "
                    f"\"{notice.entity_name}\" to consider."
                ),
                candidates=[],
                **base,
            )

        viable = [c for c in candidates if not c.address_conflict]

        if not viable:

            return MatchResult(
                registry_id=None,
                method=MatchMethod.NONE,
                confidence=CONFIDENCE_NONE,
                human_review=True,
                address_agreement=False,
                rationale=(
                    f"Name matches {len(candidates)} registry "
                    f"company/companies, but every one is registered at a "
                    f"different address than the notice gives. A matching "
                    f"name at a conflicting address is not evidence of the "
                    f"same legal entity."
                ),
                candidates=candidates,
                **base,
            )

        if len(viable) > 1:

            return MatchResult(
                registry_id=None,
                method=MatchMethod.NONE,
                confidence=CONFIDENCE_AMBIGUOUS,
                human_review=True,
                address_agreement=None,
                rationale=(
                    f"Name matches {len(viable)} registry companies and the "
                    f"notice gives no address that separates them. Left for "
                    f"review rather than guessing between them."
                ),
                candidates=candidates,
                **base,
            )

        candidate = viable[0]

        if candidate.address_agreement is True:

            confidence = (
                CONFIDENCE_NAME_AND_POSTCODE
                if self._postcodes_agree(notice, candidate.registry_id)
                else CONFIDENCE_NAME_AND_CITY
            )

            auto = confidence >= AUTO_MATCH_THRESHOLD

            return MatchResult(
                registry_id=(
                    candidate.registry_id if auto else None
                ),
                method=(
                    MatchMethod.NAME_ADDRESS
                    if auto
                    else MatchMethod.NONE
                ),
                confidence=confidence,
                human_review=not auto,
                address_agreement=True,
                rationale=(
                    f"Name similarity "
                    f"{candidate.name_similarity:.2f} against "
                    f"{candidate.registry_id}, corroborated by "
                    + (
                        "an identical postal code."
                        if confidence == CONFIDENCE_NAME_AND_POSTCODE
                        else "a matching city only, which is weaker than a "
                        "postal code and so left for review."
                    )
                ),
                candidates=candidates,
                **base,
            )

        # Single name candidate, no address to corroborate it.
        return MatchResult(
            registry_id=None,
            method=MatchMethod.NONE,
            confidence=CONFIDENCE_NAME_ONLY,
            human_review=True,
            address_agreement=None,
            rationale=(
                f"Name similarity {candidate.name_similarity:.2f} against "
                f"{candidate.registry_id}, but the notice carries no "
                f"address to corroborate it. Name alone is not sufficient "
                f"evidence of legal insolvency."
            ),
            candidates=candidates,
            **base,
        )

    # ------------------------------------------------------------------
    # Candidates and address logic
    # ------------------------------------------------------------------

    def _name_candidates(self, notice: Notice) -> list[CandidateCompany]:

        candidates = []

        for company in self.registry.companies:

            similarity = self._similarity(
                notice.entity_name, company.name
            )

            if similarity < NAME_SIMILARITY_FLOOR:
                continue

            candidates.append(self._candidate(notice, company, similarity))

        return sorted(
            candidates,
            key=lambda c: c.name_similarity,
            reverse=True,
        )

    def _candidate(
        self,
        notice: Notice,
        company: Company,
        similarity: float | None = None,
    ) -> CandidateCompany:

        if similarity is None:
            similarity = self._similarity(
                notice.entity_name, company.name
            )

        return CandidateCompany(
            registry_id=company.registry_id,
            name=company.name,
            name_similarity=similarity,
            address_agreement=self._agrees(
                notice.entity_address, company.address
            ),
            address_conflict=self._conflicts(
                notice.entity_address, company.address
            ),
        )

    def _postcodes_agree(
        self,
        notice: Notice,
        registry_id: str,
    ) -> bool:
        """
        Whether the notice and the registered company carry the same postal
        code. Checked against the registry rather than inferred from the
        candidate, which records only whether the addresses agreed and not
        on which field.
        """

        company = self.registry.by_registry_id(registry_id)

        if company is None:
            return False

        notice_postcode = notice.entity_address.postal_code
        company_postcode = company.address.postal_code

        if not notice_postcode or not company_postcode:
            return False

        return notice_postcode.strip() == company_postcode.strip()

    @staticmethod
    def _normalise(value: str | None) -> str:

        if not value:
            return ""

        return " ".join(value.split()).casefold()

    @classmethod
    def _similarity(cls, left: str | None, right: str | None) -> float:

        a = cls._normalise(left)
        b = cls._normalise(right)

        if not a or not b:
            return 0.0

        return SequenceMatcher(None, a, b).ratio()

    @classmethod
    def _agrees(cls, notice_address: Address, company: Address) -> bool | None:
        """
        True when the addresses corroborate each other, False when they
        contradict, None when there is not enough information either way.
        """

        if notice_address.is_empty or company.is_empty:
            return None

        if notice_address.postal_code and company.postal_code:
            return (
                notice_address.postal_code.strip()
                == company.postal_code.strip()
            )

        if notice_address.city and company.city:
            return cls._normalise(notice_address.city) == cls._normalise(
                company.city
            )

        return None

    @classmethod
    def _conflicts(cls, notice_address: Address, company: Address) -> bool:
        return cls._agrees(notice_address, company) is False
