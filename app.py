"""PyChronicle Web Application Entry Point.

Starts the Flask development server for PyChronicle AST Time-Travel Debugger.
Usage:
    python app.py
    python app.py --port 5000 --host 127.0.0.1
"""

import argparse
from pathlib import Path
import sys

# Ensure workspace root is in sys.path
_workspace_root = str(Path(__file__).parent.resolve())
if _workspace_root not in sys.path:
    sys.path.insert(0, _workspace_root)

from pychronicle.config import DEFAULT_DB_PATH
from web import create_app


def main() -> None:
    """Parse CLI arguments and run the Flask application server."""
    parser = argparse.ArgumentParser(description="PyChronicle Web Application")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on (default: 5000)")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="Path to SQLite database")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")

    args = parser.parse_args()

    app = create_app(db_path=args.db)

    print("=" * 65)
    print("PyChronicle — AST-Powered Python Time-Travel Debugger")
    print("Web Application Server")
    print("=" * 65)
    print(f"Database:  {Path(args.db).resolve()}")
    print(f"Running at: http://{args.host}:{args.port}/")
    print("Press Ctrl+C to stop.")
    print("=" * 65)

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
