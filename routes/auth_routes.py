"""Login and logout pages."""

from flask import Blueprint, redirect, render_template, request, session, url_for
from core.auth import login_user
from core.database import db
from core.models import AuditLog

auth_bp = Blueprint("auth", __name__)


def _audit(action, details=""):
    db.session.add(AuditLog(username=session.get("username", "system"), action=action, details=details))
    db.session.commit()


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if login_user(username, password):
            _audit("login", "Successful login")
            return redirect(url_for("dashboard.index"))
        return render_template("login.html", error="Invalid username or password")
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/access-denied")
def access_denied():
    return render_template("access_denied.html"), 403


@auth_bp.route("/help")
def help_page():
    return render_template("help.html")
