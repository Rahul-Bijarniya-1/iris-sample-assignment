"""
Errors the harvester distinguishes. FetchError lives in fetch.py, next to
the code that raises it.
"""


class ParseError(Exception):
    """
    A document could not be read as the expected page type — its markup is
    missing something every such page has (a title, a sitemap root).
    """

    def __init__(self, url: str | None, message: str):

        super().__init__(f"{message}: {url}" if url else message)

        self.url = url


class EmptyResponseError(Exception):
    """
    A discovery document parsed but yielded nothing (no project cards). The
    run must fail rather than treat the source as empty, which would retire
    every record.
    """
