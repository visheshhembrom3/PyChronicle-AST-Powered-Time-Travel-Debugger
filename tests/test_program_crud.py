"""Unit tests for Program CRUD, duplication, and cascade deletion integrity."""

from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from pychronicle.application import ApplicationService
from pychronicle.storage import SQLiteStorage


def test_program_crud_lifecycle():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        service = ApplicationService(db_path=db_path, seed_demo=False)

        # Create
        prog = service.create_program("CRUD Test", "y = 100\n", "Initial test")
        prog_id = prog["id"]
        assert prog["name"] == "CRUD Test"

        # Read
        fetched = service.get_program(prog_id)
        assert fetched is not None
        assert fetched["name"] == "CRUD Test"

        # Update
        updated = service.update_program(prog_id, name="CRUD Renamed", description="Updated desc")
        assert updated["name"] == "CRUD Renamed"
        assert updated["description"] == "Updated desc"

        # Delete
        success = service.delete_program(prog_id)
        assert success is True
        assert service.get_program(prog_id) is None


def test_program_duplicate():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        service = ApplicationService(db_path=db_path, seed_demo=False)

        prog = service.create_program("Original Demo", "val = 42\n", "Source description")
        prog_id = prog["id"]
        service.run_program(prog_id)  # Create execution on original

        # Duplicate
        dup = service.duplicate_program(prog_id)
        assert dup["id"] != prog_id
        assert dup["name"] == "Original Demo Copy"
        assert dup["source_code"] == "val = 42\n"
        assert dup["run_count"] == 0  # Execution history must NOT be copied


def test_program_cascade_delete_integrity():
    """Verify that deleting a program leaves zero orphaned rows in child tables."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        service = ApplicationService(db_path=db_path, seed_demo=False)

        prog = service.create_program("Cascade Test", "a = 1\nb = 2\n")
        prog_id = prog["id"]

        # Run multiple times to generate executions, sessions, and snapshots
        service.run_program(prog_id)
        service.update_program(prog_id, source_code="a = 10\nb = 20\n")
        service.run_program(prog_id)

        # Confirm rows exist before delete
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM program_versions WHERE program_id = ?;", (prog_id,))
        assert cur.fetchone()[0] == 2

        cur.execute("SELECT COUNT(*) FROM executions WHERE program_id = ?;", (prog_id,))
        assert cur.fetchone()[0] == 2

        cur.execute("SELECT COUNT(*) FROM sessions;")
        assert cur.fetchone()[0] >= 2

        cur.execute("SELECT COUNT(*) FROM snapshots;")
        assert cur.fetchone()[0] > 0
        conn.close()

        # Delete Program
        service.delete_program(prog_id)

        # Verify cascade cleanup in SQLite
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM programs WHERE id = ?;", (prog_id,))
        assert cur.fetchone()[0] == 0

        cur.execute("SELECT COUNT(*) FROM program_versions WHERE program_id = ?;", (prog_id,))
        assert cur.fetchone()[0] == 0

        cur.execute("SELECT COUNT(*) FROM executions WHERE program_id = ?;", (prog_id,))
        assert cur.fetchone()[0] == 0

        cur.execute("SELECT COUNT(*) FROM sessions;")
        assert cur.fetchone()[0] == 0

        cur.execute("SELECT COUNT(*) FROM snapshots;")
        assert cur.fetchone()[0] == 0

        conn.close()
