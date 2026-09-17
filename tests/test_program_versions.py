"""Unit tests for Program Versioning logic and immutable version history."""

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from pychronicle.storage import SQLiteStorage


def test_program_version_increments_on_source_edit():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        storage = SQLiteStorage(db_path=db_path)

        prog_id = storage.create_program("Version Test", "x = 10\n")
        versions = storage.get_program_versions(prog_id)
        assert len(versions) == 1
        assert versions[0]["version_number"] == 1
        assert versions[0]["source_code"] == "x = 10\n"

        # Update metadata without modifying code -> should NOT create a new version
        storage.update_program(prog_id, description="Added description")
        versions = storage.get_program_versions(prog_id)
        assert len(versions) == 1

        # Update source code -> must create Version 2
        storage.update_program(prog_id, source_code="x = 20\n")
        versions = storage.get_program_versions(prog_id)
        assert len(versions) == 2
        assert versions[0]["version_number"] == 2
        assert versions[0]["source_code"] == "x = 20\n"
        assert versions[1]["version_number"] == 1
        assert versions[1]["source_code"] == "x = 10\n"

        # Update source code again -> Version 3
        storage.update_program(prog_id, source_code="x = 30\n")
        versions = storage.get_program_versions(prog_id)
        assert len(versions) == 3
        assert versions[0]["version_number"] == 3
        assert versions[0]["source_code"] == "x = 30\n"

        latest = storage.get_latest_version(prog_id)
        assert latest is not None
        assert latest["version_number"] == 3
        assert latest["source_code"] == "x = 30\n"
