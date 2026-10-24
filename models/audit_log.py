from datetime import datetime
from db import db


class AuditLog(db.Model):
    """Records every significant user action for security and compliance."""
    __tablename__ = "audit_logs"

    id        = db.Column(db.Integer, primary_key=True)
    username  = db.Column(db.String(80))
    action    = db.Column(db.String(120))
    details   = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # named 'timestamp' to match query in admin_routes
