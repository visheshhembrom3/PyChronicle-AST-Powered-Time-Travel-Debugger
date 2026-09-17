"""PyChronicle Runtime Execution Tracer & Backend Execution Entry Point.

This module is the executable runtime backend entry point for PyChronicle.
It owns the debugging execution lifecycle: AST transformation coordination,
sys.settrace() event capture, isolated exec() execution, state delta generation,
SQLite storage persistence, and machine-readable JSON output emission to stdout.
"""

from datetime import datetime
import io
import json
import os
from pathlib import Path
import sys
import traceback
from types import FrameType
from typing import Any, Callable, Dict, List, Optional, Set

# Ensure parent directory is in sys.path when executed directly as script
_pkg_root = str(Path(__file__).parent.parent.resolve())
if _pkg_root not in sys.path:
    sys.path.insert(0, _pkg_root)

from pychronicle.ast_rewriter import ASTRewriter
from pychronicle.config import ChronicleConfig, DEFAULT_DB_PATH, IGNORED_VARIABLE_NAMES, INTERNAL_HOOK_NAME
from pychronicle.delta import DeltaGenerator, StateDelta
from pychronicle.exceptions import (
    PyChronicleError,
    SessionError,
    SourceParseError,
    StorageError,
    TraceError,
)
from pychronicle.replay import ReplayEngine
from pychronicle.serializer import compute_fingerprint, safe_deep_copy, serialize_value
from pychronicle.session import (
    STATUS_CLI_ERROR,
    STATUS_INTERRUPTED,
    STATUS_PYCHRONICLE_ERROR,
    STATUS_SUCCESS,
    STATUS_USER_ERROR,
    SessionResult,
)
from pychronicle.state import CapturedState
from pychronicle.storage import SQLiteStorage


class RuntimeTracer:
    """Manages sys.settrace execution tracing for a target Python program."""

    def __init__(
        self,
        target_filename: Optional[str] = None,
        on_state_captured: Optional[Callable[[CapturedState], None]] = None,
    ) -> None:
        self.target_filename = (
            os.path.abspath(target_filename)
            if target_filename and target_filename not in ("<target>", "<string>")
            else target_filename
        )
        self.on_state_captured = on_state_captured
        self.captured_states: List[CapturedState] = []
        self.step_counter: int = 0
        self._is_tracing: bool = False
        self._original_trace_func = None
        self._call_stack: List[str] = []

    def _should_trace_frame(self, frame: FrameType) -> bool:
        """Determine if a frame belongs to the target program and should be traced."""
        filename = frame.f_code.co_filename

        # Filter out frozen modules, builtins, and standard libraries
        if not filename or filename.startswith("<frozen") or "<pytest" in filename:
            return False

        # If target filename was specified and matches the frame, trace it!
        if self.target_filename:
            if self.target_filename in ("<target>", "<string>"):
                if filename in ("<target>", "<string>", self.target_filename):
                    return True
            else:
                try:
                    abs_frame_path = os.path.abspath(filename)
                    if os.path.samefile(abs_frame_path, self.target_filename):
                        return True
                except (OSError, ValueError):
                    pass
                if os.path.abspath(filename).lower() == self.target_filename.lower():
                    return True

        # Filter out pychronicle package internals
        pkg_dir = str(Path(__file__).parent.resolve()).lower()
        if os.path.abspath(filename).lower().startswith(pkg_dir):
            return False

        # Filter out stdlib & site-packages
        normalized = filename.lower()
        if "site-packages" in normalized or "lib\\python" in normalized or "lib/python" in normalized:
            return False

        return True

    def _extract_scope(self, frame: FrameType) -> str:
        """Resolve qualified scope name for the current frame."""
        code = frame.f_code
        if code.co_name == "<module>":
            return "<module>"

        # Python 3.11+ provides co_qualname
        qualname = getattr(code, "co_qualname", None)
        if qualname:
            return qualname

        return code.co_name

    def _capture_frame_variables(self, frame: FrameType) -> Dict[str, Dict[str, Any]]:
        """Safely capture and serialize local variables from frame."""
        variables: Dict[str, Dict[str, Any]] = {}
        try:
            locals_copy = dict(frame.f_locals)
            for var_name, raw_val in locals_copy.items():
                if var_name in IGNORED_VARIABLE_NAMES or var_name.startswith("__pychronicle"):
                    continue
                # Detach in-place mutable value snapshot
                cloned_val = safe_deep_copy(raw_val)
                variables[var_name] = serialize_value(cloned_val)
        except Exception as e:
            variables["_capture_error"] = serialize_value(str(e))

        return variables

    def _trace_dispatch(self, frame: FrameType, event: str, arg: Any) -> Any:
        """Main sys.settrace dispatch function."""
        if not self._is_tracing:
            return None

        if not self._should_trace_frame(frame):
            return self._trace_dispatch

        lineno = frame.f_lineno
        scope = self._extract_scope(frame)
        call_depth = len(self._call_stack)

        return_val_repr = None
        exception_repr = None

        if event == "call":
            self._call_stack.append(scope)
            call_depth = len(self._call_stack)
        elif event == "return":
            return_val_repr = repr(arg)
            if self._call_stack:
                self._call_stack.pop()
        elif event == "exception":
            exc_type, exc_val, _ = arg
            exception_repr = f"{exc_type.__name__}: {exc_val}"

        self.step_counter += 1
        serialized_vars = self._capture_frame_variables(frame)
        fingerprints = {
            var_name: info.get("fingerprint", "")
            for var_name, info in serialized_vars.items()
        }

        state = CapturedState(
            step=self.step_counter,
            line=lineno,
            event=event,
            scope=scope,
            variables=serialized_vars,
            fingerprints=fingerprints,
            call_depth=call_depth,
            return_value=return_val_repr,
            exception_info=exception_repr,
        )

        self.captured_states.append(state)

        if self.on_state_captured:
            try:
                self.on_state_captured(state)
            except Exception as e:
                raise TraceError(f"Error in state callback: {e}", step=self.step_counter) from e

        return self._trace_dispatch

    def start(self) -> None:
        """Start execution tracing."""
        self._is_tracing = True
        self._original_trace_func = sys.gettrace()
        sys.settrace(self._trace_dispatch)

    def stop(self) -> None:
        """Stop execution tracing and restore previous tracer."""
        self._is_tracing = False
        sys.settrace(self._original_trace_func)


class TracerBackend:
    """Backend execution manager owning target compilation, execution, tracing, and persistence."""

    def __init__(
        self,
        target_path: str | Path,
        config: Optional[ChronicleConfig] = None,
        storage: Optional[SQLiteStorage] = None,
    ) -> None:
        self.target_path = Path(target_path).resolve()
        self.config = config or ChronicleConfig()
        self.storage = storage or SQLiteStorage(self.config.db_path)
        self.ast_rewriter = ASTRewriter(hook_name=self.config.hook_name)
        self.delta_generator = DeltaGenerator()
        self.deltas: List[StateDelta] = []
        self.session_id: Optional[int] = None
        self.tracer: Optional[RuntimeTracer] = None

    def _on_state_captured(self, state: CapturedState) -> None:
        """Callback invoked by RuntimeTracer on each discrete execution event."""
        delta = self.delta_generator.compute_delta(state)
        self.deltas.append(delta)

    def execute(self) -> SessionResult:
        """Execute the target Python program with AST instrumentation and sys.settrace runtime tracing."""
        started_at = datetime.now().isoformat()
        filename_str = str(self.target_path)
        event_counts = {"call": 0, "line": 0, "return": 0, "exception": 0}

        if not self.target_path.exists():
            err_dict = {"type": "SessionError", "message": f"Target file does not exist: {self.target_path}"}
            return SessionResult(
                session_id=None,
                filename=filename_str,
                status=STATUS_PYCHRONICLE_ERROR,
                total_steps=0,
                started_at=started_at,
                finished_at=datetime.now().isoformat(),
                error=err_dict["message"],
                error_dict=err_dict,
                event_counts=event_counts,
                final_state={},
                database_path=str(self.storage.db_path),
                replay=None,
            )

        if not self.target_path.is_file():
            err_dict = {"type": "SessionError", "message": f"Target path is not a file: {self.target_path}"}
            return SessionResult(
                session_id=None,
                filename=filename_str,
                status=STATUS_PYCHRONICLE_ERROR,
                total_steps=0,
                started_at=started_at,
                finished_at=datetime.now().isoformat(),
                error=err_dict["message"],
                error_dict=err_dict,
                event_counts=event_counts,
                final_state={},
                database_path=str(self.storage.db_path),
                replay=None,
            )

        try:
            source_code = self.target_path.read_text(encoding="utf-8")
        except Exception as e:
            err_dict = {"type": type(e).__name__, "message": f"Failed to read source file '{self.target_path}': {e}"}
            return SessionResult(
                session_id=None,
                filename=filename_str,
                status=STATUS_PYCHRONICLE_ERROR,
                total_steps=0,
                started_at=started_at,
                finished_at=datetime.now().isoformat(),
                error=err_dict["message"],
                error_dict=err_dict,
                event_counts=event_counts,
                final_state={},
                database_path=str(self.storage.db_path),
                replay=None,
            )

        self.session_id = self.storage.create_session(filename=filename_str)

        status = STATUS_SUCCESS
        error_msg: Optional[str] = None
        error_dict: Optional[Dict[str, str]] = None

        # 1. AST Parse & Instrumentation
        try:
            if self.config.enable_ast_hooks:
                tree, _ = self.ast_rewriter.parse_and_rewrite(source_code, filename=filename_str)
            else:
                tree = self.ast_rewriter.parse_source(source_code, filename=filename_str)

            code_obj = self.ast_rewriter.compile_tree(tree, filename=filename_str)
        except SourceParseError as e:
            error_dict = {"type": "SourceParseError", "message": str(e)}
            self.storage.update_session(
                session_id=self.session_id,
                status=STATUS_PYCHRONICLE_ERROR,
                error=f"Syntax/Parse Error: {e}",
            )
            return SessionResult(
                session_id=self.session_id,
                filename=filename_str,
                status=STATUS_PYCHRONICLE_ERROR,
                total_steps=0,
                started_at=started_at,
                finished_at=datetime.now().isoformat(),
                error=f"Source Parse Error: {e}",
                error_dict=error_dict,
                event_counts=event_counts,
                final_state={},
                database_path=str(self.storage.db_path),
                replay=None,
            )
        except Exception as e:
            error_dict = {"type": type(e).__name__, "message": str(e)}
            self.storage.update_session(
                session_id=self.session_id,
                status=STATUS_PYCHRONICLE_ERROR,
                error=f"Internal AST/Compile Error: {e}",
            )
            return SessionResult(
                session_id=self.session_id,
                filename=filename_str,
                status=STATUS_PYCHRONICLE_ERROR,
                total_steps=0,
                started_at=started_at,
                finished_at=datetime.now().isoformat(),
                error=str(e),
                error_dict=error_dict,
                event_counts=event_counts,
                final_state={},
                database_path=str(self.storage.db_path),
                replay=None,
            )

        # 2. Prepare isolated user execution namespace
        hook_name = self.config.hook_name

        def _hook_callback(lineno: int, event: str) -> None:
            pass

        user_globals: Dict[str, Any] = {
            "__name__": "__main__",
            "__file__": filename_str,
            "__doc__": None,
            "__builtins__": __builtins__,
            hook_name: _hook_callback,
        }

        # 3. Configure Runtime Tracer
        self.tracer = RuntimeTracer(
            target_filename=filename_str,
            on_state_captured=self._on_state_captured,
        )

        prev_cwd = os.getcwd()
        target_dir = self.target_path.parent
        os.chdir(target_dir)

        # 4. Execute target program under sys.settrace()
        t_exec_start = datetime.now()
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()
        try:
            sys.stdout = captured_stdout
            sys.stderr = captured_stderr
            self.tracer.start()
            exec(code_obj, user_globals, user_globals)
        except KeyboardInterrupt:
            status = STATUS_INTERRUPTED
            error_msg = "Execution interrupted by user (KeyboardInterrupt)"
            error_dict = {"type": "KeyboardInterrupt", "message": error_msg}
        except Exception as e:
            status = STATUS_USER_ERROR
            tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
            error_msg = "".join(tb_lines).strip()
            error_dict = {"type": type(e).__name__, "message": str(e)}
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            if self.tracer:
                self.tracer.stop()
            os.chdir(prev_cwd)

        duration_ms = (datetime.now() - t_exec_start).total_seconds() * 1000.0
        stdout_str = captured_stdout.getvalue()
        stderr_str = captured_stderr.getvalue()

        # In verbose mode, echo target stdout to stderr
        if self.config.verbose and stdout_str:
            sys.stderr.write(f"[Target stdout]\n{stdout_str}\n")

        # Calculate actual execution event stats
        if self.tracer:
            for st in self.tracer.captured_states:
                if st.event in event_counts:
                    event_counts[st.event] += 1

        # 5. Persist State Deltas to SQLite Storage
        try:
            self.storage.save_snapshots_batch(self.session_id, self.deltas)
            finished_at = datetime.now().isoformat()
            self.storage.update_session(
                session_id=self.session_id,
                status=status,
                finished_at=finished_at,
                error=error_msg,
            )
        except StorageError as e:
            raise SessionError(f"Failed to persist session snapshots: {e}") from e

        # 6. Initialize Replay Engine and extract final state
        replay_engine = None
        final_state: Dict[str, Dict[str, str]] = {}
        if self.deltas:
            replay_engine = ReplayEngine(session_id=self.session_id, storage=self.storage)
            last_snap = replay_engine.last_step()
            if last_snap:
                final_state = last_snap.scopes

        return SessionResult(
            session_id=self.session_id,
            filename=filename_str,
            status=status,
            total_steps=len(self.deltas),
            started_at=started_at,
            finished_at=datetime.now().isoformat(),
            error=error_msg,
            error_dict=error_dict,
            event_counts=event_counts,
            final_state=final_state,
            database_path=str(self.storage.db_path),
            replay=replay_engine,
            stdout=stdout_str,
            stderr=stderr_str,
            duration_ms=duration_ms,
        )


def run_debug_session(
    target_path: str | Path,
    db_path: Optional[str | Path] = None,
    config: Optional[ChronicleConfig] = None,
    storage: Optional[SQLiteStorage] = None,
) -> SessionResult:
    """Primary public callable backend entry point to debug and trace a target Python script.

    Args:
        target_path: Path to the Python file to debug.
        db_path: Optional SQLite database path.
        config: Optional ChronicleConfig.
        storage: Optional SQLiteStorage instance.

    Returns:
        SessionResult containing session ID, status, total steps, error info, and ReplayEngine.
    """
    cfg = config or ChronicleConfig(db_path=Path(db_path) if db_path else DEFAULT_DB_PATH)
    if db_path and not config:
        cfg.db_path = Path(db_path)

    store = storage or SQLiteStorage(cfg.db_path)
    backend = TracerBackend(target_path=target_path, config=cfg, storage=store)
    return backend.execute()


def _main_cli() -> None:
    """CLI backend entry point when executing `python -m pychronicle.tracer <target.py>`.

    Outputs ONLY pure, valid, machine-readable JSON to stdout.
    All diagnostic or debug messages are routed exclusively to stderr.
    """
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        error_payload = {
            "tool": "PyChronicle",
            "version": "0.1.0",
            "backend": "tracer.py",
            "execution": {
                "status": STATUS_CLI_ERROR,
            },
            "error": {
                "type": "UsageError",
                "message": "Missing target file argument. Usage: python -m pychronicle.tracer <target.py> [--db <path>] [--debug] [--pretty]",
            },
        }
        sys.stdout.write(json.dumps(error_payload, indent=2) + "\n")
        sys.exit(3)

    db_arg = DEFAULT_DB_PATH
    is_debug = False
    is_pretty = True  # Format nicely by default
    target_arg = None

    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg == "--db":
            if idx + 1 < len(args):
                db_arg = Path(args[idx + 1])
                idx += 2
                continue
        elif arg in ("--debug", "-d"):
            is_debug = True
            idx += 1
            continue
        elif arg in ("--pretty", "-p"):
            is_pretty = True
            idx += 1
            continue
        elif arg == "--compact":
            is_pretty = False
            idx += 1
            continue
        elif not arg.startswith("-") and target_arg is None:
            target_arg = arg
            idx += 1
            continue
        else:
            idx += 1

    if target_arg is None:
        error_payload = {
            "tool": "PyChronicle",
            "version": "0.1.0",
            "backend": "tracer.py",
            "execution": {
                "status": STATUS_CLI_ERROR,
            },
            "error": {
                "type": "UsageError",
                "message": "No target Python file specified.",
            },
        }
        sys.stdout.write(json.dumps(error_payload, indent=2) + "\n")
        sys.exit(3)

    target_path = Path(target_arg).resolve()

    if is_debug:
        sys.stderr.write(f"[PyChronicle Debug] Target: {target_path}, DB: {db_arg}\n")

    try:
        result = run_debug_session(target_path=target_path, db_path=db_arg)
        json_output = result.to_json(indent=2 if is_pretty else None)
        sys.stdout.write(json_output + "\n")

        if is_debug and result.error:
            sys.stderr.write(f"[PyChronicle Debug] Error: {result.error}\n")

        # Exit code determination
        if result.status == STATUS_SUCCESS:
            sys.exit(0)
        elif result.status == STATUS_USER_ERROR:
            sys.exit(1)
        elif result.status == STATUS_PYCHRONICLE_ERROR:
            sys.exit(2)
        else:
            sys.exit(1)

    except Exception as e:
        if is_debug:
            sys.stderr.write(f"[PyChronicle Debug] Uncaught Exception: {traceback.format_exc()}\n")

        err_payload = {
            "tool": "PyChronicle",
            "version": "0.1.0",
            "backend": "tracer.py",
            "execution": {
                "target": str(target_path),
                "status": STATUS_PYCHRONICLE_ERROR,
            },
            "error": {
                "type": type(e).__name__,
                "message": str(e),
            },
        }
        sys.stdout.write(json.dumps(err_payload, indent=2 if is_pretty else None) + "\n")
        sys.exit(2)


main = _main_cli

if __name__ == "__main__":
    _main_cli()
