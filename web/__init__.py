"""PyChronicle Flask Web Application Factory.

Initializes the Flask app, configures template and static directories,
registers authentication, UI, and API blueprints, and attaches storage services.
"""

import os
from pathlib import Path
from typing import Optional
from flask import Flask, render_template

from pychronicle.config import DEFAULT_DB_PATH
from pychronicle.storage import SQLiteStorage
from pychronicle.application import ApplicationService


def create_app(
    db_path: Path | str = DEFAULT_DB_PATH,
    test_config: Optional[dict] = None,
) -> Flask:
    """Create and configure the Flask web application."""
    project_root = Path(__file__).parent.parent.resolve()
    template_dir = project_root / "templates"
    static_dir = project_root / "static"

    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
        static_url_path="/static",
    )

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("PYCHRONICLE_SECRET_KEY", "pychronicle-dev-secret-key-2026-ast"),
        DB_PATH=Path(db_path),
    )

    if test_config:
        app.config.update(test_config)

    # Initialize storage and application service
    storage = SQLiteStorage(db_path=app.config["DB_PATH"])
    service = ApplicationService(db_path=app.config["DB_PATH"], storage=storage)
    app.storage = storage
    app.service = service

    # Register Blueprints
    from web.auth import auth_bp
    from web.routes import routes_bp
    from web.api import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(routes_bp)
    app.register_blueprint(api_bp)

    @app.context_processor
    def inject_globals():
        return {
            "app_name": "PyChronicle",
            "app_version": "0.1.0",
        }

    return app
