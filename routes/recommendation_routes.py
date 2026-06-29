"""
recommendation_routes.py
------------------------
Recommendations page + its search and feedback API endpoints.
"""

import logging

from flask import Blueprint, jsonify, render_template, request, session

from core.auth import login_required, module_required
from core.database import db
from core.models import AuditLog, Feedback, Incident
from services.recommendation import RecommendationEngine
from services.snow_client import ServiceNowClient

log = logging.getLogger(__name__)
rec_bp = Blueprint("recommendations", __name__)


@rec_bp.get("/recommendations")
@module_required("recommendations")
def recommendations_page():
    return render_template("recommendations.html")


def _audit(action, details=""):
    db.session.add(AuditLog(username=session.get("username", "system"), action=action, details=details))
    db.session.commit()


@rec_bp.post("/api/recommend")
@login_required
def recommend():
    payload         = request.get_json(silent=True) or {}
    query_text      = payload.get("query_text", "").strip()
    incident_number = payload.get("incident_number", "").strip()

    if not query_text and not incident_number:
        return jsonify({"error": "Enter an incident number or error text."}), 400

    live_incident = None  # details about an open/in-progress incident from SNOW

    # If the incident is not in our local DB (open or in-progress),
    # fetch it live from ServiceNow and use its description as the search text.
    if incident_number and not Incident.query.filter_by(incident_number=incident_number).first():
        from flask import current_app
        snow = ServiceNowClient(current_app.config)
        raw  = snow.get_incident_by_number(incident_number)
        if raw:
            description = " ".join(filter(None, [
                raw.get("short_description", ""),
                raw.get("description", ""),
            ])).strip()

            if description and not query_text:
                query_text = description

            live_incident = {
                "number":      raw.get("number", incident_number),
                "state":       raw.get("state", ""),
                "priority":    raw.get("priority", ""),
                "group":       raw.get("assignment_group", ""),
                "description": raw.get("short_description", ""),
            }
            log.info("Fetched live incident %s (state: %s)", incident_number, live_incident["state"])

    engine  = RecommendationEngine()
    results = engine.search(query_text or incident_number, incident_number)

    if results:
        engine.save_history(query_text, results[0])

    _audit("recommendation_search", incident_number or query_text)
    return jsonify({"items": results, "live_incident": live_incident})


@rec_bp.post("/api/feedback")
@login_required
def feedback():
    payload = request.get_json(silent=True) or {}
    db.session.add(Feedback(
        recommendation_id = payload.get("recommendation_id"),
        value             = payload.get("value"),
        comments          = payload.get("comments", ""),
    ))
    db.session.commit()
    _audit("feedback", payload.get("value", ""))
    return jsonify({"message": "Feedback saved"})
