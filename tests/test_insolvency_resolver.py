"""
Acceptance test 2: similar company names at different addresses do not
auto-match.

The brief's reason for this task: legal insolvency must never be inferred
from name similarity alone. A wrong match asserts in writing that a real
company is insolvent, so the resolver is deliberately biased towards
"needs review" over "matched".
"""

from app.insolvency.notice_parser import NoticeParser
from app.insolvency.registry import CompanyRegistry
from app.insolvency.resolver import EntityResolver, MatchMethod


BATCH_1 = "fixtures/insolvency/notices/batch_001.json"
BATCH_2 = "fixtures/insolvency/notices/batch_002.json"
REGISTRY = "fixtures/insolvency/registry/companies.json"


def _resolve(batch=BATCH_1):
    resolver = EntityResolver(CompanyRegistry.load(REGISTRY))

    notices = NoticeParser().parse(batch)

    return {n.notice_id: resolver.resolve(n) for n in notices}


def test_a_registry_id_matches_on_the_identifier_alone():
    """
    NOT-2026-000101 carries HRB 12345. A stable identifier is authoritative.
    """

    match = _resolve()["NOT-2026-000101"]

    assert match.registry_id == "HRB 12345"
    assert match.method is MatchMethod.REGISTRY_ID
    assert match.auto_matched is True
    assert match.human_review is False


def test_name_plus_postal_code_is_enough_to_auto_match():
    """
    NOT-2026-000102 has no registry id, but name and postal code both agree
    with exactly one company.
    """

    match = _resolve()["NOT-2026-000102"]

    assert match.registry_id == "HRB 11111"
    assert match.method is MatchMethod.NAME_ADDRESS
    assert match.auto_matched is True


def test_same_name_at_a_different_address_does_not_auto_match():
    """
    ACCEPTANCE TEST 2.

    NOT-2026-000104 names "Nordlicht Rechenzentrum GmbH" exactly, but in
    Berlin while the registered company is in Hamburg. A conflicting address
    is disqualifying, not merely weakening.
    """

    match = _resolve()["NOT-2026-000104"]

    assert match.auto_matched is False, (
        "a notice naming a company at a different address was auto-matched"
    )
    assert match.registry_id is None


def test_an_ambiguous_name_with_no_address_is_flagged_not_matched():
    """
    NOT-2026-000103 names a company that exists twice in the registry, at
    different addresses, and gives no address to discriminate.
    """

    match = _resolve()["NOT-2026-000103"]

    assert match.auto_matched is False
    assert match.human_review is True
    assert len(match.candidates) == 2


def test_a_name_alone_never_auto_matches():
    """
    The guarantee the whole task exists for: no notice may be auto-matched
    on name similarity without corroborating address evidence.
    """

    for match in _resolve().values():

        if match.method is MatchMethod.REGISTRY_ID:
            continue

        if match.auto_matched:
            assert match.address_agreement is True, (
                f"{match.notice_id} auto-matched without address evidence"
            )


def test_every_result_carries_a_rationale():
    for match in _resolve().values():
        assert match.rationale, f"{match.notice_id} has no rationale"


def test_a_withdrawn_notice_does_not_report_an_active_insolvency():
    """
    NOT-2026-000106 is withdrawn. It may still resolve to a company, but it
    must not be reported as a live insolvency.
    """

    match = _resolve(BATCH_2)["NOT-2026-000106"]

    assert match.notice_is_active is False


def test_no_result_claims_anything_about_the_property():
    """
    Acceptance test 3: nothing in the output may imply the matched site is
    for sale or otherwise available.
    """

    for match in _resolve().values():

        text = (match.rationale or "").lower()

        for claim in ("for sale", "available", "vacant", "on the market"):
            assert claim not in text, (
                f"{match.notice_id} rationale implies availability: {text}"
            )
