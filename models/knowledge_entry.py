from db import db


class KnowledgeEntry(db.Model):
    """Manually entered error pattern + resolution, added through the Knowledge page."""
    __tablename__ = "knowledge_repository"

    id               = db.Column(db.Integer, primary_key=True)
    pattern          = db.Column(db.String(300), index=True)
    meaning          = db.Column(db.Text)
    resolution       = db.Column(db.Text)
    assignment_group = db.Column(db.String(120))
    frequency        = db.Column(db.Integer, default=0)
    active           = db.Column(db.Boolean, default=True)
    last_seen        = db.Column(db.DateTime)
