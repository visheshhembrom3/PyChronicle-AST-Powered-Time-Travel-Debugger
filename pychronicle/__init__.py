"""PyChronicle — AST-Powered Python Time-Travel Debugger.

A time-travel debugger that combines AST instrumentation, runtime sys.settrace tracing,
differential delta capture, and SQLite storage for exact historical state reconstruction.
"""

from typing import Any

from pychronicle.application import ApplicationService
from pychronicle.ast_parser import get_assignments, get_statement_map, parse_file, parse_source
from pychronicle.ast_rewriter import ASTRewriter, ChronicleASTTransformer, rewrite_source, rewrite_tree
from pychronicle.config import ChronicleConfig
from pychronicle.database import Database
from pychronicle.debugger import Debugger, run_debugger
from pychronicle.delta import DeltaGenerator, StateDelta, VariableChange, calculate_delta
from pychronicle.exceptions import (
    PyChronicleError,
    ReplayError,
    SerializationError,
    SessionError,
    SourceParseError,
    StorageError,
    TraceError,
)
from pychronicle.replay import ReconstructedState, ReplayEngine
from pychronicle.serializer import compute_fingerprint, safe_deep_copy, serialize_value
from pychronicle.session import DebugSession, SessionMetadata, SessionResult
from pychronicle.state import CapturedState
from pychronicle.storage import SQLiteStorage
from pychronicle.validation import (
    ValidationResult,
    validate_database_connection,
    validate_source_syntax,
    validate_target_file,
)

__version__ = "0.1.0"
__all__ = [
    "ApplicationService",
    "parse_file",
    "parse_source",
    "get_assignments",
    "get_statement_map",
    "ASTRewriter",
    "ChronicleASTTransformer",
    "rewrite_tree",
    "rewrite_source",
    "ChronicleConfig",
    "Database",
    "Debugger",
    "run_debugger",
    "DeltaGenerator",
    "StateDelta",
    "VariableChange",
    "calculate_delta",
    "CapturedState",
    "ReconstructedState",
    "ReplayEngine",
    "RuntimeTracer",
    "TracerBackend",
    "SQLiteStorage",
    "DebugSession",
    "SessionMetadata",
    "SessionResult",
    "run_debug_session",
    "serialize_value",
    "compute_fingerprint",
    "safe_deep_copy",
    "ValidationResult",
    "validate_target_file",
    "validate_source_syntax",
    "validate_database_connection",
    "PyChronicleError",
    "SourceParseError",
    "TraceError",
    "SerializationError",
    "StorageError",
    "ReplayError",
    "SessionError",
]


def __getattr__(name: str) -> Any:
    """Lazy import for tracer components to prevent runpy execution order warnings."""
    if name in ("RuntimeTracer", "TracerBackend", "run_debug_session"):
        import pychronicle.tracer as _tracer_mod

        return getattr(_tracer_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

