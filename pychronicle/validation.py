"""PyChronicle Validation System.

Provides pre-execution validation checks for Python target files, syntax integrity,
AST parsing, database accessibility, and environment prerequisites.
"""

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import sys
from typing import List, Optional, Tuple, Union

from pychronicle.ast_parser import parse_source


@dataclass
class ValidationResult:
    """Encapsulates the result of target script and environment validation."""

    is_valid: bool
    errors: List[str]
    warnings: List[str]
    target_path: Optional[Path] = None
    line_count: int = 0
    ast_nodes_count: int = 0

    @property
    def error_message(self) -> str:
        """Return formatted single or multi-line error string."""
        if not self.errors:
            return ""
        return "\n".join(f"ERROR: {e}" for e in self.errors)


def validate_target_file(path: Union[str, Path]) -> ValidationResult:
    """Perform comprehensive validation on a target Python file.

    Checks:
    1. Path exists.
    2. Path is a regular file.
    3. File has a .py extension.
    4. File content can be read (encoding/permissions).
    5. Python syntax is valid.
    6. AST can be constructed.

    Returns:
        ValidationResult indicating validity, errors, warnings, and line count.
    """
    errors: List[str] = []
    warnings: List[str] = []
    target = Path(path)
    line_count = 0
    ast_nodes_count = 0

    if not target.exists():
        errors.append(f"Target file does not exist: {target}")
        return ValidationResult(is_valid=False, errors=errors, warnings=warnings, target_path=target)

    if not target.is_file():
        errors.append(f"Target path is not a file: {target}")
        return ValidationResult(is_valid=False, errors=errors, warnings=warnings, target_path=target)

    if target.suffix.lower() != ".py":
        errors.append(f"Target file must have a .py extension (got '{target.suffix}')")

    source_code = ""
    try:
        source_code = target.read_text(encoding="utf-8")
        line_count = len(source_code.splitlines())
    except UnicodeDecodeError:
        errors.append("Target file is not valid UTF-8 text.")
    except Exception as e:
        errors.append(f"Could not read target file: {e}")

    if errors:
        return ValidationResult(is_valid=False, errors=errors, warnings=warnings, target_path=target, line_count=line_count)

    if not source_code.strip():
        warnings.append("Target file is empty.")

    # Syntax and AST validation
    try:
        tree = parse_source(source_code, filename=str(target))
        import ast
        ast_nodes_count = sum(1 for _ in ast.walk(tree))
    except Exception as e:
        errors.append(str(e))

    return ValidationResult(
        is_valid=(len(errors) == 0),
        errors=errors,
        warnings=warnings,
        target_path=target,
        line_count=line_count,
        ast_nodes_count=ast_nodes_count,
    )


def validate_source_syntax(source: str, filename: str = "<target>") -> Tuple[bool, Optional[str]]:
    """Quick validation check for Python source code syntax.

    Returns:
        (True, None) if syntax is valid, (False, "ERROR: Invalid Python syntax at line X...") otherwise.
    """
    try:
        parse_source(source, filename=filename)
        return True, None
    except Exception as e:
        return False, f"ERROR: {e}"


def validate_database_connection(db_path: Union[str, Path]) -> Tuple[bool, Optional[str]]:
    """Validate that SQLite database can be created or connected to.

    Returns:
        (True, None) if connection succeeds, (False, error_message) otherwise.
    """
    db_str = str(db_path)
    if db_str == ":memory:" or "mode=memory" in db_str:
        return True, None

    try:
        p = Path(db_path).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(p))
        conn.execute("SELECT 1;")
        conn.close()
        return True, None
    except Exception as e:
        return False, f"ERROR: Database connection failed: {e}"
