"""Stage 3: nothing a model wrote reaches the database unchecked.

Layers on top of the S1 read-only guard: every table named in the statement must be
one a human approved. A hallucinated table is rejected before execution, and an
unapproved one means nobody ever verified what it holds.
"""

import sqlglot
from sqlglot import exp

from jamasp.safety.readonly import UnsafeQueryError, apply_limit, assert_readonly

__all__ = ["UnsafeQueryError", "referenced_tables", "validate_sql"]


def referenced_tables(sql: str, dialect: str) -> set[str]:
    """Real table references only: CTE aliases are names the query defines itself."""
    statement = sqlglot.parse_one(sql, read=dialect)

    cte_names = {
        cte.alias_or_name.lower()
        for cte in statement.find_all(exp.CTE)
        if cte.alias_or_name
    }

    tables: set[str] = set()
    for table in statement.find_all(exp.Table):
        name = (table.name or "").lower()
        if name and name not in cte_names:
            tables.add(name)
    return tables


def validate_sql(
    sql: str,
    approved_tables: set[str],
    dialect: str,
    limit: int,
) -> str:
    assert_readonly(sql, dialect)

    approved = {name.lower() for name in approved_tables}
    used = referenced_tables(sql, dialect)
    unknown = sorted(used - approved)
    if unknown:
        raise UnsafeQueryError(
            f"query references tables that are not approved: {', '.join(unknown)}"
        )

    return apply_limit(sql, dialect, limit)
