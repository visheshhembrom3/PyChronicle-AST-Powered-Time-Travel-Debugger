"""PyChronicle State Capture Model.

Defines the structure and representations of program states captured
at discrete runtime execution steps across execution scopes.
"""

from dataclasses import dataclass, field
import time
from typing import Any, Dict, Optional


@dataclass
class CapturedState:
    """Represents a frozen snapshot of execution state at a single step."""

    step: int
    line: int
    event: str  # "call", "line", "return", "exception"
    scope: str  # e.g. "<module>", "calculate", "Worker.run", "outer.<locals>.inner"
    variables: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # var_name -> serialized info
    fingerprints: Dict[str, str] = field(default_factory=dict)  # var_name -> SHA-256 hash
    call_depth: int = 0
    return_value: Optional[str] = None
    exception_info: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def get_var_repr(self, name: str, default: str = "null") -> str:
        """Get the human-readable string representation of a variable."""
        if name in self.variables:
            return self.variables[name].get("repr", default)
        return default

    def get_var_raw(self, name: str, default: Any = None) -> Any:
        """Get the raw JSON-compatible value of a variable."""
        if name in self.variables:
            return self.variables[name].get("raw", default)
        return default

    def to_dict(self) -> Dict[str, Any]:
        """Convert state into a structured dictionary."""
        return {
            "step": self.step,
            "line": self.line,
            "event": self.event,
            "scope": self.scope,
            "call_depth": self.call_depth,
            "return_value": self.return_value,
            "exception_info": self.exception_info,
            "timestamp": self.timestamp,
            "variables": {k: v.get("repr") for k, v in self.variables.items()},
        }
