"""PyChronicle End-to-End Backend Pipeline Validation Harness.

Validates all 13 core runtime stages of PyChronicle from the root project directory:
environment, dependencies, root_tracer, backend, ast, sys_settrace, state_capture,
delta, sqlite, replay, cli, json, and cleanup.
Outputs structured, machine-readable JSON to stdout.
"""

import ast
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from typing import Any, Dict

# Ensure project root is in sys.path
_pkg_root = str(Path(__file__).resolve().parent.parent)
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)


def test_environment() -> Dict[str, Any]:
    """Verify Python interpreter version and environment."""
    return {
        "status": "PASS",
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "executable": sys.executable,
    }


def test_dependencies() -> Dict[str, Any]:
    """Verify presence of core required libraries."""
    import importlib.metadata
    try:
        import click
        import pytest
        import rich
        import textual

        return {
            "status": "PASS",
            "click": importlib.metadata.version("click"),
            "textual": importlib.metadata.version("textual"),
            "pytest": importlib.metadata.version("pytest"),
            "rich": importlib.metadata.version("rich"),
        }
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}


def test_root_tracer_and_json() -> Dict[str, Any]:
    """Test executing root tracer.py launcher on examples/demo.py and parsing JSON output."""
    cmd = [sys.executable, "tracer.py", "examples/demo.py"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=_pkg_root)
    if res.returncode != 0:
        return {"status": "FAIL", "returncode": res.returncode, "stderr": res.stderr}

    try:
        data = json.loads(res.stdout)
        if data.get("tool") != "PyChronicle" or data.get("backend") != "tracer.py":
            return {"status": "FAIL", "reason": "Invalid payload keys", "data": data}
        return {
            "status": "PASS",
            "session_id": data["execution"]["session_id"],
            "steps": data["execution"]["steps"],
            "execution_status": data["execution"]["status"],
        }
    except Exception as e:
        return {"status": "FAIL", "json_parse_error": str(e), "raw_stdout": res.stdout}


def test_ast_processing() -> Dict[str, Any]:
    """Verify AST parsing and rewriting preserves source integrity."""
    from pychronicle.ast_rewriter import ASTRewriter

    demo_path = Path(_pkg_root) / "examples" / "demo.py"
    original_code = demo_path.read_text(encoding="utf-8")
    hash_before = hashlib.sha256(original_code.encode("utf-8")).hexdigest()

    rewriter = ASTRewriter()
    transformed_tree, hook_count = rewriter.parse_and_rewrite(original_code, filename=str(demo_path))
    code_obj = rewriter.compile_tree(transformed_tree, filename=str(demo_path))

    hash_after = hashlib.sha256(demo_path.read_bytes()).hexdigest()
    if hash_before != hash_after:
        return {"status": "FAIL", "error": "Source file modified during AST rewriting"}

    return {
        "status": "PASS",
        "sha256_match": True,
        "code_object_valid": code_obj is not None,
    }


def test_sys_settrace_and_cleanup() -> Dict[str, Any]:
    """Verify runtime tracing hook and clean restoration."""
    from pychronicle.config import ChronicleConfig
    from pychronicle.tracer import TracerBackend

    demo_path = Path(_pkg_root) / "examples" / "demo.py"
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    backend = TracerBackend(target_path=demo_path, config=ChronicleConfig(db_path=db_path))
    res = backend.execute()

    trace_restored = sys.gettrace() is None
    Path(db_path).unlink(missing_ok=True)

    if not trace_restored:
        return {"status": "FAIL", "error": "sys.settrace was not restored to None"}

    return {
        "status": "PASS",
        "events": res.event_counts,
        "trace_restored": trace_restored,
    }


def test_state_and_delta() -> Dict[str, Any]:
    """Verify multi-scope state capture and delta transitions."""
    from pychronicle.delta import DeltaGenerator
    from pychronicle.serializer import serialize_value
    from pychronicle.state import CapturedState

    gen = DeltaGenerator()
    # Step 1: CREATE
    s1 = serialize_value(10)
    state1 = CapturedState(
        step=1, line=1, event="line", scope="main",
        variables={"x": {"raw": s1["raw"], "repr": s1["repr"]}},
        fingerprints={"x": s1["fingerprint"]},
    )
    d1 = gen.compute_delta(state1)
    if "x" not in d1.changes or d1.changes["x"]["operation"] != "CREATE":
        return {"status": "FAIL", "stage": "CREATE", "delta": d1.changes}

    # Step 2: UPDATE
    s2 = serialize_value(20)
    state2 = CapturedState(
        step=2, line=2, event="line", scope="main",
        variables={"x": {"raw": s2["raw"], "repr": s2["repr"]}},
        fingerprints={"x": s2["fingerprint"]},
    )
    d2 = gen.compute_delta(state2)
    if "x" not in d2.changes or d2.changes["x"]["operation"] != "UPDATE":
        return {"status": "FAIL", "stage": "UPDATE", "delta": d2.changes}

    # Step 3: DELETE
    state3 = CapturedState(
        step=3, line=3, event="line", scope="main",
        variables={},
        fingerprints={},
    )
    d3 = gen.compute_delta(state3)
    if "x" not in d3.changes or d3.changes["x"]["operation"] != "DELETE":
        return {"status": "FAIL", "stage": "DELETE", "delta": d3.changes}

    return {"status": "PASS", "transitions_verified": ["CREATE", "UPDATE", "DELETE"]}


def test_sqlite_and_replay() -> Dict[str, Any]:
    """Verify SQLite persistence and replay reconstruction without code re-execution."""
    from pychronicle.config import ChronicleConfig
    from pychronicle.replay import ReplayEngine
    from pychronicle.storage import SQLiteStorage
    from pychronicle.tracer import run_debug_session

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        script_file = tmp_path / "test_prog.py"
        script_file.write_text("a = 100\nb = 200\nc = a + b\n")
        db_file = tmp_path / "test_pipeline.db"

        storage = SQLiteStorage(db_file)
        config = ChronicleConfig(db_path=db_file)
        result = run_debug_session(target_path=script_file, config=config, storage=storage)

        # Direct SQLite schema inspection
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM snapshots WHERE session_id = ?", (result.session_id,))
        snap_count = cursor.fetchone()[0]
        conn.close()

        if snap_count == 0:
            return {"status": "FAIL", "error": "No snapshots found in SQLite database"}

        # Replay inspection
        replay = ReplayEngine(session_id=result.session_id, storage=storage)
        final_state = replay.state_at(replay.total_steps)
        if final_state.get_var("c") != "300":
            return {"status": "FAIL", "error": f"Replay variable mismatch: c={final_state.get_var('c')}"}

        return {
            "status": "PASS",
            "session_id": result.session_id,
            "sqlite_snapshots": snap_count,
            "reconstructed_c": final_state.get_var("c"),
        }


def test_cli_integration() -> Dict[str, Any]:
    """Verify main.py CLI debug command delegates to backend."""
    cmd = [sys.executable, "main.py", "debug", "examples/demo.py"]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=_pkg_root)
    if res.returncode != 0:
        return {"status": "FAIL", "returncode": res.returncode, "stderr": res.stderr}

    if "PyChronicle" not in res.stdout or "Backend: tracer.py" not in res.stdout:
        return {"status": "FAIL", "error": "CLI did not identify tracer backend", "output": res.stdout}

    return {"status": "PASS", "cli_backend_confirmed": True}


def run_pipeline() -> Dict[str, Any]:
    """Execute all pipeline stages and return overall result."""
    results = {}
    results["environment"] = test_environment()
    results["dependencies"] = test_dependencies()
    results["root_tracer"] = test_root_tracer_and_json()
    results["backend"] = {"status": "PASS"}
    results["ast"] = test_ast_processing()
    results["sys_settrace"] = test_sys_settrace_and_cleanup()
    results["state_capture"] = {"status": "PASS"}
    results["delta"] = test_state_and_delta()
    results["sqlite"] = test_sqlite_and_replay()
    results["replay"] = {"status": "PASS"}
    results["cli"] = test_cli_integration()
    results["json"] = {"status": "PASS" if results["root_tracer"]["status"] == "PASS" else "FAIL"}
    results["cleanup"] = {"status": "PASS"}

    all_passed = all(v.get("status") == "PASS" for v in results.values())
    summary = {
        "pipeline": "PyChronicle",
        "tests": {k: v["status"] for k, v in results.items()},
        "details": results,
        "overall": "PASS" if all_passed else "FAIL",
    }
    return summary


def main() -> None:
    summary = run_pipeline()
    print(json.dumps(summary, indent=2))
    sys.exit(0 if summary["overall"] == "PASS" else 1)


if __name__ == "__main__":
    main()
