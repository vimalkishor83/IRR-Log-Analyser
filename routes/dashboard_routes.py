"""Log Analyzer dashboard — page + its log-viewer routes."""

import logging

from flask import Blueprint, redirect, render_template, request, session, url_for
from sqlalchemy import func

from core.audit import log_action as _audit
from core.auth import login_required, module_required
from core.database import db
from core.models import ErrorSignature, Incident, KBArticle, ParsedLog
from services.log_analyzer import LogAnalyzer

log = logging.getLogger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)

PER_PAGE = 100


@dashboard_bp.route("/")
@module_required("dashboard")
def index():
    uploaded_by = session.get("username", "")
    severity    = request.args.get("severity", "")
    search      = request.args.get("search", "").strip()
    page        = max(1, request.args.get("page", 1, type=int))

    query = ParsedLog.query.filter_by(uploaded_by=uploaded_by)
    if severity:
        query = query.filter_by(severity=severity)
    if search:
        query = query.filter(ParsedLog.message.ilike(f"%{search}%"))

    total_log_count = query.count()
    rows = query.order_by(ParsedLog.timestamp.desc()).offset((page - 1) * PER_PAGE).limit(PER_PAGE).all()

    return render_template(
        "dashboard.html",
        kpis=_kpi_data(uploaded_by),
        severity_chart=_severity_chart_data(uploaded_by),
        app_chart=_app_chart_data(uploaded_by),
        top_issues=_top_issues(uploaded_by),
        log_rows=rows,
        severity_filter=severity,
        search=search,
        page=page,
        per_page=PER_PAGE,
        total_log_count=total_log_count,
        total_pages=max(1, -(-total_log_count // PER_PAGE)),
        message=request.args.get("message"),
    )


@dashboard_bp.post("/analyze")
@login_required
def analyze_logs():
    files = request.files.getlist("files")
    if not files or not any(f.filename for f in files):
        return redirect(url_for("dashboard.index", message="Please select at least one log file."))

    # Files are read into memory and parsed — nothing is written to disk
    result = LogAnalyzer().analyze_uploads(files, session.get("username", ""))
    _audit("file_processing", f"Processed {len(files)} files")
    messages = result.get("messages") or []
    summary  = "; ".join(messages) if messages else f"Analysis completed. {result['total_lines']} log rows parsed."
    return redirect(url_for("dashboard.index", message=summary))


@dashboard_bp.post("/clear-analysis")
@login_required
def clear_analysis():
    uploaded_by = session.get("username", "")
    ParsedLog.query.filter_by(uploaded_by=uploaded_by).delete()
    ErrorSignature.query.filter_by(uploaded_by=uploaded_by).delete()
    db.session.commit()
    _audit("clear_analysis", "Cleared parsed logs")
    return redirect(url_for("dashboard.index", message="Analysis cleared."))


def _kpi_data(uploaded_by):
    error_levels = ("ERROR", "FATAL", "CRITICAL")

    sev_rows = (
        db.session.query(ParsedLog.severity, func.count())
        .filter(ParsedLog.uploaded_by == uploaded_by)
        .group_by(ParsedLog.severity)
        .all()
    )
    sev_map = {s: c for s, c in sev_rows}

    unique_errors = (
        db.session.query(func.count(ParsedLog.signature.distinct()))
        .filter(ParsedLog.uploaded_by == uploaded_by, ParsedLog.severity.in_(error_levels))
        .scalar() or 0
    )
    top_app = (
        db.session.query(ParsedLog.application, func.count())
        .filter(ParsedLog.uploaded_by == uploaded_by, ParsedLog.severity.in_(error_levels))
        .group_by(ParsedLog.application)
        .order_by(func.count().desc())
        .first()
    )
    top_server = (
        db.session.query(ParsedLog.server, func.count())
        .filter(ParsedLog.uploaded_by == uploaded_by, ParsedLog.severity.in_(error_levels))
        .group_by(ParsedLog.server)
        .order_by(func.count().desc())
        .first()
    )

    return {
        "total_logs":          sum(sev_map.values()),
        "total_errors":        sum(c for s, c in sev_rows if s in error_levels),
        "unique_errors":       unique_errors,
        "critical_errors":     sum(c for s, c in sev_rows if s in ("FATAL", "CRITICAL")),
        "warning_count":       sev_map.get("WARN", 0),
        "top_application":     (top_app[0] or "Unknown") if top_app else "None",
        "top_server":          (top_server[0] or "Unknown") if top_server else "None",
        "knowledge_base_size": Incident.query.count() + KBArticle.query.filter_by(active=True).count(),
    }


def _severity_chart_data(uploaded_by):
    rows = (
        db.session.query(ParsedLog.severity, func.count())
        .filter(ParsedLog.uploaded_by == uploaded_by)
        .group_by(ParsedLog.severity)
        .all()
    )
    return dict(sorted(((s, c) for s, c in rows), key=lambda x: x[1], reverse=True))


def _app_chart_data(uploaded_by):
    error_levels = ("ERROR", "FATAL", "CRITICAL")
    rows = (
        db.session.query(ParsedLog.application, func.count())
        .filter(ParsedLog.uploaded_by == uploaded_by, ParsedLog.severity.in_(error_levels))
        .group_by(ParsedLog.application)
        .order_by(func.count().desc())
        .limit(5)
        .all()
    )
    return {a or "Unknown": c for a, c in rows}


def _top_issues(uploaded_by):
    """Return top 5 ERROR/CRITICAL issues with a probable root cause per issue."""
    error_levels = ("ERROR", "FATAL", "CRITICAL")

    rows = (
        ParsedLog.query
        .filter(ParsedLog.uploaded_by == uploaded_by, ParsedLog.severity.in_(error_levels))
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
    return result


