import json
from typing import Any

BILINGUAL = {
    "type": "object",
    "properties": {"fa": {"type": "string"}, "en": {"type": "string"}},
    "required": ["fa", "en"],
}

REPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": BILINGUAL,
        "summary": BILINGUAL,
        "findings": {"type": "array", "items": BILINGUAL},
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "kpi", "bar", "line", "area", "pie", "donut", "radar", "table",
                        ],
                    },
                    "title": BILINGUAL,
                    "narrative": BILINGUAL,
                    "dataset": {"type": "string"},
                    "span": {"type": ["integer", "null"], "enum": [1, 2, 3, None]},
                    "x": {"type": ["string", "null"]},
                    "y": {"type": ["string", "null"]},
                    "series": {"type": ["string", "null"]},
                    "column": {"type": ["string", "null"]},
                    "aggregate": {"type": ["string", "null"]},
                    "unit": {"type": ["string", "null"]},
                    "label": BILINGUAL,
                    "columns": {"type": ["array", "null"], "items": {"type": "string"}},
                },
                "required": ["type", "title", "dataset"],
            },
        },
    },
    "required": ["title", "summary", "blocks"],
}

SYSTEM = """You design report pages for جاماسپ, a bilingual (Persian/English) tool.

You are given several datasets. Each has a key, the question it answers, its
columns, sample rows, and computed facts about its own numbers — totals, the
leading category and its share, and the direction of any trend. Those facts are
arithmetic already done for you: use them, never recompute them, never contradict
them.

Build a dense, readable report page — not a bare stack of charts. A reader should
be able to learn what happened by reading, with the charts as evidence.

## Block types

- "kpi"   one headline number from a dataset. Give `column` and an `aggregate`
          ("sum", "avg", "min", "max", "count", "first").
- "bar"   a value across categories. Needs `x` and `y`.
- "line"  a value over time. Needs `x` and `y`.
- "area"  as line, when cumulative volume is the point.
- "pie"   a share of a whole, 2 to 6 categories only. Never over time.
- "donut" as pie, when the total in the centre helps.
- "radar" comparing 3 to 8 categories on one measure, when the shape of the
          profile matters more than exact ranking.
- "table" detail rows, long category lists, or text-only results.

## What every report needs

1. **A KPI row first.** Two to four `kpi` blocks with `span: 1`, each from a
   dataset's headline number. This is what makes the page open with substance.
2. **A chart per dataset**, at the size its shape needs.
3. **A second view where it earns one.** A dataset with a clear leader also reads
   well as a pie or donut; a dataset with 3–8 categories also reads as a radar.
   Do not add a second view of a dataset that has nothing more to say.
4. **A table for any dataset with more than 8 rows**, so the detail is reachable.
5. **`narrative` on every block**: one or two sentences, in both languages, saying
   what THIS block shows, quoting the actual numbers from the facts given. Not
   "this chart shows users by role" — say which role leads, by how much, and what
   that means for the reader.
6. **`findings`**: three to five bilingual sentences, each a specific observation
   drawn from the facts across datasets. This is the part a reader quotes in a
   meeting. No filler, no restating the title.

## Layout

`span` is how many of three columns a block occupies. Vary them — a page where
every block spans 3 is a stack, not a report.
- 1  KPI, pie, donut, radar
- 2  bar, or a line with few points
- 3  a long time series, or a table

Aim for 6 to 10 blocks total.

## Rules

- Use ONLY the column names listed for the dataset a block names. Never mix
  datasets inside a block.
- Prefer a dataset's Persian label column (names ending `_fa`, or a `label`
  column) over a raw code column for chart axes.
- Persian text must be fully Persian: no Latin words left inside it, no
  half-translated strings, and use Persian digits in prose.
- Never state a number that is not in the facts or rows you were given.
"""


def build_report_messages(
    question: str,
    datasets: list[dict[str, Any]],
    locale: str,
) -> list[dict[str, str]]:
    payload = {
        "request": question,
        "request_locale": locale,
        "datasets": [
            {
                "key": dataset["key"],
                "answers": dataset.get("question"),
                "row_count": dataset.get("row_count", 0),
                "columns": dataset.get("columns", []),
                "sample_rows": (dataset.get("rows") or [])[:6],
                # Arithmetic already done, so the model narrates instead of counting.
                "facts": dataset.get("facts", {}),
            }
            for dataset in datasets
        ],
    }
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2, default=str)},
    ]
