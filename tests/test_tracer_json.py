"""Automated tests for PyChronicle tracer.py JSON terminal interface and stdout purity."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile

# Ensure package is discoverable
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest

PYTHON_EXE = sys.executable


def run_tracer_cmd(args, cwd=None):
    """Run `python -m pychronicle.tracer ...` via subprocess and capture stdout, stderr, and exitcode."""
    cmd = [PYTHON_EXE, "-m", "pychronicle.tracer"] + args
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)
    return res


def test_tracer_json_stdout_purity():
    """Verify that stdout contains strictly parseable JSON with no leading/trailing banner text."""
    demo_file = str(Path("examples/demo.py").resolve())
    res = run_tracer_cmd([demo_file])

    assert res.returncode == 0
    # stdout must be parseable directly without trimming non-json text
    payload = json.loads(res.stdout)
    assert isinstance(payload, dict)
    assert payload["tool"] == "PyChronicle"
    assert payload["backend"] == "tracer.py"
    assert payload["execution"]["status"] == "SUCCESS"
    assert payload["execution"]["steps"] > 0
    assert payload["trace"]["engine"] == "sys.settrace"
    assert payload["error"] is None


def test_tracer_json_user_error():
    """Verify that user exceptions produce structured JSON on stdout with exit code 1."""
    exc_file = str(Path("validation/exceptions.py").resolve())
    res = run_tracer_cmd([exc_file])

    assert res.returncode == 1
    payload = json.loads(res.stdout)
    assert payload["execution"]["status"] == "USER_ERROR"
    assert payload["error"] is not None
    assert payload["error"]["type"] == "ZeroDivisionError"
    assert "division by zero" in payload["error"]["message"]
    assert payload["trace"]["events"]["exception"] >= 1


def test_tracer_json_syntax_error():
    """Verify that source parse errors emit JSON with status PYCHRONICLE_ERROR and exit code 2."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        bad_file = Path(tmp) / "bad.py"
        bad_file.write_text("def broken(: pass\n", encoding="utf-8")

        res = run_tracer_cmd([str(bad_file)])
        assert res.returncode == 2
        payload = json.loads(res.stdout)
        assert payload["execution"]["status"] == "PYCHRONICLE_ERROR"
        assert payload["error"]["type"] == "SourceParseError"


def test_tracer_json_missing_file():
    """Verify that non-existent target files emit JSON with exit code 2."""
    res = run_tracer_cmd(["non_existent_file_xyz.py"])
    assert res.returncode == 2
    payload = json.loads(res.stdout)
    assert payload["execution"]["status"] == "PYCHRONICLE_ERROR"
    assert payload["error"]["type"] == "SessionError"


def test_tracer_json_cli_usage_error():
    """Verify that invoking without arguments emits JSON with exit code 3."""
    res = run_tracer_cmd([])
    assert res.returncode == 3
    payload = json.loads(res.stdout)
    assert payload["execution"]["status"] == "CLI_ERROR"
    assert payload["error"]["type"] == "UsageError"


def test_tracer_debug_flag_routes_to_stderr():
    """Verify that --debug outputs diagnostic logs to stderr while stdout remains pure JSON."""
    demo_file = str(Path("examples/demo.py").resolve())
    res = run_tracer_cmd([demo_file, "--debug"])

    assert res.returncode == 0
    # stderr has diagnostic logs
    assert "[PyChronicle Debug]" in res.stderr
    # stdout is still pure JSON
    payload = json.loads(res.stdout)
    assert payload["execution"]["status"] == "SUCCESS"


def test_tracer_mutable_objects_json_and_replay():
    """Verify mutable objects dataset runs via JSON backend and produces accurate final state."""
    mut_file = str(Path("validation/mutable_objects.py").resolve())
    res = run_tracer_cmd([mut_file])

    assert res.returncode == 0
    payload = json.loads(res.stdout)
    assert payload["execution"]["status"] == "SUCCESS"
    mod_vars = payload["final_state"].get("<module>", {})
    assert mod_vars.get("numbers") == "[1, 2, 3, 4]"
    assert mod_vars.get("popped") == "5"
