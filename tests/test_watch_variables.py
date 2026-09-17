"""Unit and integration tests for PyChronicle Watch Variables support."""

from pathlib import Path
import tempfile

from click.testing import CliRunner
import pytest

from main import cli
from pychronicle.config import ChronicleConfig
from pychronicle.replay import ReplayEngine
from pychronicle.storage import SQLiteStorage
from pychronicle.tracer import run_debug_session
from pychronicle.tui import PyChronicleTUI


@pytest.fixture
def watch_test_session():
    """Fixture creating a recorded session with variable mutations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        target_file = tmp_path / "script_watch.py"
        target_file.write_text(
            "x = 10\n"
            "y = [1, 2]\n"
            "x = 20\n"
            "y.append(3)\n"
            "z = x + len(y)\n"
        )
        db_file = tmp_path / "test_watch.db"
        storage = SQLiteStorage(db_path=db_file)
        config = ChronicleConfig(db_path=db_file)

        result = run_debug_session(target_file, config=config, storage=storage)
        replay = ReplayEngine(session_id=result.session_id, storage=storage)
        yield result, replay, db_file, target_file


def test_watch_values_at(watch_test_session):
    """Test querying watch values at specific discrete steps."""
    result, replay, db_file, target_file = watch_test_session

    # Query step 1 (call event before lines execute)
    step1_vals = replay.get_watch_values_at(1, ["x", "y", "z", "non_existent"])
    assert step1_vals["x"] is None
    assert step1_vals["y"] is None
    assert step1_vals["non_existent"] is None

    # Query step 3 (after line 1 'x = 10' executed)
    step3_vals = replay.get_watch_values_at(3, ["x", "y", "z"])
    assert step3_vals["x"] == "10"

    # Query final step
    final_step = replay.total_steps
    final_vals = replay.get_watch_values_at(final_step, ["x", "y", "z"])
    assert final_vals["x"] == "20"
    assert "[1, 2, 3]" in final_vals["y"]
    assert final_vals["z"] == "23"


def test_watch_history(watch_test_session):
    """Test retrieving complete watch history across all execution steps."""
    result, replay, db_file, target_file = watch_test_session

    history = replay.get_watch_history(["x", "y", "z"])
    assert "x" in history
    assert "y" in history
    assert "z" in history

    # Validate x mutations
    x_steps = history["x"]
    assert len(x_steps) == replay.total_steps
    x_values = [s["value"] for s in x_steps if s["value"] is not None]
    assert "10" in x_values
    assert "20" in x_values

    # Check that is_changed flag marks steps where mutation occurred
    x_changed_steps = [s for s in x_steps if s["is_changed"]]
    assert len(x_changed_steps) >= 2


def test_cli_debug_with_watch(watch_test_session):
    """Test running debug command with --watch option."""
    result, replay, db_file, target_file = watch_test_session

    runner = CliRunner()
    cli_res = runner.invoke(cli, ["debug", str(target_file), "--db", str(db_file), "-w", "x", "-w", "y"])
    assert cli_res.exit_code == 0
    assert "Watched Variables History" in cli_res.output
    assert "x = " in cli_res.output
    assert "y = " in cli_res.output


def test_cli_replay_with_watch(watch_test_session):
    """Test replaying session with --watch option."""
    result, replay, db_file, target_file = watch_test_session

    runner = CliRunner()
    # Replay specific step where x is defined (step 3)
    cli_res = runner.invoke(cli, ["replay", str(result.session_id), "--step", "3", "--db", str(db_file), "-w", "x"])
    assert cli_res.exit_code == 0
    assert "Watched Variables:" in cli_res.output
    assert "x = 10" in cli_res.output

    # Replay all steps
    cli_res_all = runner.invoke(cli, ["replay", str(result.session_id), "--db", str(db_file), "-w", "x", "-w", "z"])
    assert cli_res_all.exit_code == 0
    assert "Watched:" in cli_res_all.output


def test_tui_watch_actions(watch_test_session):
    """Test TUI initialization and watch actions."""
    result, replay, db_file, target_file = watch_test_session

    tui = PyChronicleTUI(replay=replay, source_file=target_file, watch_vars=["x", "y"])
    assert tui.watch_vars == ["x", "y"]

    # Set current step to step 3 where x is defined
    tui.current_step_num = 3
    tui.action_toggle_watch_active()
    assert "x" in tui.watch_vars

    # Test clear watches
    tui.action_clear_watches()
    assert len(tui.watch_vars) == 0
