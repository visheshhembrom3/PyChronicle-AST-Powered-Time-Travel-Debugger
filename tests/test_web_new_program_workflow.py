"""Automated test suite verifying New Program (+) workspace isolation,
unsaved workspace creation, separate record persistence, and non-overwriting behavior.
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
        db_path = Path(tmp) / "test_workspace_workflow.db"
        app = create_app(
            db_path=db_path,
            test_config={"TESTING": True, "SECRET_KEY": "test-workflow-key"},
        )
        with app.test_client() as client:
            client.post(
                "/signup",
                data={
                    "name": "Developer Tester",
                    "email": "dev@test.org",
                    "gender": "Other",
                    "dob": "1995-05-05",
                    "password": "password123",
                    "confirm_password": "password123",
                },
                follow_redirects=True,
            )
            yield app, client, db_path


def test_new_program_creates_fresh_workspace_without_loading_previous(logged_in_client):
    """Verify Section 14 full workflow:
    1. Save program 'Even Number'.
    2. Request /programs (New Program) -> returns fresh blank Untitled Program.
    3. Save program 'Odd Number'.
    4. Verify 'Even Number' is not overwritten and retains original code.
    5. Verify 'Odd Number' has separate ID and new code.
    6. Verify both can be independently loaded, run, and debugged.
    """
    app, client, _ = logged_in_client

    even_code = (
        "start = 1\n"
        "end = 20\n"
        "for num in range(start, end + 1):\n"
        "    if num % 2 == 0:\n"
        "        print(num)\n"
    )

    # STEP 1: Save 'Even Number'
    res_even = client.post(
        "/api/programs/save",
        json={
            "name": "Even Number",
            "source_code": even_code,
        },
    )
    assert res_even.status_code == 200
    even_data = res_even.get_json()
    assert even_data["success"] is True
    even_id = even_data["program"]["id"]

    # Verify Even Number workspace page
    res_even_view = client.get(f"/programs/{even_id}")
    assert res_even_view.status_code == 200
    assert b"Even Number" in res_even_view.data
    assert b"range(start, end + 1)" in res_even_view.data

    # STEP 2: Request New Program workspace via /programs (Simulating + button)
    res_new_view = client.get("/programs")
    assert res_new_view.status_code == 200
    # Must NOT contain Even Number code or name
    assert b'value="Untitled Program"' in res_new_view.data
    assert b'value=""' in res_new_view.data  # id is empty
    assert b"start = 1" not in res_new_view.data
    assert b"No output yet." in res_new_view.data

    # STEP 3: Save 'Odd Number' as a new program
    odd_code = (
        "for num in range(1, 10):\n"
        "    if num % 2 != 0:\n"
        "        print(num)\n"
    )
    res_odd = client.post(
        "/api/programs/save",
        json={
            "name": "Odd Number",
            "source_code": odd_code,
        },
    )
    assert res_odd.status_code == 200
    odd_data = res_odd.get_json()
    assert odd_data["success"] is True
    odd_id = odd_data["program"]["id"]

    assert odd_id != even_id

    # STEP 4: Verify 'Even Number' is unchanged
    res_even_check = client.get(f"/programs/{even_id}")
    assert res_even_check.status_code == 200
    assert b"Even Number" in res_even_check.data
    assert b"range(start, end + 1)" in res_even_check.data
    assert b"range(1, 10)" not in res_even_check.data

    # STEP 5: Verify 'Odd Number' has its own code
    res_odd_check = client.get(f"/programs/{odd_id}")
    assert res_odd_check.status_code == 200
    assert b"Odd Number" in res_odd_check.data
    assert b"range(1, 10)" in res_odd_check.data
    assert b"start = 1" not in res_odd_check.data

    # STEP 6: Run both programs and verify execution output
    run_even = client.post(f"/api/programs/{even_id}/run", json={})
    assert run_even.status_code == 200
    assert "2\n4\n6" in run_even.get_json()["result"]["stdout"]

    run_odd = client.post(f"/api/programs/{odd_id}/run", json={})
    assert run_odd.status_code == 200
    assert "1\n3\n5" in run_odd.get_json()["result"]["stdout"]

    # STEP 7: Verify History
    hist_res = client.get("/history")
    assert hist_res.status_code == 200
    assert b"Even Number" in hist_res.data
    assert b"Odd Number" in hist_res.data
