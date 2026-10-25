"""
`news-signals` must be a registered, reachable command — but
deliberately absent from every phase, same reasoning as news-embed
(test_news_embed_wiring.py): it makes paid OpenAI calls, so running it
is an explicit choice, never a side effect of `main.py all`.
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
    "news_signals",
)


def test_news_signals_is_an_available_command():
    assert "news-signals" in PipelineRunner().commands


def test_phase_4_never_calls_news_signals(monkeypatch):
    runner = PipelineRunner()

    calls: list[str] = []

    def recorder(step: str):
        return lambda: calls.append(step)

    for step in PHASE_4_STEPS:
        monkeypatch.setattr(runner, step, recorder(step), raising=False)

    runner.phase_4()

    assert "news_signals" not in calls, (
        "news-signals must stay out of phase_4 — it is a paid step"
    )
