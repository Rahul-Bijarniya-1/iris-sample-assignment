"""
`main.py transnetbw` — a live harvest with default settings.

For flags (--offline, --full, --dry-run, -v, …) use the harvester's own
command line: uv run python -m app.transnetbw.cli harvest --help
"""

from app.transnetbw.cli import main


def run() -> int:
    """
    Run a live harvest; returns the harvester's exit code.
    """

    return main(["harvest"])
