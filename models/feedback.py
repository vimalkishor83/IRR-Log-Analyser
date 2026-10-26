from db import db, get_now


class Feedback(db.Model):
    __tablename__ = "feedback"

    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.String(40))
    comments = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=get_now)
