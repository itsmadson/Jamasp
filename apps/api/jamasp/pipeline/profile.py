"""Stage 2: collect statistics and sample values, masking PII before anything leaves.

The Describer's only input is an EntityProfile. Nothing here that a HIGH-class
classifier rejected can therefore reach an external LLM provider.
"""

from dataclasses import dataclass, field
from typing import Any

from jamasp.adapters.base import SourceAdapter
from jamasp.models.entity import PIIClass
from jamasp.models.source import SamplingPolicy
from jamasp.pipeline.snapshot import ColumnStats, EntitySnapshot
from jamasp.safety.pii import classify_column, mask_value


@dataclass
class ColumnProfile:
    name: str
    data_type: str
    pii_class: PIIClass
    distinct_count: int | None = None
    null_ratio: float | None = None
    min_value: Any = None
    max_value: Any = None
    sample_values: list[Any] = field(default_factory=list)


@dataclass
class EntityProfile:
    schema_name: str
    name: str
    row_count: int | None
    columns: list[ColumnProfile]
    sample_rows: list[dict[str, Any]] = field(default_factory=list)

    def column(self, name: str) -> ColumnProfile | None:
        return next((column for column in self.columns if column.name == name), None)


async def profile_entity(
    adapter: SourceAdapter,
    entity: EntitySnapshot,
    policy: SamplingPolicy,
    max_rows: int = 20,
    max_distinct: int = 50,
) -> EntityProfile:
    """One sample query per table, not per column.

    The earlier version asked the database a question about every single column,
    which on a remote server meant hundreds of round trips per table and turned a
    scan into a half-hour job. Everything the describer needs — a couple of real
    values per column, and which columns look like personal data — is already in a
    handful of sampled rows.
    """
    column_names = [column.name for column in entity.columns]

    # Cheap planner statistics: distinct counts and null fractions, no table scan.
    batched: dict[str, ColumnStats] = {}
    if hasattr(adapter, "table_stats"):
        batched = await adapter.table_stats(entity)

    sample_rows: list[dict[str, Any]] = []
    if policy is SamplingPolicy.MASKED and column_names:
        try:
            sample_rows = await adapter.sample(entity, column_names, max_rows)
        except Exception:  # noqa: BLE001 - a table we cannot sample is still describable
            sample_rows = []

    # Values seen per column, taken from the rows already fetched.
    seen: dict[str, list[Any]] = {name: [] for name in column_names}
    for row in sample_rows:
        for name in column_names:
            value = row.get(name)
            if value is not None and value not in seen[name]:
                seen[name].append(value)

    columns: list[ColumnProfile] = []
    for column in entity.columns:
        observed = seen.get(column.name, [])
        stats = batched.get(column.name) or ColumnStats()
        pii_class = classify_column(column.name, column.data_type, observed[:5])

        profile = ColumnProfile(
            name=column.name,
            data_type=column.data_type,
            pii_class=pii_class,
            distinct_count=stats.distinct_count,
            null_ratio=stats.null_ratio,
        )

        if policy is SamplingPolicy.MASKED and pii_class is not PIIClass.HIGH:
            profile.sample_values = [
                masked
                for masked in (mask_value(value, pii_class) for value in observed[:max_distinct])
                if masked is not None
            ]

        columns.append(profile)

    masked_rows: list[dict[str, Any]] = []
    if policy is SamplingPolicy.MASKED:
        pii_by_name = {column.name: column.pii_class for column in columns}
        for row in sample_rows:
            masked_rows.append({
                name: mask_value(value, pii_by_name[name])
                for name, value in row.items()
                if pii_by_name.get(name, PIIClass.HIGH) is not PIIClass.HIGH
            })

    sample_rows = masked_rows

    return EntityProfile(
        schema_name=entity.schema_name,
        name=entity.name,
        row_count=entity.row_count_approx,
        columns=columns,
        sample_rows=sample_rows,
    )
