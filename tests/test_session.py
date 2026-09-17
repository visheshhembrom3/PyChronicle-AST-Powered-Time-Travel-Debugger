"""Unit tests for DebugSession orchestration."""

from pathlib import Path
import sys
import tempfile

# Ensure package is discoverable
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from pychronicle.config import ChronicleConfig
from pychronicle.exceptions import SessionError
from pychronicle.session import DebugSession
from pychronicle.storage import SQLiteStorage


def test_session_successful_run():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_dir = Path(tmp)
        src_file = tmp_dir / "target.py"
        src_file.write_text("a = 100\nb = 200\nc = a + b\n", encoding="utf-8")
        db_file = tmp_dir / "debug.db"

        config = ChronicleConfig(db_path=db_file)
        storage = SQLiteStorage(db_path=db_file)
        session = DebugSession(target_path=src_file, config=config, storage=storage)

        result = session.run()
        assert result.status == "SUCCESS"
        assert result.total_steps > 0
        assert result.replay is not None

        final_st = result.replay.last_step()
        assert final_st.get_var("c", "<module>") == "300"


def test_session_user_runtime_error():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_dir = Path(tmp)
        src_file = tmp_dir / "error_target.py"
        src_file.write_text("x = 10\ny = 0\nz = x / y\n", encoding="utf-8")
        db_file = tmp_dir / "debug.db"

        config = ChronicleConfig(db_path=db_file)
        storage = SQLiteStorage(db_path=db_file)
        session = DebugSession(target_path=src_file, config=config, storage=storage)

        result = session.run()
        assert result.status == "USER_ERROR"
        assert "ZeroDivisionError" in result.error
        assert result.total_steps > 0


def test_session_syntax_error():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_dir = Path(tmp)
        src_file = tmp_dir / "bad_syntax.py"
        src_file.write_text("def broken(: pass\n", encoding="utf-8")
        db_file = tmp_dir / "debug.db"

        config = ChronicleConfig(db_path=db_file)
        storage = SQLiteStorage(db_path=db_file)
        session = DebugSession(target_path=src_file, config=config, storage=storage)

        result = session.run()
        assert result.status == "PYCHRONICLE_ERROR"
        assert result.error_dict is not None
        assert result.error_dict["type"] == "SourceParseError"
        assert result.total_steps == 0


def test_session_missing_file():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_file = Path(tmp) / "debug.db"
        storage = SQLiteStorage(db_path=db_file)
        missing_file = Path(tmp) / "does_not_exist.py"
        session = DebugSession(target_path=missing_file, storage=storage)

        result = session.run()
        assert result.status == "PYCHRONICLE_ERROR"
        assert result.error_dict is not None
        assert result.error_dict["type"] == "SessionError"
        assert "Target file does not exist" in result.error
