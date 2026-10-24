"""
Database tests must follow the project's own configuration.

The scratch-database fixtures originally hardcoded localhost:5433, which is
this machine's Postgres.app port. On a default 5432 install every database
test would skip rather than run, silently disabling the migration regression
test, so the server details are derived from DATABASE_URL instead.
"""


def test_params_come_from_the_url(server_params_from_url):
    params = server_params_from_url(
        "postgresql://postgres:postgres@localhost:5433/nrw_dc_bi"
    )

    assert params == {
        "host": "localhost",
        "port": 5433,
        "user": "postgres",
        "password": "postgres",
    }


def test_a_non_default_server_is_respected(server_params_from_url):
    params = server_params_from_url(
        "postgresql://iris:secret@db.internal:6000/nrw_dc_bi"
    )

    assert params["host"] == "db.internal"
    assert params["port"] == 6000
    assert params["user"] == "iris"
    assert params["password"] == "secret"


def test_percent_encoded_credentials_are_decoded(server_params_from_url):
    """
    A password containing reserved characters is percent-encoded in a URL.
    """

    params = server_params_from_url(
        "postgresql://us%40er:p%40ss%2Fword@localhost:5432/nrw_dc_bi"
    )

    assert params["user"] == "us@er"
    assert params["password"] == "p@ss/word"


def test_omitted_port_falls_back_to_the_postgres_default(
    server_params_from_url,
):
    params = server_params_from_url("postgresql://postgres@localhost/x")

    assert params["port"] == 5432


def test_no_url_means_no_server(server_params_from_url):
    """
    Without DATABASE_URL there is nothing to connect to, and the database
    fixtures skip rather than guessing a port.
    """

    assert server_params_from_url(None) is None
    assert server_params_from_url("") is None
