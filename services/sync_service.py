"""
sync_service.py
---------------
Pulls data from ServiceNow and saves only quality records to the database.

Before saving each incident, six validation rules are applied:
  1. Required fields    — must have incident number, description, and resolution
  2. Minimum length     — description ≥ 10 chars, resolution ≥ 20 chars
  3. Junk text          — skip placeholders like "test", "n/a", "done", "fixed"
  4. Duplicate resolution — skip if 5+ incidents already share the same resolution
  5. State verification — record must actually be Resolved or Closed
  6. Assignment group   — if a group filter is configured, reject non-matching records

The sync summary includes a `skipped_validation` count so admins can see
how many records were filtered out.
"""

import logging
import re
from datetime import datetime

from core.database import db
from core.models import Incident, KBArticle, SyncHistory
from services.snow_client import ServiceNowClient

log = logging.getLogger(__name__)

# States we accept as "done" and worth storing
VALID_STATES = {"resolved", "closed"}

# Any resolution text that appears on 5+ incidents is likely a copy-paste template
MAX_DUPLICATE_RESOLUTIONS = 5

# Short words that indicate a throwaway / placeholder entry
JUNK_PHRASES = {
    "test", "testing", "n/a", "na", "none", "tbd", "todo",
    "see above", "see comments", "as per call", "as discussed",
    "done", "fixed", "closed", "resolved", "ok", "yes", "no",
    "please see above", "refer above", "as per email",
}


class SyncService:

    def __init__(self, config):
        self.client = ServiceNowClient(config)

        raw = (config.get("SERVICENOW_ASSIGNMENT_GROUPS") or "").strip()
        self.allowed_groups = {g.strip().lower() for g in raw.split(",") if g.strip()}

    # ── Public sync methods ───────────────────────────────────────────────────

    def sync_incidents(self):
        """
        Pull Resolved/Closed incidents from ServiceNow.
        Validate each one before saving — bad data is counted and skipped.
        """
        try:
            rows = self.client.get_closed_incidents(
                assignment_groups=list(self.allowed_groups) if self.allowed_groups else None
            )

            imported      = 0
            updated       = 0
            skip_reasons  = {}  # { reason_category: count }

            # Pre-load resolution texts to detect copy-paste duplicates (validation 4)
            resolution_counts = _count_existing_resolutions()

            for row in rows:
                reason = self._validate_incident(row, resolution_counts)
                if reason:
                    category = _skip_category(reason)
                    skip_reasons[category] = skip_reasons.get(category, 0) + 1
                    log.debug("Skipped %s — %s", row.get("number", "?"), reason)
                    continue

                number  = row["number"].strip()
                item    = Incident.query.filter_by(incident_number=number).first()
                is_new  = item is None
                if is_new:
                    item = Incident(incident_number=number)

                resolution = _clean(row.get("close_notes") or "")

                item.application       = _clean(row.get("category"))         or "Unknown"
                item.server            = _clean(row.get("subcategory"))       or "Unknown"
                item.environment       = _clean(row.get("category"))          or ""
                item.error_description = _clean(row.get("short_description")) or ""
                item.exception_message = _clean(row.get("description"))       or ""
                item.root_cause        = _clean(row.get("work_notes") or row.get("description") or "")
                item.resolution        = resolution
                item.assignment_group  = _clean(row.get("assignment_group"))  or "Application Team"
                item.status            = _clean(row.get("state"))             or "Resolved"
                item.updated_at        = datetime.utcnow()

                db.session.add(item)

                # Track this resolution so further duplicates get caught
                resolution_counts[resolution] = resolution_counts.get(resolution, 0) + 1

                if is_new:
                    imported += 1
                else:
                    updated += 1

            db.session.commit()
            total_skipped = sum(skip_reasons.values())
            skip_detail   = ", ".join(f"{c} {r}" for r, c in sorted(skip_reasons.items(), key=lambda x: -x[1]))
            msg = (
                f"Imported {imported} new, updated {updated} existing, "
                f"skipped {total_skipped} (failed validation)"
                + (f": {skip_detail}" if skip_detail else "") + "."
            )
            log.info("Incident sync done. %s", msg)
            self._record_sync("servicenow_incidents", "Success", msg)

        except Exception as err:
            db.session.rollback()
            log.error("Incident sync failed: %s", err)
            self._record_sync("servicenow_incidents", "Failed", str(err))

    def sync_kb_articles(self):
        """
        Pull KB articles from ServiceNow.
        Skips articles that have no usable content or already exist in the DB.
        """
        try:
            rows     = self.client.get_kb_articles()
            imported = 0
            skipped  = 0

            for row in rows:
                title      = _clean(row.get("short_description") or row.get("title") or "")
                resolution = _clean(row.get("text") or "")

                if not title or len(title) < 10:
                    skipped += 1
                    continue
                if _is_junk(title) or _is_junk(resolution):
                    skipped += 1
                    continue
                if KBArticle.query.filter_by(title=title).first():
                    skipped += 1
                    continue

                db.session.add(KBArticle(
                    title            = title,
                    error_pattern    = title,
                    root_cause       = _clean(row.get("description") or ""),
                    resolution       = resolution or "See KB article for details.",
                    assignment_group = _clean(row.get("assignment_group")) or "Application Team",
                    active           = True,
                ))
                imported += 1

            db.session.commit()
            msg = f"Imported {imported} new KB articles, skipped {skipped}."
            log.info("KB sync done. %s", msg)
            self._record_sync("servicenow_kb", "Success", msg)

        except Exception as err:
            db.session.rollback()
            log.error("KB sync failed: %s", err)
            self._record_sync("servicenow_kb", "Failed", str(err))

    # ── Validation ────────────────────────────────────────────────────────────

    def _validate_incident(self, row, resolution_counts):
        """
        Run all six validation rules against one raw ServiceNow record.
        Returns a short failure reason string, or None if the record is good.
        """
        number      = (row.get("number") or "").strip()
        description = _clean(row.get("short_description") or "")
        resolution  = _clean(row.get("close_notes") or "")
        state       = (row.get("state") or "").strip().lower()
        group       = (row.get("assignment_group") or "").strip().lower()

        # Rule 1 — required fields must exist
        if not number:
            return "missing incident number"
        if not description:
            return "missing description"
        if not resolution:
            return "missing resolution (close_notes)"

        # Rule 2 — minimum useful length
        if len(description) < 10:
            return f"description too short ({len(description)} chars)"
        if len(resolution) < 20:
            return f"resolution too short ({len(resolution)} chars)"

        # Rule 3 — reject junk / placeholder text
        if _is_junk(description):
            return f"junk description: '{description[:40]}'"
        if _is_junk(resolution):
            return f"junk resolution: '{resolution[:40]}'"

        # Rule 4 — reject copy-paste resolutions (same text on 5+ records)
        count = resolution_counts.get(resolution, 0)
        if count >= MAX_DUPLICATE_RESOLUTIONS:
            return f"duplicate resolution used {count} times already"

        # Rule 5 — state must actually be resolved or closed
        if state and state not in VALID_STATES:
            return f"unexpected state: '{state}'"

        # Rule 6 — assignment group must be in the allowed list (if configured)
        if self.allowed_groups and group not in self.allowed_groups:
            return f"group '{group}' not in allowed list"

        return None  # all checks passed

    # ── Helper ────────────────────────────────────────────────────────────────

    def _record_sync(self, source, status, message):
        """Save one sync result row so admins can see the last sync outcome."""
        try:
            db.session.add(SyncHistory(
                source         = source,
                last_sync_time = datetime.utcnow(),
                status         = status,
                message        = message,
            ))
            db.session.commit()
        except Exception as err:
            log.error("Could not save sync record: %s", err)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _clean(text):
    """
    Strip leading/trailing whitespace and collapse internal whitespace.
    Returns an empty string if text is None.
    """
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text).strip())


def _is_junk(text):
    """
    Return True if the text is a known throwaway value.
    Checks exact match and also whether the whole text is just one junk phrase.
    """
    if not text:
        return True
    normalised = text.strip().lower()
    # Exact match
    if normalised in JUNK_PHRASES:
        return True
    # Very short and only letters/punctuation — likely meaningless
    if len(normalised) < 5 and not any(c.isdigit() for c in normalised):
        return True
    return False


def _skip_category(reason):
    """Map a detailed validation reason to a short readable category label."""
    if "missing" in reason:
        return "missing required field"
    if "too short" in reason:
        return "text too short"
    if "junk" in reason:
        return "junk/placeholder text"
    if "duplicate resolution" in reason:
        return "duplicate resolution"
    if "state" in reason:
        return "wrong state"
    if "group" in reason:
        return "wrong assignment group"
    return "other"


def _count_existing_resolutions():
    """
    Build a dict of { resolution_text: count } from incidents already in the DB.
    Used so we can detect duplicate resolutions across the current sync batch
    combined with what's already stored.
    """
    counts = {}
    for inc in Incident.query.with_entities(Incident.resolution).all():
        text = (inc.resolution or "").strip()
        if text:
            counts[text] = counts.get(text, 0) + 1
    return counts
