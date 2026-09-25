"""Tests for PyChronicle AST Parser."""

import ast
from pathlib import Path
import tempfile
import pytest

from pychronicle.ast_parser import (
    extract_target_names,
    get_assignments,
    get_statement_map,
    parse_file,
    parse_source,
)
from pychronicle.exceptions import SourceParseError


def test_parse_valid_source():
    code = "x = 10\ny = 20\nz = x + y"
    tree = parse_source(code)
    assert isinstance(tree, ast.Module)
    assert len(tree.body) == 3


def test_parse_invalid_syntax():
    code = "x = 10 +\n"
    with pytest.raises(SourceParseError) as exc_info:
        parse_source(code)
    assert "Invalid Python syntax" in str(exc_info.value) or "SyntaxError" in str(exc_info.value)


def test_parse_file():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("a = 100\nb = a * 2\n")
        f_path = Path(f.name)

    try:
        tree = parse_file(f_path)
        assert isinstance(tree, ast.Module)
        assert len(tree.body) == 2
    finally:
        if f_path.exists():
            f_path.unlink()


def test_parse_nonexistent_file():
    with pytest.raises(SourceParseError):
        parse_file("non_existent_file_12345.py")


def test_get_assignments():
    code = """
x = 10
y: int = 20
x += 5
a, b = 1, 2
"""
    tree = parse_source(code)
    assignments = get_assignments(tree)

    assert len(assignments) == 4
    assert assignments[0]["type"] == "Assign"
    assert assignments[0]["variables"] == ["x"]
    assert assignments[1]["type"] == "AnnAssign"
    assert assignments[1]["variables"] == ["y"]
    assert assignments[2]["type"] == "AugAssign"
    assert assignments[2]["variables"] == ["x"]
    assert assignments[3]["type"] == "Assign"
    assert assignments[3]["variables"] == ["a", "b"]


def test_get_statement_map():
    code = """
import math
from os import path

def calc(n):
    total = 0
    for i in range(n):
        total += i
    if total > 5:
        return total
    return 0
"""
    tree = parse_source(code)
    stmt_map = get_statement_map(tree)

    types_found = {info["type"] for info in stmt_map.values()}
    assert "Import" in types_found
    assert "ImportFrom" in types_found
    assert "FunctionDef" in types_found
    assert "For" in types_found
    assert "If" in types_found
    assert "Return" in types_found
