from logging.config import fileConfig
import os

from dotenv import load_dotenv

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

from app.database.base import Base
import app.database.models


# ==========================================================
# Load Environment Variables
# ==========================================================

load_dotenv()


# ==========================================================
# Alembic Configuration
# ==========================================================

config = context.config

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError(
        "DATABASE_URL not found in .env"
    )

config.set_main_option(
    "sqlalchemy.url",
    database_url,
)


# ==========================================================
# Logging
# ==========================================================

if config.config_file_name is not None:
    fileConfig(
        config.config_file_name
    )


# ==========================================================
# SQLAlchemy Metadata
# ==========================================================

target_metadata = Base.metadata


# ==========================================================
# Schema Configuration
# ==========================================================

APPLICATION_SCHEMAS = {
    "iris_core",
    "iris_staging",
}


def include_name(
    name,
    type_,
    parent_names,
):
    """
    Only autogenerate migrations for the
    application schemas.

    PostgreSQL/PostGIS system schemas such as:

        - public
        - topology
        - tiger
        - tiger_data

    are ignored.
    """

    if type_ == "schema":
        return name in APPLICATION_SCHEMAS

    return True


# ==========================================================
# Offline Migrations
# ==========================================================

def run_migrations_offline() -> None:

    url = config.get_main_option(
        "sqlalchemy.url"
    )

    context.configure(
        url=url,
        target_metadata=target_metadata,

        include_schemas=True,
        include_name=include_name,

        literal_binds=True,

        dialect_opts={
            "paramstyle": "named"
        },

        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():

        context.run_migrations()


# ==========================================================
# Online Migrations
# ==========================================================

def run_migrations_online() -> None:

    connectable = engine_from_config(
        config.get_section(
            config.config_ini_section,
            {},
        ),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:

        context.configure(
            connection=connection,
            target_metadata=target_metadata,

            include_schemas=True,
            include_name=include_name,

            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():

            context.run_migrations()


# ==========================================================
# Run
# ==========================================================

if context.is_offline_mode():

    run_migrations_offline()

else:

    run_migrations_online()