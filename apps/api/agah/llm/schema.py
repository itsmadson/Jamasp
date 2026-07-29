"""Convert a plain JSON schema into one OpenAI strict mode accepts.

Strict mode has three rules that ordinary schemas break: every object must set
`additionalProperties: false`, every property must appear in `required`, and there
is no notion of an optional key — an optional field is expressed as one that may
be null. A schema that breaks them is rejected with HTTP 400, which quietly removes
that provider from the fallback chain.
"""

import copy
from typing import Any


def _nullable(node: dict[str, Any]) -> dict[str, Any]:
    kind = node.get("type")
    if kind is None:
        return node
    if isinstance(kind, list):
        if "null" not in kind:
            node["type"] = [*kind, "null"]
    elif kind != "null":
        node["type"] = [kind, "null"]
    return node


def _convert(node: Any) -> Any:
    if isinstance(node, list):
        return [_convert(item) for item in node]
    if not isinstance(node, dict):
        return node

    converted = {key: _convert(value) for key, value in node.items()}

    if converted.get("type") == "object" and "properties" in converted:
        properties = converted["properties"]
        previously_required = set(converted.get("required") or properties.keys())

        # Anything the original schema did not require becomes explicitly nullable,
        # since strict mode requires every key to be present.
        for name, definition in properties.items():
            if name not in previously_required and isinstance(definition, dict):
                properties[name] = _nullable(definition)

        converted["required"] = list(properties.keys())
        converted["additionalProperties"] = False

    return converted


def strict(schema: dict[str, Any]) -> dict[str, Any]:
    return _convert(copy.deepcopy(schema))
