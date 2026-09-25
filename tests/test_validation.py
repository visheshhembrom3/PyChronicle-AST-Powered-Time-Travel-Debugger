"""Tests for PyChronicle Validation Module."""

from pathlib import Path
import tempfile
import pytest

from pychronicle.validation import (
    validate_database_connection,
    validate_source_syntax,
    validate_target_file,
)


def test_validate_valid_file():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("x = 10\ny = 20\n")
        f_path = Path(f.name)

    try:
        res = validate_target_file(f_path)
        assert res.is_valid is True
        assert len(res.errors) == 0
        assert res.line_count == 2
        assert res.ast_nodes_count > 0
    finally:
        if f_path.exists():
            f_path.unlink()


def test_validate_nonexistent_file():
    res = validate_target_file("does_not_exist_file.py")
    assert res.is_valid is False
    assert any("does not exist" in err for err in res.errors)


def test_validate_non_python_extension():
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("hello world\n")
        f_path = Path(f.name)

    try:
        res = validate_target_file(f_path)
        assert res.is_valid is False
        assert any(".py extension" in err for err in res.errors)
    finally:
        if f_path.exists():
            f_path.unlink()


def test_validate_syntax_error():
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def broken(\n")
        f_path = Path(f.name)

    try:
        res = validate_target_file(f_path)
        assert res.is_valid is False
        assert len(res.errors) > 0
    finally:
        if f_path.exists():
            f_path.unlink()


def test_validate_source_syntax():
    ok, err = validate_source_syntax("a = 1 + 2")
    assert ok is True
    assert err is None

    ok, err = validate_source_syntax("a = 1 +")
    assert ok is False
    assert err is not None


def test_validate_database_connection():
    ok, err = validate_database_connection(":memory:")
    assert ok is True
    assert err is None
