"""ReportSpec: what the AI proposes, and what the rules allow.

The model chooses blocks; this module decides whether its choice matches the shape
of the data. Form rules are not judgement calls — a pie chart over a time series is
wrong regardless of how confidently it was proposed — so they live in code.

A report holds several datasets, each from its own query. Every block names the one
dataset it draws from, and is checked against that dataset's columns alone. A block
whose columns belong to a different dataset is dropped, because rendering it would
mean plotting one panel's rows on another panel's axes.
"""

from typing import Any

from jamasp.report.insights import narrative_for

SCHEMA_VERSION = "2.0"
BLOCK_TYPES = {"kpi", "bar", "line", "area", "pie", "donut", "radar", "table"}
AGGREGATES = {"sum", "avg", "min", "max", "count", "first"}

# Above this a chart stops communicating and the table is the honest presentation.
MAX_CHART_ROWS = 200
# Above this a categorical axis is unreadable.
MAX_CATEGORIES = 40
# A share-of-whole chart with more slices than this is a colour wheel, not a figure.
MAX_SLICES = 8
# A radar with too few axes is a triangle; with too many it is unreadable.
MIN_RADAR_AXES = 3
MAX_RADAR_AXES = 8
# Beyond this a table block is paged rather than dumped whole.
TABLE_THRESHOLD = 8

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


def default_span(kind: str) -> int:
    if kind in {"kpi", "pie", "donut", "radar"}:
        return 1
    if kind == "table":
        return 3
    return 2


def _bilingual(value: Any, fallback: str = "") -> dict[str, str]:
    if isinstance(value, dict):
        return {"fa": str(value.get("fa") or fallback), "en": str(value.get("en") or fallback)}
    text = str(value or fallback)
    return {"fa": text, "en": text}


def _span(value: Any, kind: str) -> int:
    try:
        span = int(value)
    except (TypeError, ValueError):
        return default_span(kind)
    return span if span in {1, 2, 3} else default_span(kind)


def _table_block(title: dict[str, str], columns: list[Column], dataset: str) -> dict[str, Any]:
    return {
        "type": "table",
        "title": title,
        "dataset": dataset,
        "span": 3,
        "columns": [column["name"] for column in columns],
    }


def fallback_spec(title: dict[str, str], datasets: list[dict[str, Any]]) -> dict[str, Any]:
    """The data always reaches the user, even when every proposed block was unusable.

    One table per dataset: unstyled, but complete and correctly separated.
    """
    blocks = [
        _table_block(
            _bilingual(dataset.get("question"), title.get("en", "")),
            dataset.get("columns") or [],
            dataset["key"],
        )
        for dataset in datasets
        if dataset.get("columns")
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "title": _bilingual(title),
        "summary": {"fa": "", "en": ""},
        "findings": [],
        "blocks": _enrich(blocks, datasets),
    }


def _valid_block(
    block: Any, dataset_key: str, columns: list[Column], row_count: int
) -> dict[str, Any] | None:
    if not isinstance(block, dict):
        return None

    names = {column["name"] for column in columns}
    title = _bilingual(block.get("title"))
    kind = block.get("type")
    common: dict[str, Any] = {"title": title, "dataset": dataset_key}
    narrative = block.get("narrative")
    if isinstance(narrative, dict) and (narrative.get("fa") or narrative.get("en")):
        common["narrative"] = _bilingual(narrative)

    if kind == "table":
        wanted = [name for name in (block.get("columns") or []) if name in names]
        if not wanted:
            wanted = [column["name"] for column in columns]
        return {
            **common,
            "type": "table",
            "span": _span(block.get("span"), "table"),
            "columns": wanted,
        }

    if kind == "kpi":
        column = block.get("column")
        if column not in names:
            return None
        return {
            **common,
            "type": "kpi",
            "span": _span(block.get("span"), "kpi"),
            "label": _bilingual(block.get("label"), title["en"]),
            "column": column,
            "aggregate": block.get("aggregate")
            if block.get("aggregate") in AGGREGATES
            else "first",
            "unit": block.get("unit"),
        }

    if kind in {"bar", "line", "area"}:
        x, y = block.get("x"), block.get("y")
        if x not in names or y not in names:
            return None
        series = block.get("series")
        # An unknown series column is dropped rather than making the block invalid:
        # the chart is still meaningful without the split.
        return {
            **common,
            "type": kind,
            "span": _span(block.get("span"), kind),
            "x": x,
            "y": y,
            "series": series if series in names and series not in {x, y} else None,
        }

    if kind == "radar":
        x, y = block.get("x"), block.get("y")
        if x not in names or y not in names:
            return None
        # Outside this range the shape stops being the point, so the honest form is
        # a bar: ranking without pretending the profile means something.
        if not (MIN_RADAR_AXES <= row_count <= MAX_RADAR_AXES):
            return _valid_block({**block, "type": "bar"}, dataset_key, columns, row_count)
        return {
            **common,
            "type": "radar",
            "span": _span(block.get("span"), "radar"),
            "x": x,
            "y": y,
            "series": None,
        }

    if kind in {"pie", "donut"}:
        x, y = block.get("x"), block.get("y")
        if x not in names or y not in names:
            return None
        # A share of a whole only reads as one when there are few enough slices, and
        # never over time — a timeline has no whole to be a share of.
        if row_count > MAX_SLICES or _by_type(columns, "temporal"):
            return _valid_block({**block, "type": "bar"}, dataset_key, columns, row_count)
        return {
            **common,
            "type": kind,
            "span": _span(block.get("span"), kind),
            "x": x,
            "y": y,
            "series": None,
        }

    # An unrecognised type is replaced by whatever the data actually supports.
    suggested = suggest_block_type(columns, row_count)
    if suggested == "table":
        return _table_block(title, columns, dataset_key)
    return _valid_block({**block, "type": suggested}, dataset_key, columns, row_count)


def _findings(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    findings = []
    for item in value[:6]:
        text = _bilingual(item)
        if text["fa"] or text["en"]:
            findings.append(text)
    return findings


def _headline(dataset: dict[str, Any]) -> dict[str, Any] | None:
    """A KPI the data definitely supports, for when the model proposed none."""
    facts = dataset.get("facts") or {}
    measure = facts.get("measure")
    if not measure:
        return None
    label = _bilingual(dataset.get("question") or dataset["key"])
    return {
        "type": "kpi",
        "title": label,
        "dataset": dataset["key"],
        "span": 1,
        "label": label,
        "column": measure,
        "aggregate": "sum",
        "unit": None,
    }


def _enrich(
    blocks: list[dict[str, Any]], datasets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Guarantee the page opens with numbers and that long panels stay reachable.

    The prompt asks for a KPI row and a table for long panels. A model that skips
    them leaves a page that reads as a bare stack of charts, which is a layout
    failure the reader pays for — so the floor is enforced here rather than hoped
    for. Anything the model did provide is left alone.
    """
    usable = [dataset for dataset in datasets if dataset.get("columns")]
    by_key = {dataset["key"]: dataset for dataset in usable}

    kpis = [block for block in blocks if block["type"] == "kpi"]
    rest = [block for block in blocks if block["type"] != "kpi"]

    if not kpis:
        kpis = [
            headline
            for headline in (_headline(dataset) for dataset in usable[:4])
            if headline is not None
        ]

    # A long panel with no table means its detail is only in the collapsed section.
    tabled = {block["dataset"] for block in rest if block["type"] == "table"}
    for dataset in usable:
        if dataset["key"] in tabled:
            continue
        if dataset.get("row_count", 0) > TABLE_THRESHOLD:
            rest.append(
                _table_block(
                    _bilingual(dataset.get("question") or dataset["key"]),
                    dataset["columns"],
                    dataset["key"],
                )
            )

    # KPIs first: the page should open with the numbers, not with a chart.
    ordered = kpis + rest

    # Narrative is the reader's floor — a chart with no words makes them do the
    # reading. Computed facts fill any block the model left silent.
    for block in ordered:
        if block.get("narrative"):
            continue
        dataset = by_key.get(block["dataset"])
        if dataset and dataset.get("facts"):
            block["narrative"] = narrative_for(dataset["facts"])

    return ordered


def coerce_spec(spec: Any, datasets: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate proposed blocks against the dataset each one claims to draw from."""
    spec = spec if isinstance(spec, dict) else {}
    title = _bilingual(spec.get("title"), "Report")
    by_key = {dataset["key"]: dataset for dataset in datasets}
    usable = [dataset for dataset in datasets if dataset.get("columns")]

    if not usable:
        # Nothing to draw, but the title and an explicit empty state still tell the
        # user their questions ran.
        return {
            "schema_version": SCHEMA_VERSION,
            "title": title,
            "summary": _bilingual(spec.get("summary")),
            "findings": [],
            "blocks": [],
        }

    only_key = usable[0]["key"] if len(usable) == 1 else None

    blocks: list[dict[str, Any]] = []
    for block in spec.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        # With a single dataset there is nothing to confuse, so an omitted key is
        # filled in. With several, an unnamed or unknown dataset is a real error:
        # guessing would risk drawing one panel's numbers on another's axes.
        key = block.get("dataset") or only_key
        dataset = by_key.get(key) if key else None
        if dataset is None or not dataset.get("columns"):
            continue
        valid = _valid_block(
            block, dataset["key"], dataset["columns"], dataset.get("row_count", 0)
        )
        if valid is not None:
            blocks.append(valid)

    # Any dataset the model ignored still gets shown: the user asked for it.
    covered = {block["dataset"] for block in blocks}
    for dataset in usable:
        if dataset["key"] not in covered:
            blocks.append(
                _table_block(
                    _bilingual(dataset.get("question"), title["en"]),
                    dataset["columns"],
                    dataset["key"],
                )
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "title": title,
        "summary": _bilingual(spec.get("summary")),
        "findings": _findings(spec.get("findings")),
        "blocks": _enrich(blocks, datasets),
    }
