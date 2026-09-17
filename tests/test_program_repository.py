"""Unit tests for SQLiteStorage Program Repository operations, search, filter, and sort."""

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from pychronicle.exceptions import StorageError
from pychronicle.storage import SQLiteStorage


def test_program_repository_create_and_fetch():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        storage = SQLiteStorage(db_path=db_path)

        prog_id = storage.create_program(
            name="Calculator Demo",
            source_code="x = 10\ny = 20\n",
            description="Basic arithmetic demo",
        )
        assert prog_id is not None
        assert prog_id > 0

        prog = storage.get_program(prog_id)
        assert prog is not None
        assert prog["name"] == "Calculator Demo"
        assert prog["source_code"] == "x = 10\ny = 20\n"
        assert prog["description"] == "Basic arithmetic demo"
        assert prog["last_status"] == "NEVER_RUN"
        assert prog["version_count"] == 1
        assert prog["run_count"] == 0


def test_program_repository_unique_name_constraint():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        storage = SQLiteStorage(db_path=db_path)

        storage.create_program("Unique Program", "a = 1\n")
        with pytest.raises(StorageError) as exc_info:
            storage.create_program("Unique Program", "a = 2\n")
        assert "already exists" in str(exc_info.value)


def test_program_repository_search_and_filter():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        storage = SQLiteStorage(db_path=db_path)

        storage.create_program("Factorial Demo", "def fact(n): pass", "Compute factorials")
        storage.create_program("Fibonacci Demo", "def fib(n): pass", "Compute fibonacci numbers")
        storage.create_program("Quick Sort", "def qsort(arr): pass", "Sorting algorithm")

        # Search by name
        res = storage.list_programs(search_query="Factorial")
        assert len(res) == 1
        assert res[0]["name"] == "Factorial Demo"

        # Search by description
        res = storage.list_programs(search_query="algorithm")
        assert len(res) == 1
        assert res[0]["name"] == "Quick Sort"

        # Search by source code
        res = storage.list_programs(search_query="def fib")
        assert len(res) == 1
        assert res[0]["name"] == "Fibonacci Demo"

        # Filter by NEVER_RUN
        res = storage.list_programs(status_filter="NEVER_RUN")
        assert len(res) == 3


def test_program_repository_sorting():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        storage = SQLiteStorage(db_path=db_path)

        storage.create_program("Beta", "b = 1\n")
        storage.create_program("Alpha", "a = 1\n")
        storage.create_program("Gamma", "g = 1\n")

        # Sort Name ASC
        res_asc = storage.list_programs(sort_by="name_asc")
        names_asc = [p["name"] for p in res_asc]
        assert names_asc == ["Alpha", "Beta", "Gamma"]

        # Sort Name DESC
        res_desc = storage.list_programs(sort_by="name_desc")
        names_desc = [p["name"] for p in res_desc]
        assert names_desc == ["Gamma", "Beta", "Alpha"]
