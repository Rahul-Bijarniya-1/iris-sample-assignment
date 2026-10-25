"""AI workspace errors must not disclose internal exception details."""

import logging

from ui.components.ai import ai_panel


def test_call_ai_logs_exception_without_returning_its_details(
    monkeypatch,
    caplog,
):
    sensitive_detail = "database host internal-db.example:5432"

    class _Session:
        closed = False

        def close(self):
            self.closed = True

    session = _Session()

    monkeypatch.setattr(ai_panel, "SessionLocal", lambda: session)

    def fail_to_build_advisor(_session):
        raise RuntimeError(sensitive_detail)

    monkeypatch.setattr(
        ai_panel,
        "AIAdvisorService",
        fail_to_build_advisor,
    )

    with caplog.at_level(logging.ERROR, logger=ai_panel.__name__):
        response, trace, citations = ai_panel._call_ai(
            question="Any news?",
            facility_id=None,
        )

    assert response == "AI unavailable right now. Please try again later."
    assert sensitive_detail not in response
    assert sensitive_detail in caplog.text
    assert trace is None
    assert citations is None
    assert session.closed is True
