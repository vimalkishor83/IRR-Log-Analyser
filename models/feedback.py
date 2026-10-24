from datetime import datetime
from db import db


class Feedback(db.Model):
    """User rating on a recommendation — Helpful or Not Helpful."""
    __tablename__ = "feedback"

    id         = db.Column(db.Integer, primary_key=True)
    value      = db.Column(db.String(40))   # "Helpful" or "Not Helpful"
    comments   = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
