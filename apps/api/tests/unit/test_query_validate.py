import pytest

from agah.query.validate import UnsafeQueryError, validate_sql

APPROVED = {"leave_requests", "employees", "departments"}


def test_accepts_a_select_over_approved_tables():
    sql = validate_sql(
        "SELECT e.full_name FROM leave_requests l JOIN employees e ON e.id = l.emp_id",
        approved_tables=APPROVED,
        dialect="postgres",
        limit=100,
    )
    assert "LIMIT 100" in sql.upper()


def test_rejects_a_table_that_was_never_approved():
    # A hallucinated table name must be stopped before it reaches the database,
    # and an unapproved one means no human ever verified what it contains.
    with pytest.raises(UnsafeQueryError, match="not approved"):
        validate_sql(
            "SELECT * FROM salaries_secret",
            approved_tables=APPROVED,
            dialect="postgres",
            limit=100,
        )


def test_rejects_a_write_disguised_as_a_query():
    with pytest.raises(UnsafeQueryError):
        validate_sql(
            "WITH d AS (DELETE FROM employees RETURNING *) SELECT * FROM d",
            approved_tables=APPROVED,
            dialect="postgres",
            limit=100,
        )


def test_rejects_stacked_statements():
    with pytest.raises(UnsafeQueryError):
        validate_sql(
            "SELECT 1; DROP TABLE employees",
            approved_tables=APPROVED,
            dialect="postgres",
            limit=100,
        )


def test_allows_cte_names_that_are_not_real_tables():
    # A CTE alias is not a table reference and must not trip the approval check.
    sql = validate_sql(
        "WITH recent AS (SELECT * FROM leave_requests) SELECT * FROM recent",
        approved_tables=APPROVED,
        dialect="postgres",
        limit=50,
    )
    assert "recent" in sql


def test_allows_schema_qualified_approved_tables():
    sql = validate_sql(
        "SELECT * FROM public.employees",
        approved_tables=APPROVED,
        dialect="postgres",
        limit=10,
    )
    assert "employees" in sql


def test_tightens_a_limit_the_model_chose_itself():
    sql = validate_sql(
        "SELECT * FROM employees LIMIT 100000",
        approved_tables=APPROVED,
        dialect="postgres",
        limit=100,
    )
    assert "100000" not in sql
