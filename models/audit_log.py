from db import db, get_now


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80))
    action = db.Column(db.String(120))
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=get_now)
