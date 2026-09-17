"""PyChronicle Configuration and Defaults.

Central configuration settings for database storage, serialization limits,
filtering rules, and AST hook injection.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Set


# Internal hook name injected by the AST rewriter
INTERNAL_HOOK_NAME: str = "__pychronicle_hook__"

# Default SQLite database path
DEFAULT_DB_PATH: Path = Path("data") / "pychronicle.db"

# Internal variables to filter from user state capture
IGNORED_VARIABLE_NAMES: Set[str] = {
    INTERNAL_HOOK_NAME,
    "__builtins__",
    "__doc__",
    "__file__",
    "__name__",
    "__package__",
    "__loader__",
    "__spec__",
    "__cached__",
    "__annotations__",
}

# Maximum depth for recursive container serialization
MAX_SERIALIZATION_DEPTH: int = 5

# Maximum items to inspect in large sequences/dictionaries
MAX_CONTAINER_ITEMS: int = 100

# Maximum string length before truncation in representation
MAX_REPR_LENGTH: int = 1000


@dataclass
class ChronicleConfig:
    """Runtime configuration for a PyChronicle debugging session."""

    db_path: Path = DEFAULT_DB_PATH
    hook_name: str = INTERNAL_HOOK_NAME
    max_depth: int = MAX_SERIALIZATION_DEPTH
    max_items: int = MAX_CONTAINER_ITEMS
    max_repr_length: int = MAX_REPR_LENGTH
    verbose: bool = False
    enable_ast_hooks: bool = True
    record_full_snapshots: bool = False
