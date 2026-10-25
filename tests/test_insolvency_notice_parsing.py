"""
Insolvency notices must normalise into a stable shape.

The source fixtures use German portal field names (gericht, aktenzeichen,
schuldner, bekanntmachung_am ...). Everything downstream — dedup keys, match
rationale, the audit trail — depends on those landing in known fields with
real date and status types rather than raw strings.
"""

from datetime import date

from app.insolvency.notice import NoticeStatus
from app.insolvency.notice_parser import NoticeParser


FIXTURE = "fixtures/insolvency/notices/batch_001.json"


def test_parses_every_notice_in_the_batch():
    notices = NoticeParser().parse(FIXTURE)

    assert len(notices) == 5


def test_normalises_the_german_source_field_names():
    notices = NoticeParser().parse(FIXTURE)

    notice = next(n for n in notices if n.notice_id == "NOT-2026-000101")

    assert notice.court == "Amtsgericht Hamburg"
    assert notice.case_number == "67 IN 123/26"
    assert notice.entity_name == "Nordlicht Rechenzentrum GmbH"
    assert notice.entity_registry_id == "HRB 12345"
    assert notice.entity_address.postal_code == "20095"
    assert notice.entity_address.city == "Hamburg"


def test_parses_dates_as_dates_not_strings():
    notices = NoticeParser().parse(FIXTURE)

    notice = next(n for n in notices if n.notice_id == "NOT-2026-000101")

    assert notice.published_on == date(2026, 10, 21)
    assert notice.event_on == date(2026, 10, 20)


def test_carries_the_source_reference_for_provenance():
    notices = NoticeParser().parse(FIXTURE)

    notice = next(n for n in notices if n.notice_id == "NOT-2026-000101")

    assert notice.source_reference.startswith("synthetic-fixture://")


def test_maps_the_opened_status():
    notices = NoticeParser().parse(FIXTURE)

    notice = next(n for n in notices if n.notice_id == "NOT-2026-000101")

    assert notice.status is NoticeStatus.OPENED
    assert notice.is_active is True


def test_a_notice_without_an_address_parses_with_an_empty_address():
    """
    NOT-2026-000103 omits the address entirely. That must parse rather than
    fail, because the missing address is exactly what makes it ambiguous.
    """

    notices = NoticeParser().parse(FIXTURE)

    notice = next(n for n in notices if n.notice_id == "NOT-2026-000103")

    assert notice.entity_address.postal_code is None
    assert notice.entity_address.city is None


def test_withdrawn_notices_are_not_active():
    """
    A withdrawn notice must never read as a live insolvency.
    """

    notices = NoticeParser().parse(
        "fixtures/insolvency/notices/batch_002.json"
    )

    notice = next(n for n in notices if n.notice_id == "NOT-2026-000106")

    assert notice.status is NoticeStatus.WITHDRAWN
    assert notice.is_active is False
