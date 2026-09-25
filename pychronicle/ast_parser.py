"""PyChronicle AST Parser.

Provides source code parsing, AST inspection, variable assignment identification,
and statement mapping across Python abstract syntax trees.
Strictly read-only: never modifies the original source file.
"""

import ast
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from pychronicle.exceptions import SourceParseError


def parse_source(source: str, filename: str = "<target>") -> ast.AST:
    """Parse a Python source string into an Abstract Syntax Tree.

    Args:
        source: Python source code string.
        filename: Optional filename for traceback and error reporting.

    Returns:
        ast.AST root node.

    Raises:
        SourceParseError: If the source code contains syntax errors.
    """
    try:
        return ast.parse(source, filename=filename)
    except SyntaxError as e:
        raise SourceParseError(
            message=f"Invalid Python syntax at line {e.lineno}: {e.msg}",
            filename=filename,
            lineno=e.lineno,
            details=f"Text: {e.text.strip() if e.text else 'N/A'}",
        ) from e
    except Exception as e:
        raise SourceParseError(
            message=f"Failed to parse source: {e}",
            filename=filename,
            details=str(e),
        ) from e


def parse_file(path: Union[str, Path]) -> ast.AST:
    """Read a target Python file and parse its AST.

    The original source file is strictly read-only and never modified.

    Args:
        path: Path to the Python file.

    Returns:
        ast.AST root node.

    Raises:
        SourceParseError: If the file cannot be read or contains syntax errors.
    """
    file_path = Path(path).resolve()
    if not file_path.exists():
        raise SourceParseError(
            message=f"Target file does not exist: {file_path}",
            filename=str(file_path),
        )
    if not file_path.is_file():
        raise SourceParseError(
            message=f"Target path is not a file: {file_path}",
            filename=str(file_path),
        )

    try:
        source = file_path.read_text(encoding="utf-8")
    except Exception as e:
        raise SourceParseError(
            message=f"Failed to read file '{file_path}': {e}",
            filename=str(file_path),
            details=str(e),
        ) from e

    return parse_source(source, filename=str(file_path))


def extract_target_names(target_node: ast.AST) -> List[str]:
    """Extract variable identifiers from an assignment target node."""
    names: List[str] = []
    if isinstance(target_node, ast.Name):
        names.append(target_node.id)
    elif isinstance(target_node, (ast.Tuple, ast.List)):
        for elt in target_node.elts:
            names.extend(extract_target_names(elt))
    elif isinstance(target_node, ast.Attribute):
        # Attribute assignment e.g. obj.attr
        names.append(target_node.attr)
    elif isinstance(target_node, ast.Subscript):
        # Subscript assignment e.g. d[k]
        if isinstance(target_node.value, ast.Name):
            names.append(target_node.value.id)
    elif isinstance(target_node, ast.Starred):
        names.extend(extract_target_names(target_node.value))
    return names


def get_assignments(tree: ast.AST) -> List[Dict[str, Any]]:
    """Identify and extract all variable assignments from an AST tree.

    Inspects:
    - Assign (e.g. x = 1, a, b = 2, 3)
    - AnnAssign (e.g. x: int = 10)
    - AugAssign (e.g. x += 5)

    Returns:
        List of dictionaries with:
        - 'line': line number (1-indexed)
        - 'col_offset': column number
        - 'type': statement type string ('Assign', 'AnnAssign', 'AugAssign')
        - 'variables': list of assigned variable names
        - 'targets_repr': string representation of target(s)
    """
    assignments: List[Dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            var_names: List[str] = []
            for target in node.targets:
                var_names.extend(extract_target_names(target))
            assignments.append({
                "line": getattr(node, "lineno", 1),
                "col_offset": getattr(node, "col_offset", 0),
                "type": "Assign",
                "variables": var_names,
            })
        elif isinstance(node, ast.AnnAssign):
            var_names = extract_target_names(node.target)
            assignments.append({
                "line": getattr(node, "lineno", 1),
                "col_offset": getattr(node, "col_offset", 0),
                "type": "AnnAssign",
                "variables": var_names,
            })
        elif isinstance(node, ast.AugAssign):
            var_names = extract_target_names(node.target)
            assignments.append({
                "line": getattr(node, "lineno", 1),
                "col_offset": getattr(node, "col_offset", 0),
                "type": "AugAssign",
                "variables": var_names,
            })

    # Sort assignments by line number then column offset
    assignments.sort(key=lambda item: (item["line"], item["col_offset"]))
    return assignments


def get_statement_map(tree: ast.AST) -> Dict[int, Dict[str, Any]]:
    """Build a mapping of line numbers to AST statement metadata.

    Identifies and categorizes:
    - Assign, AnnAssign, AugAssign
    - FunctionDef, AsyncFunctionDef
    - For, AsyncFor, While
    - If
    - Return
    - Import, ImportFrom

    Returns:
        Dictionary mapping line number -> statement metadata dict:
        - 'line': int
        - 'col_offset': int
        - 'type': statement class name (e.g. 'FunctionDef', 'For', 'Assign')
        - 'variables': list of variables defined, assigned, or bound
    """
    stmt_map: Dict[int, Dict[str, Any]] = {}

    for node in ast.walk(tree):
        if not hasattr(node, "lineno"):
            continue

        lineno = node.lineno
        col_offset = getattr(node, "col_offset", 0)

        # Skip expressions that are sub-nodes unless they are top statements
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            vars_list: List[str] = []
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    vars_list.extend(extract_target_names(t))
            elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
                vars_list.extend(extract_target_names(node.target))

            stmt_map[lineno] = {
                "line": lineno,
                "col_offset": col_offset,
                "type": type(node).__name__,
                "variables": vars_list,
            }

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            stmt_map[lineno] = {
                "line": lineno,
                "col_offset": col_offset,
                "type": type(node).__name__,
                "variables": [node.name],
            }

        elif isinstance(node, (ast.For, ast.AsyncFor)):
            target_vars = extract_target_names(node.target)
            stmt_map[lineno] = {
                "line": lineno,
                "col_offset": col_offset,
                "type": type(node).__name__,
                "variables": target_vars,
            }

        elif isinstance(node, ast.While):
            stmt_map[lineno] = {
                "line": lineno,
                "col_offset": col_offset,
                "type": "While",
                "variables": [],
            }

        elif isinstance(node, ast.If):
            stmt_map[lineno] = {
                "line": lineno,
                "col_offset": col_offset,
                "type": "If",
                "variables": [],
            }

        elif isinstance(node, ast.Return):
            stmt_map[lineno] = {
                "line": lineno,
                "col_offset": col_offset,
                "type": "Return",
                "variables": [],
            }

        elif isinstance(node, ast.Import):
            imported_names = [alias.asname or alias.name for alias in node.names]
            stmt_map[lineno] = {
                "line": lineno,
                "col_offset": col_offset,
                "type": "Import",
                "variables": imported_names,
            }

        elif isinstance(node, ast.ImportFrom):
            imported_names = [alias.asname or alias.name for alias in node.names]
            stmt_map[lineno] = {
                "line": lineno,
                "col_offset": col_offset,
                "type": "ImportFrom",
                "variables": imported_names,
            }

    return stmt_map
