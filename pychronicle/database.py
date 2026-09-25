"""PyChronicle SQLite Database Layer.

Provides high-level database abstraction for managing sessions, snapshots,
and variable deltas in SQLite. Supports both in-memory (':memory:') and persistent
file-based databases with transactional integrity.
"""

from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, Generator, List, Optional, Union

from pychronicle.config import DEFAULT_DB_PATH
from pychronicle.delta import StateDelta
from pychronicle.exceptions import StorageError


class Database:
    """Database interface supporting both in-memory and persistent SQLite backends."""

    def __init__(self, db_path: Union[str, Path] = ":memory:") -> None:
        self.raw_path = str(db_path)
        self.is_memory = (self.raw_path == ":memory:" or "mode=memory" in self.raw_path)

        if self.is_memory:
            self.db_path = Path(":memory:")
            # Keep a persistent connection for in-memory DB so schema and records persist
            self._memory_conn: Optional[sqlite3.Connection] = sqlite3.connect(
                "file:pychronicle_shared_mem?mode=memory&cache=shared",
                uri=True,
                check_same_thread=False,
            )
            self._memory_conn.row_factory = sqlite3.Row
            self._memory_conn.execute("PRAGMA foreign_keys = ON;")
        else:
            self.db_path = Path(db_path).resolve()
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._memory_conn = None

        self.init_schema()

    @contextmanager
    def get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Provide a connection context. Uses shared in-memory connection or opens file connection."""
        if self.is_memory and self._memory_conn is not None:
            yield self._memory_conn
        else:
            conn = None
            try:
                conn = sqlite3.connect(str(self.db_path))
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON;")
                conn.execute("PRAGMA journal_mode = WAL;")
                yield conn
            except sqlite3.Error as e:
                raise StorageError(
                    message=f"Failed to connect to SQLite database: {e}",
                    db_path=str(self.db_path),
                    details=str(e),
                ) from e
            finally:
                if conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def init_schema(self) -> None:
        """Initialize database tables for sessions, snapshots, variable_deltas, and programs."""
        schema_sql = """
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL DEFAULT 'RUNNING',
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            step INTEGER NOT NULL,
            line INTEGER,
            event TEXT NOT NULL,
            scope TEXT NOT NULL,
            changes TEXT NOT NULL,
            return_value TEXT,
            exception_info TEXT,
            call_depth INTEGER DEFAULT 0,
            FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS variable_deltas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            session_id INTEGER NOT NULL,
            step INTEGER NOT NULL,
            line INTEGER,
            variable_name TEXT NOT NULL,
            operation TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            serialized_value TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE,
            FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_session_step ON snapshots(session_id, step);
        CREATE INDEX IF NOT EXISTS idx_vardeltas_session_var ON variable_deltas(session_id, variable_name);
        CREATE INDEX IF NOT EXISTS idx_vardeltas_step ON variable_deltas(session_id, step);
        """
        try:
            with self.get_connection() as conn:
                conn.executescript(schema_sql)
                conn.commit()
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to initialize database schema: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def create_session(self, filename: str) -> int:
        """Create a new debug session record and return its ID."""
        now = datetime.now().isoformat()
        try:
            with self.get_connection() as conn:
                cur = conn.execute(
                    "INSERT INTO sessions (filename, started_at, status) VALUES (?, ?, 'RUNNING');",
                    (filename, now),
                )
                conn.commit()
                if cur.lastrowid is None:
                    raise StorageError("Failed to create session record.")
                return cur.lastrowid
        except sqlite3.Error as e:
            raise StorageError(f"Failed to create session: {e}", db_path=str(self.db_path)) from e

    def update_session(
        self,
        session_id: int,
        status: str,
        finished_at: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update session execution status, finish timestamp, and error."""
        if finished_at is None:
            finished_at = datetime.now().isoformat()
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "UPDATE sessions SET status = ?, finished_at = ?, error = ? WHERE id = ?;",
                    (status, finished_at, error, session_id),
                )
                conn.commit()
        except sqlite3.Error as e:
            raise StorageError(f"Failed to update session {session_id}: {e}", db_path=str(self.db_path)) from e

    def get_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve a session by ID."""
        try:
            with self.get_connection() as conn:
                cur = conn.execute("SELECT * FROM sessions WHERE id = ?;", (session_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            raise StorageError(f"Failed to fetch session {session_id}: {e}", db_path=str(self.db_path)) from e

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List all recorded sessions with step counts."""
        query = """
        SELECT s.id, s.filename, s.started_at, s.finished_at, s.status, s.error, COUNT(sn.id) as step_count
        FROM sessions s
        LEFT JOIN snapshots sn ON s.id = sn.session_id
        GROUP BY s.id
        ORDER BY s.id DESC;
        """
        try:
            with self.get_connection() as conn:
                cur = conn.execute(query)
                return [dict(r) for r in cur.fetchall()]
        except sqlite3.Error as e:
            raise StorageError(f"Failed to list sessions: {e}", db_path=str(self.db_path)) from e

    def save_snapshot(self, session_id: int, delta: StateDelta) -> int:
        """Save a single snapshot and its decomposed variable deltas."""
        now = datetime.now().isoformat()
        changes_json = delta.to_json()
        try:
            with self.get_connection() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO snapshots (
                        session_id, step, line, event, scope, changes, return_value, exception_info, call_depth
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        session_id,
                        delta.step,
                        delta.line,
                        delta.event,
                        delta.scope,
                        changes_json,
                        delta.return_value,
                        delta.exception_info,
                        delta.call_depth,
                    ),
                )
                snap_id = cur.lastrowid

                # Save individual variable deltas for granular delta querying
                for var_name, chg in delta.changes.items():
                    conn.execute(
                        """
                        INSERT INTO variable_deltas (
                            snapshot_id, session_id, step, line, variable_name, operation, old_value, new_value, serialized_value, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """,
                        (
                            snap_id,
                            session_id,
                            delta.step,
                            delta.line,
                            var_name,
                            chg.get("operation", "UPDATE"),
                            str(chg.get("old")) if chg.get("old") is not None else None,
                            str(chg.get("new")) if chg.get("new") is not None else None,
                            str(chg.get("new")) if chg.get("new") is not None else None,
                            now,
                        ),
                    )

                conn.commit()
                return snap_id or 0
        except sqlite3.Error as e:
            raise StorageError(f"Failed to save snapshot: {e}", db_path=str(self.db_path)) from e

    def save_snapshots_batch(self, session_id: int, deltas: List[StateDelta]) -> None:
        """Save a batch of snapshots and variable deltas atomically."""
        for d in deltas:
            self.save_snapshot(session_id, d)

    def get_snapshots(self, session_id: int) -> List[Dict[str, Any]]:
        """Retrieve all snapshots for a session ordered by step."""
        query = "SELECT * FROM snapshots WHERE session_id = ? ORDER BY step ASC;"
        try:
            with self.get_connection() as conn:
                cur = conn.execute(query, (session_id,))
                rows = cur.fetchall()
                results = []
                for r in rows:
                    item = dict(r)
                    item["changes"] = json.loads(item["changes"]) if isinstance(item["changes"], str) else item["changes"]
                    results.append(item)
                return results
        except sqlite3.Error as e:
            raise StorageError(f"Failed to get snapshots: {e}", db_path=str(self.db_path)) from e

    def get_variable_deltas(self, session_id: int, variable_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Query individual variable delta records."""
        if variable_name:
            query = "SELECT * FROM variable_deltas WHERE session_id = ? AND variable_name = ? ORDER BY step ASC;"
            params = (session_id, variable_name)
        else:
            query = "SELECT * FROM variable_deltas WHERE session_id = ? ORDER BY step ASC, id ASC;"
            params = (session_id,)

        try:
            with self.get_connection() as conn:
                cur = conn.execute(query, params)
                return [dict(r) for r in cur.fetchall()]
        except sqlite3.Error as e:
            raise StorageError(f"Failed to get variable deltas: {e}", db_path=str(self.db_path)) from e

    def close(self) -> None:
        """Close persistent in-memory connection if active."""
        if self._memory_conn:
            try:
                self._memory_conn.close()
            except Exception:
                pass
            self._memory_conn = None
