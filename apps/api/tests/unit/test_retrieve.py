import pytest

from agah.query.retrieve import lexical_scores, select_tables

KNOWLEDGE = {
    "schema_version": "1.0",
    "source": {"id": "s1", "name": "HR", "kind": "postgres", "dialect": "postgres"},
    "entities": [
        {
            "id": "e1", "kind": "table", "schema_name": "public", "name": "leave_requests",
            "summary": {
                "fa": "درخواست‌های مرخصی کارکنان",
                "en": "Employee leave requests with review status",
            },
            "grain": "one row per leave request",
            "fields": [
                {"name": "emp_id", "type": "integer", "nullable": False,
                 "meaning": {"fa": "شناسه کارمند", "en": "Employee identifier"},
                 "enum_map": None, "unit": None, "pii_class": "none"},
                {"name": "status", "type": "smallint", "nullable": False,
                 "meaning": {"fa": "وضعیت", "en": "Review status"},
                 "enum_map": {"2": {"fa": "تایید شده", "en": "approved"}},
                 "unit": None, "pii_class": "none"},
            ],
            "relationships": [
                {"from": "emp_id", "to": "employees.id", "kind": "inferred",
                 "cardinality": "many_to_one", "confidence": 1.0},
            ],
            "sample_questions": ["افرادی که این ماه مرخصی گرفتند"],
        },
        {
            "id": "e2", "kind": "table", "schema_name": "public", "name": "employees",
            "summary": {"fa": "کارکنان شرکت", "en": "Company employees"},
            "grain": "one row per employee",
            "fields": [
                {"name": "id", "type": "integer", "nullable": False,
                 "meaning": {"fa": "شناسه", "en": "Identifier"},
                 "enum_map": None, "unit": None, "pii_class": "none"},
                {"name": "dept_id", "type": "integer", "nullable": False,
                 "meaning": {"fa": "واحد سازمانی", "en": "Department"},
                 "enum_map": None, "unit": None, "pii_class": "none"},
            ],
            "relationships": [],
            "sample_questions": [],
        },
        {
            "id": "e3", "kind": "table", "schema_name": "public", "name": "products",
            "summary": {"fa": "کالاها", "en": "Product catalogue with prices"},
            "grain": "one row per product",
            "fields": [
                {"name": "price", "type": "numeric", "nullable": True,
                 "meaning": {"fa": "قیمت", "en": "Unit price"},
                 "enum_map": None, "unit": "IRR", "pii_class": "none"},
            ],
            "relationships": [],
            "sample_questions": [],
        },
    ],
}


def test_lexical_scores_rank_the_matching_table_first():
    scores = lexical_scores("چه کسانی مرخصی گرفتند؟", KNOWLEDGE["entities"])
    assert scores[0][0]["name"] == "leave_requests"
    assert scores[0][1] > 0


def test_english_question_matches_english_summary():
    scores = lexical_scores("most expensive products by price", KNOWLEDGE["entities"])
    assert scores[0][0]["name"] == "products"


def test_selection_works_without_embeddings():
    """A self-hosted install with no embedding service is a normal state."""
    selected = select_tables("مرخصی", KNOWLEDGE, embeddings=None)
    assert "leave_requests" in {entity["name"] for entity in selected}


def test_selection_expands_one_hop_along_relationships():
    selected = select_tables("مرخصی", KNOWLEDGE, embeddings=None, limit=1)
    names = {entity["name"] for entity in selected}
    # A question about leave requests is unanswerable without the employee table.
    assert "leave_requests" in names
    assert "employees" in names


def test_selection_does_not_pull_in_unrelated_tables():
    selected = select_tables("مرخصی", KNOWLEDGE, embeddings=None, limit=1)
    assert "products" not in {entity["name"] for entity in selected}


def test_returns_empty_when_nothing_matches():
    # Better to report no match than to invent a query over irrelevant tables.
    assert select_tables("weather forecast in Tehran", KNOWLEDGE, embeddings=None) == []


@pytest.mark.parametrize("question", ["", "   ", "?"])
def test_empty_question_matches_nothing(question):
    assert select_tables(question, KNOWLEDGE, embeddings=None) == []
