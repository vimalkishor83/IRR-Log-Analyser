from db import db, get_now


class ErrorSignature(db.Model):
    __tablename__ = "error_signatures"

    id = db.Column(db.Integer, primary_key=True)
    uploaded_by = db.Column(db.String(80), index=True)
    uploaded_at = db.Column(db.DateTime, default=get_now, index=True)
    signature = db.Column(db.String(500), index=True)
    application = db.Column(db.String(120))
    server = db.Column(db.String(120))
    severity = db.Column(db.String(30))
    frequency = db.Column(db.Integer, default=1)
    last_seen = db.Column(db.DateTime, default=get_now)
