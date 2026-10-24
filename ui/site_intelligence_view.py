"""
Helpers for reading the site intelligence payload in the dashboard.

`DashboardService.get_site_intelligence` is only called when a facility is
selected, and no facility is selected when the facilities table is empty.
Every read of the payload therefore has to tolerate its absence.
"""


def site_section(
    intelligence: dict | None,
    key: str,
):
    """
    Return one section of the site intelligence payload, or None.

    Returns None when there is no payload at all, and when the payload
    simply has no such section. Both panels treat None as "no data".
    """

    if not intelligence:
        return None

    return intelligence.get(key)
