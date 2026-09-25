"""Automated test suite verifying complete multi-user data isolation:
Users can only view, execute, debug, and manage their own programs and historical traces.
"""

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from web import create_app


@pytest.fixture
def multi_user_app():
    """Create a temporary test app with two distinct users."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test_isolation.db"
        app = create_app(
            db_path=db_path,
            test_config={"TESTING": True, "SECRET_KEY": "test-isolation-key"},
        )
        yield app, db_path


def test_user_data_isolation(multi_user_app):
    app, _ = multi_user_app

    client_a = app.test_client()
    client_b = app.test_client()

    # Register User A
    client_a.post(
        "/signup",
        data={
            "name": "User Alice",
            "email": "alice@isolation.test",
            "gender": "Female",
            "dob": "1990-01-01",
            "password": "alicepassword",
            "confirm_password": "alicepassword",
        },
        follow_redirects=True,
    )

    # Register User B
    client_b.post(
        "/signup",
        data={
            "name": "User Bob",
            "email": "bob@isolation.test",
            "gender": "Male",
            "dob": "1992-02-02",
            "password": "bobpassword",
            "confirm_password": "bobpassword",
        },
        follow_redirects=True,
    )

    # 1. User A saves Program A
    res_a = client_a.post(
        "/api/programs/save",
        json={"name": "Alice Secret Formula", "source_code": "x = 42\n"},
    )
    prog_a_id = res_a.get_json()["program"]["id"]

    # 2. User B saves Program B
    res_b = client_b.post(
        "/api/programs/save",
        json={"name": "Bob Secret Project", "source_code": "y = 99\n"},
    )
    prog_b_id = res_b.get_json()["program"]["id"]

    # 3. User A runs Program A
    run_a = client_a.post(f"/api/programs/{prog_a_id}/run", json={})
    exec_a_id = run_a.get_json()["result"]["execution_id"]

    # 4. User B runs Program B
    run_b = client_b.post(f"/api/programs/{prog_b_id}/run", json={})
    exec_b_id = run_b.get_json()["result"]["execution_id"]

    # 5. User A tries to access User B's program
    view_b_by_a = client_a.get(f"/programs/{prog_b_id}", follow_redirects=False)
    # Should redirect with warning
    assert view_b_by_a.status_code == 302

    # User A tries to run User B's program via API
    run_b_by_a = client_a.post(f"/api/programs/{prog_b_id}/run", json={})
    assert run_b_by_a.status_code == 404

    # User A tries to delete User B's program via API
    del_b_by_a = client_a.delete(f"/api/programs/{prog_b_id}")
    assert del_b_by_a.status_code == 404

    # User A tries to access User B's execution step
    step_b_by_a = client_a.get(f"/api/executions/{exec_b_id}/step/1")
    assert step_b_by_a.status_code == 404

    # User A history list does not contain User B's executions
    hist_a = client_a.get("/history")
    assert b"Alice Secret Formula" in hist_a.data
    assert b"Bob Secret Project" not in hist_a.data

    # User B history list does not contain User A's executions
    hist_b = client_b.get("/history")
    assert b"Bob Secret Project" in hist_b.data
    assert b"Alice Secret Formula" not in hist_b.data
