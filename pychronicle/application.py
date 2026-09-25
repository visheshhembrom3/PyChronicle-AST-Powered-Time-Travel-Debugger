"""PyChronicle Application Service Layer.

Orchestrates program lifecycle management, version history, execution pipeline,
replay state reconstruction, watch variable tracking, and input validation.
Acts as the unified high-level interface for both the Web UI and CLI interfaces.
"""

import ast
from datetime import datetime
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional

from pychronicle.config import ChronicleConfig, DEFAULT_DB_PATH
from pychronicle.exceptions import PyChronicleError, ReplayError, StorageError
from pychronicle.replay import ReplayEngine
from pychronicle.session import (
    STATUS_PYCHRONICLE_ERROR,
    STATUS_SUCCESS,
    STATUS_USER_ERROR,
    SessionResult,
)
from pychronicle.storage import SQLiteStorage
from pychronicle.tracer import run_debug_session

DEFAULT_DEMO_NAME = "5 Digit Palindrome"
DEFAULT_DEMO_DESC = "Checks if a 5-digit number is palindrome using arithmetic reverse loop."
DEFAULT_DEMO_CODE = '''num = 12321

original = num
reverse = 0
temp = num

while temp > 0:
    digit = temp % 10
    reverse = reverse * 10 + digit
    temp = temp // 10

if original == reverse:
    result = "Palindrome"
else:
    result = "Not Palindrome"

print("Number:", original)
print("Reversed:", reverse)
print("Result:", result)
'''


class ApplicationService:
    """Application service coordinating storage, program management, execution, and replay."""

    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB_PATH,
        config: Optional[ChronicleConfig] = None,
        storage: Optional[SQLiteStorage] = None,
        seed_demo: bool = True,
    ) -> None:
        self.db_path = Path(db_path)
        self.config = config or ChronicleConfig(db_path=self.db_path)
        self.storage = storage or SQLiteStorage(self.db_path)

        if seed_demo:
            self.seed_default_demo_if_empty()

    def seed_default_demo_if_empty(self) -> None:
        """Seed the default Factorial Demo program if no programs exist."""
        try:
            existing = self.storage.list_programs()
            if not existing:
                self.create_program(
                    name=DEFAULT_DEMO_NAME,
                    source_code=DEFAULT_DEMO_CODE,
                    description=DEFAULT_DEMO_DESC,
                )
        except Exception:
            pass

    # =========================================================================
    # Validation Helpers
    # =========================================================================

    def validate_program_input(
        self,
        name: str,
        source_code: str,
        program_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> None:
        """Validate program name, duplicate checks, and Python code syntax."""
        if not name or not name.strip():
            raise ValueError("Program name cannot be empty.")

        clean_name = name.strip()
        if len(clean_name) > 255:
            raise ValueError("Program name cannot exceed 255 characters.")

        # Check for duplicate name
        existing = self.storage.get_program_by_name(clean_name, user_id=user_id)
        if existing and (program_id is None or existing["id"] != program_id):
            raise ValueError(f"A program named '{clean_name}' already exists.")

        if not source_code or not source_code.strip():
            raise ValueError("Source code cannot be empty.")

        if len(source_code.encode("utf-8")) > 5 * 1024 * 1024:
            raise ValueError("Source code exceeds maximum allowed size (5MB).")

        # Check Python syntax
        try:
            ast.parse(source_code, filename=f"<{clean_name}>")
        except SyntaxError as e:
            raise ValueError(f"Python Syntax Error at line {e.lineno}: {e.msg}") from e

    # =========================================================================
    # Program Lifecycle Operations
    # =========================================================================

    def create_program(
        self,
        name: str,
        source_code: str,
        description: Optional[str] = "",
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a new program with initial version."""
        clean_name = name.strip()
        self.validate_program_input(clean_name, source_code, user_id=user_id)
        prog_id = self.storage.create_program(
            name=clean_name,
            source_code=source_code,
            description=description.strip() if description else "",
            user_id=user_id,
        )
        prog = self.storage.get_program(prog_id, user_id=user_id)
        if not prog:
            raise StorageError(f"Failed to fetch newly created program {prog_id}.")
        return prog

    def update_program(
        self,
        program_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        source_code: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Update program metadata and create a new version if source changed."""
        prog = self.storage.get_program(program_id, user_id=user_id)
        if not prog:
            raise ValueError(f"Program with ID {program_id} not found.")

        target_name = name.strip() if name is not None else prog["name"]
        target_code = source_code if source_code is not None else prog["source_code"]
        target_desc = description.strip() if description is not None else prog["description"]

        self.validate_program_input(target_name, target_code, program_id=program_id, user_id=user_id)

        self.storage.update_program(
            program_id=program_id,
            name=target_name,
            description=target_desc,
            source_code=target_code,
            user_id=user_id,
        )

        updated = self.storage.get_program(program_id, user_id=user_id)
        if not updated:
            raise StorageError(f"Failed to fetch updated program {program_id}.")
        return updated

    def get_program(self, program_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Retrieve program by ID."""
        return self.storage.get_program(program_id, user_id=user_id)

    def list_programs(
        self,
        search_query: Optional[str] = None,
        status_filter: Optional[str] = None,
        sort_by: Optional[str] = "updated_desc",
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List programs with filtering, search query matching, and sorting."""
        return self.storage.list_programs(
            search_query=search_query,
            status_filter=status_filter,
            sort_by=sort_by,
            user_id=user_id,
        )

    def delete_program(self, program_id: int, user_id: Optional[int] = None) -> bool:
        """Atomically delete a program and all its child versions, executions, and debug traces."""
        prog = self.storage.get_program(program_id, user_id=user_id)
        if not prog:
            return False
        return self.storage.delete_program(program_id, user_id=user_id)

    def duplicate_program(self, program_id: int, new_name: Optional[str] = None, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Duplicate an existing program without copying its execution history."""
        new_id = self.storage.duplicate_program(program_id, new_name=new_name, user_id=user_id)
        new_prog = self.storage.get_program(new_id, user_id=user_id)
        if not new_prog:
            raise StorageError(f"Failed to fetch duplicated program {new_id}.")
        return new_prog

    def get_program_versions(self, program_id: int) -> List[Dict[str, Any]]:
        """List all recorded versions of a program."""
        return self.storage.get_program_versions(program_id)

    # =========================================================================
    # Execution & Debugging Pipeline Operations
    # =========================================================================

    def run_program(
        self,
        program_id: int,
        source_override: Optional[str] = None,
        watch_vars: Optional[List[str]] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Execute and trace a program through the canonical PyChronicle backend.

        Captures stdout, stderr, execution duration, registers an immutable execution record,
        links the debug session, and returns structured execution and timeline data.
        """
        prog = self.storage.get_program(program_id, user_id=user_id)
        if not prog:
            raise ValueError(f"Program ID {program_id} does not exist.")

        code_to_run = source_override if source_override is not None else prog["source_code"]
        started_at = datetime.now().isoformat()

        # Retrieve active version ID
        latest_ver = self.storage.get_latest_version(program_id)
        version_id = latest_ver["id"] if latest_ver else None

        # Pre-create execution record with source snapshot
        exec_id = self.storage.create_execution(
            program_id=program_id,
            version_id=version_id,
            source_snapshot=code_to_run,
            started_at=started_at,
            status="RUNNING",
        )

        # Write code to a deterministic runner file in a managed temp location
        runner_dir = Path(tempfile.gettempdir()) / "pychronicle_runner"
        runner_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in prog["name"])
        target_file = runner_dir / f"{safe_name}_{program_id}_{exec_id}.py"
        target_file.write_text(code_to_run, encoding="utf-8")

        # Execute through canonical tracer backend
        try:
            result: SessionResult = run_debug_session(
                target_path=target_file,
                config=self.config,
                storage=self.storage,
            )
        except Exception as e:
            finished_at = datetime.now().isoformat()
            self.storage.update_execution(
                execution_id=exec_id,
                status=STATUS_PYCHRONICLE_ERROR,
                finished_at=finished_at,
                stdout="",
                stderr=str(e),
                duration_ms=0.0,
                exit_code=2,
                debug_session_id=None,
            )
            return {
                "execution_id": exec_id,
                "program_id": program_id,
                "program_name": prog["name"],
                "status": STATUS_PYCHRONICLE_ERROR,
                "exit_code": 2,
                "stdout": "",
                "stderr": f"Execution failed: {e}",
                "duration_ms": 0.0,
                "total_steps": 0,
                "session_id": None,
                "started_at": started_at,
                "finished_at": finished_at,
                "error": str(e),
                "error_dict": {"type": type(e).__name__, "message": str(e)},
                "source_snapshot": code_to_run,
                "timeline": [],
                "current_step_state": None,
                "watch_values": {},
            }
        finally:
            try:
                if target_file.exists():
                    target_file.unlink(missing_ok=True)
            except Exception:
                pass

        exit_code = 0 if result.status == STATUS_SUCCESS else (1 if result.status == STATUS_USER_ERROR else 2)
        finished_at = result.finished_at or datetime.now().isoformat()

        # Update execution record with session metrics
        self.storage.update_execution(
            execution_id=exec_id,
            status=result.status,
            finished_at=finished_at,
            stdout=result.stdout,
            stderr=result.stderr or (result.error or ""),
            duration_ms=result.duration_ms,
            exit_code=exit_code,
            debug_session_id=result.session_id,
        )

        timeline = []
        initial_state = None
        watch_vals = {}
        if result.replay and result.total_steps > 0:
            timeline = result.replay.get_timeline()
            initial_state = result.replay.state_at(1).to_dict()
            if watch_vars:
                watch_vals = result.replay.get_watch_values_at(1, watch_vars)

        return {
            "execution_id": exec_id,
            "program_id": program_id,
            "program_name": prog["name"],
            "status": result.status,
            "exit_code": exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr or (result.error or ""),
            "duration_ms": round(result.duration_ms, 2),
            "total_steps": result.total_steps,
            "session_id": result.session_id,
            "started_at": result.started_at,
            "finished_at": finished_at,
            "error": result.error,
            "error_dict": result.error_dict,
            "source_snapshot": code_to_run,
            "timeline": timeline,
            "current_step_state": initial_state,
            "watch_values": watch_vals,
        }

    def get_execution(self, execution_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Retrieve execution record by ID including its timeline and step count."""
        record = self.storage.get_execution(execution_id, user_id=user_id)
        if not record:
            return None

        timeline = []
        if record.get("debug_session_id"):
            try:
                replay = ReplayEngine(session_id=record["debug_session_id"], storage=self.storage)
                timeline = replay.get_timeline()
            except Exception:
                timeline = []

        record["timeline"] = timeline
        return record

    def list_executions(self, program_id: int, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """List all execution records for a program ordered newest first."""
        return self.storage.list_executions_for_program(program_id, user_id=user_id)

    def list_all_executions(
        self,
        search_query: Optional[str] = None,
        status_filter: Optional[str] = None,
        sort_by: Optional[str] = "started_desc",
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """List all recorded executions across all programs with search, status filtering, and sorting."""
        return self.storage.list_all_executions(
            search_query=search_query,
            status_filter=status_filter,
            sort_by=sort_by,
            user_id=user_id,
        )

    def copy_execution_to_workspace(
        self,
        execution_id: int,
        new_name: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a new editable program in the workspace using a historical execution's source snapshot."""
        new_prog_id = self.storage.copy_execution_to_program(execution_id, new_name=new_name, user_id=user_id)
        new_prog = self.storage.get_program(new_prog_id, user_id=user_id)
        if not new_prog:
            raise StorageError(f"Failed to fetch copied program {new_prog_id}.")
        return new_prog

    def replay_execution_step(
        self,
        execution_id: int,
        step_num: int,
        watch_vars: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Reconstruct historical execution state at a step without re-executing target code."""
        record = self.storage.get_execution(execution_id)
        if not record:
            raise ValueError(f"Execution {execution_id} not found.")

        session_id = record.get("debug_session_id")
        if not session_id:
            raise ReplayError(f"Execution {execution_id} has no linked debug session.")

        replay = ReplayEngine(session_id=session_id, storage=self.storage)
        if replay.total_steps == 0:
            raise ReplayError(f"Session {session_id} has 0 recorded steps.")

        target_step = max(1, min(step_num, replay.total_steps))
        state = replay.state_at(target_step)

        watch_values = {}
        if watch_vars:
            watch_values = replay.get_watch_values_at(target_step, watch_vars)

        return {
            "execution_id": execution_id,
            "session_id": session_id,
            "step": state.step,
            "total_steps": replay.total_steps,
            "line": state.line,
            "event": state.event,
            "active_scope": state.active_scope,
            "scopes": state.scopes,
            "active_variables": state.active_variables,
            "changes": state.changes,
            "return_value": state.return_value,
            "exception_info": state.exception_info,
            "call_depth": state.call_depth,
            "watch_values": watch_values,
        }

    def get_watch_values(
        self,
        execution_id: int,
        step_num: int,
        watch_vars: List[str],
    ) -> Dict[str, Optional[str]]:
        """Query watched variable values at a step."""
        res = self.replay_execution_step(execution_id, step_num, watch_vars=watch_vars)
        return res.get("watch_values", {})
