"""
recommendation.py
-----------------
Finds the best-matching resolved incidents and KB articles for a user query.

Search order:
  1. Exact incident number match   — instant, 100% confidence
  2. TF-IDF similarity search      — fast, uses the pre-built index
  3. SequenceMatcher fuzzy search  — slower fallback if index is not built

Confidence score (0-99) combines:
  - Similarity to the query
  - How many times the resolution has been used successfully
  - Overall user feedback (Helpful vs Not Helpful ratings)
"""

from difflib import SequenceMatcher

from core.database import db
from core.models import Feedback, Incident, KBArticle, KnowledgeEntry
from services import tfidf_engine


class RecommendationEngine:

    def search(self, query_text, incident_number=""):
        """
        Return up to 5 recommendations for the given query.

        query_text      — error message, exception, or log snippet
        incident_number — optional; if given, check for an exact match first
        """
        helpful     = Feedback.query.filter_by(value="Helpful").count()
        not_helpful = Feedback.query.filter_by(value="Not Helpful").count()

        candidates = []

        # Step 1: exact match by incident number
        if incident_number:
            inc = Incident.query.filter_by(incident_number=incident_number).first()
            if inc:
                candidates.append(self._incident_result(inc, 100, "Exact incident match", helpful, not_helpful))

        # Step 2: TF-IDF search (requires retrain() to have been called)
        if tfidf_engine.is_trained():
            candidates.extend(self._tfidf_search(query_text, helpful, not_helpful))
        else:
            # Step 3: fallback — compare text directly (slower but always works)
            candidates.extend(self._fuzzy_search(query_text, helpful, not_helpful))

        # Sort best results first
        candidates.sort(key=lambda r: (r["confidence"], r["similarity"]), reverse=True)

        # Remove duplicates — keep the highest-scoring entry per incident
        seen   = set()
        unique = []
        for item in candidates:
            key = item["incident_number"]
            if key not in seen:
                seen.add(key)
                unique.append(item)

        top5 = unique[:5]

        return top5

    # ── TF-IDF search ─────────────────────────────────────────────────────────

    def _tfidf_search(self, query_text, helpful, not_helpful):
        docs       = tfidf_engine.search(query_text, top_n=20)
        candidates = []
        for doc in docs:
            confidence = self._confidence(doc["similarity"], doc["success_count"], helpful, not_helpful)
            candidates.append({
                "source":           doc["source"],
                "incident_number":  doc["incident_number"],
                "similarity":       doc["similarity"],
                "confidence":       confidence,
                "resolution":       doc["resolution"],
                "root_cause":       doc["root_cause"],
                "assignment_group": doc["assignment_group"],
                "success_count":    doc["success_count"],
                "reason":           doc["reason"],
            })
        return candidates

    # ── Fuzzy fallback ────────────────────────────────────────────────────────

    def _fuzzy_search(self, query_text, helpful, not_helpful):
        candidates = []
        min_score  = 25  # ignore anything below 25% similar

        for inc in Incident.query.all():
            text  = " ".join([inc.error_description or "", inc.exception_message or "", inc.root_cause or ""])
            score = self._similarity(query_text, text)
            if score >= min_score:
                candidates.append(self._incident_result(inc, score, "Similar historical incident", helpful, not_helpful))

        for article in KBArticle.query.filter_by(active=True).all():
            text  = " ".join([article.title or "", article.error_pattern or "", article.root_cause or ""])
            score = self._similarity(query_text, text)
            if score >= min_score:
                candidates.append({
                    "source":           "KB Article",
                    "incident_number":  "KB",
                    "similarity":       score,
                    "confidence":       self._confidence(score, 1, helpful, not_helpful),
                    "resolution":       article.resolution       or "",
                    "root_cause":       article.root_cause       or "",
                    "assignment_group": article.assignment_group or "",
                    "success_count":    1,
                    "reason":           "Matched active KB article",
                })

        for entry in KnowledgeEntry.query.filter_by(active=True).all():
            score = self._similarity(query_text, entry.pattern or "")
            if score >= min_score:
                candidates.append({
                    "source":           "Knowledge Repository",
                    "incident_number":  "Manual Knowledge",
                    "similarity":       score,
                    "confidence":       self._confidence(score, entry.frequency or 1, helpful, not_helpful),
                    "resolution":       entry.resolution       or "",
                    "root_cause":       entry.meaning          or "",
                    "assignment_group": entry.assignment_group or "",
                    "success_count":    entry.frequency        or 0,
                    "reason":           "Matched SME knowledge entry",
                })

        return candidates

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _incident_result(self, inc, score, reason, helpful, not_helpful):
        """Convert an Incident model into a result dict."""
        return {
            "source":           "Historical Incident",
            "incident_number":  inc.incident_number,
            "similarity":       score,
            "confidence":       self._confidence(score, inc.success_count or 1, helpful, not_helpful),
            "resolution":       inc.resolution       or "",
            "root_cause":       inc.root_cause       or "",
            "assignment_group": inc.assignment_group or "",
            "success_count":    inc.success_count    or 1,
            "reason":           reason,
        }

    def _confidence(self, similarity, success_count, helpful, not_helpful):
        """
        Calculate a confidence score between 0 and 99.
        Higher similarity, more past uses, and positive feedback all increase it.
        """
        feedback_bonus = max(-10, min(10, helpful - not_helpful))
        usage_bonus    = min(15, (success_count or 0) * 1.5)
        raw            = similarity * 0.75 + usage_bonus + feedback_bonus
        return round(min(99, max(0, raw)), 2)

    def _similarity(self, text_a, text_b):
        """Compare two strings and return similarity as a percentage (0-100)."""
        if not text_a or not text_b:
            return 0
        ratio = SequenceMatcher(None, text_a.lower(), text_b.lower()).ratio()
        return round(ratio * 100, 2)
