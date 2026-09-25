"""Automated test suite for PyChronicle Web Workspace, Debugger Integration,
Time-Travel State Reconstruction, Watch Variables, and Copy-to-Workspace.
"""

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from web import create_app


@pytest.fixture
def logged_in_client():
    """Create a temporary test app, register and log in a test user."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test_debugger.db"
        app = create_app(
            db_path=db_path,
            test_config={"TESTING": True, "SECRET_KEY": "test-debugger-key"},
        )
        with app.test_client() as client:
            client.post(
                "/signup",
                data={
                    "name": "Dev User",
                    "email": "dev@pychronicle.io",
                    "gender": "Female",
                    "dob": "1994-04-04",
                    "password": "devpassword",
                    "confirm_password": "devpassword",
                },
                follow_redirects=True,
            )
            yield app, client, db_path


def test_dashboard_renders(logged_in_client):
    app, client, _ = logged_in_client
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert b"Welcome" in res.data
    assert b"Dev User" in res.data
    assert b"Total Programs" in res.data


def test_save_program_api(logged_in_client):
    app, client, _ = logged_in_client

    # Create new program via API
    res = client.post(
        "/api/programs/save",
        json={
            "name": "Fibonacci Generator",
            "source_code": "a, b = 0, 1\nfor _ in range(5):\n    a, b = b, a + b\n",
            "description": "Calculates Fibonacci sequence",
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["program"]["id"] is not None
    assert data["program"]["name"] == "Fibonacci Generator"

    # Update existing program
    prog_id = data["program"]["id"]
    res_update = client.post(
        "/api/programs/save",
        json={
            "id": prog_id,
            "name": "Fibonacci Generator Updated",
            "source_code": "a, b = 0, 1\nfor _ in range(10):\n    a, b = b, a + b\n",
        },
    )
    assert res_update.status_code == 200
    data_up = res_update.get_json()
    assert data_up["program"]["name"] == "Fibonacci Generator Updated"


def test_run_and_debug_program_api(logged_in_client):
    app, client, _ = logged_in_client

    # 1. Save program
    save_res = client.post(
        "/api/programs/save",
        json={
            "name": "Math Loop",
            "source_code": "total = 0\nfor i in range(1, 4):\n    total += i\nprint('Total:', total)\n",
        },
    )
    prog_id = save_res.get_json()["program"]["id"]

    # 2. Run program via PyChronicle tracer
    run_res = client.post(
        f"/api/programs/{prog_id}/run",
        json={},
    )
    assert run_res.status_code == 200
    run_data = run_res.get_json()
    assert run_data["success"] is True
    assert run_data["result"]["status"] == "SUCCESS"
    assert "Total: 6" in run_data["result"]["stdout"]
    assert run_data["result"]["total_steps"] > 0
    exec_id = run_data["result"]["execution_id"]

    # 3. Step state reconstruction via ReplayEngine
    step_res = client.get(f"/api/executions/{exec_id}/step/1")
    assert step_res.status_code == 200
    step_data = step_res.get_json()
    assert step_data["success"] is True
    assert step_data["state"]["step"] == 1
    assert step_data["state"]["active_scope"] == "<module>"

    # Step at later step with watched variable
    watch_res = client.get(f"/api/executions/{exec_id}/step/4?watch=total&watch=i")
    assert watch_res.status_code == 200
    watch_data = watch_res.get_json()
    assert watch_data["success"] is True
    assert "total" in watch_data["state"]["watch_values"]


def test_debug_view_and_historical_replay(logged_in_client):
    app, client, _ = logged_in_client

    # Create and debug a program
    save_res = client.post(
        "/api/programs/save",
        json={
            "name": "Palindrome Program",
            "source_code": "s = 'radar'\nrev = s[::-1]\nresult = (s == rev)\n",
        },
    )
    prog_id = save_res.get_json()["program"]["id"]

    debug_res = client.post(f"/api/programs/{prog_id}/debug", json={})
    assert debug_res.status_code == 200
    dbg_data = debug_res.get_json()
    assert dbg_data["success"] is True
    exec_id = dbg_data["result"]["execution_id"]

    # Load HTML Debug View
    html_dbg = client.get(f"/debug/{exec_id}")
    assert html_dbg.status_code == 200
    assert b"Palindrome Program" in html_dbg.data
    assert b"Source Code" in html_dbg.data
    assert b"Variables" in html_dbg.data
    assert b"Watch Variables" in html_dbg.data

    # Load HTML Historical Execution (read-only)
    html_hist = client.get(f"/history/{exec_id}")
    assert html_hist.status_code == 200
    assert b"READ-ONLY HISTORICAL" in html_hist.data
    assert b"Copy to Workspace" in html_hist.data

    # Copy to workspace
    copy_res = client.post(f"/api/executions/{exec_id}/copy")
    assert copy_res.status_code == 200
    copy_data = copy_res.get_json()
    assert copy_data["success"] is True
    assert copy_data["program_id"] is not None
