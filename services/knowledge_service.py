"""
knowledge_service.py
--------------------
CRUD operations for the manually-maintained Knowledge Repository.
These are entries added by admins/SMEs through the Knowledge page.
"""

from core.database import db
from core.models import KnowledgeEntry


class KnowledgeService:

    def list_all(self):
        """Return all knowledge entries, newest first."""
        return KnowledgeEntry.query.order_by(KnowledgeEntry.id.desc()).all()

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
