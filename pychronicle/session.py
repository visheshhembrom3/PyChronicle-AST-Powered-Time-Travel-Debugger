"""PyChronicle Session Data Model and Metadata Representation.

Defines session results, execution statuses, structured JSON schemas, and lifecycle models.
Note: Runtime debugging execution is owned and launched by pychronicle.tracer.
"""

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from pychronicle.config import ChronicleConfig, DEFAULT_DB_PATH
from pychronicle.replay import ReplayEngine
from pychronicle.storage import SQLiteStorage


# Execution Status Constants
STATUS_SUCCESS = "SUCCESS"
STATUS_USER_ERROR = "USER_ERROR"
STATUS_PYCHRONICLE_ERROR = "PYCHRONICLE_ERROR"
STATUS_INTERNAL_ERROR = "INTERNAL_ERROR"
STATUS_INTERRUPTED = "INTERRUPTED"
STATUS_RUNNING = "RUNNING"
STATUS_CLI_ERROR = "CLI_ERROR"


@dataclass
class SessionMetadata:
    """Metadata representing a recorded debugging session."""

    session_id: int
    filename: str
    started_at: str
    finished_at: Optional[str] = None
    status: str = STATUS_RUNNING
    error: Optional[str] = None
    total_steps: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "filename": self.filename,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "error": self.error,
            "total_steps": self.total_steps,
        }


@dataclass
class SessionResult:
    """Result summary of a completed debug session."""

    session_id: Optional[int]
    filename: str
    status: str  # "SUCCESS", "USER_ERROR", "PYCHRONICLE_ERROR", "INTERRUPTED"
    total_steps: int
    started_at: str
    finished_at: str
    error: Optional[str] = None
    error_dict: Optional[Dict[str, str]] = None
    event_counts: Dict[str, int] = field(default_factory=lambda: {"call": 0, "line": 0, "return": 0, "exception": 0})
    final_state: Dict[str, Dict[str, str]] = field(default_factory=dict)
    database_path: Optional[str] = None
    replay: Optional[ReplayEngine] = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert result into standard structured machine-readable dictionary."""
        return {
            "tool": "PyChronicle",
            "version": "0.1.0",
            "backend": "tracer.py",
            "execution": {
                "target": self.filename,
                "status": self.status,
                "session_id": self.session_id,
                "steps": self.total_steps,
                "snapshots": self.total_steps,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            },
            "trace": {
                "engine": "sys.settrace",
                "events": self.event_counts,
            },
            "storage": {
                "database": self.database_path or str(DEFAULT_DB_PATH),
            },
            "final_state": self.final_state,
            "error": self.error_dict,
        }

    def to_json(self, indent: Optional[int] = 2) -> str:
        """Serialize result to valid JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


class DebugSession:
    """Session adapter delegating execution to the primary tracer backend (pychronicle.tracer).

    Maintained for API compatibility while runtime execution is owned by tracer.py.
    """

    def __init__(
        self,
        target_path: str | Path,
        config: Optional[ChronicleConfig] = None,
        storage: Optional[SQLiteStorage] = None,
    ) -> None:
        self.target_path = Path(target_path).resolve()
        self.config = config or ChronicleConfig()
        self.storage = storage or SQLiteStorage(self.config.db_path)

    def run(self) -> SessionResult:
        """Delegate target execution to the primary runtime tracer backend."""
        from pychronicle.tracer import run_debug_session

        return run_debug_session(
            target_path=self.target_path,
            config=self.config,
            storage=self.storage,
        )
