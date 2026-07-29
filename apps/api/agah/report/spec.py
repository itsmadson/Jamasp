"""ReportSpec: what the AI proposes, and what the rules allow.

The model chooses blocks; this module decides whether its choice matches the shape
of the data. Form rules are not judgement calls — a pie chart over a time series is
wrong regardless of how confidently it was proposed — so they live in code.
"""

from typing import Any

SCHEMA_VERSION = "1.0"
BLOCK_TYPES = {"kpi", "bar", "line", "table"}

# Above this a chart stops communicating and the table is the honest presentation.
MAX_CHART_ROWS = 200
# Above this a categorical axis is unreadable.
MAX_CATEGORIES = 40

Column = dict[str, str]


def _by_type(columns: list[Column], kind: str) -> list[Column]:
    return [column for column in columns if column.get("type") == kind]


def suggest_block_type(columns: list[Column], row_count: int) -> str:
    numeric = _by_type(columns, "number")
    temporal = _by_type(columns, "temporal")
    textual = _by_type(columns, "text")

    if not numeric:
        return "table"
    if row_count == 1 and len(columns) == 1:
        return "kpi"
    if row_count > MAX_CHART_ROWS:
        return "table"
    if temporal:
        return "line"
    if textual and row_count <= MAX_CATEGORIES:
        return "bar"
    return "table"


def _bilingual(value: Any, fallback: str = "") -> dict[str, str]:
    if isinstance(value, dict):
        return {"fa": str(value.get("fa") or fallback), "en": str(value.get("en") or fallback)}
    text = str(value or fallback)
    return {"fa": text, "en": text}


def _table_block(title: dict[str, str], columns: list[Column]) -> dict[str, Any]:
    return {
        "type": "table",
        "title": title,
        "columns": [column["name"] for column in columns],
    }


def fallback_spec(
    title: dict[str, str], columns: list[Column], row_count: int
) -> dict[str, Any]:
    """The data always reaches the user, even when every proposed block was unusable."""
    return {
        "schema_version": SCHEMA_VERSION,
        "title": _bilingual(title),
        "summary": {"fa": "", "en": ""},
        "blocks": [] if not columns else [_table_block(_bilingual(title), columns)],
    }


def _valid_block(
    block: Any, names: set[str], columns: list[Column], row_count: int
) -> dict[str, Any] | None:
    if not isinstance(block, dict):
        return None

    title = _bilingual(block.get("title"))
    kind = block.get("type")

    if kind == "table":
        wanted = [name for name in (block.get("columns") or []) if name in names]
        if not wanted:
            wanted = [column["name"] for column in columns]
        return {"type": "table", "title": title, "columns": wanted}

    if kind == "kpi":
        column = block.get("column")
        if column not in names:
            return None
        return {
            "type": "kpi",
            "title": title,
            "label": _bilingual(block.get("label"), title["en"]),
            "column": column,
            "aggregate": block.get("aggregate") if block.get("aggregate") in
            {"sum", "avg", "min", "max", "count", "first"} else "first",
            "unit": block.get("unit"),
        }

    if kind in {"bar", "line"}:
        x, y = block.get("x"), block.get("y")
        if x not in names or y not in names:
            return None
        series = block.get("series")
        # An unknown series column is dropped rather than making the block invalid:
        # the chart is still meaningful without the split.
        return {
            "type": kind,
            "title": title,
            "x": x,
            "y": y,
            "series": series if series in names else None,
        }

    # An unrecognised type is replaced by whatever the data actually supports.
    suggested = suggest_block_type(columns, row_count)
    if suggested == "table":
        return _table_block(title, columns)
    return _valid_block({**block, "type": suggested}, names, columns, row_count)


def coerce_spec(
    spec: Any, columns: list[Column], row_count: int
) -> dict[str, Any]:
    spec = spec if isinstance(spec, dict) else {}
    title = _bilingual(spec.get("title"), "Report")
    names = {column["name"] for column in columns}

    if not columns:
        # Nothing to draw, but the title and an explicit empty state still tell the
        # user their query ran.
        return {
            "schema_version": SCHEMA_VERSION,
            "title": title,
            "summary": _bilingual(spec.get("summary")),
            "blocks": [],
        }

    blocks: list[dict[str, Any]] = []
    for block in spec.get("blocks") or []:
        valid = _valid_block(block, names, columns, row_count)
        if valid is not None:
            blocks.append(valid)

    if not blocks:
        blocks = [_table_block(title, columns)]

    return {
        "schema_version": SCHEMA_VERSION,
        "title": title,
        "summary": _bilingual(spec.get("summary")),
        "blocks": blocks,
    }
