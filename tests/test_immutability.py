"""Tests for historical execution immutability and Copy to Workspace workflow."""

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from pychronicle.application import ApplicationService
from pychronicle.session import STATUS_SUCCESS


def test_historical_execution_immutability_and_copy_to_workspace():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "immutable_test.db"
        app = ApplicationService(db_path=db_path, seed_demo=False)

        # 1. Create and Run Initial Program
        source_v1 = "val = 42\nprint('Answer:', val)\n"
        prog = app.create_program(name="Base Program", source_code=source_v1)
        prog_id = prog["id"]

        res = app.run_program(prog_id)
        assert res["status"] == STATUS_SUCCESS
        exec_id = res["execution_id"]

        exec_before = app.get_execution(exec_id)
        assert exec_before["source_snapshot"] == source_v1
        assert "Answer: 42" in exec_before["stdout"]

        # 2. Modify and Re-run Program (Mutating the active workspace)
        source_v2 = "val = 999\nprint('Answer:', val)\n"
        app.update_program(prog_id, source_code=source_v2)
        res_v2 = app.run_program(prog_id)
        assert res_v2["status"] == STATUS_SUCCESS

        # 3. Assert Historical Record 1 has NOT been mutated
        exec_after = app.get_execution(exec_id)
        assert exec_after["source_snapshot"] == source_v1
        assert "Answer: 42" in exec_after["stdout"]
        assert exec_after["id"] == exec_id

        # 4. Copy Historical Execution to Workspace
        copied_prog = app.copy_execution_to_workspace(exec_id, new_name="Restored Answer 42")
        assert copied_prog["id"] != prog_id
        assert copied_prog["name"] == "Restored Answer 42"
        assert copied_prog["source_code"] == source_v1
        assert copied_prog["version_count"] == 1

        # 5. Run the newly spawned workspace program
        res_copy = app.run_program(copied_prog["id"])
        assert res_copy["status"] == STATUS_SUCCESS
        assert "Answer: 42" in res_copy["stdout"]

        # 6. Delete Copied Program and ensure Original Execution remains safe
        app.delete_program(copied_prog["id"])
        assert app.get_program(copied_prog["id"]) is None
        assert app.get_execution(exec_id) is not None
