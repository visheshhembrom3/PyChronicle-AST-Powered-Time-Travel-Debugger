"""PyChronicle Debugger Core Engine.

Coordinates AST instrumentation, sys.settrace() runtime tracing, execution event
capture (line, call, return, exception), differential delta state capture, and
persistence into SQLite storage.
"""

from datetime import datetime
import os
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Optional, Union

from pychronicle.ast_parser import parse_file, parse_source
from pychronicle.ast_rewriter import ASTRewriter, rewrite_tree
from pychronicle.config import ChronicleConfig, DEFAULT_DB_PATH
from pychronicle.delta import DeltaGenerator, StateDelta, calculate_delta
from pychronicle.exceptions import PyChronicleError, TraceError
from pychronicle.replay import ReplayEngine
from pychronicle.session import SessionResult
from pychronicle.state import CapturedState
from pychronicle.storage import SQLiteStorage
from pychronicle.tracer import RuntimeTracer, TracerBackend, run_debug_session


class Debugger:
    """Core PyChronicle time-travel execution tracer and debugger engine."""

    def __init__(
        self,
        target_path: Union[str, Path],
        db_path: Union[str, Path] = DEFAULT_DB_PATH,
        config: Optional[ChronicleConfig] = None,
        storage: Optional[SQLiteStorage] = None,
    ) -> None:
        self.target_path = Path(target_path).resolve()
        self.config = config or ChronicleConfig(db_path=Path(db_path) if db_path != ":memory:" else Path(":memory:"))
        self.storage = storage or SQLiteStorage(db_path=db_path)
        self.backend = TracerBackend(
            target_path=self.target_path,
            config=self.config,
            storage=self.storage,
        )

    def run(self) -> SessionResult:
        """Execute the target Python file under sys.settrace() and record execution history."""
        return self.backend.execute()

    @property
    def session_id(self) -> Optional[int]:
        """Return the active recorded session ID."""
        return self.backend.session_id


def run_debugger(
    target_path: Union[str, Path],
    db_path: Union[str, Path] = DEFAULT_DB_PATH,
    verbose: bool = False,
) -> SessionResult:
    """Convenience function to debug a Python script and record its timeline.

    Args:
        target_path: Target .py script to execute and trace.
        db_path: Path to SQLite database or ':memory:'.
        verbose: If True, echo target outputs to stderr.

    Returns:
        SessionResult containing status, total steps, and ReplayEngine.
    """
    config = ChronicleConfig(
        db_path=Path(db_path) if db_path != ":memory:" else Path(":memory:"),
        verbose=verbose,
    )
    debugger = Debugger(target_path=target_path, db_path=db_path, config=config)
    return debugger.run()
