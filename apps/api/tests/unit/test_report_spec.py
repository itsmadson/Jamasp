from agah.report.spec import coerce_spec, fallback_spec, suggest_block_type

COLUMNS_CATEGORICAL = [
    {"name": "status_label", "type": "text"},
    {"name": "request_count", "type": "number"},
]
COLUMNS_TEMPORAL = [
    {"name": "month", "type": "temporal"},
    {"name": "total", "type": "number"},
]
COLUMNS_SINGLE = [{"name": "total", "type": "number"}]


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
    result = coerce_spec(spec, COLUMNS_CATEGORICAL, row_count=3)
    # One bad block must not cost the whole page.
    assert len(result["blocks"]) == 1
    assert result["blocks"][0]["x"] == "status_label"


def test_coerce_replaces_an_unknown_block_type():
    spec = {
        "title": {"fa": "گزارش", "en": "Report"},
        "summary": {"fa": "", "en": ""},
        "blocks": [
            {"type": "pie", "title": {"fa": "الف", "en": "a"},
             "x": "status_label", "y": "request_count"},
        ],
    }
    result = coerce_spec(spec, COLUMNS_CATEGORICAL, row_count=3)
    # A chart type the renderer cannot draw is worse than the right one.
    assert result["blocks"][0]["type"] == "bar"


def test_coerce_falls_back_to_a_table_when_every_block_is_invalid():
    spec = {
        "title": {"fa": "گزارش", "en": "Report"},
        "summary": {"fa": "", "en": ""},
        "blocks": [
            {"type": "bar", "title": {"fa": "الف", "en": "a"},
             "x": "nope", "y": "also_nope"},
        ],
    }
    result = coerce_spec(spec, COLUMNS_CATEGORICAL, row_count=3)
    assert [block["type"] for block in result["blocks"]] == ["table"]
    assert result["blocks"][0]["columns"] == ["status_label", "request_count"]


def test_coerce_keeps_a_bilingual_title():
    spec = {
        "title": {"fa": "مرخصی‌های تاییدشده", "en": "Approved leave"},
        "summary": {"fa": "خلاصه", "en": "Summary"},
        "blocks": [],
    }
    result = coerce_spec(spec, COLUMNS_CATEGORICAL, row_count=3)
    assert result["title"]["fa"] == "مرخصی‌های تاییدشده"
    assert result["summary"]["en"] == "Summary"


def test_fallback_spec_always_renders_the_data():
    result = fallback_spec(
        {"fa": "گزارش", "en": "Report"}, COLUMNS_CATEGORICAL, row_count=3
    )
    assert result["blocks"][0]["type"] == "table"
    assert result["blocks"][0]["columns"] == ["status_label", "request_count"]


def test_empty_result_still_produces_a_renderable_spec():
    result = coerce_spec(
        {"title": {"fa": "خالی", "en": "Empty"}, "summary": {"fa": "", "en": ""},
         "blocks": [{"type": "bar", "title": {"fa": "x", "en": "x"}, "x": "a", "y": "b"}]},
        [],
        row_count=0,
    )
    # A blank page tells the user nothing about whether the query ran.
    assert result["blocks"] == []
    assert result["title"]["en"] == "Empty"
