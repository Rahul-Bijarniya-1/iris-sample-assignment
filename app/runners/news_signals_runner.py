from app.commands.extract_news_signals_command import (
    ExtractNewsSignalsCommand,
)
from app.database.session import SessionLocal


def run():
    """
    Extract structured signals (OpenAIExtractor) for every news article
    and load them into news_signals.

    Deliberately not wired into any pipeline phase — see
    PipelineRunner.news_signals. Makes paid OpenAI calls; operates
    directly on the live database, same as news-embed.
    """

    session = SessionLocal()

    try:

        command = ExtractNewsSignalsCommand(
            session
        )

        return command.execute()

    finally:

        session.close()
