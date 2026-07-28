import pytest

from agah.safety.readonly import UnsafeQueryError, apply_limit, assert_readonly

SAFE = [
    "SELECT * FROM employees",
    "SELECT e.id, d.name FROM employees e JOIN departments d ON d.id = e.dept_id",
    "WITH recent AS (SELECT * FROM leave_requests WHERE created_at > now()) SELECT * FROM recent",
    "SELECT count(*) FROM orders WHERE status = 3",
]

UNSAFE = [
    "DELETE FROM employees",
    "UPDATE employees SET salary = 0",
    "INSERT INTO employees (name) VALUES ('x')",
    "DROP TABLE employees",
    "TRUNCATE employees",
    "ALTER TABLE employees ADD COLUMN x int",
    "CREATE TABLE t (id int)",
    "GRANT ALL ON employees TO public",
    "SELECT 1; DROP TABLE employees",
    "WITH d AS (DELETE FROM employees RETURNING *) SELECT * FROM d",
    "SELECT * FROM employees /* */ ; TRUNCATE employees",
    "COPY employees TO '/tmp/out.csv'",
    "SELECT pg_sleep(100)",
]


@pytest.mark.parametrize("sql", SAFE)
def test_safe_queries_pass(sql):
    assert_readonly(sql, "postgres")


@pytest.mark.parametrize("sql", UNSAFE)
def test_unsafe_queries_rejected(sql):
    with pytest.raises(UnsafeQueryError):
        assert_readonly(sql, "postgres")


def test_apply_limit_wraps_query():
    out = apply_limit("SELECT * FROM employees", "postgres", 100)
    assert "LIMIT 100" in out.upper()


def test_apply_limit_tightens_existing_limit():
    out = apply_limit("SELECT * FROM employees LIMIT 5000", "postgres", 100)
    assert "5000" not in out
