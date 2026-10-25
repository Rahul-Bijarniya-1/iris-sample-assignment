from app.commands.embed_news_command import EmbedNewsCommand
from app.database.session import SessionLocal


def run():
    """
    Translate and embed news articles into pgvector.

    Deliberately not wired into any pipeline phase — see
    PipelineRunner.news_embed. Always uses the live database directly;
    there is no staged-run input file to read.
    """

    session = SessionLocal()

    try:

        command = EmbedNewsCommand(
            session
        )

        return command.execute()

    finally:

        session.close()
