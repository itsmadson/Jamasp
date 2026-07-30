import pytest

from jamasp.adapters.dsn import InvalidDsnError, normalise_postgres_dsn


@pytest.mark.parametrize(
    "given",
    [
        "postgresql://u:p@host:5432/db",
        "postgres://u:p@host:5432/db",
        "postgresql+asyncpg://u:p@host:5432/db",
    ],
)
def test_every_accepted_form_ends_up_on_the_async_driver(given):
    """A user pastes what their other tools gave them. All three forms are the
    same database, and only one of them works with an async engine."""
    assert normalise_postgres_dsn(given).startswith("postgresql+asyncpg://")


def test_a_url_encoded_password_survives_untouched():
    # Passwords with @ in them are normal and must not be re-encoded or split.
    dsn = normalise_postgres_dsn(
        "postgresql://tourism:idk%40eliot%401992@10.0.0.1:5433/tourism_db"
    )
    assert "idk%40eliot%401992" in dsn
    assert dsn.endswith("/tourism_db")


def test_a_jdbc_url_is_rejected_with_an_instruction():
    # Copying a JDBC string out of a config file is the obvious mistake to make.
    with pytest.raises(InvalidDsnError, match="jdbc"):
        normalise_postgres_dsn("jdbc:postgresql://10.0.0.1:5433/tourism_db")


def test_a_synchronous_driver_is_swapped_rather_than_refused():
    assert normalise_postgres_dsn("postgresql+psycopg2://u:p@h/db").startswith(
        "postgresql+asyncpg://"
    )


def test_a_mysql_url_is_rejected_by_the_postgres_adapter():
    with pytest.raises(InvalidDsnError):
        normalise_postgres_dsn("mysql://u:p@h/db")


def test_nonsense_is_rejected_with_a_readable_message():
    with pytest.raises(InvalidDsnError):
        normalise_postgres_dsn("just some text")
