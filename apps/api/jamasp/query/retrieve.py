"""Stage 1: pick the handful of tables a question actually touches.

A 200-table schema does not fit in a prompt. Vector search is used when the scan
managed to build embeddings; the lexical path is a first-class fallback, because a
self-hosted install with no embedding service is a normal state rather than a fault.
"""

import re
from typing import Any

Entity = dict[str, Any]

MIN_SCORE = 1.0
DEFAULT_LIMIT = 6

# Words that appear in almost every question and would match almost every table.
STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "for", "by", "to", "and", "or", "is", "are",
    "what", "which", "who", "how", "many", "much", "list", "show", "me", "all", "per",
    "از", "در", "به", "را", "که", "با", "این", "آن", "برای", "چه", "چند", "کدام",
    "کسانی", "است", "هست", "شده", "های", "ها", "و", "یا",
}

TOKEN = re.compile(r"[\w؀-ۿ]+", re.UNICODE)


def tokenize(text: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN.findall(text or "")
        if len(token) > 1 and token.lower() not in STOPWORDS
    }


def _entity_terms(entity: Entity) -> set[str]:
    """Every term a question could plausibly match this table on."""
    parts: list[str] = [entity["name"].replace("_", " ")]
    summary = entity.get("summary") or {}
    parts.extend([summary.get("fa", ""), summary.get("en", "")])
    parts.extend(entity.get("sample_questions") or [])
    parts.append(entity.get("grain") or "")

    for field in entity.get("fields") or []:
        parts.append(field["name"].replace("_", " "))
        meaning = field.get("meaning") or {}
        parts.extend([meaning.get("fa", ""), meaning.get("en", "")])
        for label in (field.get("enum_map") or {}).values():
            parts.extend([label.get("fa", ""), label.get("en", "")])

    return tokenize(" ".join(part for part in parts if part))


def lexical_scores(question: str, entities: list[Entity]) -> list[tuple[Entity, float]]:
    asked = tokenize(question)
    if not asked:
        return []

    scored: list[tuple[Entity, float]] = []
    for entity in entities:
        terms = _entity_terms(entity)
        overlap = asked & terms
        if not overlap:
            continue
        # Name matches count double: a question naming a table almost certainly means it.
        name_terms = tokenize(entity["name"].replace("_", " "))
        score = len(overlap) + len(asked & name_terms)
        scored.append((entity, float(score)))

    return sorted(scored, key=lambda pair: pair[1], reverse=True)


def _vector_scores(
    question_vector: list[float], entities: list[Entity], embeddings: dict[str, list[float]]
) -> list[tuple[Entity, float]]:
    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        return 0.0 if norm_a == 0 or norm_b == 0 else dot / (norm_a * norm_b)

    scored = [
        (entity, cosine(question_vector, embeddings[entity["id"]]))
        for entity in entities
        if entity["id"] in embeddings
    ]
    return sorted(scored, key=lambda pair: pair[1], reverse=True)


def _expand_one_hop(selected: list[Entity], entities: list[Entity]) -> list[Entity]:
    """Pull in directly related tables: a question about leave requests is not
    answerable without the employee table it points at."""
    by_name = {entity["name"]: entity for entity in entities}
    chosen = {entity["name"]: entity for entity in selected}

    for entity in list(selected):
        for relationship in entity.get("relationships") or []:
            target = str(relationship.get("to", "")).split(".")[0]
            if target and target in by_name and target not in chosen:
                chosen[target] = by_name[target]

    return list(chosen.values())


def select_tables(
    question: str,
    knowledge: dict[str, Any],
    embeddings: dict[str, list[float]] | None = None,
    question_vector: list[float] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[Entity]:
    entities = knowledge.get("entities") or []
    if not entities:
        return []

    if embeddings and question_vector:
        ranked = _vector_scores(question_vector, entities, embeddings)
        top = [entity for entity, score in ranked[:limit] if score > 0.2]
    else:
        ranked = lexical_scores(question, entities)
        top = [entity for entity, score in ranked[:limit] if score >= MIN_SCORE]

    if not top:
        return []
    return _expand_one_hop(top, entities)
