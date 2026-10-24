"""Login, logout, and page-level access control."""

from functools import wraps
from flask import redirect, session, url_for

from models.user import User

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


def login_user(username, password):
    """Check credentials and store user info in the session."""
    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return False

    session["username"] = user.username
    session["role"]     = user.role
    session["modules"]  = ADMIN_MODULES if user.is_admin() else (user.modules or "")
    return True


def parse_modules(raw):
    """Split a comma-separated modules string into a clean list."""
    return [m.strip() for m in (raw or "").split(",") if m.strip()]


def get_current_modules():
    """Return the logged-in user's allowed modules as a list."""
    return parse_modules(session.get("modules", ""))


def user_modules(user):
    """Return a user's allowed modules as a list. Admins always get all modules."""
    return ALL_MODULES if user.is_admin() else parse_modules(user.modules)


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
    """Only users who have the given module can access this route. Admin users always pass through."""
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
