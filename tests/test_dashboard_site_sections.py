"""
The dashboard must survive a facility with no site intelligence.

ui/app.py called `site_intelligence.get("site_score")` with no guard, while
site_intelligence is initialised to None and only replaced when a facility
is selected. With an empty facilities table nothing is ever selected, so the
page died on load with:

    AttributeError: 'NoneType' object has no attribute 'get'

Both panels already handle a missing payload; only the lookup was unguarded.
"""

from ui.components.site_intelligence_panel import render_site_intelligence
from ui.components.site_score_panel import render_site_score
from ui.site_intelligence_view import site_section


def test_site_section_returns_none_when_there_is_no_intelligence():
    """
    The empty-database case: no facility selected, so no intelligence.
    """

    assert site_section(None, "site_score") is None


def test_site_section_returns_none_for_an_empty_payload():
    assert site_section({}, "site_score") is None


def test_site_section_returns_none_for_a_missing_section():
    assert site_section({"power": {}}, "site_score") is None


def test_site_section_reads_the_requested_section():
    intelligence = {
        "site_score": {"overall_score": 72, "rating": "Strong"},
        "power": {},
    }

    assert site_section(intelligence, "site_score") == {
        "overall_score": 72,
        "rating": "Strong",
    }


def test_site_score_panel_renders_a_missing_score():
    """
    The value site_section returns for missing data must be renderable.
    """

    render_site_score(site_section(None, "site_score"))


def test_site_intelligence_panel_renders_a_missing_payload():
    render_site_intelligence(None)
