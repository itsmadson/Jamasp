from typing import Any

from agah.adapters.base import SourceAdapter
from agah.adapters.postgres import PostgresAdapter
from agah.models.source import SourceKind


def adapter_for(kind: SourceKind, config: dict[str, Any]) -> SourceAdapter:
    if kind is SourceKind.POSTGRES:
        return PostgresAdapter(config["dsn"])
    raise NotImplementedError(
        f"no adapter for source kind '{kind}' yet; implement it against the "
        f"SourceAdapter protocol in agah/adapters/base.py"
    )
