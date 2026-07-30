"""Stage 5: compare this scan's structure against the last one.

This is what keeps human review effort from being thrown away. An unchanged table
keeps its approval and costs nothing to rescan; only genuinely new or altered
structure goes back to a reviewer.
"""

from dataclasses import dataclass, field

from jamasp.models.entity import EntityStatus
from jamasp.pipeline.snapshot import EntitySnapshot, Identity, StructuralSnapshot


@dataclass
class EntityChange:
    identity: Identity
    change: str
    previous_hash: str | None
    current_hash: str | None
    column_changes: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class SnapshotDiff:
    added: list[Identity] = field(default_factory=list)
    changed: list[EntityChange] = field(default_factory=list)
    unchanged: list[Identity] = field(default_factory=list)
    removed: list[Identity] = field(default_factory=list)


def _column_changes(before: EntitySnapshot, after: EntitySnapshot) -> dict[str, list[str]]:
    old = {column.name: column for column in before.columns}
    new = {column.name: column for column in after.columns}
    return {
        "added": sorted(new.keys() - old.keys()),
        "removed": sorted(old.keys() - new.keys()),
        "retyped": sorted(
            name for name in old.keys() & new.keys() if old[name].data_type != new[name].data_type
        ),
    }


def diff_snapshots(
    previous: StructuralSnapshot | None, current: StructuralSnapshot
) -> SnapshotDiff:
    result = SnapshotDiff()
    current_map = current.by_identity()

    if previous is None:
        result.added = sorted(current_map.keys())
        return result

    previous_map = previous.by_identity()

    for identity, entity in sorted(current_map.items()):
        if identity not in previous_map:
            result.added.append(identity)
            continue
        before = previous_map[identity]
        previous_hash = previous.hash_for(before)
        current_hash = current.hash_for(entity)
        if previous_hash == current_hash:
            result.unchanged.append(identity)
        else:
            result.changed.append(
                EntityChange(
                    identity=identity,
                    change="changed",
                    previous_hash=previous_hash,
                    current_hash=current_hash,
                    column_changes=_column_changes(before, entity),
                )
            )

    result.removed = sorted(previous_map.keys() - current_map.keys())
    return result


def status_for(change: str) -> EntityStatus:
    return {
        "added": EntityStatus.PENDING,
        "changed": EntityStatus.STALE,
        "removed": EntityStatus.ARCHIVED,
    }[change]
