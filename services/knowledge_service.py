"""CRUD operations for the manually-maintained Knowledge Repository."""

from core.database import db
from core.models import KnowledgeEntry


class KnowledgeService:

    def list_all(self, status="all", search=""):
        """Return knowledge entries, newest first, optionally filtered by status/search."""
        query = KnowledgeEntry.query
        if status == "active":
            query = query.filter_by(active=True)
        elif status == "inactive":
            query = query.filter_by(active=False)
        if search:
            like = f"%{search}%"
            query = query.filter(db.or_(
                KnowledgeEntry.pattern.ilike(like),
                KnowledgeEntry.meaning.ilike(like),
                KnowledgeEntry.resolution.ilike(like),
                KnowledgeEntry.assignment_group.ilike(like),
            ))
        return query.order_by(KnowledgeEntry.id.desc()).all()

    def add(self, data):
        """Create a new knowledge entry from a dict of field values."""
        item = KnowledgeEntry(
            pattern          = data.get("pattern"),
            meaning          = data.get("meaning"),
            resolution       = data.get("resolution"),
            assignment_group = data.get("assignment_group"),
            active           = True,
        )
        db.session.add(item)
        db.session.commit()
        return item

    def update(self, entry_id, data):
        """Update fields on an existing entry. Returns None if not found."""
        item = KnowledgeEntry.query.get(entry_id)
        if not item:
            return None
        for field in ("pattern", "meaning", "resolution", "assignment_group"):
            if field in data:
                setattr(item, field, data[field])
        db.session.commit()
        return item

    def set_active(self, entry_id, active):
        """Activate or deactivate an entry. Returns None if not found."""
        item = KnowledgeEntry.query.get(entry_id)
        if not item:
            return None
        item.active = active
        db.session.commit()
        return item

    def delete(self, entry_id):
        """Delete an entry. Returns True on success, False if not found."""
        item = KnowledgeEntry.query.get(entry_id)
        if not item:
            return False
        db.session.delete(item)
        db.session.commit()
        return True
