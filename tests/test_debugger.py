"""Tests for PyChronicle Debugger Core Engine."""

from pathlib import Path
import tempfile
import pytest

from pychronicle.debugger import Debugger, run_debugger


def test_debugger_execution():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("x = 10\ny = 20\nz = x + y\n")
        f_path = Path(f.name)

    try:
        res = run_debugger(f_path, db_path=":memory:")
        assert res.status == "SUCCESS"
        assert res.total_steps >= 3
        assert res.replay is not None

        # Time travel replay verification without rerun
        st1 = res.replay.get_state_at_step(1)
        assert st1.event in ("call", "line")
        st_final = res.replay.last_step()
        assert st_final.scopes["<module>"]["z"] == "30"
        assert st_final.scopes["<module>"]["x"] == "10"
        assert st_final.scopes["<module>"]["y"] == "20"
    finally:

        if f_path.exists():
            f_path.unlink()


def test_debugger_class_interface():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("val = 42\n")
        f_path = Path(f.name)

    try:
        dbg = Debugger(target_path=f_path, db_path=":memory:")
        res = dbg.run()
        assert res.status == "SUCCESS"
        assert dbg.session_id is not None
        assert res.session_id == dbg.session_id
    finally:
        if f_path.exists():
            f_path.unlink()
