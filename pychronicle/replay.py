"""PyChronicle Time-Travel Replay Engine.

Reconstructs exact historical program states at any execution step by
sequentially applying delta transitions across scoped execution namespaces.
"""

from dataclasses import dataclass, field
import json
from typing import Any, Dict, List, Optional

from pychronicle.exceptions import ReplayError
from pychronicle.storage import SQLiteStorage


@dataclass
class ReconstructedState:
    """Historical state at a discrete execution step across all scopes."""

    step: int
    line: int
    event: str
    active_scope: str
    scopes: Dict[str, Dict[str, str]] = field(default_factory=dict)
    changes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    return_value: Optional[str] = None
    exception_info: Optional[str] = None
    call_depth: int = 0

    @property
    def active_variables(self) -> Dict[str, str]:
        """Variables within the active execution scope at this step."""
        return self.scopes.get(self.active_scope, {})

    def get_var(self, name: str, scope: Optional[str] = None) -> Optional[str]:
        """Retrieve variable value in the given scope or current active scope."""
        target_scope = scope or self.active_scope
        return self.scopes.get(target_scope, {}).get(name)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step,
            "line": self.line,
            "event": self.event,
            "active_scope": self.active_scope,
            "scopes": self.scopes,
            "changes": self.changes,
            "return_value": self.return_value,
            "exception_info": self.exception_info,
            "call_depth": self.call_depth,
        }


class ReplayEngine:
    """Reconstructs execution history from persisted SQLite snapshots."""

    def __init__(self, session_id: int, storage: SQLiteStorage) -> None:
        self.session_id = session_id
        self.storage = storage
        self.session_info = self.storage.get_session(session_id)
        if not self.session_info:
            raise ReplayError(
                f"Session ID {session_id} not found in database.",
                details="Verify that the session exists by listing sessions.",
            )

        self.snapshots = self.storage.get_snapshots(session_id)
        self._current_step_index: int = 0
        # Cache for reconstructed states to optimize repeated lookups
        self._state_cache: Dict[int, ReconstructedState] = {}

    @property
    def total_steps(self) -> int:
        return len(self.snapshots)

    def get_timeline(self) -> List[Dict[str, Any]]:
        """Return the timeline index containing step, line, event, and scope for each snapshot."""
        return [
            {
                "step": s["step"],
                "line": s["line"],
                "event": s["event"],
                "scope": s["scope"],
                "call_depth": s.get("call_depth", 0),
                "has_changes": len(s.get("changes", {})) > 0,
                "has_exception": s.get("exception_info") is not None,
                "has_return": s.get("return_value") is not None,
            }
            for s in self.snapshots
        ]

    def state_at(self, step: int) -> ReconstructedState:
        """Reconstruct the scoped program state at a specific step number (1-indexed)."""
        if not self.snapshots:
            raise ReplayError(
                f"No execution snapshots recorded for session {self.session_id}.",
                step=step,
            )

        if step < 1 or step > len(self.snapshots):
            raise ReplayError(
                f"Requested step {step} is out of bounds (1 to {len(self.snapshots)}).",
                step=step,
            )

        if step in self._state_cache:
            return self._state_cache[step]

        # Reconstruct from initial empty state up to target step
        # Scopes: Dict[scope_name, Dict[var_name, repr_str]]
        scopes: Dict[str, Dict[str, str]] = {}

        last_snap = None
        for snap in self.snapshots:
            current_step = snap["step"]
            if current_step > step:
                break

            last_snap = snap
            scope_name = snap["scope"]
            if scope_name not in scopes:
                scopes[scope_name] = {}

            changes = snap["changes"]
            for var_name, change in changes.items():
                op = change.get("operation")
                new_val = change.get("new")
                if op in ("CREATE", "UPDATE"):
                    scopes[scope_name][var_name] = str(new_val) if new_val is not None else "null"
                elif op == "DELETE":
                    scopes[scope_name].pop(var_name, None)

        if last_snap is None:
            raise ReplayError(f"Could not find snapshot for step {step}.", step=step)

        # Deep clone scopes dictionary for state immutability
        cloned_scopes = {s_name: dict(v_map) for s_name, v_map in scopes.items()}

        reconstructed = ReconstructedState(
            step=last_snap["step"],
            line=last_snap["line"],
            event=last_snap["event"],
            active_scope=last_snap["scope"],
            scopes=cloned_scopes,
            changes=last_snap["changes"],
            return_value=last_snap.get("return_value"),
            exception_info=last_snap.get("exception_info"),
            call_depth=last_snap.get("call_depth", 0),
        )

        self._state_cache[step] = reconstructed
        self._current_step_index = step - 1
        return reconstructed

    def current_step(self) -> Optional[ReconstructedState]:
        """Return reconstructed state at the current pointer position."""
        if not self.snapshots:
            return None
        return self.state_at(self._current_step_index + 1)

    def first_step(self) -> Optional[ReconstructedState]:
        """Navigate to and return the first execution step."""
        if not self.snapshots:
            return None
        return self.state_at(1)

    def last_step(self) -> Optional[ReconstructedState]:
        """Navigate to and return the final execution step."""
        if not self.snapshots:
            return None
        return self.state_at(len(self.snapshots))

    def next_step(self) -> Optional[ReconstructedState]:
        """Advance one step forward in time."""
        if self._current_step_index + 1 < len(self.snapshots):
            self._current_step_index += 1
            return self.state_at(self._current_step_index + 1)
        return self.state_at(len(self.snapshots)) if self.snapshots else None

    def previous_step(self) -> Optional[ReconstructedState]:
        """Step one step backward in time."""
        if self._current_step_index > 0:
            self._current_step_index -= 1
            return self.state_at(self._current_step_index + 1)
        return self.state_at(1) if self.snapshots else None

    def get_watch_history(
        self, var_names: List[str], scope: Optional[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Retrieve historical values and changes across time for specific watched variables.

        Args:
            var_names: List of variable identifiers to track across execution.
            scope: Optional specific scope filter. If None, resolves across active and all scopes.

        Returns:
            Dict mapping each variable name to a list of step-by-step state entries.
        """
        history: Dict[str, List[Dict[str, Any]]] = {var: [] for var in var_names}
        for step_num in range(1, self.total_steps + 1):
            state = self.state_at(step_num)
            for var in var_names:
                val = None
                if scope:
                    val = state.scopes.get(scope, {}).get(var)
                else:
                    if var in state.active_variables:
                        val = state.active_variables[var]
                    else:
                        for s_vars in state.scopes.values():
                            if var in s_vars:
                                val = s_vars[var]
                                break

                change = state.changes.get(var)
                history[var].append({
                    "step": state.step,
                    "line": state.line,
                    "scope": state.active_scope,
                    "value": val,
                    "is_changed": change is not None,
                    "change": change,
                })
        return history

    def get_watch_values_at(
        self, step: int, var_names: List[str], scope: Optional[str] = None
    ) -> Dict[str, Optional[str]]:
        """Retrieve current values of watched variables at a specific discrete step.

        Args:
            step: Step index (1-based).
            var_names: List of variable identifiers to query.
            scope: Optional specific scope filter.

        Returns:
            Dict mapping each variable name to its string representation or None if undefined.
        """
        state = self.state_at(step)
        result: Dict[str, Optional[str]] = {}
        for var in var_names:
            if scope:
                result[var] = state.scopes.get(scope, {}).get(var)
            else:
                if var in state.active_variables:
                    result[var] = state.active_variables[var]
                else:
                    found = None
                    for s_vars in state.scopes.values():
                        if var in s_vars:
                            found = s_vars[var]
                            break
                    result[var] = found
        return result


    def get_state_at_step(self, step: int) -> ReconstructedState:
        """Reconstruct historical program state at the given step (1-indexed).

        Alias for state_at(step).
        """
        return self.state_at(step)

    def get_variable_history(
        self, variable_name: str, scope: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve step-by-step history of a specific variable across time.

        Args:
            variable_name: The identifier of the variable to inspect.
            scope: Optional scope filter.

        Returns:
            List of historical state dicts for this variable across steps.
        """
        history_map = self.get_watch_history([variable_name], scope=scope)
        return history_map.get(variable_name, [])

    def get_line_at_step(self, step: int) -> Optional[int]:
        """Return the source line number corresponding to a specific execution step."""
        state = self.state_at(step)
        return state.line

    def get_available_steps(self) -> List[int]:
        """Return a list of all recorded step indices (1 to N)."""
        return [s["step"] for s in self.snapshots]

