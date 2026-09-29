"""
auth.py
-------
Handles login, logout, and page-level access control.

Roles
-----
Admin   — full access to every page, no restrictions
Analyst — can only access pages listed in their 'modules' field

How to protect a route
-----------------------
    from core.auth import login_required, role_required, module_required

    @app.route("/recommendations")
    @module_required("recommendations")   # only users who have this module
    def recommendations_page(): ...

    @app.route("/admin")
    @role_required("Admin")               # Admin role only
    def admin_page(): ...
"""

import logging
import os

from functools import wraps
from flask import redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from core.database import db
from core.models import User

# All module keys that exist in the application
ALL_MODULES = ["dashboard", "recommendations", "knowledge", "admin"]

# Human-readable names shown in the UI
MODULE_LABELS = {
    "dashboard":       "Log Analyzer",
    "recommendations": "Recommendations",
    "knowledge":       "Knowledge Repository",
    "admin":           "Admin Panel",
}

# Admin users always get all modules
ADMIN_MODULES = ",".join(ALL_MODULES)


# ── Startup helper ────────────────────────────────────────────────────────────

def create_first_admin():
    """Create the first Admin user from environment variables, if none exists
    yet and the required variables are set. Never hardcodes a username or
    password -- if ADMIN_USERNAME/ADMIN_PASSWORD aren't both set, this
    silently does nothing (fails closed: no default account is ever
    created), and an operator sets up the first admin by setting these
    variables once and restarting the app."""
    if User.query.first():
        return

    username = os.environ.get("ADMIN_USERNAME")
    password = os.environ.get("ADMIN_PASSWORD")
    if not (username and password):
        logging.getLogger(__name__).warning(
            "No users exist yet and ADMIN_USERNAME/ADMIN_PASSWORD are not "
            "both set -- skipping first-admin creation. Set both and "
            "restart the app to create the first admin account."
        )
        return

    db.session.add(User(
        username=username,
        password=generate_password_hash(password),
        role="Admin",
        modules=ADMIN_MODULES,
    ))
    db.session.commit()
    logging.getLogger(__name__).info("First admin created: username=%s", username)


# ── Login / logout ────────────────────────────────────────────────────────────

def login_user(username, password):
    """
    Check username and password. If correct, save user info in the session.
    Returns True on success, False if credentials are wrong.
    """
    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password, password):
        return False

    # Store user info in the session so we don't query DB on every request
    session["username"] = user.username
    session["role"]     = user.role
    session["modules"]  = ADMIN_MODULES if user.role == "Admin" else (user.modules or "")
    return True


def get_current_modules():
    """Return the logged-in user's allowed modules as a list."""
    raw = session.get("modules", "")
    return [m.strip() for m in raw.split(",") if m.strip()]


# ── Route decorators ──────────────────────────────────────────────────────────

def login_required(view):
    """Redirect to login page if the user is not logged in."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapper


def role_required(role):
    """Only users with the given role can access this route."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "username" not in session:
                return redirect(url_for("auth.login"))
            if session.get("role") != role:
                return redirect(url_for("dashboard.index"))
            return view(*args, **kwargs)
        return wrapper
    return decorator


def module_required(module_key):
    """
    Only users who have the given module can access this route.
    Admin users always pass through.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "username" not in session:
                return redirect(url_for("auth.login"))
            if session.get("role") == "Admin":
                return view(*args, **kwargs)
            if module_key not in get_current_modules():
                return redirect(url_for("auth.access_denied"))
            return view(*args, **kwargs)
        return wrapper
    return decorator
