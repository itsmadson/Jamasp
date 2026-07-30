"""The facts under every narrative.

A model asked to do arithmetic over sample rows will sometimes be wrong, and a
report that misstates a number is worse than one with no prose at all. So the
numbers are computed here and these tests pin them.
"""

from jamasp.report.insights import describe_panel, narrative_for

CATEGORICAL = [
    {"name": "role_label_fa", "type": "text"},
    {"name": "user_count", "type": "number"},
]
ROLE_ROWS = [
    {"role_label_fa": "مصاحبه‌کننده", "user_count": 60},
    {"role_label_fa": "موسسه", "user_count": 30},
    {"role_label_fa": "کارشناس استانی", "user_count": 15},
    {"role_label_fa": "متدرب", "user_count": 8},
]

TEMPORAL = [
    {"name": "month", "type": "temporal"},
    {"name": "user_count", "type": "number"},
]
MONTH_ROWS = [
    {"month": "2026-05", "user_count": 30},
    {"month": "2026-06", "user_count": 48},
    {"month": "2026-07", "user_count": 47},
]


def test_totals_and_leader_come_from_the_rows():
    facts = describe_panel("users by role", CATEGORICAL, ROLE_ROWS)

    assert facts["total"] == 113
    assert facts["max"] == 60
    assert facts["top"][0]["label"] == "مصاحبه‌کننده"
    # 60/113 — the share a reader would otherwise have to work out.
    assert facts["leader_share"] == 53.1
    # (60 + 30 + 15) / 113
    assert facts["top3_share"] == 92.9


def test_a_trend_records_its_direction_and_size():
    facts = describe_panel("monthly growth", TEMPORAL, MONTH_ROWS)

    assert facts["direction"] == "up"
    assert facts["first"] == 30
    assert facts["last"] == 47
    assert facts["change"] == 17
    assert facts["change_pct"] == 56.7


def test_a_period_column_typed_as_text_is_still_a_timeline():
    """Postgres date_trunc formatted with to_char arrives as text, not a date."""
    columns = [{"name": "period", "type": "text"}, {"name": "total", "type": "number"}]
    rows = [
        {"period": "2026-05", "total": 10},
        {"period": "2026-06", "total": 20},
        {"period": "2026-07", "total": 5},
    ]
    facts = describe_panel("by period", columns, rows)
    assert facts["direction"] == "down"


def test_no_numeric_column_yields_no_invented_numbers():
    columns = [{"name": "city", "type": "text"}, {"name": "province", "type": "text"}]
    facts = describe_panel("cities", columns, [{"city": "تهران", "province": "تهران"}])
    assert "total" not in facts
    assert facts["row_count"] == 1


def test_an_empty_panel_says_so_in_both_languages():
    facts = describe_panel("nothing", CATEGORICAL, [])
    text = narrative_for(facts)
    assert text["fa"] and text["en"]
    assert "یافت نشد" in text["fa"]


def test_the_narrative_states_the_computed_numbers_in_persian_digits():
    facts = describe_panel("users by role", CATEGORICAL, ROLE_ROWS)
    text = narrative_for(facts)

    # Persian prose with Latin digits reads as a half-finished translation.
    assert "۱۱۳" in text["fa"]
    assert "مصاحبه‌کننده" in text["fa"]
    assert "113" in text["en"]
    assert "%" in text["en"]


def test_the_narrative_describes_a_rise_as_a_rise():
    facts = describe_panel("monthly growth", TEMPORAL, MONTH_ROWS)
    text = narrative_for(facts)

    assert "افزایش" in text["fa"]
    assert "rose" in text["en"]


def test_a_flat_series_is_not_described_as_change():
    columns = [{"name": "month", "type": "temporal"}, {"name": "total", "type": "number"}]
    rows = [
        {"month": "2026-05", "total": 10},
        {"month": "2026-06", "total": 12},
        {"month": "2026-07", "total": 10},
    ]
    facts = describe_panel("flat", columns, rows)
    assert facts["direction"] == "flat"
    assert "تغییر" in narrative_for(facts)["fa"]


def test_non_numeric_values_in_a_numeric_column_do_not_crash_the_arithmetic():
    """A column typed number can still carry nulls or strings from a cast."""
    rows = [
        {"role_label_fa": "الف", "user_count": 5},
        {"role_label_fa": "ب", "user_count": None},
        {"role_label_fa": "ج", "user_count": "7"},
    ]
    facts = describe_panel("mixed", CATEGORICAL, rows)
    assert facts["total"] == 12
