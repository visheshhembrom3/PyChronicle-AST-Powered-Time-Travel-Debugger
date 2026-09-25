"""Automated test suite for PyChronicle Web Authentication, Signup Validation,
Session Handling, Password Resets, and Profile Management.
"""

from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

import pytest
from werkzeug.security import check_password_hash
from web import create_app
from pychronicle.storage import SQLiteStorage


@pytest.fixture
def app_and_client():
    """Create a temporary test application and client."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "test_auth.db"
        app = create_app(
            db_path=db_path,
            test_config={"TESTING": True, "SECRET_KEY": "test-secret-key"},
        )
        with app.test_client() as client:
            yield app, client, db_path


def test_signup_successful(app_and_client):
    app, client, db_path = app_and_client

    response = client.post(
        "/signup",
        data={
            "name": "Alan Turing",
            "email": "alan@enigma.org",
            "gender": "Male",
            "dob": "1912-06-23",
            "password": "secretpassword",
            "confirm_password": "secretpassword",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Welcome" in response.data or b"Dashboard" in response.data or b"Alan Turing" in response.data

    # Verify user in database and password is safe hash
    storage = SQLiteStorage(db_path=db_path)
    user = storage.get_user_by_email("alan@enigma.org")
    assert user is not None
    assert user["name"] == "Alan Turing"
    assert user["gender"] == "Male"
    assert user["dob"] == "1912-06-23"
    assert user["password_hash"] != "secretpassword"
    assert check_password_hash(user["password_hash"], "secretpassword")


def test_signup_validation_missing_fields(app_and_client):
    app, client, _ = app_and_client

    # Missing name
    res = client.post(
        "/signup",
        data={
            "name": "",
            "email": "test@example.com",
            "gender": "Male",
            "dob": "1990-01-01",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert b"Full Name is required" in res.data

    # Missing email
    res = client.post(
        "/signup",
        data={
            "name": "Test User",
            "email": "",
            "gender": "Male",
            "dob": "1990-01-01",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert b"Email address is required" in res.data

    # Invalid email format
    res = client.post(
        "/signup",
        data={
            "name": "Test User",
            "email": "invalid-email",
            "gender": "Male",
            "dob": "1990-01-01",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert b"valid email address" in res.data


def test_signup_duplicate_email_rejected(app_and_client):
    app, client, _ = app_and_client

    # First user
    client.post(
        "/signup",
        data={
            "name": "User One",
            "email": "user1@example.com",
            "gender": "Female",
            "dob": "1995-05-15",
            "password": "password123",
            "confirm_password": "password123",
        },
        follow_redirects=True,
    )

    # Logout
    client.get("/logout", follow_redirects=True)

    # Duplicate registration (case insensitive normalized)
    res = client.post(
        "/signup",
        data={
            "name": "User One Duplicate",
            "email": "USER1@EXAMPLE.COM",
            "gender": "Other",
            "dob": "1996-06-16",
            "password": "password456",
            "confirm_password": "password456",
        },
    )
    assert b"An account with this email already exists" in res.data


def test_signup_password_rules(app_and_client):
    app, client, _ = app_and_client

    # Password less than 6 characters
    res = client.post(
        "/signup",
        data={
            "name": "Short Pass User",
            "email": "short@example.com",
            "gender": "Other",
            "dob": "2000-01-01",
            "password": "12345",
            "confirm_password": "12345",
        },
    )
    assert b"at least 6 characters" in res.data

    # Password mismatch
    res = client.post(
        "/signup",
        data={
            "name": "Mismatch User",
            "email": "mismatch@example.com",
            "gender": "Prefer not to say",
            "dob": "2000-01-01",
            "password": "password123",
            "confirm_password": "differentpassword",
        },
    )
    assert b"do not match" in res.data


def test_login_and_logout_flow(app_and_client):
    app, client, _ = app_and_client

    # Register user
    client.post(
        "/signup",
        data={
            "name": "Login Tester",
            "email": "tester@domain.com",
            "gender": "Male",
            "dob": "1988-08-08",
            "password": "securepassword",
            "confirm_password": "securepassword",
        },
        follow_redirects=True,
    )

    # Logout
    logout_res = client.get("/logout", follow_redirects=True)
    assert b"logged out" in logout_res.data or b"LOGIN" in logout_res.data

    # Wrong password
    bad_login = client.post(
        "/login",
        data={"email": "tester@domain.com", "password": "wrongpassword"},
    )
    assert b"Invalid email or password" in bad_login.data

    # Successful login
    good_login = client.post(
        "/login",
        data={"email": "tester@domain.com", "password": "securepassword"},
        follow_redirects=True,
    )
    assert good_login.status_code == 200
    assert b"Welcome" in good_login.data or b"Dashboard" in good_login.data


def test_protected_routes_require_authentication(app_and_client):
    app, client, _ = app_and_client

    routes_to_test = [
        "/dashboard",
        "/programs",
        "/history",
        "/profile",
    ]

    for route in routes_to_test:
        res = client.get(route, follow_redirects=False)
        assert res.status_code == 302
        assert "/login" in res.headers["Location"]


def test_forgot_password_and_reset_workflow(app_and_client):
    app, client, db_path = app_and_client

    # Register user
    client.post(
        "/signup",
        data={
            "name": "Forgot Tester",
            "email": "forgot@test.com",
            "gender": "Female",
            "dob": "1992-02-02",
            "password": "initialpassword",
            "confirm_password": "initialpassword",
        },
        follow_redirects=True,
    )
    client.get("/logout", follow_redirects=True)

    # Request password reset
    forgot_res = client.post(
        "/forgot-password",
        data={"email": "forgot@test.com"},
    )
    assert forgot_res.status_code == 200

    # Retrieve reset token from DB
    storage = SQLiteStorage(db_path=db_path)
    user = storage.get_user_by_email("forgot@test.com")
    with storage._get_connection() as conn:
        row = conn.execute("SELECT token, expires_at FROM password_resets WHERE user_id = ?;", (user["id"],)).fetchone()
        token = row["token"]

    assert token is not None

    # Perform Reset
    reset_res = client.post(
        f"/reset-password?token={token}",
        data={"token": token, "password": "newsecretpassword", "confirm_password": "newsecretpassword"},
        follow_redirects=True,
    )
    assert b"Password reset successfully" in reset_res.data or b"LOGIN" in reset_res.data

    # Login with new password
    login_new = client.post(
        "/login",
        data={"email": "forgot@test.com", "password": "newsecretpassword"},
        follow_redirects=True,
    )
    assert login_new.status_code == 200
    assert b"Welcome" in login_new.data or b"Dashboard" in login_new.data


def test_profile_update_and_change_password(app_and_client):
    app, client, db_path = app_and_client

    # Signup & login
    client.post(
        "/signup",
        data={
            "name": "Original Name",
            "email": "profile@test.com",
            "gender": "Male",
            "dob": "1990-01-01",
            "password": "oldpassword123",
            "confirm_password": "oldpassword123",
        },
        follow_redirects=True,
    )

    # Update profile details
    update_res = client.post(
        "/profile",
        data={
            "action": "update_profile",
            "name": "Updated Name",
            "gender": "Other",
            "dob": "1991-02-02",
        },
        follow_redirects=True,
    )
    assert b"Profile updated successfully" in update_res.data

    # Change password
    pw_res = client.post(
        "/profile",
        data={
            "action": "change_password",
            "current_password": "oldpassword123",
            "new_password": "newpassword123",
            "confirm_password": "newpassword123",
        },
        follow_redirects=True,
    )
    assert b"Password changed successfully" in pw_res.data
