"""Log Analyzer dashboard — page + all its API endpoints."""

import csv
import io
import logging

from flask import Blueprint, Response, jsonify, render_template, request, session
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


@dashboard_bp.route("/")
@module_required("dashboard")
def index():
    return render_template("dashboard.html")


@dashboard_bp.get("/api/dashboard")
@login_required
def dashboard_data():
    error_levels = ("ERROR", "FATAL", "CRITICAL")
    uploaded_by  = session.get("username", "")

    sev_rows = (
        db.session.query(ParsedLog.severity, func.count())
        .filter(ParsedLog.uploaded_by == uploaded_by)
        .group_by(ParsedLog.severity)
        .all()
    )
    sev_map  = {s: c for s, c in sev_rows}

    total_logs      = sum(sev_map.values())
    total_errors    = sum(c for s, c in sev_rows if s in error_levels)
    critical_errors = sum(c for s, c in sev_rows if s in ("FATAL", "CRITICAL"))
    warning_count   = sev_map.get("WARN", 0)
    unique_errors   = (
        db.session.query(func.count(ParsedLog.signature.distinct()))
        .filter(ParsedLog.uploaded_by == uploaded_by, ParsedLog.severity.in_(error_levels))
        .scalar() or 0
    )

    app_rows = (
        db.session.query(ParsedLog.application, func.count())
        .filter(ParsedLog.uploaded_by == uploaded_by, ParsedLog.severity.in_(error_levels))
        .group_by(ParsedLog.application)
        .order_by(func.count().desc())
        .all()
    )
    server_rows = (
        db.session.query(ParsedLog.server, func.count())
        .filter(ParsedLog.uploaded_by == uploaded_by, ParsedLog.severity.in_(error_levels))
        .group_by(ParsedLog.server)
        .order_by(func.count().desc())
        .all()
    )

    applications = {a or "Unknown": c for a, c in app_rows[:5]}
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

    query = ParsedLog.query.filter_by(uploaded_by=session.get("username", ""))
    if severity:
        query = query.filter_by(severity=severity)
    if search:
        query = query.filter(ParsedLog.message.ilike(f"%{search}%"))

    rows = query.order_by(ParsedLog.timestamp.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return jsonify([_log_dict(row) for row in rows])


@dashboard_bp.get("/api/logs/top-issues")
@login_required
def top_issues():
    """Return top 5 ERROR/CRITICAL issues with a probable root cause per issue."""
    error_levels = ("ERROR", "FATAL", "CRITICAL")

    rows = (
        ParsedLog.query
        .filter(ParsedLog.uploaded_by == session.get("username", ""), ParsedLog.severity.in_(error_levels))
        .order_by(ParsedLog.timestamp.desc())
        .all()
    )

    groups = {}
    for r in rows:
        key = r.exception or r.error_code or (r.message or "")[:60]
        if not key:
            continue
        if key not in groups:
            groups[key] = {"key": key, "count": 0, "severity": r.severity,
                           "app": r.application, "entries": []}
        groups[key]["count"] += 1
        groups[key]["entries"].append({
            "message":   r.message or "",
            "exception": r.exception or "",
            "error_code": r.error_code or "",
            "timestamp": r.timestamp,
            "severity":  r.severity,
            "signature": r.signature or "",
        })

    analyzer = LogAnalyzer()
    top = sorted(groups.values(), key=lambda x: x["count"], reverse=True)[:5]
    result = []
    for issue in top:
        root_cause = analyzer._root_cause(issue["entries"])
        result.append({
            "key":        issue["key"],
            "count":      issue["count"],
            "severity":   issue["severity"],
            "app":        issue["app"],
            "root_cause": root_cause if root_cause != "No errors found." else None,
            "example":    issue["entries"][0]["message"] if issue["entries"] else "",
        })
    return jsonify(result)


@dashboard_bp.get("/api/logs/export")
@login_required
def export_logs():
    """Export the current parsed log data as a CSV download."""
    severity = request.args.get("severity", "")
    search   = request.args.get("search", "")

    query = ParsedLog.query.filter_by(uploaded_by=session.get("username", ""))
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
    query    = ParsedLog.query.filter_by(uploaded_by=session.get("username", ""))
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
    result = LogAnalyzer().analyze_uploads(files, session.get("username", ""))
    _audit("file_processing", f"Processed {len(files)} files")
    return jsonify(result)


@dashboard_bp.post("/api/clear-analysis")
@login_required
def clear_analysis():
    uploaded_by = session.get("username", "")
    ParsedLog.query.filter_by(uploaded_by=uploaded_by).delete()
    ErrorSignature.query.filter_by(uploaded_by=uploaded_by).delete()
    db.session.commit()
    _audit("clear_analysis", "Cleared parsed logs")
    return jsonify({"message": "Analysis cleared."})


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


