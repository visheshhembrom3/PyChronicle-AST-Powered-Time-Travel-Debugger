"""Unit tests for Historical Replay reconstruction without re-execution."""

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from pychronicle.application import ApplicationService


def test_history_replay_reconstructs_state_at_steps():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        service = ApplicationService(db_path=db_path, seed_demo=False)

        code = """def calc(val):
    res = val * 2
    return res

x = 5
y = calc(x)
"""
        prog = service.create_program("Replay Step Test", code)
        res = service.run_program(prog["id"])
        exec_id = res["execution_id"]
        total_steps = res["total_steps"]
        assert total_steps > 0

        # Step 1: initial
        st1 = service.replay_execution_step(exec_id, 1)
        assert st1["step"] == 1
        assert st1["total_steps"] == total_steps

        # Last step: final state
        st_final = service.replay_execution_step(exec_id, total_steps)
        mod_vars = st_final["scopes"].get("<module>", {})
        assert mod_vars.get("x") == "5"
        assert mod_vars.get("y") == "10"


def test_history_replay_watch_variables():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        service = ApplicationService(db_path=db_path, seed_demo=False)

        code = """total = 0
for i in range(1, 4):
    total += i
"""
        prog = service.create_program("Watch Test", code)
        res = service.run_program(prog["id"])
        exec_id = res["execution_id"]

        # Step through and evaluate watched variable 'total'
        watch_vals_final = service.get_watch_values(exec_id, res["total_steps"], ["total"])
        assert watch_vals_final.get("total") == "6"
