"""Shared helper for writing audit-log entries."""

from flask import session

from db import db
from models.audit_log import AuditLog


def log_action(action, details=""):
    db.session.add(AuditLog(username=session.get("username", "system"), action=action, details=details))
    db.session.commit()
