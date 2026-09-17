"""Unit tests for RuntimeTracer and TracerBackend execution entry point."""

from pathlib import Path
import sys
import tempfile

# Ensure package is discoverable
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from pychronicle.config import ChronicleConfig
from pychronicle.storage import SQLiteStorage
from pychronicle.tracer import RuntimeTracer, TracerBackend, run_debug_session


def test_tracer_captures_execution_events():
    captured = []
    tracer = RuntimeTracer(
        target_filename="<test_target>",
        on_state_captured=lambda st: captured.append(st),
    )

    code = compile(
        """
def add(a, b):
    return a + b

x = 10
y = 20
z = add(x, y)
""",
        "<test_target>",
        "exec",
    )

    try:
        tracer.start()
        exec(code, {"__name__": "__main__"})
    finally:
        tracer.stop()

    assert len(captured) > 0
    events = [s.event for s in captured]
    assert "line" in events
    assert "call" in events
    assert "return" in events

    # Check scopes
    scopes = set(s.scope for s in captured)
    assert "<module>" in scopes
    assert "add" in scopes


def test_tracer_exception_cleanup():
    captured = []
    tracer = RuntimeTracer(
        target_filename="<test_target>",
        on_state_captured=lambda st: captured.append(st),
    )

    code = compile(
        """
x = 10
y = 0
res = x / y
""",
        "<test_target>",
        "exec",
    )

    try:
        tracer.start()
        with pytest.raises(ZeroDivisionError):
            exec(code, {"__name__": "__main__"})
    finally:
        tracer.stop()

    # Tracer should have caught exception event
    exc_states = [s for s in captured if s.event == "exception"]
    assert len(exc_states) > 0
    assert "ZeroDivisionError" in exc_states[0].exception_info
    assert sys.gettrace() != tracer._trace_dispatch


def test_tracer_backend_run_debug_session():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        target = tmp_path / "backend_test.py"
        target.write_text("a = 5\nb = 10\nc = a * b\n", encoding="utf-8")
        db_path = tmp_path / "backend.db"

        result = run_debug_session(target_path=target, db_path=db_path)
        assert result.status == "SUCCESS"
        assert result.total_steps > 0
        assert result.session_id is not None
        assert result.replay is not None

        final_st = result.replay.last_step()
        assert final_st.get_var("c", "<module>") == "50"


def test_tracer_cleanup_regression_on_runtime_error():
    """Mandatory test: Ensure sys.gettrace() is restored even on unhandled runtime exceptions."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_path = Path(tmp)
        target = tmp_path / "crash_test.py"
        target.write_text("raise RuntimeError('intentional failure')\n", encoding="utf-8")
        db_path = tmp_path / "crash.db"

        result = run_debug_session(target_path=target, db_path=db_path)
        assert result.status == "USER_ERROR"
        assert "intentional failure" in result.error
        # Verify trace was cleaned up
        assert sys.gettrace() is None
