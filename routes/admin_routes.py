"""Admin panel routes: user management, sync controls, audit log."""

import csv
import io
import logging

from flask import Blueprint, Response, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from core.auth import ALL_MODULES, MODULE_LABELS, login_required, role_required
from core.database import db
from core.models import AuditLog, Incident, KBArticle, ServiceNowGroup, SyncHistory, User

log = logging.getLogger(__name__)
admin_bp = Blueprint("admin", __name__)


def _audit(action, details=""):
    db.session.add(AuditLog(username=session.get("username", "system"), action=action, details=details))
    db.session.commit()


@admin_bp.get("/admin")
@role_required("Admin")
def admin_page():
    return render_template(
        "admin.html",
        system_status=_status_data(),
        snow_groups=ServiceNowGroup.query.order_by(ServiceNowGroup.name).all(),
        message=request.args.get("message"),
        error=request.args.get("error"),
    )


@admin_bp.get("/admin/users")
@role_required("Admin")
def users_page():
    users = User.query.all()
    for u in users:
        u.module_list = ALL_MODULES if u.role == "Admin" else \
            [m.strip() for m in (u.modules or "").split(",") if m.strip()]
    modules = [{"key": k, "label": MODULE_LABELS[k]} for k in ALL_MODULES]
    return render_template("users.html", users=users, modules=modules,
                            status=request.args.get("status"), error=request.args.get("error"))


@admin_bp.get("/admin/users/add")
@role_required("Admin")
def add_user_form():
    modules = [{"key": k, "label": MODULE_LABELS[k]} for k in ALL_MODULES]
    role = request.args.get("role", "Analyst")
    selected = ALL_MODULES if role == "Admin" else request.args.getlist("modules")
    return render_template("user_form.html", user=None, modules=modules,
                            selected_modules=selected, role=role)


@admin_bp.get("/admin/users/<int:user_id>/edit")
@role_required("Admin")
def edit_user_form(user_id):
    user = User.query.get_or_404(user_id)
    modules = [{"key": k, "label": MODULE_LABELS[k]} for k in ALL_MODULES]
    role = request.args.get("role", user.role)
    if "role" in request.args:
        selected = ALL_MODULES if role == "Admin" else request.args.getlist("modules")
    else:
        selected = ALL_MODULES if user.role == "Admin" else \
            [m.strip() for m in (user.modules or "").split(",") if m.strip()]
    return render_template("user_form.html", user=user, modules=modules,
                            selected_modules=selected, role=role)


@admin_bp.post("/admin/users/add")
@role_required("Admin")
def create_user():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    role     = request.form.get("role", "Analyst")
    modules  = request.form.getlist("modules")

    if not username or not password:
        return redirect(url_for("admin.users_page", error="Username and password are required."))
    if User.query.filter_by(username=username).first():
        return redirect(url_for("admin.users_page", error="Username already exists."))

    user = User(
        username = username,
        password = generate_password_hash(password),
        role     = role,
        modules  = _modules_str(role, modules),
    )
    db.session.add(user)
    db.session.commit()
    _audit("create_user", user.username)
    return redirect(url_for("admin.users_page", status=f"User '{username}' created successfully."))


@admin_bp.post("/admin/users/<int:user_id>/edit")
@role_required("Admin")
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    password = request.form.get("password") or ""
    role     = request.form.get("role", user.role)
    modules  = request.form.getlist("modules")

    if password:
        user.password = generate_password_hash(password)
    user.role    = role
    user.modules = _modules_str(role, modules)
    db.session.commit()
    _audit("update_user", user.username)
    return redirect(url_for("admin.users_page", status="User updated successfully."))


@admin_bp.post("/admin/users/<int:user_id>/delete")
@role_required("Admin")
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.username == "admin":
        return redirect(url_for("admin.users_page", error="Cannot delete the built-in admin account."))
    db.session.delete(user)
    db.session.commit()
    _audit("delete_user", user.username)
    return redirect(url_for("admin.users_page", status=f"User '{user.username}' deleted."))


@admin_bp.post("/admin/sync")
@role_required("Admin")
def sync_now():
    try:
        from flask import current_app
        from services.sync_service import SyncService
        svc = SyncService(current_app.config)
        svc.sync_incidents()
        svc.sync_kb_articles()
        count = _rebuild_index()
        _audit("manual_sync", f"Sync complete — {count} documents indexed")
        return redirect(url_for("admin.admin_page", message=f"Sync complete. Index rebuilt with {count} documents."))
    except Exception as err:
        log.error("Manual sync failed: %s", err)
        return redirect(url_for("admin.admin_page", error=f"Sync failed: {err}"))


@admin_bp.post("/admin/retrain")
@role_required("Admin")
def retrain_now():
    """Rebuild the TF-IDF search index without syncing from ServiceNow."""
    count = _rebuild_index()
    _audit("retrain", f"{count} documents indexed")
    return redirect(url_for("admin.admin_page", message=f"Index rebuilt with {count} documents."))


@admin_bp.post("/admin/import-csv")
@role_required("Admin")
def import_csv_now():
    """Bulk-import incidents from an uploaded CSV file (read in memory, no disk write)."""
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return redirect(url_for("admin.admin_page", error="Please choose a CSV file first."))

    raw_bytes = uploaded.read()
    imported, skipped = _import_incidents_csv(raw_bytes)
    count = _rebuild_index()
    _audit("import_csv", f"Imported {imported}, skipped {skipped}")
    return redirect(url_for(
        "admin.admin_page",
        message=f"Import done: {imported} added, {skipped} skipped. Index rebuilt with {count} documents.",
    ))


@admin_bp.get("/admin/import-template")
@role_required("Admin")
def download_import_template():
    """Download a sample CSV showing the expected columns for incident import."""
    headers = [
        "incident_number", "application", "server", "environment",
        "error_description", "exception_message", "root_cause",
        "resolution", "assignment_group", "status",
    ]
    examples = [
        ["INC0001001", "OrderService", "app-server-01", "Production",
         "ORA-12541: TNS no listener", "java.sql.SQLException: Listener refused connection",
         "Database listener was not running on port 1521",
         "Started DB listener using: lsnrctl start. Verified connectivity.",
         "DBA Team", "Resolved"],
        ["INC0001002", "PaymentService", "app-server-02", "Production",
         "Connection refused to 10.0.0.5:8080", "java.net.ConnectException: Connection refused",
         "Target microservice was down after deployment",
         "Restarted PaymentService pod. Added health-check to deployment pipeline.",
         "Application Support", "Resolved"],
    ]
    output = io.StringIO()
    csv.writer(output).writerows([headers, *examples])
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=incident_import_template.csv"},
    )


@admin_bp.get("/api/admin/status")
@login_required
def status():
    """Return system status for the Index Status panel."""
    return jsonify(_status_data())


@admin_bp.get("/api/admin/sync-history")
@login_required
def sync_history():
    rows = SyncHistory.query.order_by(SyncHistory.last_sync_time.desc()).limit(50).all()
    return jsonify([{
        "source":    r.source,
        "time":      r.last_sync_time.isoformat(sep=" ") if r.last_sync_time else "",
        "status":    r.status,
        "message":   r.message,
    } for r in rows])


@admin_bp.get("/api/admin/audit-log")
@role_required("Admin")
def audit_log():
    rows = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(200).all()
    return jsonify([{
        "timestamp": r.timestamp.isoformat(sep=" ") if r.timestamp else "",
        "username":  r.username,
        "action":    r.action,
        "details":   r.details,
    } for r in rows])


@admin_bp.post("/admin/snow-groups/add")
@role_required("Admin")
def add_snow_group():
    name = (request.form.get("name") or "").strip()
    if not name:
        return redirect(url_for("admin.admin_page", error="Group name is required."))
    if ServiceNowGroup.query.filter_by(name=name).first():
        return redirect(url_for("admin.admin_page", error="Group already exists."))
    db.session.add(ServiceNowGroup(name=name))
    db.session.commit()
    _audit("create_snow_group", name)
    return redirect(url_for("admin.admin_page", message=f"Group '{name}' added."))


@admin_bp.post("/admin/snow-groups/<int:group_id>/toggle")
@role_required("Admin")
def toggle_snow_group(group_id):
    group = ServiceNowGroup.query.get_or_404(group_id)
    group.active = not group.active
    db.session.commit()
    _audit("update_snow_group", group.name)
    return redirect(url_for("admin.admin_page"))


@admin_bp.post("/admin/snow-groups/<int:group_id>/delete")
@role_required("Admin")
def delete_snow_group(group_id):
    group = ServiceNowGroup.query.get_or_404(group_id)
    db.session.delete(group)
    db.session.commit()
    _audit("delete_snow_group", group.name)
    return redirect(url_for("admin.admin_page", message="Group deleted."))


@admin_bp.get("/api/admin/stats")
@login_required
def stats():
    return jsonify({
        "total_incidents":   Incident.query.count(),
        "total_kb_articles": KBArticle.query.count(),
        "total_users":       User.query.count(),
    })


def _status_data():
    """Build the system-status dict shown on the admin page and index status panel."""
    from flask import current_app
    from services import tfidf_engine
    from core.models import KnowledgeEntry

    def last_sync(source):
        record = SyncHistory.query.filter_by(source=source).order_by(SyncHistory.last_sync_time.desc()).first()
        if not record:
            return None
        return {
            "time":    record.last_sync_time.strftime("%Y-%m-%d %H:%M:%S") if record.last_sync_time else "",
            "status":  record.status,
            "message": record.message,
        }

    cfg = current_app.config
    snow_ok = bool(cfg.get("SERVICENOW_URL") and cfg.get("SERVICENOW_USERNAME") and cfg.get("SERVICENOW_PASSWORD"))

    return {
        "tfidf_trained":       tfidf_engine.is_trained(),
        "tfidf_documents":     tfidf_engine.document_count(),
        "incident_count":      Incident.query.count(),
        "kb_count":            KBArticle.query.filter_by(active=True).count(),
        "knowledge_count":     KnowledgeEntry.query.filter_by(active=True).count(),
        "snow_configured":     snow_ok,
        "snow_url":            cfg.get("SERVICENOW_URL", ""),
        "last_sync_incidents": last_sync("servicenow_incidents"),
        "last_sync_kb":        last_sync("servicenow_kb"),
    }


def _modules_str(role, selected_modules):
    """Comma-separated module list for storage. Admin role always gets all modules."""
    from core.auth import ADMIN_MODULES
    if role == "Admin":
        return ADMIN_MODULES
    return ",".join(m for m in selected_modules if m in ALL_MODULES)


def _rebuild_index():
    """Rebuild the TF-IDF search index from all DB data. Returns document count."""
    from services import tfidf_engine
    from core.models import KnowledgeEntry
    incidents    = Incident.query.all()
    kb_articles  = KBArticle.query.filter_by(active=True).all()
    knowledge    = KnowledgeEntry.query.filter_by(active=True).all()
    return tfidf_engine.retrain(incidents, kb_articles, knowledge)


def _import_incidents_csv(raw_bytes):
    """
    Parse CSV from raw bytes and insert new incidents into the DB.
    Returns (imported_count, skipped_count).
    Nothing is written to disk.
    """
    allowed_fields = {
        "incident_number", "application", "server", "environment",
        "error_description", "exception_message", "root_cause",
        "resolution", "assignment_group", "status",
    }
    imported = skipped = 0
    text = raw_bytes.decode("utf-8-sig", errors="ignore")
    for row in csv.DictReader(io.StringIO(text)):
        row    = {k.strip(): v for k, v in row.items()}
        number = row.get("incident_number", "").strip()
        if not number or Incident.query.filter_by(incident_number=number).first():
            skipped += 1
            continue
        db.session.add(Incident(**{k: v for k, v in row.items() if k in allowed_fields}))
        imported += 1
    db.session.commit()
    return imported, skipped
