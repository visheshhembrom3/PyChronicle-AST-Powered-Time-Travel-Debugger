"""Tests for PyChronicle SQLite Database Layer."""

from pathlib import Path
import tempfile
import pytest

from pychronicle.database import Database
from pychronicle.delta import StateDelta


def test_database_in_memory():
    db = Database(":memory:")
    session_id = db.create_session("sample_test.py")
    assert session_id is not None
    assert session_id > 0

    delta = StateDelta(
        step=1,
        line=1,
        event="line",
        scope="<module>",
        changes={"x": {"operation": "CREATE", "old": None, "new": 10}},
    )
    snap_id = db.save_snapshot(session_id, delta)
    assert snap_id > 0

    snaps = db.get_snapshots(session_id)
    assert len(snaps) == 1
    assert snaps[0]["step"] == 1
    assert snaps[0]["changes"]["x"]["new"] == 10

    vardeltas = db.get_variable_deltas(session_id, "x")
    assert len(vardeltas) == 1
    assert vardeltas[0]["variable_name"] == "x"
    assert vardeltas[0]["new_value"] == "10"

    db.close()


def test_database_file_based():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    try:
        db = Database(db_path)
        session_id = db.create_session("script.py")

        delta1 = StateDelta(
            step=1,
            line=1,
            event="line",
            scope="<module>",
            changes={"a": {"operation": "CREATE", "old": None, "new": 5}},
        )
        delta2 = StateDelta(
            step=2,
            line=2,
            event="line",
            scope="<module>",
            changes={"a": {"operation": "UPDATE", "old": 5, "new": 15}},
        )

        db.save_snapshots_batch(session_id, [delta1, delta2])
        db.update_session(session_id=session_id, status="SUCCESS")

        sess = db.get_session(session_id)
        assert sess["status"] == "SUCCESS"

        snaps = db.get_snapshots(session_id)
        assert len(snaps) == 2

        all_deltas = db.get_variable_deltas(session_id)
        assert len(all_deltas) == 2
    finally:
        if db_path.exists():
            db_path.unlink()
