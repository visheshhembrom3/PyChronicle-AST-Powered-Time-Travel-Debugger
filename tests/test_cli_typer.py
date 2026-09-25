"""Tests for PyChronicle Typer CLI."""

from pathlib import Path
import tempfile
import pytest
from typer.testing import CliRunner

from pychronicle.cli import app

runner = CliRunner()


def test_cli_validate_command():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("x = 10\ny = 20\n")
        f_path = Path(f.name)

    try:
        res = runner.invoke(app, ["validate", str(f_path)])
        assert res.exit_code == 0
        assert "Validation Passed" in res.stdout
    finally:
        if f_path.exists():
            f_path.unlink()


def test_cli_validate_command_invalid():
    res = runner.invoke(app, ["validate", "non_existent_file.py"])
    assert res.exit_code == 1
    assert "Validation Failed" in res.stdout


def test_cli_debug_command():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("a = 5\nb = 10\nc = a + b\n")
        f_path = Path(f.name)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_db:
        db_path = Path(tmp_db.name)

    try:
        res = runner.invoke(app, ["debug", str(f_path), "--db", str(db_path)])
        assert res.exit_code == 0
        assert "PyChronicle Execution Result" in res.stdout
        assert "SUCCESS" in res.stdout

        # Check history command
        res_hist = runner.invoke(app, ["history", "--db", str(db_path)])
        assert res_hist.exit_code == 0
        assert "PyChronicle Recorded Sessions" in res_hist.stdout

        # Check replay command
        res_rep = runner.invoke(app, ["replay", "1", "--step", "2", "--db", str(db_path)])
        assert res_rep.exit_code == 0
        assert "Reconstructed State at Step 2" in res_rep.stdout
    finally:
        if f_path.exists():
            f_path.unlink()
        if db_path.exists():
            db_path.unlink()
