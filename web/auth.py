"""PyChronicle Authentication Blueprint.

Handles user signup, login, logout, password reset workflows, profile management,
and session-based access control with Werkzeug password hashing.
"""

from datetime import datetime, timedelta
from functools import wraps
import re
import secrets
from typing import Any, Callable, Optional
from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from pychronicle.exceptions import StorageError

auth_bp = Blueprint("auth", __name__)

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")
VALID_GENDERS = ["Male", "Female", "Other", "Prefer not to say"]


def login_required(view: Callable) -> Callable:
    """Decorator to require authenticated user session for protected routes."""
    @wraps(view)
    def wrapped_view(*args: Any, **kwargs: Any) -> Any:
        user_id = session.get("user_id")
        if not user_id:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("auth.login", next=request.full_path if request.query_string else request.path))
        # Ensure user still exists in database
        storage = current_app.storage
        user = storage.get_user_by_id(user_id)
        if not user:
            session.clear()
            flash("Your session has expired. Please log in again.", "warning")
            return redirect(url_for("auth.login"))
        g.user = user
        return view(*args, **kwargs)

    return wrapped_view


@auth_bp.before_app_request
def load_logged_in_user() -> None:
    """Load logged-in user into Flask's `g` context if session active."""
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        storage = current_app.storage
        g.user = storage.get_user_by_id(user_id)


# =============================================================================
# Signup & Login
# =============================================================================

@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    """User registration page with comprehensive server-side validation."""
    if g.user:
        return redirect(url_for("routes.dashboard"))

    form_data = {
        "name": "",
        "email": "",
        "gender": "",
        "dob": "",
    }
    error = None

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        gender = request.form.get("gender", "").strip()
        dob = request.form.get("dob", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        form_data = {
            "name": name,
            "email": email,
            "gender": gender,
            "dob": dob,
        }

        # Server-side validation
        if not name:
            error = "Full Name is required."
        elif len(name) > 100:
            error = "Full Name cannot exceed 100 characters."
        elif not email:
            error = "Email address is required."
        elif not EMAIL_REGEX.match(email):
            error = "Please enter a valid email address."
        elif not gender or gender not in VALID_GENDERS:
            error = "Please select a valid gender option."
        elif not dob:
            error = "Date of Birth is required."
        elif not password:
            error = "Password is required."
        elif len(password) < 6:
            error = "Password must be at least 6 characters long."
        elif password != confirm_password:
            error = "Password and Confirm Password do not match."
        else:
            # Validate DOB date format
            try:
                dob_date = datetime.strptime(dob, "%Y-%m-%d")
                if dob_date > datetime.now():
                    error = "Date of Birth cannot be in the future."
            except ValueError:
                error = "Invalid Date of Birth format. Please use YYYY-MM-DD."

        if not error:
            storage = current_app.storage
            # Check unique email
            existing_user = storage.get_user_by_email(email)
            if existing_user:
                error = "An account with this email already exists."
            else:
                pw_hash = generate_password_hash(password)
                try:
                    user_id = storage.create_user(
                        name=name,
                        email=email,
                        gender=gender,
                        dob=dob,
                        password_hash=pw_hash,
                    )
                    # Automatically seed default demo program for new user
                    service = current_app.service
                    from pychronicle.application import DEFAULT_DEMO_NAME, DEFAULT_DEMO_CODE, DEFAULT_DEMO_DESC
                    try:
                        service.create_program(
                            name=DEFAULT_DEMO_NAME,
                            source_code=DEFAULT_DEMO_CODE,
                            description=DEFAULT_DEMO_DESC,
                            user_id=user_id,
                        )
                    except Exception:
                        pass

                    session.clear()
                    session["user_id"] = user_id
                    session["user_name"] = name
                    session["user_email"] = email
                    flash("Account created successfully! Welcome to PyChronicle.", "success")
                    return redirect(url_for("routes.dashboard"))
                except StorageError as e:
                    error = str(e)
                except Exception as e:
                    error = f"Registration failed: {e}"

    return render_template(
        "signup.html",
        form_data=form_data,
        error=error,
        valid_genders=VALID_GENDERS,
    )


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """User authentication login page."""
    if g.user:
        return redirect(url_for("routes.dashboard"))

    error = None
    email_val = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        email_val = email

        if not email or not password:
            error = "Both email and password are required."
        else:
            storage = current_app.storage
            user = storage.get_user_by_email(email)
            if not user or not check_password_hash(user["password_hash"], password):
                error = "Invalid email or password."
            else:
                session.clear()
                session["user_id"] = user["id"]
                session["user_name"] = user["name"]
                session["user_email"] = user["email"]

                next_url = request.args.get("next")
                if next_url and next_url.startswith("/"):
                    return redirect(next_url)
                return redirect(url_for("routes.dashboard"))

    return render_template("login.html", error=error, email=email_val)


@auth_bp.route("/logout")
def logout():
    """Clear session and redirect to login."""
    session.clear()
    flash("You have been successfully logged out.", "info")
    return redirect(url_for("auth.login"))


# =============================================================================
# Password Reset Workflows
# =============================================================================

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Forgot password request page."""
    if g.user:
        return redirect(url_for("routes.dashboard"))

    error = None
    reset_link = None
    email_val = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        email_val = email

        if not email:
            error = "Please enter your registered email address."
        else:
            storage = current_app.storage
            user = storage.get_user_by_email(email)
            if not user:
                error = "No registered account found with that email address."
            else:
                token = secrets.token_urlsafe(32)
                expires_at = (datetime.now() + timedelta(hours=1)).isoformat()
                try:
                    storage.create_password_reset(user_id=user["id"], token=token, expires_at=expires_at)
                    reset_link = url_for("auth.reset_password", token=token, _external=True)
                    flash("Password reset token generated. Use the link below to set a new password.", "info")
                except Exception as e:
                    error = f"Failed to generate reset token: {e}"

    return render_template("forgot_password.html", error=error, reset_link=reset_link, email=email_val)


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """Password reset form using secure token validation."""
    token = request.args.get("token") or request.form.get("token", "")
    if not token:
        flash("Invalid or missing password reset token.", "danger")
        return redirect(url_for("auth.forgot_password"))

    storage = current_app.storage
    reset_record = storage.get_password_reset(token)
    now_iso = datetime.now().isoformat()

    if not reset_record or reset_record["used"] == 1:
        flash("This password reset link has already been used or is invalid.", "danger")
        return redirect(url_for("auth.forgot_password"))

    if reset_record["expires_at"] < now_iso:
        flash("This password reset link has expired. Please request a new one.", "danger")
        return redirect(url_for("auth.forgot_password"))

    error = None
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not password:
            error = "New Password is required."
        elif len(password) < 6:
            error = "Password must be at least 6 characters long."
        elif password != confirm_password:
            error = "New Password and Confirm Password do not match."
        else:
            try:
                new_hash = generate_password_hash(password)
                storage.update_user_password(reset_record["user_id"], new_hash)
                storage.mark_password_reset_used(reset_record["id"])
                flash("Password reset successfully. You can now log in.", "success")
                return redirect(url_for("auth.login"))
            except Exception as e:
                error = f"Failed to reset password: {e}"

    return render_template("reset_password.html", token=token, error=error)


# =============================================================================
# User Profile
# =============================================================================

@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """User profile viewing and updating page."""
    user = g.user
    storage = current_app.storage
    error = None
    success = None

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_profile":
            name = request.form.get("name", "").strip()
            gender = request.form.get("gender", "").strip()
            dob = request.form.get("dob", "").strip()

            if not name:
                error = "Name cannot be empty."
            elif len(name) > 100:
                error = "Name cannot exceed 100 characters."
            elif gender not in VALID_GENDERS:
                error = "Please select a valid gender option."
            elif not dob:
                error = "Date of Birth cannot be empty."
            else:
                try:
                    dob_date = datetime.strptime(dob, "%Y-%m-%d")
                    if dob_date > datetime.now():
                        error = "Date of Birth cannot be in the future."
                except ValueError:
                    error = "Invalid Date of Birth format (YYYY-MM-DD)."

            if not error:
                try:
                    storage.update_user_profile(user["id"], name=name, gender=gender, dob=dob)
                    session["user_name"] = name
                    user = storage.get_user_by_id(user["id"])
                    g.user = user
                    success = "Profile updated successfully."
                except Exception as e:
                    error = f"Failed to update profile: {e}"

        elif action == "change_password":
            current_pw = request.form.get("current_password", "")
            new_pw = request.form.get("new_password", "")
            confirm_pw = request.form.get("confirm_password", "")

            if not current_pw:
                error = "Current password is required."
            elif not check_password_hash(user["password_hash"], current_pw):
                error = "Current password is incorrect."
            elif not new_pw:
                error = "New password is required."
            elif len(new_pw) < 6:
                error = "New password must be at least 6 characters long."
            elif new_pw != confirm_pw:
                error = "New password and Confirm Password do not match."
            else:
                try:
                    new_hash = generate_password_hash(new_pw)
                    storage.update_user_password(user["id"], new_hash)
                    success = "Password changed successfully."
                except Exception as e:
                    error = f"Failed to change password: {e}"

    return render_template(
        "profile.html",
        user=user,
        error=error,
        success=success,
        valid_genders=VALID_GENDERS,
    )
