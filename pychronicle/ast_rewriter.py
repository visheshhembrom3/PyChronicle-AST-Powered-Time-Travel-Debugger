"""PyChronicle AST Parser and Code Rewriter.

Provides source code parsing, structural analysis, and AST instrumentation.
Injects non-intrusive runtime hook calls (__pychronicle_hook__) before
executable statements and branches while strictly preserving source line numbers
and original program semantics.
"""

import ast
from typing import List, Optional, Tuple

from pychronicle.config import INTERNAL_HOOK_NAME
from pychronicle.exceptions import SourceParseError


class ChronicleASTTransformer(ast.NodeTransformer):
    """AST NodeTransformer that inserts __pychronicle_hook__(lineno, event) calls."""

    def __init__(self, hook_name: str = INTERNAL_HOOK_NAME) -> None:
        super().__init__()
        self.hook_name = hook_name
        self.hook_count = 0

    def _create_hook_call(self, lineno: int, event: str) -> ast.Expr:
        """Create an ast.Expr node representing: __pychronicle_hook__(lineno, event)."""
        call = ast.Call(
            func=ast.Name(id=self.hook_name, ctx=ast.Load()),
            args=[
                ast.Constant(value=lineno),
                ast.Constant(value=event),
            ],
            keywords=[],
        )
        expr = ast.Expr(value=call)
        expr.lineno = lineno
        expr.col_offset = 0
        self.hook_count += 1
        return expr

    def _instrument_statement_list(
        self, statements: List[ast.stmt], default_event: str = "line"
    ) -> List[ast.stmt]:
        """Instrument a list of statements by inserting a hook call before each statement."""
        new_stmts: List[ast.stmt] = []
        for stmt in statements:
            # Transform child nodes first
            transformed_stmt = self.visit(stmt)
            if transformed_stmt is None:
                continue

            # Don't instrument our own injected hooks or docstrings
            if isinstance(transformed_stmt, ast.Expr) and isinstance(
                transformed_stmt.value, ast.Call
            ):
                if (
                    isinstance(transformed_stmt.value.func, ast.Name)
                    and transformed_stmt.value.func.id == self.hook_name
                ):
                    new_stmts.append(transformed_stmt)
                    continue

            # Don't instrument standalone string literal docstrings at start of module/func
            if (
                isinstance(transformed_stmt, ast.Expr)
                and isinstance(transformed_stmt.value, ast.Constant)
                and isinstance(transformed_stmt.value.value, str)
                and len(new_stmts) == 0
            ):
                new_stmts.append(transformed_stmt)
                continue

            # Insert hook before the statement with its line number
            lineno = getattr(transformed_stmt, "lineno", 1)
            hook_node = self._create_hook_call(lineno, default_event)
            ast.copy_location(hook_node, transformed_stmt)
            new_stmts.append(hook_node)
            new_stmts.append(transformed_stmt)

        return new_stmts

    def visit_Module(self, node: ast.Module) -> ast.Module:
        node.body = self._instrument_statement_list(node.body, "line")
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        # Instrument function body
        node.body = self._instrument_statement_list(node.body, "line")
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AsyncFunctionDef:
        node.body = self._instrument_statement_list(node.body, "line")
        return node

    def visit_For(self, node: ast.For) -> ast.For:
        node.body = self._instrument_statement_list(node.body, "line")
        if node.orelse:
            node.orelse = self._instrument_statement_list(node.orelse, "line")
        return node

    def visit_AsyncFor(self, node: ast.AsyncFor) -> ast.AsyncFor:
        node.body = self._instrument_statement_list(node.body, "line")
        if node.orelse:
            node.orelse = self._instrument_statement_list(node.orelse, "line")
        return node

    def visit_While(self, node: ast.While) -> ast.While:
        node.body = self._instrument_statement_list(node.body, "line")
        if node.orelse:
            node.orelse = self._instrument_statement_list(node.orelse, "line")
        return node

    def visit_If(self, node: ast.If) -> ast.If:
        node.body = self._instrument_statement_list(node.body, "line")
        if node.orelse:
            node.orelse = self._instrument_statement_list(node.orelse, "line")
        return node

    def visit_Try(self, node: ast.Try) -> ast.Try:
        node.body = self._instrument_statement_list(node.body, "line")
        for handler in node.handlers:
            handler.body = self._instrument_statement_list(handler.body, "line")
        if node.orelse:
            node.orelse = self._instrument_statement_list(node.orelse, "line")
        if node.finalbody:
            node.finalbody = self._instrument_statement_list(node.finalbody, "line")
        return node

    def visit_With(self, node: ast.With) -> ast.With:
        node.body = self._instrument_statement_list(node.body, "line")
        return node

    def visit_AsyncWith(self, node: ast.AsyncWith) -> ast.AsyncWith:
        node.body = self._instrument_statement_list(node.body, "line")
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        node.body = self._instrument_statement_list(node.body, "line")
        return node


class ASTRewriter:
    """High-level API for parsing, analyzing, and rewriting Python source code."""

    def __init__(self, hook_name: str = INTERNAL_HOOK_NAME) -> None:
        self.hook_name = hook_name

    def parse_source(self, source: str, filename: str = "<target>") -> ast.AST:
        """Parse source code into an AST tree with detailed error reporting."""
        try:
            return ast.parse(source, filename=filename)
        except SyntaxError as e:
            raise SourceParseError(
                message=str(e.msg),
                filename=filename,
                lineno=e.lineno,
                details=f"Text: {e.text.strip() if e.text else 'N/A'}",
            ) from e
        except Exception as e:
            raise SourceParseError(
                message=str(e),
                filename=filename,
                details=f"Unexpected error: {type(e).__name__}",
            ) from e

    def rewrite(self, tree: ast.AST) -> Tuple[ast.AST, int]:
        """Instrument the AST tree and return the modified tree along with the number of injected hooks."""
        transformer = ChronicleASTTransformer(hook_name=self.hook_name)
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)
        return new_tree, transformer.hook_count

    def parse_and_rewrite(self, source: str, filename: str = "<target>") -> Tuple[ast.AST, int]:
        """Convenience method to parse and rewrite source code in a single step."""
        tree = self.parse_source(source, filename=filename)
        return self.rewrite(tree)

    def compile_tree(self, tree: ast.AST, filename: str = "<target>") -> object:
        """Compile AST into a Python code object."""
        try:
            return compile(tree, filename=filename, mode="exec")
        except Exception as e:
            raise SourceParseError(
                message=f"Failed to compile instrumented AST: {e}",
                filename=filename,
                details=str(e),
            ) from e

    def to_source(self, tree: ast.AST) -> str:
        """Unparse an AST tree back to Python source code."""
        return ast.unparse(tree)


def rewrite_tree(tree: ast.AST, hook_name: str = INTERNAL_HOOK_NAME) -> ast.AST:
    """Instrument an AST tree by inserting execution hook calls before statements.

    Preserves source line numbers and semantics without mutating the original tree in place.

    Args:
        tree: Input AST tree.
        hook_name: Injected hook function identifier.

    Returns:
        Transformed and location-fixed AST tree.
    """
    transformer = ChronicleASTTransformer(hook_name=hook_name)
    new_tree = transformer.visit(tree)
    ast.fix_missing_locations(new_tree)
    return new_tree


def rewrite_source(source: str, filename: str = "<target>", hook_name: str = INTERNAL_HOOK_NAME) -> Tuple[ast.AST, str]:
    """Parse Python source code, instrument the AST, and return the transformed tree and source.

    Args:
        source: Python source code string.
        filename: Optional source identifier for syntax errors.
        hook_name: Injected hook function identifier.

    Returns:
        Tuple of (transformed_ast_tree, instrumented_source_code_str).
    """
    rewriter = ASTRewriter(hook_name=hook_name)
    tree, _ = rewriter.parse_and_rewrite(source, filename=filename)
    return tree, rewriter.to_source(tree)

