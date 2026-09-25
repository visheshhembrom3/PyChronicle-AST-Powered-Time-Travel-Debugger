"""PyChronicle UI Routes Blueprint.

Provides HTML page routes for Dashboard, Workspace, Time-Travel Debugger,
Execution History, and Historical Read-Only Replay.
"""

from typing import Any, Dict, List, Optional
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)

from web.auth import login_required
from pychronicle.replay import ReplayEngine

routes_bp = Blueprint("routes", __name__)


@routes_bp.route("/")
def index():
    """Root entry point: redirects to dashboard or login."""
    if g.user:
        return redirect(url_for("routes.dashboard"))
    return redirect(url_for("auth.login"))


@routes_bp.route("/dashboard")
@login_required
def dashboard():
    """Developer Dashboard displaying user's recent programs, executions, and metrics."""
    user_id = g.user["id"]
    service = current_app.service

    # Fetch user's programs and executions
    programs = service.list_programs(user_id=user_id)
    executions = service.list_all_executions(user_id=user_id)

    total_programs = len(programs)
    total_executions = len(executions)

    recent_programs = programs[:5]
    recent_executions = executions[:10]

    return render_template(
        "dashboard.html",
        user=g.user,
        total_programs=total_programs,
        total_executions=total_executions,
        recent_programs=recent_programs,
        recent_executions=recent_executions,
    )


@routes_bp.route("/programs")
@routes_bp.route("/programs/<int:program_id>")
@login_required
def workspace(program_id: Optional[int] = None):
    """Interactive Python Programming Workspace."""
    user_id = g.user["id"]
    service = current_app.service

    active_program = None
    if program_id is not None:
        active_program = service.get_program(program_id, user_id=user_id)
        if not active_program:
            flash(f"Program #{program_id} not found or access denied.", "warning")
            return redirect(url_for("routes.workspace"))
    else:
        active_program = {
            "id": None,
            "name": "Untitled Program",
            "source_code": "",
            "description": "",
            "last_status": "READY",
        }

    all_programs = service.list_programs(user_id=user_id)

    return render_template(
        "workspace.html",
        user=g.user,
        program=active_program,
        programs=all_programs,
    )


@routes_bp.route("/debug/<int:execution_id>")
@login_required
def debug_view(execution_id: int):
    """Interactive Time-Travel Debugger view for an execution run."""
    user_id = g.user["id"]
    service = current_app.service
    storage = current_app.storage

    exec_record = service.get_execution(execution_id, user_id=user_id)
    if not exec_record:
        flash(f"Execution #{execution_id} not found or access denied.", "danger")
        return redirect(url_for("routes.dashboard"))

    session_id = exec_record.get("debug_session_id")
    if not session_id:
        flash("This execution does not contain recorded debug snapshots.", "warning")
        return redirect(url_for("routes.workspace", program_id=exec_record["program_id"]))

    try:
        replay = ReplayEngine(session_id=session_id, storage=storage)
        timeline = replay.get_timeline()
        initial_state = replay.state_at(1).to_dict() if replay.total_steps > 0 else None
    except Exception as e:
        flash(f"Failed to load replay engine: {e}", "danger")
        return redirect(url_for("routes.dashboard"))

    return render_template(
        "debug.html",
        user=g.user,
        execution=exec_record,
        timeline=timeline,
        initial_state=initial_state,
        is_readonly=False,
    )


@routes_bp.route("/history")
@login_required
def history():
    """Execution History listing page."""
    user_id = g.user["id"]
    service = current_app.service

    search = request.args.get("search")
    status = request.args.get("status")
    sort_by = request.args.get("sort", "started_desc")

    executions = service.list_all_executions(
        search_query=search,
        status_filter=status,
        sort_by=sort_by,
        user_id=user_id,
    )

    return render_template(
        "history.html",
        user=g.user,
        executions=executions,
        search=search or "",
        status_filter=status or "ALL",
        sort_by=sort_by,
    )


@routes_bp.route("/history/<int:execution_id>")
@login_required
def historical_execution(execution_id: int):
    """Read-only historical execution viewer with Copy to Workspace action."""
    user_id = g.user["id"]
    service = current_app.service
    storage = current_app.storage

    exec_record = service.get_execution(execution_id, user_id=user_id)
    if not exec_record:
        flash(f"Execution #{execution_id} not found or access denied.", "danger")
        return redirect(url_for("routes.history"))

    session_id = exec_record.get("debug_session_id")
    timeline = []
    initial_state = None
    if session_id:
        try:
            replay = ReplayEngine(session_id=session_id, storage=storage)
            timeline = replay.get_timeline()
            if replay.total_steps > 0:
                initial_state = replay.state_at(1).to_dict()
        except Exception:
            pass

    return render_template(
        "debug.html",
        user=g.user,
        execution=exec_record,
        timeline=timeline,
        initial_state=initial_state,
        is_readonly=True,
    )
