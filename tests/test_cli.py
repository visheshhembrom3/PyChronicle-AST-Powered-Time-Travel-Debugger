"""Unit tests for PyChronicle Click CLI commands."""

from pathlib import Path
import sys
import tempfile

# Ensure package is discoverable
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from click.testing import CliRunner
import pytest
from main import cli


def test_cli_debug_command():
    runner = CliRunner()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        target = tmp_path / "simple.py"
        target.write_text("x = 10\ny = 20\n", encoding="utf-8")
        db_path = tmp_path / "cli.db"

        res = runner.invoke(cli, ["debug", str(target), "--db", str(db_path)])
        assert res.exit_code == 0
        assert "Session ID:" in res.output
        assert "SUCCESS" in res.output
        assert "Execution History" in res.output


def test_cli_sessions_list():
    runner = CliRunner()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        target = tmp_path / "simple.py"
        target.write_text("a = 1\n", encoding="utf-8")
        db_path = tmp_path / "cli.db"

        # Run debug first
        runner.invoke(cli, ["debug", str(target), "--db", str(db_path)])

        # List sessions
        res = runner.invoke(cli, ["sessions", "--db", str(db_path)])
        assert res.exit_code == 0
        assert "simple.py" in res.output
        assert "SUCCESS" in res.output


def test_cli_inspect_command():
    runner = CliRunner()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        target = tmp_path / "simple.py"
        target.write_text("a = 1\n", encoding="utf-8")
        db_path = tmp_path / "cli.db"

        runner.invoke(cli, ["debug", str(target), "--db", str(db_path)])

        # Inspect session 1
        res = runner.invoke(cli, ["inspect", "1", "--db", str(db_path)])
        assert res.exit_code == 0
        assert "Session #1" in res.output
        assert "Snapshots" in res.output


def test_cli_replay_command():
    runner = CliRunner()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        target = tmp_path / "simple.py"
        target.write_text("a = 1\n", encoding="utf-8")
        db_path = tmp_path / "cli.db"

        runner.invoke(cli, ["debug", str(target), "--db", str(db_path)])

        # Replay at specific step
        res = runner.invoke(cli, ["replay", "1", "--step", "1", "--db", str(db_path)])
        assert res.exit_code == 0
        assert "Reconstructed State at Step 1" in res.output
