from db import db, get_now


class ServiceNowGroup(db.Model):
    __tablename__ = "servicenow_groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=get_now)
