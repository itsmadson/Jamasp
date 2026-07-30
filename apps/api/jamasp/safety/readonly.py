"""Read-only enforcement for every statement جاماسپ sends to a customer database.

Layer 2 of the four described in the design spec §8. String matching is never used:
the statement is parsed into an AST and anything not provably a single SELECT is
rejected. Unrecognized syntax is rejected rather than allowed.
"""

import sqlglot
from sqlglot import exp

WRITE_EXPRESSIONS: tuple[type[exp.Expression], ...] = tuple(
    node
    for node in (
        getattr(exp, name, None)
        for name in (
            "Insert", "Update", "Delete", "Drop", "Create", "Alter", "TruncateTable",
            "Grant", "Merge", "Copy", "Command", "Set", "Analyze",
        )
    )
    if node is not None
)

BANNED_FUNCTIONS = {"pg_sleep", "dblink", "pg_read_file", "lo_import", "lo_export"}


class UnsafeQueryError(Exception):
    pass


def assert_readonly(sql: str, dialect: str) -> None:
    try:
        parsed = sqlglot.parse(sql, read=dialect)
    except Exception as exc:
        raise UnsafeQueryError(f"unparseable SQL: {exc}") from exc

    statements = [statement for statement in parsed if statement is not None]
    if len(statements) != 1:
        raise UnsafeQueryError(f"expected exactly one statement, got {len(statements)}")

    statement = statements[0]
    if not isinstance(statement, exp.Select | exp.Union | exp.Subquery):
        raise UnsafeQueryError(f"only SELECT is permitted, got {type(statement).__name__}")

    for node in statement.walk():
        if isinstance(node, WRITE_EXPRESSIONS):
            raise UnsafeQueryError(f"write operation not permitted: {type(node).__name__}")
        if isinstance(node, exp.Func):
            # Anonymous.sql_name() is the literal "ANONYMOUS"; the real name is .name.
            name = node.name if isinstance(node, exp.Anonymous) else node.sql_name()
            if (name or "").lower() in BANNED_FUNCTIONS:
                raise UnsafeQueryError(f"banned function: {name}")


def apply_limit(sql: str, dialect: str, limit: int) -> str:
    statement = sqlglot.parse_one(sql, read=dialect)
    return statement.limit(limit).sql(dialect=dialect)
