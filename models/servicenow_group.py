from datetime import datetime
from db import db


class ServiceNowGroup(db.Model):
    """ServiceNow assignment groups used to filter synced incident data."""
    __tablename__ = "servicenow_groups"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(200), unique=True, nullable=False)
    active     = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
