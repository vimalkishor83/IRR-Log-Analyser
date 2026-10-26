from db import db


class SyncHistory(db.Model):
    __tablename__ = "sync_history"

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(80))
    last_sync_time = db.Column(db.DateTime)
    status = db.Column(db.String(40))
    message = db.Column(db.Text)
