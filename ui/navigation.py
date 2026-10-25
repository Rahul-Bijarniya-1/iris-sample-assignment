"""Navigation contract shared by the sidebar and the application router."""

from collections.abc import Callable, Mapping


PAGE_NAMES = (
    "Dashboard",
    "Facilities",
    "Power Grid",
    "Land Values",
    "News Intelligence",
    "AI Assistant",
    "Settings",
)


def dispatch_page(
    selected_page: str | None,
    renderers: Mapping[str, Callable[[], None]],
) -> str:
    """Render exactly one selected page, defaulting unknown values to Dashboard."""

    resolved_page = (
        selected_page
        if selected_page in PAGE_NAMES
        else "Dashboard"
    )
    renderers[resolved_page]()
    return resolved_page
