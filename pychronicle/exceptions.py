"""PyChronicle Custom Exceptions.

Defines the exception hierarchy for PyChronicle errors, providing rich
diagnostic context to distinguish debugger errors from user program errors.
"""

from typing import Optional


class PyChronicleError(Exception):
    """Base exception class for all PyChronicle errors."""

    def __init__(
        self,
        message: str,
        component: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        self.component = component or "Core"
        self.details = details
        full_message = f"[{self.component}] {message}"
        if details:
            full_message += f"\nDetails: {details}"
        super().__init__(full_message)


class SourceParseError(PyChronicleError):
    """Raised when source code cannot be parsed or rewritten into AST."""

    def __init__(
        self,
        message: str,
        filename: Optional[str] = None,
        lineno: Optional[int] = None,
        details: Optional[str] = None,
    ) -> None:
        self.filename = filename
        self.lineno = lineno
        loc = f" in {filename}" if filename else ""
        loc += f" at line {lineno}" if lineno is not None else ""
        super().__init__(
            message=f"Failed to parse source{loc}: {message}",
            component="AST Parser",
            details=details,
        )


class TraceError(PyChronicleError):
    """Raised when an error occurs during runtime execution tracing."""

    def __init__(
        self,
        message: str,
        step: Optional[int] = None,
        details: Optional[str] = None,
    ) -> None:
        self.step = step
        super().__init__(
            message=f"Tracer error (step {step}): {message}" if step else f"Tracer error: {message}",
            component="Runtime Tracer",
            details=details,
        )


class SerializationError(PyChronicleError):
    """Raised when a runtime object fails safe serialization or fingerprinting."""

    def __init__(
        self,
        message: str,
        var_name: Optional[str] = None,
        var_type: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        self.var_name = var_name
        self.var_type = var_type
        target = f" for '{var_name}' ({var_type})" if var_name else ""
        super().__init__(
            message=f"Serialization failed{target}: {message}",
            component="Serializer",
            details=details,
        )


class StorageError(PyChronicleError):
    """Raised when an error occurs in the SQLite persistence layer."""

    def __init__(self, message: str, db_path: Optional[str] = None, details: Optional[str] = None) -> None:
        self.db_path = db_path
        super().__init__(
            message=f"Database storage error ({db_path}): {message}" if db_path else f"Database storage error: {message}",
            component="SQLite Storage",
            details=details,
        )


class ReplayError(PyChronicleError):
    """Raised when historical state cannot be reconstructed at a given step."""

    def __init__(
        self,
        message: str,
        step: Optional[int] = None,
        scope: Optional[str] = None,
        details: Optional[str] = None,
    ) -> None:
        self.step = step
        self.scope = scope
        super().__init__(
            message=f"Replay reconstruction failed (step={step}, scope={scope}): {message}",
            component="Replay Engine",
            details=details,
        )


class SessionError(PyChronicleError):
    """Raised when a debug session fails to initialize or execute."""

    def __init__(
        self,
        message: str,
        session_id: Optional[int] = None,
        details: Optional[str] = None,
    ) -> None:
        self.session_id = session_id
        super().__init__(
            message=f"Debug session error (session_id={session_id}): {message}" if session_id else f"Debug session error: {message}",
            component="Debug Session",
            details=details,
        )
