from dataclasses import replace

import pytest

from jamasp.models.entity import EntityStatus
from jamasp.pipeline.diff import diff_snapshots, status_for
from jamasp.pipeline.snapshot import ColumnInfo, EntitySnapshot, StructuralSnapshot


def _column(name, data_type="integer", ordinal=0, nullable=True, is_pk=False):
    return ColumnInfo(
        name=name, data_type=data_type, nullable=nullable, is_pk=is_pk, ordinal=ordinal
    )


def _entity(name, columns):
    return EntitySnapshot(kind="table", schema_name="public", name=name, columns=tuple(columns))


def _snapshot(entities):
    return StructuralSnapshot(dialect="postgres", entities=tuple(entities))


BASE = _snapshot([
    _entity("employees", [_column("id", is_pk=True), _column("full_name", "text", 1)]),
    _entity("departments", [_column("id", is_pk=True)]),
])


def test_first_scan_marks_everything_added():
    result = diff_snapshots(None, BASE)
    assert {identity[1] for identity in result.added} == {"employees", "departments"}
    assert result.changed == []
    assert result.removed == []


def test_identical_snapshots_produce_no_changes():
    result = diff_snapshots(BASE, BASE)
    assert result.added == []
    assert result.changed == []
    assert result.removed == []
    assert len(result.unchanged) == 2


def test_added_column_marks_only_that_table_changed():
    current = _snapshot([
        _entity("employees", [
            _column("id", is_pk=True), _column("full_name", "text", 1),
            _column("email", "text", 2),
        ]),
        _entity("departments", [_column("id", is_pk=True)]),
    ])
    result = diff_snapshots(BASE, current)
    assert [change.identity[1] for change in result.changed] == ["employees"]
    assert ("public", "departments") in result.unchanged
    assert result.changed[0].column_changes == {"added": ["email"], "removed": [], "retyped": []}


def test_retyped_column_is_reported():
    current = _snapshot([
        _entity("employees", [_column("id", is_pk=True), _column("full_name", "varchar", 1)]),
        _entity("departments", [_column("id", is_pk=True)]),
    ])
    result = diff_snapshots(BASE, current)
    assert result.changed[0].column_changes["retyped"] == ["full_name"]


def test_dropped_table_is_removed_not_changed():
    current = _snapshot([_entity("departments", [_column("id", is_pk=True)])])
    result = diff_snapshots(BASE, current)
    assert [identity[1] for identity in result.removed] == ["employees"]


def test_row_count_change_alone_is_not_a_schema_change():
    grown = _snapshot([replace(BASE.entities[0], row_count_approx=999999), BASE.entities[1]])
    assert diff_snapshots(BASE, grown).changed == []


@pytest.mark.parametrize(
    "change,expected",
    [
        ("added", EntityStatus.PENDING),
        ("changed", EntityStatus.STALE),
        ("removed", EntityStatus.ARCHIVED),
    ],
)
def test_status_mapping(change, expected):
    assert status_for(change) is expected
