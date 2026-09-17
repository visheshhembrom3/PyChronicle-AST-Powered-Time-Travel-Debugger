"""Unit tests for ReplayEngine time-travel reconstruction."""

from pathlib import Path
import sys
import tempfile

# Ensure package is discoverable
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from pychronicle.delta import StateDelta
from pychronicle.exceptions import ReplayError
from pychronicle.replay import ReplayEngine
from pychronicle.storage import SQLiteStorage


@pytest.fixture
def replay_fixture():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "replay_test.db"
        storage = SQLiteStorage(db_path)
        session_id = storage.create_session("timeline.py")

        deltas = [
            StateDelta(
                step=1,
                line=1,
                event="line",
                scope="<module>",
                changes={"x": {"operation": "CREATE", "old": None, "new": "10"}},
            ),
            StateDelta(
                step=2,
                line=2,
                event="line",
                scope="<module>",
                changes={"x": {"operation": "UPDATE", "old": "10", "new": "20"}},
            ),
            StateDelta(
                step=3,
                line=5,
                event="call",
                scope="compute",
                changes={"arg": {"operation": "CREATE", "old": None, "new": "5"}},
            ),
            StateDelta(
                step=4,
                line=6,
                event="return",
                scope="compute",
                changes={"res": {"operation": "CREATE", "old": None, "new": "25"}},
                return_value="25",
            ),
            StateDelta(
                step=5,
                line=3,
                event="line",
                scope="<module>",
                changes={"total": {"operation": "CREATE", "old": None, "new": "45"}},
            ),
        ]

        storage.save_snapshots_batch(session_id, deltas)
        storage.update_session(session_id, status="SUCCESS")

        engine = ReplayEngine(session_id=session_id, storage=storage)
        yield engine


def test_replay_state_at_steps(replay_fixture):
    engine = replay_fixture

    # Step 1: x = 10
    st1 = engine.state_at(1)
    assert st1.get_var("x", "<module>") == "10"
    assert "compute" not in st1.scopes or not st1.scopes["compute"]

    # Step 2: x = 20
    st2 = engine.state_at(2)
    assert st2.get_var("x", "<module>") == "20"

    # Step 3: compute scope active with arg = 5
    st3 = engine.state_at(3)
    assert st3.active_scope == "compute"
    assert st3.get_var("arg", "compute") == "5"
    assert st3.get_var("x", "<module>") == "20"

    # Step 5: total = 45
    st5 = engine.state_at(5)
    assert st5.get_var("total", "<module>") == "45"
    assert st5.get_var("x", "<module>") == "20"


def test_replay_navigation(replay_fixture):
    engine = replay_fixture
    assert engine.total_steps == 5

    first = engine.first_step()
    assert first.step == 1

    last = engine.last_step()
    assert last.step == 5

    prev = engine.previous_step()
    assert prev.step == 4

    next_st = engine.next_step()
    assert next_st.step == 5


def test_replay_out_of_bounds(replay_fixture):
    engine = replay_fixture
    with pytest.raises(ReplayError):
        engine.state_at(0)
    with pytest.raises(ReplayError):
        engine.state_at(99)
