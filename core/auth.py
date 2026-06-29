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
    from core.auth import login_required, admin_required, module_required

    @app.route("/recommendations")
    @module_required("recommendations")   # only users who have this module
    def recommendations_page(): ...

    @app.route("/admin")
    @admin_required                       # Admin role only
    def admin_page(): ...
"""

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

# New Analyst accounts get these modules by default
DEFAULT_ANALYST_MODULES = "dashboard,recommendations"

# Admin users always get all modules
ADMIN_MODULES = ",".join(ALL_MODULES)


# ── Startup helper ────────────────────────────────────────────────────────────

def create_default_admin():
    """Create the built-in admin account on first startup if it doesn't exist."""
    if not User.query.filter_by(username="admin").first():
        db.session.add(User(
            username="admin",
            password=generate_password_hash("admin123"),
            role="Admin",
            modules=ADMIN_MODULES,
        ))
        db.session.commit()


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


# Keep admin_required as a shorthand for role_required("Admin")
def admin_required(view):
    """Only Admin users can access this route."""
    return role_required("Admin")(view)


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
