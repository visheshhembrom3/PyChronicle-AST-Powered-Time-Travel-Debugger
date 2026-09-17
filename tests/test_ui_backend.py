"""Unit tests for ApplicationService API, input validation, and error handling."""

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from pychronicle.application import ApplicationService


def test_ui_backend_input_validation():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        service = ApplicationService(db_path=db_path, seed_demo=False)

        # Empty name
        with pytest.raises(ValueError) as exc:
            service.create_program("", "x = 1\n")
        assert "Program name cannot be empty" in str(exc.value)

        # Empty source
        with pytest.raises(ValueError) as exc:
            service.create_program("Valid Name", "   \n\t  ")
        assert "Source code cannot be empty" in str(exc.value)

        # Syntax error
        with pytest.raises(ValueError) as exc:
            service.create_program("Syntax Err", "def broken(: pass\n")
        assert "Syntax Error" in str(exc.value)


def test_ui_backend_user_runtime_error_graceful_handling():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test.db"
        service = ApplicationService(db_path=db_path, seed_demo=False)

        prog = service.create_program("Error Test", "a = 10\nb = 0\nc = a / b\n")
        res = service.run_program(prog["id"])

        assert res["status"] == "USER_ERROR"
        assert res["exit_code"] == 1
        assert "ZeroDivisionError" in res["error"]
        assert res["execution_id"] is not None

        # Verify execution record preserved in DB
        saved = service.get_execution(res["execution_id"])
        assert saved is not None
        assert saved["status"] == "USER_ERROR"
