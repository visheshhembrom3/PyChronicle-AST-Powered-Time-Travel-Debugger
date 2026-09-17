"""Tests for program editing workflows, version increments, and historical output fidelity."""

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from pychronicle.application import ApplicationService
from pychronicle.session import STATUS_SUCCESS


def test_program_editing_maintains_independent_execution_history():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "edit_test.db"
        app = ApplicationService(db_path=db_path, seed_demo=False)

        # 1. Create Initial Program (Version 1 - Palindrome: 12321)
        v1_code = '''num = 12321
original = num
reverse = 0
temp = num
while temp > 0:
    digit = temp % 10
    reverse = reverse * 10 + digit
    temp = temp // 10

if original == reverse:
    result = "Palindrome"
else:
    result = "Not Palindrome"
print("Result:", result)
'''
        prog = app.create_program(
            name="Palindrome Checker",
            source_code=v1_code,
            description="Checks palindromes",
        )
        prog_id = prog["id"]
        assert prog["version_count"] == 1

        # 2. Run Version 1
        res_v1 = app.run_program(prog_id, watch_vars=["num", "reverse", "result"])
        assert res_v1["status"] == STATUS_SUCCESS
        assert "Result: Palindrome" in res_v1["stdout"]
        exec_1_id = res_v1["execution_id"]
        assert exec_1_id is not None

        # 3. Edit Program to Version 2 (Non-Palindrome: 12345)
        v2_code = '''num = 12345
original = num
reverse = 0
temp = num
while temp > 0:
    digit = temp % 10
    reverse = reverse * 10 + digit
    temp = temp // 10

if original == reverse:
    result = "Palindrome"
else:
    result = "Not Palindrome"
print("Result:", result)
'''
        updated_prog = app.update_program(
            program_id=prog_id,
            source_code=v2_code,
            description="Updated to 12345",
        )
        assert updated_prog["version_count"] == 2

        # 4. Run Version 2
        res_v2 = app.run_program(prog_id, watch_vars=["num", "reverse", "result"])
        assert res_v2["status"] == STATUS_SUCCESS
        assert "Result: Not Palindrome" in res_v2["stdout"]
        exec_2_id = res_v2["execution_id"]
        assert exec_2_id != exec_1_id

        # 5. Verify History & Immutability of Stored Outputs
        execs = app.list_executions(prog_id)
        assert len(execs) == 2

        # Execution 1 (old run) remains unaltered with Version 1 source & output
        exec_1_record = app.get_execution(exec_1_id)
        assert "num = 12321" in exec_1_record["source_snapshot"]
        assert "Result: Palindrome" in exec_1_record["stdout"]

        # Execution 2 (new run) has Version 2 source & output
        exec_2_record = app.get_execution(exec_2_id)
        assert "num = 12345" in exec_2_record["source_snapshot"]
        assert "Result: Not Palindrome" in exec_2_record["stdout"]

        # 6. Verify Time-Travel Replay on Execution 1 (Zero Re-Execution)
        final_step_v1 = res_v1["total_steps"]
        step_state_v1 = app.replay_execution_step(exec_1_id, final_step_v1, watch_vars=["num", "reverse", "result"])
        assert step_state_v1["scopes"]["<module>"]["num"] == "12321"
        assert step_state_v1["scopes"]["<module>"]["reverse"] == "12321"
        assert step_state_v1["scopes"]["<module>"]["result"] == "'Palindrome'"

        # 7. Verify Time-Travel Replay on Execution 2 (Zero Re-Execution)
        final_step_v2 = res_v2["total_steps"]
        step_state_v2 = app.replay_execution_step(exec_2_id, final_step_v2, watch_vars=["num", "reverse", "result"])
        assert step_state_v2["scopes"]["<module>"]["num"] == "12345"
        assert step_state_v2["scopes"]["<module>"]["reverse"] == "54321"
        assert step_state_v2["scopes"]["<module>"]["result"] == "'Not Palindrome'"
