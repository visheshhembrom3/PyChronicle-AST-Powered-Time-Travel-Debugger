"""Unit tests for SQLite storage layer."""

from pathlib import Path
import sys
import tempfile

# Ensure package is discoverable
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from pychronicle.delta import StateDelta
from pychronicle.storage import SQLiteStorage


@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        storage = SQLiteStorage(db_path)
        yield storage


def test_session_lifecycle(temp_storage):
    session_id = temp_storage.create_session("app.py")
    assert session_id is not None and session_id > 0

    session_data = temp_storage.get_session(session_id)
    assert session_data["filename"] == "app.py"
    assert session_data["status"] == "RUNNING"

    temp_storage.update_session(session_id, status="SUCCESS", error=None)
    updated = temp_storage.get_session(session_id)
    assert updated["status"] == "SUCCESS"
    assert updated["finished_at"] is not None


def test_save_and_retrieve_snapshots(temp_storage):
    session_id = temp_storage.create_session("calc.py")

    deltas = [
        StateDelta(
            step=1,
            line=1,
            event="line",
            scope="<module>",
            changes={"a": {"operation": "CREATE", "old": None, "new": "10"}},
        ),
        StateDelta(
            step=2,
            line=2,
            event="line",
            scope="<module>",
            changes={"b": {"operation": "CREATE", "old": None, "new": "20"}},
        ),
        StateDelta(
            step=3,
            line=3,
            event="return",
            scope="<module>",
            changes={},
            return_value="30",
        ),
    ]

    temp_storage.save_snapshots_batch(session_id, deltas)

    retrieved = temp_storage.get_snapshots(session_id)
    assert len(retrieved) == 3
    assert retrieved[0]["step"] == 1
    assert retrieved[0]["changes"]["a"]["new"] == "10"
    assert retrieved[2]["return_value"] == "30"

    step_2 = temp_storage.get_snapshot_at_step(session_id, 2)
    assert step_2 is not None
    assert step_2["step"] == 2
    assert step_2["changes"]["b"]["new"] == "20"


def test_multiple_sessions(temp_storage):
    s1 = temp_storage.create_session("file1.py")
    s2 = temp_storage.create_session("file2.py")

    temp_storage.save_snapshot(
        s1,
        StateDelta(step=1, line=1, event="line", scope="<module>", changes={"x": {"operation": "CREATE", "old": None, "new": "1"}}),
    )
    temp_storage.save_snapshot(
        s2,
        StateDelta(step=1, line=1, event="line", scope="<module>", changes={"y": {"operation": "CREATE", "old": None, "new": "2"}}),
    )

    all_sessions = temp_storage.list_sessions()
    assert len(all_sessions) == 2

    snaps_1 = temp_storage.get_snapshots(s1)
    snaps_2 = temp_storage.get_snapshots(s2)
    assert len(snaps_1) == 1
    assert "x" in snaps_1[0]["changes"]
    assert len(snaps_2) == 1
    assert "y" in snaps_2[0]["changes"]
