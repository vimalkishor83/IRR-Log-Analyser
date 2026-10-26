from db import db, get_now


class Incident(db.Model):
    __tablename__ = "incidents"

    id = db.Column(db.Integer, primary_key=True)
    incident_number = db.Column(db.String(40), unique=True, index=True)
    application = db.Column(db.String(120), index=True)
    server = db.Column(db.String(120), index=True)
    environment = db.Column(db.String(50), index=True)
    error_description = db.Column(db.Text)
    exception_message = db.Column(db.Text)
    root_cause = db.Column(db.Text)
    resolution = db.Column(db.Text)
    assignment_group = db.Column(db.String(120))
    status = db.Column(db.String(40))
    success_count = db.Column(db.Integer, default=1)
    updated_at = db.Column(db.DateTime, default=get_now)
