"""Comprehensive End-to-End Pipeline Validation for PyChronicle Debugger."""

from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from pychronicle.application import ApplicationService


def test_full_end_to_end_debugger_lifecycle_pipeline():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "e2e_pipeline.db"
        service = ApplicationService(db_path=db_path, seed_demo=False)

        # 1. Create program
        initial_source = "x = 10\nprint('Value is:', x)\n"
        prog = service.create_program(
            name="Pipeline Demo",
            source_code=initial_source,
            description="End-to-end integration test program",
        )
        prog_id = prog["id"]
        assert prog_id > 0

        # 2. Run program (Version 1)
        res1 = service.run_program(prog_id)
        assert res1["status"] == "SUCCESS"
        assert "Value is: 10" in res1["stdout"]
        assert res1["total_steps"] > 0
        exec1_id = res1["execution_id"]
        session1_id = res1["session_id"]

        # 3. Verify SQLite records
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Check programs
        cur.execute("SELECT * FROM programs WHERE id = ?;", (prog_id,))
        p_row = cur.fetchone()
        assert p_row["name"] == "Pipeline Demo"
        assert p_row["last_status"] == "SUCCESS"

        # Check execution 1
        cur.execute("SELECT * FROM executions WHERE id = ?;", (exec1_id,))
        e1_row = cur.fetchone()
        assert e1_row["source_snapshot"] == initial_source
        assert "Value is: 10" in e1_row["stdout"]
        assert e1_row["debug_session_id"] == session1_id

        # Check session & snapshots
        cur.execute("SELECT * FROM sessions WHERE id = ?;", (session1_id,))
        assert cur.fetchone()["status"] == "SUCCESS"

        cur.execute("SELECT COUNT(*) FROM snapshots WHERE session_id = ?;", (session1_id,))
        snap_count1 = cur.fetchone()[0]
        assert snap_count1 == res1["total_steps"]
        conn.close()

        # 4. Replay step from Run 1
        st_mid = service.replay_execution_step(exec1_id, 1)
        assert st_mid["step"] == 1

        # 5. Modify program to Version 2
        v2_source = "x = 20\nprint('Value is:', x)\n"
        updated_prog = service.update_program(prog_id, source_code=v2_source)
        assert updated_prog["version_count"] == 2

        # 6. Run Version 2
        res2 = service.run_program(prog_id)
        assert res2["status"] == "SUCCESS"
        assert "Value is: 20" in res2["stdout"]
        exec2_id = res2["execution_id"]
        session2_id = res2["session_id"]

        # 7. CRITICAL VERIFICATION: Ensure Execution 1 remains completely immutable!
        e1_after = service.get_execution(exec1_id)
        assert e1_after["source_snapshot"] == initial_source
        assert "Value is: 10" in e1_after["stdout"]
        assert e1_after["debug_session_id"] == session1_id

        # And Execution 2 has Version 2 data
        e2_after = service.get_execution(exec2_id)
        assert e2_after["source_snapshot"] == v2_source
        assert "Value is: 20" in e2_after["stdout"]
        assert e2_after["debug_session_id"] == session2_id

        # 8. Replay both executions independently without re-executing code
        replay1_final = service.replay_execution_step(exec1_id, res1["total_steps"])
        assert replay1_final["scopes"]["<module>"]["x"] == "10"

        replay2_final = service.replay_execution_step(exec2_id, res2["total_steps"])
        assert replay2_final["scopes"]["<module>"]["x"] == "20"

        # 9. Delete program and verify 0 orphaned rows
        service.delete_program(prog_id)

        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        for table in ["programs", "program_versions", "executions", "sessions", "snapshots"]:
            cur.execute(f"SELECT COUNT(*) FROM {table};")
            count = cur.fetchone()[0]
            assert count == 0, f"Table {table} still has {count} orphaned rows after cascade delete!"
        conn.close()
