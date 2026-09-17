"""PyChronicle Web Server & REST API.

Provides a lightweight, zero-external-dependency local HTTP server using Python's
standard library `http.server` to serve the rich interactive Web UI and REST API.
"""

from datetime import datetime
import http.server
import json
import mimetypes
import os
from pathlib import Path
import socket
import sys
import threading
import time
from typing import Any, Dict, Optional
import urllib.parse
import webbrowser

from pychronicle.application import ApplicationService
from pychronicle.config import ChronicleConfig, DEFAULT_DB_PATH
from pychronicle.exceptions import PyChronicleError, ReplayError, StorageError

STATIC_DIR = Path(__file__).parent / "static"


class PyChronicleRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP Request Handler for PyChronicle Web UI and REST API."""

    service: ApplicationService

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP server access logs unless debugging."""
        pass

    def _send_json(self, data: Any, status: int = 200) -> None:
        """Helper to send JSON response."""
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message: str, status: int = 400, details: Optional[str] = None) -> None:
        """Helper to send JSON error response."""
        payload = {"error": message}
        if details:
            payload["details"] = details
        self._send_json(payload, status=status)

    def _read_json_body(self) -> Dict[str, Any]:
        """Read and parse JSON request body."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        try:
            return json.loads(raw) if raw.strip() else {}
        except Exception as e:
            raise ValueError(f"Invalid JSON payload: {e}") from e

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests for REST API endpoints and static assets."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            # API Routes
            if path == "/api/health":
                self._send_json({"status": "ok", "app": "PyChronicle", "version": "0.1.0"})
                return

            if path == "/api/programs":
                search = query.get("search", [None])[0]
                status = query.get("status", [None])[0]
                sort = query.get("sort", ["updated_desc"])[0]
                programs = self.service.list_programs(search_query=search, status_filter=status, sort_by=sort)
                self._send_json({"programs": programs})
                return

            if path == "/api/history":
                search = query.get("search", [None])[0]
                status = query.get("status", [None])[0]
                sort = query.get("sort", ["started_desc"])[0]
                executions = self.service.list_all_executions(search_query=search, status_filter=status, sort_by=sort)
                self._send_json({"executions": executions})
                return

            if path.startswith("/api/programs/"):
                parts = path.strip("/").split("/")
                if len(parts) == 3 and parts[2].isdigit():
                    # /api/programs/<id>
                    prog_id = int(parts[2])
                    prog = self.service.get_program(prog_id)
                    if not prog:
                        self._send_error(f"Program {prog_id} not found", status=404)
                        return
                    versions = self.service.get_program_versions(prog_id)
                    executions = self.service.list_executions(prog_id)
                    self._send_json({"program": prog, "versions": versions, "executions": executions})
                    return

                if len(parts) == 4 and parts[2].isdigit() and parts[3] == "executions":
                    # /api/programs/<id>/executions
                    prog_id = int(parts[2])
                    executions = self.service.list_executions(prog_id)
                    self._send_json({"executions": executions})
                    return

                if len(parts) == 4 and parts[2].isdigit() and parts[3] == "versions":
                    # /api/programs/<id>/versions
                    prog_id = int(parts[2])
                    versions = self.service.get_program_versions(prog_id)
                    self._send_json({"versions": versions})
                    return

            if path.startswith("/api/executions/"):
                parts = path.strip("/").split("/")
                if len(parts) == 3 and parts[2].isdigit():
                    # /api/executions/<id>
                    exec_id = int(parts[2])
                    execution = self.service.get_execution(exec_id)
                    if not execution:
                        self._send_error(f"Execution {exec_id} not found", status=404)
                        return
                    self._send_json({"execution": execution})
                    return

                if len(parts) == 5 and parts[2].isdigit() and parts[3] == "replay" and parts[4].isdigit():
                    # /api/executions/<id>/replay/<step>
                    exec_id = int(parts[2])
                    step_num = int(parts[4])
                    watch_param = query.get("watch", [])
                    watch_vars = []
                    if watch_param:
                        for item in watch_param:
                            watch_vars.extend([v.strip() for v in item.split(",") if v.strip()])

                    replay_state = self.service.replay_execution_step(
                        execution_id=exec_id,
                        step_num=step_num,
                        watch_vars=watch_vars if watch_vars else None,
                    )
                    self._send_json(replay_state)
                    return

            # Static File Serving
            self._serve_static(path)

        except Exception as e:
            self._send_error(str(e), status=500, details=str(e))

    def do_POST(self) -> None:
        """Handle POST requests for creating, duplicating, executing programs, and copying historical runs."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            body = self._read_json_body()

            if path == "/api/programs":
                name = body.get("name", "")
                source_code = body.get("source_code", "")
                description = body.get("description", "")
                prog = self.service.create_program(name=name, source_code=source_code, description=description)
                self._send_json({"program": prog}, status=201)
                return

            if path.startswith("/api/executions/"):
                parts = path.strip("/").split("/")
                if len(parts) == 4 and parts[2].isdigit() and parts[3] == "copy-to-workspace":
                    # /api/executions/<id>/copy-to-workspace
                    exec_id = int(parts[2])
                    name = body.get("name")
                    prog = self.service.copy_execution_to_workspace(execution_id=exec_id, new_name=name)
                    self._send_json({"program": prog}, status=201)
                    return

            if path.startswith("/api/programs/"):
                parts = path.strip("/").split("/")
                if len(parts) == 4 and parts[2].isdigit() and parts[3] == "duplicate":
                    # /api/programs/<id>/duplicate
                    prog_id = int(parts[2])
                    new_name = body.get("name")
                    dup = self.service.duplicate_program(program_id=prog_id, new_name=new_name)
                    self._send_json({"program": dup}, status=201)
                    return

                if len(parts) == 4 and parts[2].isdigit() and parts[3] == "run":
                    # /api/programs/<id>/run
                    prog_id = int(parts[2])
                    source_override = body.get("source_code")
                    watch_vars = body.get("watch_vars", [])
                    auto_save = body.get("auto_save", False)

                    if auto_save and source_override is not None:
                        # Update program source before running if auto_save requested
                        prog = self.service.get_program(prog_id)
                        if prog and prog["source_code"] != source_override:
                            self.service.update_program(program_id=prog_id, source_code=source_override)

                    res = self.service.run_program(
                        program_id=prog_id,
                        source_override=source_override,
                        watch_vars=watch_vars,
                    )
                    self._send_json(res)
                    return

            self._send_error(f"Route not found: {path}", status=404)

        except ValueError as e:
            self._send_error(str(e), status=400)
        except Exception as e:
            self._send_error(str(e), status=500, details=str(e))

    def do_PUT(self) -> None:
        """Handle PUT requests for updating existing programs."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            body = self._read_json_body()
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[1] == "programs" and parts[2].isdigit():
                prog_id = int(parts[2])
                name = body.get("name")
                description = body.get("description")
                source_code = body.get("source_code")
                updated = self.service.update_program(
                    program_id=prog_id,
                    name=name,
                    description=description,
                    source_code=source_code,
                )
                self._send_json({"program": updated})
                return

            self._send_error(f"Route not found: {path}", status=404)

        except ValueError as e:
            self._send_error(str(e), status=400)
        except Exception as e:
            self._send_error(str(e), status=500, details=str(e))

    def do_DELETE(self) -> None:
        """Handle DELETE requests for removing programs."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        try:
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[1] == "programs" and parts[2].isdigit():
                prog_id = int(parts[2])
                success = self.service.delete_program(prog_id)
                if not success:
                    self._send_error(f"Program {prog_id} not found", status=404)
                    return
                self._send_json({"success": True, "message": f"Program {prog_id} deleted successfully."})
                return

            self._send_error(f"Route not found: {path}", status=404)

        except Exception as e:
            self._send_error(str(e), status=500, details=str(e))

    def _serve_static(self, req_path: str) -> None:
        """Serve static front-end assets."""
        if req_path in ("/", ""):
            req_path = "/index.html"

        # Sanitize path to prevent directory traversal
        clean_rel = req_path.lstrip("/").replace("\\", "/")
        file_path = (STATIC_DIR / clean_rel).resolve()

        # Ensure requested path is inside STATIC_DIR
        try:
            file_path.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self._send_error("Forbidden", status=403)
            return

        if not file_path.is_file():
            # If not found, try fallback to index.html for client routing
            file_path = STATIC_DIR / "index.html"
            if not file_path.is_file():
                self._send_error("Static asset not found", status=404)
                return

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            if file_path.name.endswith(".js"):
                mime_type = "application/javascript"
            elif file_path.name.endswith(".css"):
                mime_type = "text/css"
            elif file_path.name.endswith(".html"):
                mime_type = "text/html"
            else:
                mime_type = "application/octet-stream"

        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{mime_type}; charset=utf-8" if "text" in mime_type or "javascript" in mime_type or "json" in mime_type else mime_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(content)


class PyChronicleServer:
    """Threaded web server manager for PyChronicle."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        db_path: Path | str = DEFAULT_DB_PATH,
        service: Optional[ApplicationService] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.db_path = Path(db_path)
        self.service = service or ApplicationService(db_path=self.db_path)
        self.httpd: Optional[http.server.ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self, find_available_port: bool = True) -> int:
        """Start the HTTP server on the configured or next available port."""
        PyChronicleRequestHandler.service = self.service

        cur_port = self.port
        while True:
            try:
                self.httpd = http.server.ThreadingHTTPServer((self.host, cur_port), PyChronicleRequestHandler)
                self.port = cur_port
                break
            except OSError:
                if not find_available_port:
                    raise
                cur_port += 1
                if cur_port > self.port + 100:
                    raise RuntimeError("Could not find an available port to bind PyChronicle server.")

        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        """Stop the HTTP server."""
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None

    @property
    def url(self) -> str:
        """Return the accessible local URL."""
        return f"http://{self.host}:{self.port}"


def launch_web_ui(
    host: str = "127.0.0.1",
    port: int = 8080,
    db_path: Path | str = DEFAULT_DB_PATH,
    open_browser: bool = True,
    block: bool = True,
) -> PyChronicleServer:
    """Convenience function to start the web server and optionally open the browser."""
    server = PyChronicleServer(host=host, port=port, db_path=db_path)
    actual_port = server.start()
    url = server.url

    print("=" * 60)
    print("PyChronicle — Generative Python Time-Travel Debugger")
    print("=" * 60)
    print(f"Web UI URL:   {url}")
    print(f"Database:     {server.db_path}")
    print("Press Ctrl+C in terminal to stop server.\n")

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    if block:
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down PyChronicle Web Server...")
            server.stop()

    return server
