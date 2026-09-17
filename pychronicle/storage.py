"""PyChronicle SQLite Storage Layer.

Provides transactional persistence for saved programs, version history, execution records,
debug sessions, and state snapshot deltas using Python's standard library sqlite3.
"""

from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, Generator, List, Optional

from pychronicle.config import DEFAULT_DB_PATH
from pychronicle.delta import StateDelta
from pychronicle.exceptions import StorageError


class SQLiteStorage:
    """Manages SQLite storage for PyChronicle programs, versions, executions, sessions, and snapshots."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Create and yield a configured sqlite3 connection, ensuring it is closed upon exit."""
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to connect to SQLite database: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e
        try:
            yield conn
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def init_db(self) -> None:
        """Initialize database schema if it doesn't already exist."""
        schema_sql = """
        CREATE TABLE IF NOT EXISTS programs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            source_code TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_run_at TEXT,
            last_status TEXT DEFAULT 'NEVER_RUN'
        );

        CREATE TABLE IF NOT EXISTS program_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program_id INTEGER NOT NULL,
            version_number INTEGER NOT NULL,
            source_code TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(program_id) REFERENCES programs(id) ON DELETE CASCADE,
            UNIQUE(program_id, version_number)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL DEFAULT 'RUNNING',
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program_id INTEGER NOT NULL,
            version_id INTEGER,
            debug_session_id INTEGER,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL DEFAULT 'RUNNING',
            exit_code INTEGER DEFAULT 0,
            stdout TEXT DEFAULT '',
            stderr TEXT DEFAULT '',
            duration_ms REAL DEFAULT 0.0,
            source_snapshot TEXT NOT NULL,
            FOREIGN KEY(program_id) REFERENCES programs(id) ON DELETE CASCADE,
            FOREIGN KEY(version_id) REFERENCES program_versions(id) ON DELETE SET NULL,
            FOREIGN KEY(debug_session_id) REFERENCES sessions(id) ON DELETE CASCADE
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

        CREATE INDEX IF NOT EXISTS idx_snapshots_session_step 
        ON snapshots(session_id, step);

        CREATE INDEX IF NOT EXISTS idx_program_versions_prog_ver 
        ON program_versions(program_id, version_number);

        CREATE INDEX IF NOT EXISTS idx_executions_prog_date 
        ON executions(program_id, started_at);
        """
        try:
            with self._get_connection() as conn:
                conn.executescript(schema_sql)
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to initialize database schema: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    # =========================================================================
    # Program Management Methods
    # =========================================================================

    def create_program(
        self,
        name: str,
        source_code: str,
        description: Optional[str] = None,
    ) -> int:
        """Create a new program and its initial version in a single transaction."""
        now = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO programs (name, description, source_code, created_at, updated_at, last_status)
                    VALUES (?, ?, ?, ?, ?, 'NEVER_RUN');
                    """,
                    (name, description or "", source_code, now, now),
                )
                program_id = cursor.lastrowid
                if program_id is None:
                    raise StorageError("Failed to obtain ID for created program.")

                conn.execute(
                    """
                    INSERT INTO program_versions (program_id, version_number, source_code, created_at)
                    VALUES (?, 1, ?, ?);
                    """,
                    (program_id, source_code, now),
                )
                conn.commit()
                return program_id
        except sqlite3.IntegrityError as e:
            raise StorageError(
                message=f"A program named '{name}' already exists.",
                db_path=str(self.db_path),
                details=str(e),
            ) from e
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to create program '{name}': {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def get_program(self, program_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a program record by ID along with latest version and run metrics."""
        query = """
        SELECT 
            p.id,
            p.name,
            p.description,
            p.source_code,
            p.created_at,
            p.updated_at,
            p.last_run_at,
            p.last_status,
            COUNT(DISTINCT v.id) as version_count,
            COUNT(DISTINCT e.id) as run_count
        FROM programs p
        LEFT JOIN program_versions v ON p.id = v.program_id
        LEFT JOIN executions e ON p.id = e.program_id
        WHERE p.id = ?
        GROUP BY p.id;
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, (program_id,))
                row = cursor.fetchone()
                if row is None:
                    return None
                return dict(row)
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to fetch program {program_id}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def get_program_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Fetch a program record by unique name."""
        query = """
        SELECT 
            p.id,
            p.name,
            p.description,
            p.source_code,
            p.created_at,
            p.updated_at,
            p.last_run_at,
            p.last_status,
            COUNT(DISTINCT v.id) as version_count,
            COUNT(DISTINCT e.id) as run_count
        FROM programs p
        LEFT JOIN program_versions v ON p.id = v.program_id
        LEFT JOIN executions e ON p.id = e.program_id
        WHERE p.name = ?
        GROUP BY p.id;
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, (name,))
                row = cursor.fetchone()
                if row is None:
                    return None
                return dict(row)
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to fetch program '{name}': {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def update_program(
        self,
        program_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        source_code: Optional[str] = None,
    ) -> bool:
        """Update program metadata. If source_code has changed, archive a new version."""
        now = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                # Fetch existing program
                cur = conn.execute(
                    "SELECT name, description, source_code FROM programs WHERE id = ?;",
                    (program_id,),
                )
                row = cur.fetchone()
                if not row:
                    return False

                current_name = row["name"]
                current_desc = row["description"]
                current_code = row["source_code"]

                new_name = name if name is not None else current_name
                new_desc = description if description is not None else current_desc
                new_code = source_code if source_code is not None else current_code

                code_changed = new_code != current_code

                conn.execute(
                    """
                    UPDATE programs
                    SET name = ?, description = ?, source_code = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (new_name, new_desc, new_code, now, program_id),
                )

                if code_changed:
                    # Find highest version number
                    v_cur = conn.execute(
                        "SELECT MAX(version_number) FROM program_versions WHERE program_id = ?;",
                        (program_id,),
                    )
                    v_row = v_cur.fetchone()
                    next_ver = (v_row[0] or 0) + 1
                    conn.execute(
                        """
                        INSERT INTO program_versions (program_id, version_number, source_code, created_at)
                        VALUES (?, ?, ?, ?);
                        """,
                        (program_id, next_ver, new_code, now),
                    )

                conn.commit()
                return True
        except sqlite3.IntegrityError as e:
            raise StorageError(
                message=f"Another program already has the name '{name}'.",
                db_path=str(self.db_path),
                details=str(e),
            ) from e
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to update program {program_id}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def delete_program(self, program_id: int) -> bool:
        """Atomically delete a program and all associated versions, executions, debug sessions, and snapshots."""
        try:
            with self._get_connection() as conn:
                # Find associated debug sessions to remove cleanly
                cursor = conn.execute(
                    "SELECT debug_session_id FROM executions WHERE program_id = ? AND debug_session_id IS NOT NULL;",
                    (program_id,),
                )
                session_ids = [r[0] for r in cursor.fetchall() if r[0] is not None]

                del_cur = conn.execute("DELETE FROM programs WHERE id = ?;", (program_id,))
                affected = del_cur.rowcount

                if session_ids:
                    placeholders = ",".join("?" * len(session_ids))
                    conn.execute(f"DELETE FROM sessions WHERE id IN ({placeholders});", session_ids)

                conn.commit()
                return affected > 0
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to delete program {program_id}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def duplicate_program(self, program_id: int, new_name: Optional[str] = None) -> int:
        """Duplicate an existing program into a new program without copying execution history."""
        prog = self.get_program(program_id)
        if not prog:
            raise StorageError(f"Cannot duplicate non-existent program {program_id}.")

        if not new_name:
            base_name = f"{prog['name']} Copy"
            new_name = base_name
            counter = 1
            while self.get_program_by_name(new_name) is not None:
                counter += 1
                new_name = f"{base_name} {counter}"

        desc = f"Copy of {prog['name']}. {prog.get('description', '')}".strip()
        return self.create_program(
            name=new_name,
            source_code=prog["source_code"],
            description=desc,
        )

    def list_programs(
        self,
        search_query: Optional[str] = None,
        status_filter: Optional[str] = None,
        sort_by: Optional[str] = "updated_desc",
    ) -> List[Dict[str, Any]]:
        """List programs with filtering, search query matching, and sorting."""
        query = """
        SELECT 
            p.id,
            p.name,
            p.description,
            p.source_code,
            p.created_at,
            p.updated_at,
            p.last_run_at,
            p.last_status,
            COUNT(DISTINCT v.id) as version_count,
            COUNT(DISTINCT e.id) as run_count
        FROM programs p
        LEFT JOIN program_versions v ON p.id = v.program_id
        LEFT JOIN executions e ON p.id = e.program_id
        """
        where_clauses = []
        params: List[Any] = []

        if search_query:
            q_like = f"%{search_query.strip()}%"
            where_clauses.append("(p.name LIKE ? OR p.description LIKE ? OR p.source_code LIKE ?)")
            params.extend([q_like, q_like, q_like])

        if status_filter and status_filter.upper() != "ALL":
            st = status_filter.upper()
            if st == "SUCCESS":
                where_clauses.append("p.last_status = 'SUCCESS'")
            elif st in ("FAILED", "USER_ERROR", "ERROR"):
                where_clauses.append("p.last_status IN ('USER_ERROR', 'PYCHRONICLE_ERROR', 'INTERNAL_ERROR')")
            elif st == "NEVER_RUN":
                where_clauses.append("p.last_status = 'NEVER_RUN'")
            elif st == "RECENTLY_EDITED":
                pass  # Handled by sort
            elif st == "RECENTLY_EXECUTED":
                where_clauses.append("p.last_run_at IS NOT NULL")

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " GROUP BY p.id "

        # Sorting logic
        sort_map = {
            "name_asc": "ORDER BY LOWER(p.name) ASC",
            "name_desc": "ORDER BY LOWER(p.name) DESC",
            "created_asc": "ORDER BY p.created_at ASC",
            "created_desc": "ORDER BY p.created_at DESC",
            "updated_asc": "ORDER BY p.updated_at ASC",
            "updated_desc": "ORDER BY p.updated_at DESC",
            "last_run_asc": "ORDER BY p.last_run_at ASC NULLS LAST",
            "last_run_desc": "ORDER BY p.last_run_at DESC NULLS LAST",
            "status": "ORDER BY p.last_status ASC, p.updated_at DESC",
        }
        if status_filter and status_filter.upper() == "RECENTLY_EDITED":
            query += " ORDER BY p.updated_at DESC"
        elif status_filter and status_filter.upper() == "RECENTLY_EXECUTED":
            query += " ORDER BY p.last_run_at DESC NULLS LAST"
        else:
            query += " " + sort_map.get(sort_by or "updated_desc", "ORDER BY p.updated_at DESC")

        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to list programs: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    # =========================================================================
    # Program Versions Methods
    # =========================================================================

    def create_program_version(
        self,
        program_id: int,
        version_number: int,
        source_code: str,
    ) -> int:
        """Explicitly record a new immutable program version."""
        now = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO program_versions (program_id, version_number, source_code, created_at)
                    VALUES (?, ?, ?, ?);
                    """,
                    (program_id, version_number, source_code, now),
                )
                vid = cursor.lastrowid
                conn.commit()
                if vid is None:
                    raise StorageError("Failed to obtain version ID.")
                return vid
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to record version {version_number} for program {program_id}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def get_program_versions(self, program_id: int) -> List[Dict[str, Any]]:
        """Retrieve all recorded versions for a program ordered newest first."""
        query = """
        SELECT id, program_id, version_number, source_code, created_at
        FROM program_versions
        WHERE program_id = ?
        ORDER BY version_number DESC;
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, (program_id,))
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to fetch versions for program {program_id}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def get_latest_version(self, program_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve the latest version record for a program."""
        query = """
        SELECT id, program_id, version_number, source_code, created_at
        FROM program_versions
        WHERE program_id = ?
        ORDER BY version_number DESC
        LIMIT 1;
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, (program_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to fetch latest version for program {program_id}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    # =========================================================================
    # Execution History Methods
    # =========================================================================

    def create_execution(
        self,
        program_id: int,
        source_snapshot: str,
        version_id: Optional[int] = None,
        debug_session_id: Optional[int] = None,
        started_at: Optional[str] = None,
        status: str = "RUNNING",
    ) -> int:
        """Create a new execution record capturing an immutable source snapshot."""
        if started_at is None:
            started_at = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO executions (
                        program_id, version_id, debug_session_id, started_at, status, source_snapshot
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (program_id, version_id, debug_session_id, started_at, status, source_snapshot),
                )
                exec_id = cursor.lastrowid
                conn.commit()
                if exec_id is None:
                    raise StorageError("Failed to obtain execution ID.")
                return exec_id
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to create execution record for program {program_id}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def update_execution(
        self,
        execution_id: int,
        status: str,
        finished_at: Optional[str] = None,
        stdout: str = "",
        stderr: str = "",
        duration_ms: float = 0.0,
        exit_code: int = 0,
        debug_session_id: Optional[int] = None,
    ) -> None:
        """Finalize an execution record and update the parent program's last status and timestamp."""
        if finished_at is None:
            finished_at = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                # Update execution
                if debug_session_id is not None:
                    conn.execute(
                        """
                        UPDATE executions
                        SET status = ?, finished_at = ?, stdout = ?, stderr = ?, duration_ms = ?, exit_code = ?, debug_session_id = ?
                        WHERE id = ?;
                        """,
                        (status, finished_at, stdout, stderr, duration_ms, exit_code, debug_session_id, execution_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE executions
                        SET status = ?, finished_at = ?, stdout = ?, stderr = ?, duration_ms = ?, exit_code = ?
                        WHERE id = ?;
                        """,
                        (status, finished_at, stdout, stderr, duration_ms, exit_code, execution_id),
                    )

                # Update parent program's last run info
                conn.execute(
                    """
                    UPDATE programs
                    SET last_run_at = ?, last_status = ?
                    WHERE id = (SELECT program_id FROM executions WHERE id = ?);
                    """,
                    (finished_at, status, execution_id),
                )
                conn.commit()
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to update execution {execution_id}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def get_execution(self, execution_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve an execution record by ID with program and version metadata."""
        query = """
        SELECT 
            e.id,
            e.program_id,
            p.name as program_name,
            e.version_id,
            v.version_number,
            e.debug_session_id,
            e.started_at,
            e.finished_at,
            e.status,
            e.exit_code,
            e.stdout,
            e.stderr,
            e.duration_ms,
            e.source_snapshot,
            s.status as session_status,
            s.error as session_error,
            COUNT(sn.id) as step_count
        FROM executions e
        JOIN programs p ON e.program_id = p.id
        LEFT JOIN program_versions v ON e.version_id = v.id
        LEFT JOIN sessions s ON e.debug_session_id = s.id
        LEFT JOIN snapshots sn ON s.id = sn.session_id
        WHERE e.id = ?
        GROUP BY e.id;
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, (execution_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to fetch execution {execution_id}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def list_executions_for_program(self, program_id: int) -> List[Dict[str, Any]]:
        """Retrieve all execution runs for a program ordered newest first."""
        query = """
        SELECT 
            e.id,
            e.program_id,
            e.version_id,
            v.version_number,
            e.debug_session_id,
            e.started_at,
            e.finished_at,
            e.status,
            e.exit_code,
            e.stdout,
            e.stderr,
            e.duration_ms,
            e.source_snapshot,
            COUNT(sn.id) as step_count
        FROM executions e
        LEFT JOIN program_versions v ON e.version_id = v.id
        LEFT JOIN sessions s ON e.debug_session_id = s.id
        LEFT JOIN snapshots sn ON s.id = sn.session_id
        WHERE e.program_id = ?
        GROUP BY e.id
        ORDER BY e.id DESC;
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, (program_id,))
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to list executions for program {program_id}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def get_latest_execution(self, program_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent execution record for a program."""
        execs = self.list_executions_for_program(program_id)
        return execs[0] if execs else None

    def list_all_executions(
        self,
        search_query: Optional[str] = None,
        status_filter: Optional[str] = None,
        sort_by: Optional[str] = "started_desc",
    ) -> List[Dict[str, Any]]:
        """Retrieve all recorded program executions across all programs with search, filter, and sorting."""
        query = """
        SELECT 
            e.id,
            e.program_id,
            p.name as program_name,
            e.version_id,
            v.version_number,
            e.debug_session_id,
            e.started_at,
            e.finished_at,
            e.status,
            e.exit_code,
            e.stdout,
            e.stderr,
            e.duration_ms,
            e.source_snapshot,
            COUNT(sn.id) as step_count
        FROM executions e
        JOIN programs p ON e.program_id = p.id
        LEFT JOIN program_versions v ON e.version_id = v.id
        LEFT JOIN sessions s ON e.debug_session_id = s.id
        LEFT JOIN snapshots sn ON s.id = sn.session_id
        """
        where_clauses = []
        params: List[Any] = []

        if search_query:
            q_like = f"%{search_query.strip()}%"
            where_clauses.append("(p.name LIKE ? OR e.source_snapshot LIKE ? OR e.stdout LIKE ?)")
            params.extend([q_like, q_like, q_like])

        if status_filter and status_filter.upper() != "ALL":
            st = status_filter.upper()
            if st == "SUCCESS":
                where_clauses.append("e.status = 'SUCCESS'")
            elif st in ("FAILED", "USER_ERROR", "ERROR"):
                where_clauses.append("e.status IN ('USER_ERROR', 'PYCHRONICLE_ERROR', 'INTERNAL_ERROR')")

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " GROUP BY e.id "

        sort_map = {
            "started_desc": "ORDER BY e.started_at DESC",
            "started_asc": "ORDER BY e.started_at ASC",
            "duration_desc": "ORDER BY e.duration_ms DESC",
            "name_asc": "ORDER BY LOWER(p.name) ASC, e.started_at DESC",
        }
        query += " " + sort_map.get(sort_by or "started_desc", "ORDER BY e.started_at DESC")

        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to list all executions: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def copy_execution_to_program(self, execution_id: int, new_name: Optional[str] = None) -> int:
        """Create a new editable program based on an immutable historical execution's source snapshot."""
        record = self.get_execution(execution_id)
        if not record:
            raise StorageError(f"Cannot copy non-existent execution {execution_id}.")

        if not new_name:
            base_name = f"{record['program_name']} (Copy from Run #{execution_id})"
            new_name = base_name
            counter = 1
            while self.get_program_by_name(new_name) is not None:
                counter += 1
                new_name = f"{base_name} {counter}"

        desc = f"Editable copy created from execution #{execution_id} of '{record['program_name']}'."
        return self.create_program(
            name=new_name,
            source_code=record["source_snapshot"],
            description=desc,
        )

    # =========================================================================
    # Debug Session & Snapshot Methods (Core Backend Storage)
    # =========================================================================

    def create_session(self, filename: str) -> int:
        """Create a new debugging session record and return its ID."""
        started_at = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "INSERT INTO sessions (filename, started_at, status) VALUES (?, ?, ?);",
                    (filename, started_at, "RUNNING"),
                )
                session_id = cursor.lastrowid
                conn.commit()
                if session_id is None:
                    raise StorageError("Failed to obtain lastrowid for created session.")
                return session_id
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to create session: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def update_session(
        self,
        session_id: int,
        status: str,
        finished_at: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update status, completion timestamp, and error info for an existing session."""
        if finished_at is None:
            finished_at = datetime.now().isoformat()

        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE sessions
                    SET status = ?, finished_at = ?, error = ?
                    WHERE id = ?;
                    """,
                    (status, finished_at, error, session_id),
                )
                conn.commit()
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to update session {session_id}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def save_snapshot(self, session_id: int, delta: StateDelta) -> None:
        """Save a single StateDelta snapshot."""
        self.save_snapshots_batch(session_id, [delta])

    def save_snapshots_batch(self, session_id: int, deltas: List[StateDelta]) -> None:
        """Persist a batch of StateDelta snapshots in a single transaction."""
        if not deltas:
            return

        records = [
            (
                session_id,
                d.step,
                d.line,
                d.event,
                d.scope,
                d.to_json(),
                d.return_value,
                d.exception_info,
                d.call_depth,
            )
            for d in deltas
        ]

        insert_sql = """
        INSERT INTO snapshots (
            session_id, step, line, event, scope, changes, return_value, exception_info, call_depth
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        try:
            with self._get_connection() as conn:
                conn.executemany(insert_sql, records)
                conn.commit()
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to save snapshots for session {session_id}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def get_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve session record by ID."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, filename, started_at, finished_at, status, error FROM sessions WHERE id = ?;",
                    (session_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                return dict(row)
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to fetch session {session_id}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Retrieve all recorded sessions with step counts."""
        query = """
        SELECT 
            s.id, 
            s.filename, 
            s.started_at, 
            s.finished_at, 
            s.status, 
            s.error,
            COUNT(sn.id) as step_count
        FROM sessions s
        LEFT JOIN snapshots sn ON s.id = sn.session_id
        GROUP BY s.id
        ORDER BY s.id DESC;
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query)
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to list sessions: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def get_snapshots(self, session_id: int) -> List[Dict[str, Any]]:
        """Retrieve all snapshots for a given session ordered by step."""
        query = """
        SELECT 
            id, session_id, step, line, event, scope, changes, return_value, exception_info, call_depth
        FROM snapshots
        WHERE session_id = ?
        ORDER BY step ASC;
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, (session_id,))
                rows = cursor.fetchall()
                results = []
                for row in rows:
                    item = dict(row)
                    item["changes"] = json.loads(item["changes"])
                    results.append(item)
                return results
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to fetch snapshots for session {session_id}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e

    def get_snapshot_at_step(self, session_id: int, step: int) -> Optional[Dict[str, Any]]:
        """Retrieve a specific step's snapshot."""
        query = """
        SELECT 
            id, session_id, step, line, event, scope, changes, return_value, exception_info, call_depth
        FROM snapshots
        WHERE session_id = ? AND step = ?;
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(query, (session_id, step))
                row = cursor.fetchone()
                if row is None:
                    return None
                item = dict(row)
                item["changes"] = json.loads(item["changes"])
                return item
        except sqlite3.Error as e:
            raise StorageError(
                message=f"Failed to fetch snapshot for session {session_id} step {step}: {e}",
                db_path=str(self.db_path),
                details=str(e),
            ) from e
