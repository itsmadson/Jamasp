"""The SQL each engine actually gets sent.

No server needed: quoting, casts and how a row bound is spelled are decided
locally, and they are where a multi-dialect adapter goes wrong. The MySQL and
Postgres adapters are additionally exercised against real servers; this file is the
only coverage SQL Server has without an ODBC driver installed, so it carries more
weight there.
"""

import pytest

from jamasp.adapters.dsn import InvalidDsnError, normalise_dsn
from jamasp.adapters.mssql import MssqlAdapter
from jamasp.adapters.mysql import MySQLAdapter
from jamasp.adapters.postgres import PostgresAdapter
from jamasp.pipeline.snapshot import ColumnInfo, EntitySnapshot
from jamasp.safety.readonly import apply_limit

ADAPTERS = {
    "postgres": (PostgresAdapter, "postgresql://u:p@h:5432/db"),
    "mysql": (MySQLAdapter, "mysql://u:p@h:3306/db"),
    "mssql": (MssqlAdapter, "mssql://u:p@h:1433/db"),
}


def build(kind: str):
    adapter_class, dsn = ADAPTERS[kind]
    return adapter_class(dsn)


ENTITY = EntitySnapshot(
    kind="table",
    schema_name="hr",
    name="order",
    columns=(ColumnInfo(name="select", data_type="text", nullable=True, is_pk=False, ordinal=0),),
    foreign_keys=(),
    unique_constraints=(),
    indexes=(),
    comment=None,
)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("postgres", '"hr"."order"'), ("mysql", "`hr`.`order`"), ("mssql", "[hr].[order]")],
)
def test_each_engine_quotes_identifiers_its_own_way(kind, expected):
    """A table called "order" is only reachable with the right quoting."""
    assert build(kind).qualify(ENTITY) == expected


@pytest.mark.parametrize(
    ("kind", "fragment"),
    [("postgres", "::text"), ("mysql", "AS CHAR"), ("mssql", "AS NVARCHAR")],
)
def test_each_engine_casts_to_text_its_own_way(kind, fragment):
    """CAST(x AS VARCHAR) is a syntax error on MySQL, and ::text is Postgres-only."""
    assert fragment in build(kind).cast_text("col")


def test_postgres_uses_filter_and_the_others_use_case():
    # FILTER reads better and only Postgres has it.
    assert "FILTER" in build("postgres").count_where("x IS NULL")
    assert "CASE WHEN" in build("mysql").count_where("x IS NULL")
    assert "CASE WHEN" in build("mssql").count_where("x IS NULL")


def test_a_quote_inside_an_identifier_cannot_break_out():
    assert build("postgres").quote('a"b') == '"a""b"'
    assert build("mysql").quote("a`b") == "`a``b`"
    assert build("mssql").quote("a]b") == "[a]]b]"


def test_sql_server_bounds_rows_with_top_because_it_has_no_limit():
    bounded = apply_limit("SELECT id FROM employees", "tsql", 10)
    assert "TOP" in bounded.upper()
    assert "LIMIT" not in bounded.upper()


def test_mysql_and_postgres_bound_rows_with_limit():
    for dialect in ("mysql", "postgres"):
        assert "LIMIT" in apply_limit("SELECT id FROM employees", dialect, 10).upper()


@pytest.mark.parametrize(
    ("kind", "given", "expected_scheme"),
    [
        ("postgres", "postgres://u:p@h/db", "postgresql+asyncpg://"),
        ("postgres", "postgresql://u:p@h/db", "postgresql+asyncpg://"),
        ("mysql", "mysql://u:p@h/db", "mysql+asyncmy://"),
        ("mysql", "mariadb://u:p@h/db", "mysql+asyncmy://"),
        ("mysql", "mysql+pymysql://u:p@h/db", "mysql+asyncmy://"),
        ("mssql", "sqlserver://u:p@h/db", "mssql+aioodbc://"),
    ],
)
def test_whatever_the_admin_pasted_becomes_the_async_driver_form(kind, given, expected_scheme):
    assert normalise_dsn(given, kind).startswith(expected_scheme)


def test_a_percent_encoded_password_survives_normalisation():
    """The password in the field is often encoded; re-encoding it breaks the login."""
    dsn = normalise_dsn("postgresql://user:p%40ss%40word@host:5432/db", "postgres")
    assert "p%40ss%40word" in dsn


def test_sql_server_is_told_which_driver_to_use():
    """pyodbc cannot connect without a driver name and says nothing useful about why."""
    assert "driver=" in normalise_dsn("mssql://u:p@h/db", "mssql").lower()


def test_an_explicit_driver_choice_is_left_alone():
    dsn = normalise_dsn("mssql+aioodbc://u:p@h/db?driver=FreeTDS", "mssql")
    assert dsn.count("driver=") == 1
    assert "FreeTDS" in dsn


def test_a_jdbc_url_is_refused_with_the_reason():
    with pytest.raises(InvalidDsnError, match="jdbc"):
        normalise_dsn("jdbc:mysql://host:3306/db", "mysql")


def test_a_postgres_string_given_to_a_mysql_source_is_refused():
    """Silently connecting to the wrong engine would be worse than an error."""
    with pytest.raises(InvalidDsnError, match="MySQL"):
        normalise_dsn("postgresql://u:p@h/db", "mysql")


def test_every_adapter_declares_a_dialect_its_safety_layer_knows():
    """sqlglot must recognise the name, or reads go unbounded and unchecked."""
    for kind in ADAPTERS:
        adapter = build(kind)
        assert apply_limit("SELECT 1 FROM t", adapter.dialect, 5)
