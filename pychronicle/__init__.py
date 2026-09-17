"""PyChronicle — AST-Powered Python Time-Travel Debugger.

A time-travel debugger that combines AST instrumentation, runtime sys.settrace tracing,
differential delta capture, and SQLite storage for exact historical state reconstruction.
"""

from typing import Any

from pychronicle.application import ApplicationService
from pychronicle.ast_rewriter import ASTRewriter, ChronicleASTTransformer
from pychronicle.config import ChronicleConfig
from pychronicle.delta import DeltaGenerator, StateDelta, VariableChange
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

__version__ = "0.1.0"
__all__ = [
    "ApplicationService",
    "ASTRewriter",
    "ChronicleASTTransformer",
    "ChronicleConfig",
    "DeltaGenerator",
    "StateDelta",
    "VariableChange",
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
