"""
`build_news_context` must be defined exactly once.

ContextBuilderService defined it twice: a dict-returning version at line
252 (matching the generic build() dispatcher's convention of returning
structured context) and a string-building version at line 294 that
actually gets called — Python method resolution makes the second
definition win, silently shadowing the first with an incompatible
signature (news= vs the first's articles=).
"""

from pathlib import Path


SOURCE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "context_builder_service.py"
).read_text()


def test_build_news_context_defined_once():
    count = SOURCE.count("def build_news_context(")

    assert count == 1, (
        f"expected exactly one build_news_context definition, found {count}"
    )
