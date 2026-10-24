from datetime import datetime
from db import db


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
