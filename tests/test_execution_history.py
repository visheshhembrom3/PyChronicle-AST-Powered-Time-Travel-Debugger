"""Unit tests for Execution History tracking, source snapshots, and run immutability."""

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from pychronicle.application import ApplicationService
from pychronicle.storage import SQLiteStorage


def test_execution_history_records_and_immutable_snapshots():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        service = ApplicationService(db_path=db_path, seed_demo=False)

        # 1. Create Program
        prog = service.create_program("History Test", "x = 10\nprint('x is', x)\n")
        prog_id = prog["id"]

        # 2. Run Version 1
        res1 = service.run_program(prog_id)
        assert res1["status"] == "SUCCESS"
        assert "x is 10" in res1["stdout"]
        assert res1["source_snapshot"] == "x = 10\nprint('x is', x)\n"
        exec1_id = res1["execution_id"]

        # 3. Edit Program to Version 2
        service.update_program(prog_id, source_code="x = 20\nprint('x is', x)\n")

        # 4. Run Version 2
        res2 = service.run_program(prog_id)
        assert res2["status"] == "SUCCESS"
        assert "x is 20" in res2["stdout"]
        assert res2["source_snapshot"] == "x = 20\nprint('x is', x)\n"
        exec2_id = res2["execution_id"]

        # 5. List Executions
        execs = service.list_executions(prog_id)
        assert len(execs) == 2

        # Verify Execution 1 is unchanged
        saved_exec1 = service.get_execution(exec1_id)
        assert saved_exec1 is not None
        assert saved_exec1["source_snapshot"] == "x = 10\nprint('x is', x)\n"
        assert "x is 10" in saved_exec1["stdout"]

        # Verify Execution 2 is distinct
        saved_exec2 = service.get_execution(exec2_id)
        assert saved_exec2 is not None
        assert saved_exec2["source_snapshot"] == "x = 20\nprint('x is', x)\n"
        assert "x is 20" in saved_exec2["stdout"]


def test_execution_history_re_run():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        service = ApplicationService(db_path=db_path, seed_demo=False)

        prog = service.create_program("Re-run Test", "count = 5\n")
        prog_id = prog["id"]

        res1 = service.run_program(prog_id)
        res2 = service.run_program(prog_id)

        assert res1["execution_id"] != res2["execution_id"]
        execs = service.list_executions(prog_id)
        assert len(execs) == 2
