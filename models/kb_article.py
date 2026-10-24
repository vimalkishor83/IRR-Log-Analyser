from db import db


class KBArticle(db.Model):
    """Knowledge base article synced from ServiceNow."""
    __tablename__ = "kb_articles"

    id               = db.Column(db.Integer, primary_key=True)
    title            = db.Column(db.String(200))
    error_pattern    = db.Column(db.String(300), index=True)
    root_cause       = db.Column(db.Text)
    resolution       = db.Column(db.Text)
    assignment_group = db.Column(db.String(120))
    active           = db.Column(db.Boolean, default=True)
