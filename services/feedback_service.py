"""
feedback_service.py
-------------------
Saves user ratings on recommendations (Helpful / Not Helpful).
These ratings are used to adjust confidence scores over time.
"""

from core.database import db
from core.models import Feedback


class FeedbackService:

    def save(self, recommendation_id, value, comments=""):
        """Save one feedback record to the database."""
        record = Feedback(
            recommendation_id = recommendation_id,
            value             = value,
            comments          = comments,
        )
        db.session.add(record)
        db.session.commit()
        return record
