"""Stage 2: collect statistics and sample values, masking PII before anything leaves.

The Describer's only input is an EntityProfile. Nothing here that a HIGH-class
classifier rejected can therefore reach an external LLM provider.
"""

from dataclasses import dataclass, field
from typing import Any

from agah.adapters.base import SourceAdapter
from agah.models.entity import PIIClass
from agah.models.source import SamplingPolicy
from agah.pipeline.snapshot import EntitySnapshot
from agah.safety.pii import classify_column, mask_value


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
    columns: list[ColumnProfile] = []

    for column in entity.columns:
        stats = await adapter.column_stats(entity, column.name)

        # A small unmasked probe, used only to classify. It never escapes this loop.
        probe: list[Any] = []
        if policy is SamplingPolicy.MASKED:
            probe = await adapter.distinct_values(entity, column.name, limit=5)
        pii_class = classify_column(column.name, column.data_type, probe)

        profile = ColumnProfile(
            name=column.name,
            data_type=column.data_type,
            pii_class=pii_class,
            distinct_count=stats.distinct_count,
            null_ratio=stats.null_ratio,
        )

        if policy is SamplingPolicy.MASKED and pii_class is not PIIClass.HIGH:
            if stats.distinct_count is not None and stats.distinct_count <= max_distinct:
                values = await adapter.distinct_values(entity, column.name, limit=max_distinct)
                profile.sample_values = [
                    masked
                    for masked in (mask_value(value, pii_class) for value in values)
                    if masked is not None
                ]
            profile.min_value = mask_value(stats.min_value, pii_class)
            profile.max_value = mask_value(stats.max_value, pii_class)

        columns.append(profile)

    sample_rows: list[dict[str, Any]] = []
    if policy is SamplingPolicy.MASKED:
        pii_by_name = {column.name: column.pii_class for column in columns}
        raw_rows = await adapter.sample(
            entity, [column.name for column in entity.columns], max_rows
        )
        for row in raw_rows:
            sample_rows.append({
                name: mask_value(value, pii_by_name[name])
                for name, value in row.items()
                if pii_by_name.get(name, PIIClass.HIGH) is not PIIClass.HIGH
            })

    return EntityProfile(
        schema_name=entity.schema_name,
        name=entity.name,
        row_count=entity.row_count_approx,
        columns=columns,
        sample_rows=sample_rows,
    )
