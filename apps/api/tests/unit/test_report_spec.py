from jamasp.report.spec import coerce_spec, fallback_spec, suggest_block_type

COLUMNS_CATEGORICAL = [
    {"name": "status_label", "type": "text"},
    {"name": "request_count", "type": "number"},
]
COLUMNS_TEMPORAL = [
    {"name": "month", "type": "temporal"},
    {"name": "total", "type": "number"},
]
COLUMNS_SINGLE = [{"name": "total", "type": "number"}]


def dataset(key="main", columns=None, row_count=3, question="q"):
    return {
        "key": key,
        "question": question,
        "columns": COLUMNS_CATEGORICAL if columns is None else columns,
        "row_count": row_count,
    }


def test_temporal_plus_numeric_suggests_a_line():
    assert suggest_block_type(COLUMNS_TEMPORAL, row_count=12) == "line"


def test_category_plus_numeric_suggests_a_bar():
    assert suggest_block_type(COLUMNS_CATEGORICAL, row_count=3) == "bar"


def test_single_numeric_row_suggests_a_kpi():
    assert suggest_block_type(COLUMNS_SINGLE, row_count=1) == "kpi"


def test_many_rows_fall_back_to_a_table():
    # A 500-bar chart is unreadable; the table is the honest presentation.
    assert suggest_block_type(COLUMNS_CATEGORICAL, row_count=500) == "table"


def test_text_only_columns_fall_back_to_a_table():
    columns = [{"name": "full_name", "type": "text"}, {"name": "city", "type": "text"}]
    assert suggest_block_type(columns, row_count=10) == "table"


def test_coerce_drops_a_block_naming_a_column_that_does_not_exist():
    spec = {
        "title": {"fa": "گزارش", "en": "Report"},
        "summary": {"fa": "", "en": ""},
        "blocks": [
            {"type": "bar", "title": {"fa": "الف", "en": "a"},
             "x": "status_label", "y": "request_count"},
            {"type": "bar", "title": {"fa": "ب", "en": "b"},
             "x": "invented_column", "y": "request_count"},
        ],
    }
    result = coerce_spec(spec, [dataset()])
    # One bad block must not cost the whole page.
    assert len(result["blocks"]) == 1
    assert result["blocks"][0]["x"] == "status_label"


def test_coerce_replaces_an_unknown_block_type():
    spec = {
        "title": {"fa": "گزارش", "en": "Report"},
        "summary": {"fa": "", "en": ""},
        "blocks": [
            {"type": "sunburst", "title": {"fa": "الف", "en": "a"},
             "x": "status_label", "y": "request_count"},
        ],
    }
    result = coerce_spec(spec, [dataset()])
    # A chart type the renderer cannot draw is worse than the right one.
    assert result["blocks"][0]["type"] == "bar"


def test_a_pie_over_too_many_slices_becomes_a_bar():
    spec = {
        "title": {"fa": "گزارش", "en": "Report"},
        "summary": {"fa": "", "en": ""},
        "blocks": [
            {"type": "pie", "title": {"fa": "الف", "en": "a"},
             "x": "status_label", "y": "request_count"},
        ],
    }
    # Thirty slices is a colour wheel, not a share of a whole.
    result = coerce_spec(spec, [dataset(row_count=30)])
    assert result["blocks"][0]["type"] == "bar"


def test_a_pie_over_few_categories_is_kept():
    spec = {
        "title": {"fa": "گزارش", "en": "Report"},
        "summary": {"fa": "", "en": ""},
        "blocks": [
            {"type": "pie", "title": {"fa": "الف", "en": "a"},
             "x": "status_label", "y": "request_count"},
        ],
    }
    result = coerce_spec(spec, [dataset(row_count=4)])
    assert result["blocks"][0]["type"] == "pie"


def test_a_block_may_not_borrow_another_panels_columns():
    """The bug this prevents: one panel's rows drawn on another panel's axes."""
    monthly = dataset("monthly", COLUMNS_TEMPORAL, row_count=3)
    by_status = dataset("by_status", COLUMNS_CATEGORICAL, row_count=4)
    spec = {
        "title": {"fa": "گزارش", "en": "Report"},
        "summary": {"fa": "", "en": ""},
        "blocks": [
            # Claims the monthly panel but names the other panel's columns.
            {"type": "bar", "title": {"fa": "الف", "en": "a"}, "dataset": "monthly",
             "x": "status_label", "y": "request_count"},
            {"type": "line", "title": {"fa": "ب", "en": "b"}, "dataset": "monthly",
             "x": "month", "y": "total"},
        ],
    }
    result = coerce_spec(spec, [monthly, by_status])
    charts = [block for block in result["blocks"] if block["type"] != "table"]
    assert len(charts) == 1
    assert charts[0]["dataset"] == "monthly"
    # The panel the model ignored is still shown rather than silently dropped.
    assert any(block["dataset"] == "by_status" for block in result["blocks"])


def test_a_block_with_no_dataset_is_dropped_when_several_exist():
    """Guessing which panel it meant risks charting the wrong numbers."""
    spec = {
        "title": {"fa": "گزارش", "en": "Report"},
        "summary": {"fa": "", "en": ""},
        "blocks": [
            {"type": "bar", "title": {"fa": "الف", "en": "a"},
             "x": "status_label", "y": "request_count"},
        ],
    }
    result = coerce_spec(
        spec,
        [dataset("a", COLUMNS_CATEGORICAL), dataset("b", COLUMNS_TEMPORAL)],
    )
    assert all(block["type"] == "table" for block in result["blocks"])


def test_a_lone_dataset_needs_no_naming():
    spec = {
        "title": {"fa": "گزارش", "en": "Report"},
        "summary": {"fa": "", "en": ""},
        "blocks": [
            {"type": "bar", "title": {"fa": "الف", "en": "a"},
             "x": "status_label", "y": "request_count"},
        ],
    }
    result = coerce_spec(spec, [dataset()])
    assert result["blocks"][0]["dataset"] == "main"


def test_spans_are_clamped_to_the_grid():
    spec = {
        "title": {"fa": "گزارش", "en": "Report"},
        "summary": {"fa": "", "en": ""},
        "blocks": [
            {"type": "bar", "title": {"fa": "الف", "en": "a"}, "span": 9,
             "x": "status_label", "y": "request_count"},
        ],
    }
    result = coerce_spec(spec, [dataset()])
    assert result["blocks"][0]["span"] == 2


def test_coerce_falls_back_to_a_table_when_every_block_is_invalid():
    spec = {
        "title": {"fa": "گزارش", "en": "Report"},
        "summary": {"fa": "", "en": ""},
        "blocks": [
            {"type": "bar", "title": {"fa": "الف", "en": "a"},
             "x": "nope", "y": "also_nope"},
        ],
    }
    result = coerce_spec(spec, [dataset()])
    assert [block["type"] for block in result["blocks"]] == ["table"]
    assert result["blocks"][0]["columns"] == ["status_label", "request_count"]


def test_coerce_keeps_a_bilingual_title():
    spec = {
        "title": {"fa": "مرخصی‌های تاییدشده", "en": "Approved leave"},
        "summary": {"fa": "خلاصه", "en": "Summary"},
        "blocks": [],
    }
    result = coerce_spec(spec, [dataset()])
    assert result["title"]["fa"] == "مرخصی‌های تاییدشده"
    assert result["summary"]["en"] == "Summary"


def test_fallback_spec_always_renders_the_data():
    result = fallback_spec({"fa": "گزارش", "en": "Report"}, [dataset()])
    assert result["blocks"][0]["type"] == "table"
    assert result["blocks"][0]["columns"] == ["status_label", "request_count"]


def test_empty_result_still_produces_a_renderable_spec():
    result = coerce_spec(
        {"title": {"fa": "خالی", "en": "Empty"}, "summary": {"fa": "", "en": ""},
         "blocks": [{"type": "bar", "title": {"fa": "x", "en": "x"}, "x": "a", "y": "b"}]},
        [dataset(columns=[], row_count=0)],
    )
    # A blank page tells the user nothing about whether the query ran.
    assert result["blocks"] == []
    assert result["title"]["en"] == "Empty"
