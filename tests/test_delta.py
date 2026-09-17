"""Unit tests for DeltaGenerator and StateDelta."""

from pathlib import Path
import sys

# Ensure package is discoverable
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from pychronicle.delta import DeltaGenerator
from pychronicle.serializer import compute_fingerprint, serialize_value
from pychronicle.state import CapturedState


def make_state(step: int, scope: str, variables_dict: dict) -> CapturedState:
    serialized = {k: serialize_value(v) for k, v in variables_dict.items()}
    fps = {k: compute_fingerprint(v) for k, v in variables_dict.items()}
    return CapturedState(
        step=step,
        line=step * 2,
        event="line",
        scope=scope,
        variables=serialized,
        fingerprints=fps,
    )


def test_delta_create_operation():
    gen = DeltaGenerator()
    s1 = make_state(1, "<module>", {"x": 10})
    d1 = gen.compute_delta(s1)

    assert "x" in d1.changes
    assert d1.changes["x"]["operation"] == "CREATE"
    assert d1.changes["x"]["old"] is None
    assert d1.changes["x"]["new"] == "10"


def test_delta_update_operation():
    gen = DeltaGenerator()
    s1 = make_state(1, "<module>", {"x": 10, "y": 20})
    gen.compute_delta(s1)

    s2 = make_state(2, "<module>", {"x": 20, "y": 20})
    d2 = gen.compute_delta(s2)

    assert "x" in d2.changes
    assert d2.changes["x"]["operation"] == "UPDATE"
    assert d2.changes["x"]["old"] == "10"
    assert d2.changes["x"]["new"] == "20"
    # y did not change
    assert "y" not in d2.changes


def test_delta_delete_operation():
    gen = DeltaGenerator()
    s1 = make_state(1, "<module>", {"x": 10, "y": 20})
    gen.compute_delta(s1)

    s2 = make_state(2, "<module>", {"y": 20})  # x removed
    d2 = gen.compute_delta(s2)

    assert "x" in d2.changes
    assert d2.changes["x"]["operation"] == "DELETE"
    assert d2.changes["x"]["old"] == "10"
    assert d2.changes["x"]["new"] is None
    assert "y" not in d2.changes


def test_delta_scope_isolation():
    gen = DeltaGenerator()
    s_mod = make_state(1, "<module>", {"val": 100})
    gen.compute_delta(s_mod)

    s_func = make_state(2, "calculate", {"val": 5})
    d_func = gen.compute_delta(s_func)

    # In calculate scope, val is a newly created local variable
    assert d_func.changes["val"]["operation"] == "CREATE"
    assert d_func.changes["val"]["new"] == "5"
