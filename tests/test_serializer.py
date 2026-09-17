"""Unit tests for safe serializer and deterministic fingerprinting."""

from pathlib import Path
import sys

# Ensure package is discoverable
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from pychronicle.serializer import compute_fingerprint, safe_deep_copy, serialize_value


def test_serialize_primitives():
    assert serialize_value(10)["raw"] == 10
    assert serialize_value(3.14)["raw"] == 3.14
    assert serialize_value("hello")["raw"] == "hello"
    assert serialize_value(True)["raw"] is True
    assert serialize_value(None)["raw"] is None


def test_serialize_containers():
    data = [1, 2, {"key": "val"}, (4, 5), {6, 7}]
    ser = serialize_value(data)
    assert ser["type"] == "list"
    assert ser["raw"][0] == 1
    assert ser["raw"][2]["key"] == "val"


def test_safe_deep_copy_mutation_isolation():
    original = [1, [2, 3], {"a": 10}]
    clone = safe_deep_copy(original)

    # Mutate original
    original[1].append(4)
    original[2]["b"] = 20

    # Verify clone was isolated
    assert clone[1] == [2, 3]
    assert clone[2] == {"a": 10}


def test_compute_fingerprint_determinism():
    d1 = {"a": 1, "b": [1, 2, 3]}
    d2 = {"b": [1, 2, 3], "a": 1}
    # Deterministic dictionary hashing regardless of key iteration order
    fp1 = compute_fingerprint(d1)
    fp2 = compute_fingerprint(d2)
    assert fp1 == fp2

    # Mutation produces different fingerprint
    d1["a"] = 2
    fp3 = compute_fingerprint(d1)
    assert fp1 != fp3


def test_circular_reference_protection():
    cyclic_list = [1, 2]
    cyclic_list.append(cyclic_list)

    # Must not enter infinite recursion
    ser = serialize_value(cyclic_list)
    assert ser["type"] == "list"
    fp = compute_fingerprint(cyclic_list)
    assert isinstance(fp, str) and len(fp) == 64


def test_custom_object_serialization():
    class Person:
        def __init__(self, name, age):
            self.name = name
            self.age = age

    p = Person("Alice", 30)
    ser = serialize_value(p)
    assert "Person" in ser["type"]
    assert "Alice" in ser["repr"]
    fp = compute_fingerprint(p)
    assert isinstance(fp, str)
