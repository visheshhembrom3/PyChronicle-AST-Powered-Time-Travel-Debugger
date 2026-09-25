"""PyChronicle REST API Blueprint for Web UI Interactions.

Provides JSON API endpoints for AJAX code execution, state reconstruction,
watch variable evaluation, program CRUD, and execution copying.
"""

from typing import Any, Dict, List, Optional
from flask import Blueprint, current_app, g, jsonify, request, url_for

from web.auth import login_required
from pychronicle.exceptions import PyChronicleError, ReplayError, StorageError

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/programs/save", methods=["POST"])
@login_required
def save_program():
    """Save (create or update) a Python program."""
    data = request.get_json() or {}
    program_id = data.get("id")
    name = (data.get("name") or "").strip()
    source_code = data.get("source_code", "")
    description = (data.get("description") or "").strip()

    user_id = g.user["id"]
    service = current_app.service

    if not name:
        return jsonify({"success": False, "error": "Program name cannot be empty."}), 400

    try:
        if program_id:
            prog = service.update_program(
                program_id=int(program_id),
                name=name,
                source_code=source_code,
                description=description,
                user_id=user_id,
            )
        else:
            prog = service.create_program(
                name=name,
                source_code=source_code,
                description=description,
                user_id=user_id,
            )
        return jsonify({"success": True, "program": prog})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except StorageError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to save program: {e}"}), 500


@api_bp.route("/programs/<int:program_id>/run", methods=["POST"])
@login_required
def run_program(program_id: int):
    """Execute a program via PyChronicle tracer backend and return output metrics."""
    data = request.get_json() or {}
    source_code = data.get("source_code")
    watch_vars = data.get("watch_vars", [])

    user_id = g.user["id"]
    service = current_app.service

    try:
        result = service.run_program(
            program_id=program_id,
            source_override=source_code,
            watch_vars=watch_vars,
            user_id=user_id,
        )
        return jsonify({"success": True, "result": result})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": f"Execution failed: {e}"}), 500


@api_bp.route("/programs/<int:program_id>/debug", methods=["POST"])
@login_required
def debug_program(program_id: int):
    """Execute a program through PyChronicle and prepare for interactive debugging."""
    data = request.get_json() or {}
    source_code = data.get("source_code")
    watch_vars = data.get("watch_vars", [])

    user_id = g.user["id"]
    service = current_app.service

    try:
        result = service.run_program(
            program_id=program_id,
            source_override=source_code,
            watch_vars=watch_vars,
            user_id=user_id,
        )
        redirect_url = url_for("routes.debug_view", execution_id=result["execution_id"])
        return jsonify({
            "success": True,
            "result": result,
            "redirect_url": redirect_url,
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": f"Debug initialization failed: {e}"}), 500


@api_bp.route("/executions/<int:execution_id>/step/<int:step_num>", methods=["GET"])
@login_required
def get_execution_step(execution_id: int, step_num: int):
    """Reconstruct exact historical execution state at a step via PyChronicle ReplayEngine."""
    watch_vars = request.args.getlist("watch")
    user_id = g.user["id"]
    service = current_app.service

    # Validate execution ownership
    exec_record = service.get_execution(execution_id, user_id=user_id)
    if not exec_record:
        return jsonify({"success": False, "error": "Execution not found or access denied."}), 404

    try:
        step_state = service.replay_execution_step(
            execution_id=execution_id,
            step_num=step_num,
            watch_vars=watch_vars,
        )
        return jsonify({"success": True, "state": step_state})
    except ReplayError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to reconstruct step {step_num}: {e}"}), 500


@api_bp.route("/executions/<int:execution_id>/copy", methods=["POST"])
@login_required
def copy_execution(execution_id: int):
    """Copy an immutable historical execution into a new editable program in workspace."""
    user_id = g.user["id"]
    service = current_app.service

    try:
        new_prog = service.copy_execution_to_workspace(
            execution_id=execution_id,
            user_id=user_id,
        )
        redirect_url = url_for("routes.workspace", program_id=new_prog["id"])
        return jsonify({
            "success": True,
            "program_id": new_prog["id"],
            "redirect_url": redirect_url,
        })
    except StorageError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to copy execution: {e}"}), 500


@api_bp.route("/programs/<int:program_id>", methods=["DELETE"])
@login_required
def delete_program(program_id: int):
    """Delete a program and all its execution history."""
    user_id = g.user["id"]
    service = current_app.service

    try:
        deleted = service.delete_program(program_id=program_id, user_id=user_id)
        if not deleted:
            return jsonify({"success": False, "error": "Program not found or access denied."}), 404
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to delete program: {e}"}), 500
