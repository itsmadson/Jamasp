"""Read a panel's rows and say what is in them.

Two jobs. The findings become the narrative under each chart, so a reader gets the
point without decoding the axes themselves. And they go into the design prompt, so
the model lays out a report knowing which panel has a clear leader, which is flat,
and which is too long to chart — it stops guessing from five sample rows.

Computed, not generated: "the top category holds 43%" is arithmetic, and a model
asked to do arithmetic over sample rows will sometimes be wrong. The model writes
prose; this decides the facts.
"""

from typing import Any

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _fa(value: Any) -> str:
    return str(value).translate(PERSIAN_DIGITS)


def _en(value: Any) -> str:
    return str(value)


def _numeric_columns(columns: list[dict[str, str]]) -> list[str]:
    return [column["name"] for column in columns if column.get("type") == "number"]


def _label_columns(columns: list[dict[str, str]]) -> list[str]:
    return [
        column["name"]
        for column in columns
        if column.get("type") in {"text", "temporal"}
    ]


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _round(value: float) -> int | float:
    return int(value) if float(value).is_integer() else round(value, 2)


def describe_panel(
    question: str | None,
    columns: list[dict[str, str]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Facts about one panel: totals, the leader, spread, and direction.

    Returned as plain data so the same numbers feed the prompt and the rendered
    narrative, and the two can never disagree.
    """
    facts: dict[str, Any] = {
        "row_count": len(rows),
        "question": question,
        "columns": columns,
    }
    if not rows:
        return facts

    numeric = _numeric_columns(columns)
    labels = _label_columns(columns)
    if not numeric:
        return facts

    measure = numeric[0]
    values = [value for value in (_as_number(row.get(measure)) for row in rows) if value is not None]
    if not values:
        return facts

    total = sum(values)
    facts["measure"] = measure
    facts["total"] = _round(total)
    facts["mean"] = _round(total / len(values))
    facts["max"] = _round(max(values))
    facts["min"] = _round(min(values))

    if labels:
        dimension = labels[0]
        pairs = [
            (str(row.get(dimension) or "—"), _as_number(row.get(measure)) or 0.0)
            for row in rows
        ]
        ranked = sorted(pairs, key=lambda pair: pair[1], reverse=True)
        facts["dimension"] = dimension
        facts["top"] = [
            {"label": label, "value": _round(value),
             "share": round(value / total * 100, 1) if total else 0.0}
            for label, value in ranked[:5]
        ]
        facts["distinct"] = len(pairs)

        # How concentrated it is: one dominant category is worth saying out loud, and
        # an even spread is worth saying too.
        leader = ranked[0][1] if ranked else 0
        facts["leader_share"] = round(leader / total * 100, 1) if total else 0.0
        top3 = sum(value for _, value in ranked[:3])
        facts["top3_share"] = round(top3 / total * 100, 1) if total else 0.0

    temporal = [column["name"] for column in columns if column.get("type") == "temporal"]
    if temporal or (labels and len(rows) > 2 and _looks_like_period(rows, labels[0])):
        first, last = values[0], values[-1]
        facts["first"] = _round(first)
        facts["last"] = _round(last)
        facts["change"] = _round(last - first)
        if first:
            facts["change_pct"] = round((last - first) / abs(first) * 100, 1)
        facts["direction"] = "up" if last > first else "down" if last < first else "flat"

    return facts


def _looks_like_period(rows: list[dict[str, Any]], column: str) -> bool:
    """A period column typed as text — "2026-05", "1404-03" — is still a timeline."""
    sample = [str(row.get(column) or "") for row in rows[:4]]
    return all(len(value) >= 6 and value[:4].isdigit() for value in sample if value)


def narrative_for(facts: dict[str, Any], locale: str = "fa") -> dict[str, str]:
    """One or two sentences of plain prose about a panel, in both languages.

    Used when the model wrote no narrative for a block, and as the floor for what a
    reader is owed: a chart with no words next to it makes them do the reading.
    """
    fa: list[str] = []
    en: list[str] = []

    row_count = facts.get("row_count", 0)
    if not row_count:
        return {"fa": "داده‌ای برای این بخش یافت نشد.", "en": "No data for this panel."}

    total = facts.get("total")
    measure = facts.get("measure")
    if total is not None and measure:
        fa.append(f"مجموع «{measure}» برابر {_fa(total)} در {_fa(row_count)} ردیف است.")
        en.append(f"“{measure}” totals {_en(total)} across {_en(row_count)} rows.")

    top = facts.get("top") or []
    if top:
        leader = top[0]
        fa.append(
            f"بیشترین سهم به «{leader['label']}» با {_fa(leader['value'])} "
            f"({_fa(leader['share'])}٪) می‌رسد."
        )
        en.append(
            f"“{leader['label']}” leads with {_en(leader['value'])} "
            f"({_en(leader['share'])}%)."
        )

        top3 = facts.get("top3_share")
        if top3 and facts.get("distinct", 0) > 3:
            fa.append(f"سه مورد نخست {_fa(top3)}٪ کل را در بر می‌گیرند.")
            en.append(f"The top three account for {_en(top3)}% of the total.")

    direction = facts.get("direction")
    if direction:
        change = facts.get("change")
        change_pct = facts.get("change_pct")
        if direction == "flat":
            fa.append("روند در بازه بررسی‌شده تقریباً بدون تغییر است.")
            en.append("The trend is essentially flat over the period.")
        else:
            word_fa = "افزایش" if direction == "up" else "کاهش"
            word_en = "rose" if direction == "up" else "fell"
            suffix_fa = f" ({_fa(abs(change_pct))}٪)" if change_pct is not None else ""
            suffix_en = f" ({_en(abs(change_pct))}%)" if change_pct is not None else ""
            fa.append(
                f"از {_fa(facts['first'])} به {_fa(facts['last'])} — "
                f"{word_fa} {_fa(abs(change) if change is not None else '')}{suffix_fa}."
            )
            en.append(
                f"From {_en(facts['first'])} to {_en(facts['last'])} — "
                f"{word_en} by {_en(abs(change) if change is not None else '')}{suffix_en}."
            )

    return {"fa": " ".join(fa), "en": " ".join(en)}
