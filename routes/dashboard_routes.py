"""
dashboard_routes.py
-------------------
Log Analyzer dashboard — page + all its API endpoints.
"""

import csv
import io
import logging
from pathlib import Path  # still needed for _load_incidents_csv / _load_kb_csv

from flask import Blueprint, Response, current_app, jsonify, render_template, request, session
from sqlalchemy import func

from core.auth import login_required, module_required
from core.database import db
from core.models import AuditLog, ErrorSignature, Incident, KBArticle, ParsedLog
from services.log_analyzer import LogAnalyzer

log = logging.getLogger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)


def _audit(action, details=""):
    db.session.add(AuditLog(username=session.get("username", "system"), action=action, details=details))
    db.session.commit()


# ── Pages ─────────────────────────────────────────────────────────────────────

@dashboard_bp.route("/")
@module_required("dashboard")
def index():
    return render_template("dashboard.html")


# ── Dashboard API ─────────────────────────────────────────────────────────────

@dashboard_bp.get("/api/dashboard")
@login_required
def dashboard_data():
    error_levels = ("ERROR", "FATAL", "CRITICAL")

    sev_rows = db.session.query(ParsedLog.severity, func.count()).group_by(ParsedLog.severity).all()
    sev_map  = {s: c for s, c in sev_rows}

    total_logs      = sum(sev_map.values())
    total_errors    = sum(c for s, c in sev_rows if s in error_levels)
    critical_errors = sum(c for s, c in sev_rows if s in ("FATAL", "CRITICAL"))
    warning_count   = sev_map.get("WARN", 0)
    unique_errors   = (
        db.session.query(func.count(ParsedLog.signature.distinct()))
        .filter(ParsedLog.severity.in_(error_levels))
        .scalar() or 0
    )

    app_rows = (
        db.session.query(ParsedLog.application, func.count())
        .filter(ParsedLog.severity.in_(error_levels))
        .group_by(ParsedLog.application)
        .order_by(func.count().desc())
        .all()
    )
    server_rows = (
        db.session.query(ParsedLog.server, func.count())
        .filter(ParsedLog.severity.in_(error_levels))
        .group_by(ParsedLog.server)
        .order_by(func.count().desc())
        .all()
    )

    applications = {a or "Unknown": c for a, c in app_rows}
    servers      = {s or "Unknown": c for s, c in server_rows}
    severities   = dict(sorted(sev_map.items(), key=lambda x: x[1], reverse=True))

    return jsonify({
        "kpis": {
            "total_logs":           total_logs,
            "total_errors":         total_errors,
            "unique_errors":        unique_errors,
            "critical_errors":      critical_errors,
            "warning_count":        warning_count,
            "top_application":      next(iter(applications), "None"),
            "top_server":           next(iter(servers), "None"),
            "knowledge_base_size": Incident.query.count() + KBArticle.query.filter_by(active=True).count(),
        },
        "charts": {
            "severity":     severities,
            "applications": applications,
            "servers":      servers,
        },
    })


@dashboard_bp.get("/api/logs")
@login_required
def get_logs():
    severity = request.args.get("severity", "")
    search   = request.args.get("search", "")
    page     = max(1, int(request.args.get("page", 1)))
    per_page = 100

    query = ParsedLog.query
    if severity:
        query = query.filter_by(severity=severity)
    if search:
        query = query.filter(ParsedLog.message.ilike(f"%{search}%"))

    rows = query.order_by(ParsedLog.timestamp.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return jsonify([_log_dict(row) for row in rows])


@dashboard_bp.get("/api/logs/timeline")
@login_required
def logs_timeline():
    """
    Return error/warning counts grouped by hour for the last 24 hours of log data,
    so the frontend can draw an errors-over-time line chart.
    """
    rows = (
        db.session.query(
            func.strftime("%Y-%m-%d %H:00", ParsedLog.timestamp).label("hour"),
            ParsedLog.severity,
            func.count().label("cnt"),
        )
        .filter(ParsedLog.severity.in_(("ERROR", "FATAL", "CRITICAL", "WARN")))
        .group_by("hour", ParsedLog.severity)
        .order_by("hour")
        .all()
    )

    # Build {hour -> {severity -> count}}
    buckets = {}
    for hour, severity, cnt in rows:
        if hour not in buckets:
            buckets[hour] = {"ERROR": 0, "WARN": 0, "CRITICAL": 0}
        key = "CRITICAL" if severity in ("FATAL", "CRITICAL") else severity
        buckets[hour][key] = buckets[hour].get(key, 0) + cnt

    labels  = sorted(buckets.keys())
    return jsonify({
        "labels":   labels,
        "errors":   [buckets[h].get("ERROR", 0)    for h in labels],
        "warnings": [buckets[h].get("WARN", 0)     for h in labels],
        "critical": [buckets[h].get("CRITICAL", 0) for h in labels],
    })


@dashboard_bp.get("/api/logs/export")
@login_required
def export_logs():
    """Export the current parsed log data as a CSV download."""
    severity = request.args.get("severity", "")
    search   = request.args.get("search", "")

    query = ParsedLog.query
    if severity:
        query = query.filter_by(severity=severity)
    if search:
        query = query.filter(ParsedLog.message.ilike(f"%{search}%"))

    rows = query.order_by(ParsedLog.timestamp.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Severity", "Application", "Server", "Error Code", "Exception", "Message", "Source File", "Line"])
    for r in rows:
        writer.writerow([
            r.timestamp.isoformat(sep=" ") if r.timestamp else "",
            r.severity, r.application, r.server,
            r.error_code, r.exception, r.message,
            r.source_file, r.line_number,
        ])

    _audit("export_logs", f"{len(rows)} rows exported")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=logs_export.csv"},
    )


@dashboard_bp.get("/api/logs/count")
@login_required
def logs_count():
    """Return total row count for the current filter (used by pagination)."""
    severity = request.args.get("severity", "")
    search   = request.args.get("search", "")
    query    = ParsedLog.query
    if severity:
        query = query.filter_by(severity=severity)
    if search:
        query = query.filter(ParsedLog.message.ilike(f"%{search}%"))
    return jsonify({"count": query.count()})


@dashboard_bp.post("/api/analyze")
@login_required
def analyze_logs():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "Please select at least one log file."}), 400

    # Files are read into memory and parsed — nothing is written to disk
    result = LogAnalyzer().analyze_uploads(files)
    _audit("file_processing", f"Processed {len(files)} files")
    return jsonify(result)


@dashboard_bp.post("/api/clear-analysis")
@login_required
def clear_analysis():
    ParsedLog.query.delete()
    ErrorSignature.query.delete()
    db.session.commit()
    _audit("clear_analysis", "Cleared parsed logs")
    return jsonify({"message": "Analysis cleared."})


@dashboard_bp.post("/api/load-sample-data")
@login_required
def load_sample_data():
    cfg = current_app.config
    _load_incidents_csv(cfg["SAMPLE_INCIDENTS_CSV"])
    _load_kb_csv(cfg["SAMPLE_KB_CSV"])

    log_path = cfg["DATA_DIR"] / "sample_app.log"
    raw      = log_path.read_bytes()
    result   = LogAnalyzer().analyze_file_bytes(raw, log_path.name)

    # Rebuild TF-IDF index so recommendations work immediately
    from routes.admin_routes import _rebuild_index
    doc_count = _rebuild_index()

    _audit("sample_data", "Loaded sample data")
    return jsonify({
        "message": f"Sample incidents, KB articles, and log loaded. Index built with {doc_count} documents.",
        "probable_root_cause": result["probable_root_cause"],
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _log_dict(row):
    return {
        "timestamp":   row.timestamp.isoformat(sep=" ") if row.timestamp else "",
        "severity":    row.severity,
        "application": row.application,
        "server":      row.server,
        "thread_id":   row.thread_id,
        "error_code":  row.error_code,
        "exception":   row.exception,
        "message":     row.message,
        "stack_trace": row.stack_trace,
        "source_file": row.source_file,
        "line_number": row.line_number,
    }


def _load_incidents_csv(path):
    with Path(path).open("r", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            row = {k.strip(): v for k, v in row.items()}
            number = row.get("incident_number")
            if not number or Incident.query.filter_by(incident_number=number).first():
                continue
            db.session.add(Incident(**row))
    db.session.commit()


def _load_kb_csv(path):
    with Path(path).open("r", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            row = {k.strip(): v for k, v in row.items()}
            title = row.get("title")
            if not title or KBArticle.query.filter_by(title=title).first():
                continue
            row["active"] = str(row.get("active", "1")).lower() in {"1", "true", "yes"}
            db.session.add(KBArticle(**row))
    db.session.commit()
