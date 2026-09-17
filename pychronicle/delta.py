"""PyChronicle Delta Generation Engine.

Computes differential state changes (CREATE, UPDATE, DELETE) between consecutive
execution steps within each scope, minimizing database storage requirements.
"""

from dataclasses import dataclass, field
import json
from typing import Any, Dict, Optional

from pychronicle.state import CapturedState


@dataclass
class VariableChange:
    """Represents a single variable transition."""

    operation: str  # "CREATE", "UPDATE", "DELETE"
    old: Optional[str]  # string repr of old value or None
    new: Optional[str]  # string repr of new value or None
    old_raw: Optional[Any] = None
    new_raw: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "old": self.old,
            "new": self.new,
        }


@dataclass
class StateDelta:
    """Represents the complete state transition occurring at a single execution step."""

    step: int
    line: int
    event: str
    scope: str
    changes: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # var_name -> change dict
    call_depth: int = 0
    return_value: Optional[str] = None
    exception_info: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "line": self.line,
            "event": self.event,
            "scope": self.scope,
            "changes": self.changes,
            "call_depth": self.call_depth,
            "return_value": self.return_value,
            "exception_info": self.exception_info,
        }

    def to_json(self) -> str:
        return json.dumps(self.changes)


class DeltaGenerator:
    """Generates differential state changes by comparing current state to previous scope state."""

    def __init__(self) -> None:
        # Map of scope -> previous CapturedState
        self._scope_states: Dict[str, CapturedState] = {}

    def compute_delta(self, current: CapturedState) -> StateDelta:
        """Calculate differential changes between previous and current state in the current scope."""
        scope = current.scope
        prev = self._scope_states.get(scope)
        changes: Dict[str, Dict[str, Any]] = {}

        current_vars = current.variables
        current_fps = current.fingerprints

        if prev is None:
            # All variables in current state are newly created
            for var_name, var_info in current_vars.items():
                change = VariableChange(
                    operation="CREATE",
                    old=None,
                    new=var_info.get("repr", "null"),
                    old_raw=None,
                    new_raw=var_info.get("raw"),
                )
                changes[var_name] = change.to_dict()
        else:
            prev_vars = prev.variables
            prev_fps = prev.fingerprints

            # Detect CREATE and UPDATE
            for var_name, var_info in current_vars.items():
                curr_fp = current_fps.get(var_name, "")
                if var_name not in prev_vars:
                    change = VariableChange(
                        operation="CREATE",
                        old=None,
                        new=var_info.get("repr", "null"),
                        old_raw=None,
                        new_raw=var_info.get("raw"),
                    )
                    changes[var_name] = change.to_dict()
                else:
                    prev_fp = prev_fps.get(var_name, "")
                    if curr_fp != prev_fp:
                        change = VariableChange(
                            operation="UPDATE",
                            old=prev_vars[var_name].get("repr", "null"),
                            new=var_info.get("repr", "null"),
                            old_raw=prev_vars[var_name].get("raw"),
                            new_raw=var_info.get("raw"),
                        )
                        changes[var_name] = change.to_dict()

            # Detect DELETE
            for var_name, var_info in prev_vars.items():
                if var_name not in current_vars:
                    change = VariableChange(
                        operation="DELETE",
                        old=var_info.get("repr", "null"),
                        new=None,
                        old_raw=var_info.get("raw"),
                        new_raw=None,
                    )
                    changes[var_name] = change.to_dict()

        # Update cache for this scope
        self._scope_states[scope] = current

        return StateDelta(
            step=current.step,
            line=current.line,
            event=current.event,
            scope=current.scope,
            changes=changes,
            call_depth=current.call_depth,
            return_value=current.return_value,
            exception_info=current.exception_info,
        )

    def reset_scope(self, scope: str) -> None:
        """Clear cached state for a scope that has exited."""
        self._scope_states.pop(scope, None)

    def reset_all(self) -> None:
        """Reset all scope tracking caches."""
        self._scope_states.clear()
