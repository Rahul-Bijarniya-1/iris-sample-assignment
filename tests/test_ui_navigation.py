import pytest

from ui.navigation import PAGE_NAMES, dispatch_page


EXPECTED_PAGES = (
    "Dashboard",
    "Facilities",
    "Power Grid",
    "Land Values",
    "News Intelligence",
    "AI Assistant",
    "Settings",
)


def test_navigation_exposes_every_sidebar_destination():
    assert PAGE_NAMES == EXPECTED_PAGES


@pytest.mark.parametrize("selected_page", EXPECTED_PAGES)
def test_navigation_dispatches_the_selected_page(selected_page):
    rendered = []
    renderers = {
        page: lambda page=page: rendered.append(page)
        for page in EXPECTED_PAGES
    }

    resolved_page = dispatch_page(selected_page, renderers)

    assert resolved_page == selected_page
    assert rendered == [selected_page]


def test_navigation_falls_back_to_dashboard_for_an_unknown_page():
    rendered = []

    resolved_page = dispatch_page(
        "Unknown",
        {"Dashboard": lambda: rendered.append("Dashboard")},
    )

    assert resolved_page == "Dashboard"
    assert rendered == ["Dashboard"]
