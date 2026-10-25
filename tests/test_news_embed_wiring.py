"""
`news-embed` must be a registered, reachable command — but deliberately
absent from every phase, so `main.py all` stays free and offline-safe.
It makes paid OpenAI calls; running it is an explicit choice, not a side
effect of running the pipeline.

The deliberate inverse of the Issue 1 / Issue 7 wiring tests, which guard
a command being reachable at all.
"""

from app.runners.pipeline_runner import PipelineRunner


PHASE_4_STEPS = (
    "news",
    "entity_matcher",
    "news_load",
    "news_intelligence",
    "land_values",
    "power_infrastructure",
    "osm_infrastructure",
    "news_embed",
)


def test_news_embed_is_an_available_command():
    assert "news-embed" in PipelineRunner().commands


def test_phase_4_never_calls_news_embed(monkeypatch):
    runner = PipelineRunner()

    calls: list[str] = []

    def recorder(step: str):
        return lambda: calls.append(step)

    for step in PHASE_4_STEPS:
        monkeypatch.setattr(runner, step, recorder(step), raising=False)

    runner.phase_4()

    assert "news_embed" not in calls, (
        "news-embed must stay out of phase_4 — it is a paid step, called "
        "only when the user explicitly runs `main.py news-embed`"
    )

    assert "news" in calls, "sanity check: phase_4 still ran its real steps"
