from db import db


class SyncHistory(db.Model):
    """Records the result of each ServiceNow sync run."""
    __tablename__ = "sync_history"

    id             = db.Column(db.Integer, primary_key=True)
    source         = db.Column(db.String(80))    # "servicenow_incidents" or "servicenow_kb"
    last_sync_time = db.Column(db.DateTime)
    status         = db.Column(db.String(40))    # "Success" or "Failed"
    message        = db.Column(db.Text)
