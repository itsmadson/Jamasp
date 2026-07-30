from jamasp.llm.prompts.describe_entity import DESCRIBE_SCHEMA
from jamasp.llm.schema import strict
from jamasp.query.prompts.generate_sql import GENERATE_SQL_SCHEMA


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def test_every_object_forbids_additional_properties():
    """OpenAI strict json_schema rejects any object without this, which silently
    removed the paid fallback from the chain."""
    for node in _walk(strict(DESCRIBE_SCHEMA)):
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False


def test_every_object_lists_all_properties_as_required():
    for node in _walk(strict(DESCRIBE_SCHEMA)):
        if node.get("type") == "object" and "properties" in node:
            assert set(node["required"]) == set(node["properties"])


def test_optional_fields_become_nullable_rather_than_omitted():
    # Strict mode has no notion of an optional key, so an optional field has to
    # be expressed as one that may be null.
    converted = strict(DESCRIBE_SCHEMA)
    unit = converted["properties"]["fields"]["items"]["properties"]["unit"]
    assert "null" in unit["type"]


def test_conversion_does_not_mutate_the_original():
    before = DESCRIBE_SCHEMA["required"][:]
    strict(DESCRIBE_SCHEMA)
    assert DESCRIBE_SCHEMA["required"] == before


def test_generate_sql_schema_converts_too():
    converted = strict(GENERATE_SQL_SCHEMA)
    assert converted["additionalProperties"] is False
    assert set(converted["required"]) == set(converted["properties"])


def test_object_typed_as_a_nullable_union_also_gets_the_strict_keys():
    """A dynamic map typed as ["object","null"] slipped through and produced a 400."""
    schema = {
        "type": "object",
        "properties": {"blob": {"type": ["object", "null"], "properties": {}}},
        "required": ["blob"],
    }
    converted = strict(schema)
    blob = converted["properties"]["blob"]
    assert blob["additionalProperties"] is False


def test_describe_schema_has_no_free_form_object():
    """Strict mode cannot express an open-ended map, so the schema must not use one."""
    for node in _walk(strict(DESCRIBE_SCHEMA)):
        types = node.get("type")
        types = types if isinstance(types, list) else [types]
        if "object" in types:
            assert node.get("properties"), "an object with no properties cannot be strict"
