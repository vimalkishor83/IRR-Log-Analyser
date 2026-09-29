"""Database tables."""

from datetime import datetime
from core.database import db


class User(db.Model):
    __tablename__ = "users"

    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role     = db.Column(db.String(20), default="Analyst")
    # Comma-separated list of page keys the user can access
    # e.g. "dashboard,recommendations"
    # Admin users always bypass this and get full access.
    modules  = db.Column(db.Text, default="dashboard,recommendations")


class Incident(db.Model):
    """
    One resolved incident from ServiceNow.
    These are the records the recommendation engine searches through.
    """
    __tablename__ = "incidents"

    id                = db.Column(db.Integer, primary_key=True)
    incident_number   = db.Column(db.String(40),  unique=True, index=True)
    application       = db.Column(db.String(120), index=True)
    server            = db.Column(db.String(120), index=True)
    environment       = db.Column(db.String(50),  index=True)
    error_description = db.Column(db.Text)
    exception_message = db.Column(db.Text)
    root_cause        = db.Column(db.Text)
    resolution        = db.Column(db.Text)
    assignment_group  = db.Column(db.String(120))
    status            = db.Column(db.String(40))
    success_count     = db.Column(db.Integer, default=1)
    updated_at        = db.Column(db.DateTime, default=datetime.utcnow)


class KBArticle(db.Model):
    """Knowledge base article synced from ServiceNow."""
    __tablename__ = "kb_articles"

    id               = db.Column(db.Integer, primary_key=True)
    title            = db.Column(db.String(200))
    error_pattern    = db.Column(db.String(300), index=True)
    root_cause       = db.Column(db.Text)
    resolution       = db.Column(db.Text)
    assignment_group = db.Column(db.String(120))
    active           = db.Column(db.Boolean, default=True)


class KnowledgeEntry(db.Model):
    """Manually entered error pattern + resolution, added through the Knowledge page."""
    __tablename__ = "knowledge_repository"

    id               = db.Column(db.Integer, primary_key=True)
    pattern          = db.Column(db.String(300), index=True)
    meaning          = db.Column(db.Text)
    resolution       = db.Column(db.Text)
    assignment_group = db.Column(db.String(120))
    frequency        = db.Column(db.Integer, default=0)
    active           = db.Column(db.Boolean, default=True)
    last_seen        = db.Column(db.DateTime)


class ErrorSignature(db.Model):
    """A unique error fingerprint from an uploaded log, scoped per user."""
    __tablename__ = "error_signatures"

    id          = db.Column(db.Integer, primary_key=True)
    uploaded_by = db.Column(db.String(80), index=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    signature   = db.Column(db.String(500), index=True)
    application = db.Column(db.String(120))
    server      = db.Column(db.String(120))
    severity    = db.Column(db.String(30))
    frequency   = db.Column(db.Integer, default=1)
    last_seen   = db.Column(db.DateTime, default=datetime.utcnow)


class ParsedLog(db.Model):
    """One parsed log line from a user's most recent upload."""
    __tablename__ = "parsed_logs"

    id          = db.Column(db.Integer, primary_key=True)
    uploaded_by = db.Column(db.String(80), index=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    source_file = db.Column(db.String(255))
    line_number = db.Column(db.Integer)
    timestamp   = db.Column(db.DateTime, index=True)
    severity    = db.Column(db.String(30),  index=True)
    application = db.Column(db.String(120), index=True)
    server      = db.Column(db.String(120), index=True)
    thread_id   = db.Column(db.String(80))
    error_code  = db.Column(db.String(80))
    exception   = db.Column(db.String(200))
    message     = db.Column(db.Text)
    stack_trace = db.Column(db.Text)
    signature   = db.Column(db.String(500), index=True)


class Feedback(db.Model):
    """User rating on a recommendation — Helpful or Not Helpful."""
    __tablename__ = "feedback"

    id                = db.Column(db.Integer, primary_key=True)
    recommendation_id = db.Column(db.Integer)
    value             = db.Column(db.String(40))   # "Helpful" or "Not Helpful"
    comments          = db.Column(db.Text)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)


class SyncHistory(db.Model):
    """Records the result of each ServiceNow sync run."""
    __tablename__ = "sync_history"

    id             = db.Column(db.Integer, primary_key=True)
    source         = db.Column(db.String(80))    # "servicenow_incidents" or "servicenow_kb"
    last_sync_time = db.Column(db.DateTime)
    status         = db.Column(db.String(40))    # "Success" or "Failed"
    message        = db.Column(db.Text)


class AuditLog(db.Model):
    """Records every significant user action for security and compliance."""
    __tablename__ = "audit_logs"

    id        = db.Column(db.Integer, primary_key=True)
    username  = db.Column(db.String(80))
    action    = db.Column(db.String(120))
    details   = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # named 'timestamp' to match query in admin_routes


class ServiceNowGroup(db.Model):
    """ServiceNow assignment groups used to filter synced incident data."""
    __tablename__ = "servicenow_groups"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(200), unique=True, nullable=False)
    active     = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


