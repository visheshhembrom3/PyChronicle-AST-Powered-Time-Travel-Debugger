"""Unit tests for AST parser and rewriter."""

import ast
from pathlib import Path
import sys

# Ensure package is discoverable
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from pychronicle.ast_rewriter import ASTRewriter, ChronicleASTTransformer
from pychronicle.config import INTERNAL_HOOK_NAME
from pychronicle.exceptions import SourceParseError


def test_parse_valid_source():
    rewriter = ASTRewriter()
    source = "x = 10\ny = 20\nz = x + y"
    tree = rewriter.parse_source(source)
    assert isinstance(tree, ast.Module)
    assert len(tree.body) == 3


def test_parse_invalid_syntax_raises_source_parse_error():
    rewriter = ASTRewriter()
    invalid_source = "def foo(: x ="
    with pytest.raises(SourceParseError) as exc_info:
        rewriter.parse_source(invalid_source, filename="invalid.py")
    assert "Failed to parse source" in str(exc_info.value)
    assert exc_info.value.lineno is not None


def test_ast_rewriting_injects_hooks():
    rewriter = ASTRewriter()
    source = """
def calculate(a, b):
    res = a + b
    if res > 10:
        res *= 2
    return res

total = calculate(5, 6)
"""
    tree, hook_count = rewriter.parse_and_rewrite(source)
    assert hook_count > 0

    # Ensure hook is injected before statements
    unparsed = rewriter.to_source(tree)
    assert INTERNAL_HOOK_NAME in unparsed


def test_compile_transformed_tree():
    rewriter = ASTRewriter()
    source = "val = 42"
    tree, _ = rewriter.parse_and_rewrite(source)
    code_obj = rewriter.compile_tree(tree)
    assert code_obj is not None

    # Test executing code object with dummy hook
    executed_hooks = []
    env = {
        INTERNAL_HOOK_NAME: lambda line, event: executed_hooks.append((line, event)),
        "__builtins__": __builtins__,
    }
    exec(code_obj, env, env)
    assert env["val"] == 42
    assert len(executed_hooks) > 0
