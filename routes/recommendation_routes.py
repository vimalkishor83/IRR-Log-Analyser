"""Recommendations page + its search and feedback routes."""

import logging

from flask import Blueprint, redirect, render_template, request, session, url_for

from core.auth import login_required, module_required
from core.database import db
from core.models import AuditLog, Feedback, Incident
from services.recommendation import RecommendationEngine
from services.snow_client import ServiceNowClient

log = logging.getLogger(__name__)
rec_bp = Blueprint("recommendations", __name__)


def _audit(action, details=""):
    db.session.add(AuditLog(username=session.get("username", "system"), action=action, details=details))
    db.session.commit()


@rec_bp.get("/recommendations")
@module_required("recommendations")
def recommendations_page():
    query_text      = request.args.get("q", "").strip()
    incident_number = request.args.get("incident", "").strip()
    sort_by         = request.args.get("sort", "confidence")

    if not query_text and not incident_number:
        return render_template("recommendations.html", searched=False)

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
    if sort_by in ("confidence", "similarity"):
        results = sorted(results, key=lambda r: r[sort_by], reverse=True)

    _audit("recommendation_search", incident_number or query_text)
    return render_template(
        "recommendations.html",
        searched=True,
        query_text=query_text,
        incident_number=incident_number,
        sort_by=sort_by,
        items=results,
        live_incident=live_incident,
        feedback_saved=request.args.get("feedback_saved", type=int),
    )


@rec_bp.post("/recommendations/feedback")
@login_required
def submit_feedback():
    value           = request.form.get("value", "")
    incident_number = request.form.get("incident_number", "")
    result_index    = request.form.get("result_index", type=int)

    db.session.add(Feedback(value=value, comments=incident_number))
    db.session.commit()
    _audit("feedback", value)

    return redirect(url_for(
        "recommendations.recommendations_page",
        q=request.form.get("q", ""),
        incident=request.form.get("incident", ""),
        sort=request.form.get("sort", "confidence"),
        feedback_saved=result_index,
    ))
