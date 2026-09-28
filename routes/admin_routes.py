"""
admin_routes.py
---------------
Admin panel routes: user management, sync controls, audit log.
"""

import csv
import logging
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session
from werkzeug.security import generate_password_hash

from core.auth import login_required, role_required
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
    return render_template("admin.html")


@admin_bp.get("/admin/users")
@role_required("Admin")
def users_page():
    return render_template("users.html")


@admin_bp.get("/api/admin/modules")
@role_required("Admin")
def list_modules():
    """Return all available module keys and their display labels."""
    from core.auth import ALL_MODULES, MODULE_LABELS
    return jsonify([{"key": k, "label": MODULE_LABELS[k]} for k in ALL_MODULES])


# ── Users ─────────────────────────────────────────────────────────────────────

@admin_bp.get("/api/admin/users")
@role_required("Admin")
def list_users():
    rows = User.query.all()
    return jsonify([_user_dict(u) for u in rows])


@admin_bp.post("/api/admin/users")
@role_required("Admin")
def create_user():
    data = request.get_json(silent=True) or {}
    if User.query.filter_by(username=data.get("username")).first():
        return jsonify({"error": "Username already exists"}), 400
    user = User(
        username = data["username"],
        password = generate_password_hash(data["password"]),
        role     = data.get("role", "Analyst"),
        modules  = _modules_str(data),
    )
    db.session.add(user)
    db.session.commit()
    _audit("create_user", user.username)
    return jsonify(_user_dict(user)), 201


@admin_bp.put("/api/admin/users/<int:user_id>")
@role_required("Admin")
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    if "password" in data and data["password"]:
        user.password = generate_password_hash(data["password"])
    if "role" in data:
        user.role = data["role"]
    if "modules" in data or "allowed_modules" in data:
        user.modules = _modules_str(data)
    db.session.commit()
    _audit("update_user", user.username)
    return jsonify(_user_dict(user))


@admin_bp.delete("/api/admin/users/<int:user_id>")
@role_required("Admin")
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.username == "admin":
        return jsonify({"error": "Cannot delete the built-in admin account"}), 400
    db.session.delete(user)
    db.session.commit()
    _audit("delete_user", user.username)
    return jsonify({"message": "User deleted"})


# ── Sync ──────────────────────────────────────────────────────────────────────

@admin_bp.post("/api/admin/sync")
@admin_bp.post("/api/admin/sync-now")  # alias used by the admin JS
@role_required("Admin")
def trigger_sync():
    try:
        from flask import current_app
        from services.sync_service import SyncService
        svc = SyncService(current_app.config)
        svc.sync_incidents()
        svc.sync_kb_articles()
        count = _rebuild_index()
        _audit("manual_sync", f"Sync complete — {count} documents indexed")
        return jsonify({"message": f"Sync complete. Index rebuilt with {count} documents."})
    except Exception as err:
        log.error("Manual sync failed: %s", err)
        return jsonify({"error": str(err)}), 500


@admin_bp.post("/api/admin/retrain")
@role_required("Admin")
def retrain():
    """Rebuild the TF-IDF search index without syncing from ServiceNow."""
    count = _rebuild_index()
    _audit("retrain", f"{count} documents indexed")
    return jsonify({"message": f"Index rebuilt with {count} documents."})


@admin_bp.post("/api/admin/import-csv")
@role_required("Admin")
def import_csv():
    """Bulk-import incidents from an uploaded CSV file (read in memory, no disk write)."""
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "No file uploaded."}), 400

    raw_bytes = uploaded.read()
    imported, skipped = _import_incidents_csv(raw_bytes)
    count = _rebuild_index()
    _audit("import_csv", f"Imported {imported}, skipped {skipped}")
    return jsonify({
        "message": f"Import done: {imported} added, {skipped} skipped. Index rebuilt with {count} documents."
    })


@admin_bp.get("/api/admin/status")
@login_required
def status():
    """Return system status for the Index Status panel."""
    from flask import current_app
    from services import tfidf_engine

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

    from core.models import KnowledgeEntry
    return jsonify({
        "tfidf_trained":       tfidf_engine.is_trained(),
        "tfidf_documents":     tfidf_engine.document_count(),
        "incident_count":      Incident.query.count(),
        "kb_count":            KBArticle.query.filter_by(active=True).count(),
        "knowledge_count":     KnowledgeEntry.query.filter_by(active=True).count(),
        "snow_configured":     snow_ok,
        "snow_url":            cfg.get("SERVICENOW_URL", ""),
        "last_sync_incidents": last_sync("servicenow_incidents"),
        "last_sync_kb":        last_sync("servicenow_kb"),
    })


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


# ── Audit log ─────────────────────────────────────────────────────────────────

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


# ── ServiceNow Groups ─────────────────────────────────────────────────────────

@admin_bp.get("/api/admin/snow-groups")
@role_required("Admin")
def list_snow_groups():
    rows = ServiceNowGroup.query.order_by(ServiceNowGroup.name).all()
    return jsonify([{"id": r.id, "name": r.name, "active": r.active} for r in rows])


@admin_bp.post("/api/admin/snow-groups")
@role_required("Admin")
def create_snow_group():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Group name is required"}), 400
    if ServiceNowGroup.query.filter_by(name=name).first():
        return jsonify({"error": "Group already exists"}), 400
    group = ServiceNowGroup(name=name)
    db.session.add(group)
    db.session.commit()
    _audit("create_snow_group", name)
    return jsonify({"id": group.id, "name": group.name, "active": group.active}), 201


@admin_bp.put("/api/admin/snow-groups/<int:group_id>")
@role_required("Admin")
def update_snow_group(group_id):
    group = ServiceNowGroup.query.get_or_404(group_id)
    data  = request.get_json(silent=True) or {}
    if "name" in data:
        group.name = data["name"].strip()
    if "active" in data:
        group.active = bool(data["active"])
    db.session.commit()
    _audit("update_snow_group", group.name)
    return jsonify({"id": group.id, "name": group.name, "active": group.active})


@admin_bp.delete("/api/admin/snow-groups/<int:group_id>")
@role_required("Admin")
def delete_snow_group(group_id):
    group = ServiceNowGroup.query.get_or_404(group_id)
    db.session.delete(group)
    db.session.commit()
    _audit("delete_snow_group", group.name)
    return jsonify({"message": "Group deleted"})


# ── Stats ─────────────────────────────────────────────────────────────────────

@admin_bp.get("/api/admin/stats")
@login_required
def stats():
    return jsonify({
        "total_incidents":   Incident.query.count(),
        "total_kb_articles": KBArticle.query.count(),
        "total_users":       User.query.count(),
    })


# ── Helpers ───────────────────────────────────────────────────────────────────

def _user_dict(user):
    return {
        "id":              user.id,
        "username":        user.username,
        "role":            user.role,
        "allowed_modules": user.modules or "",
        "created_at":      user.created_at.isoformat(sep=" ") if getattr(user, "created_at", None) else "",
    }


def _modules_str(data):
    """
    Convert the modules value from the request into a comma-separated string.
    Accepts either:
      - a list  ["dashboard", "recommendations"]  (sent by users.js)
      - a string "dashboard,recommendations"       (sent by older API callers)
    Admin role always gets all modules.
    """
    from core.auth import ALL_MODULES, ADMIN_MODULES
    if data.get("role") == "Admin":
        return ADMIN_MODULES
    raw = data.get("modules") or data.get("allowed_modules") or []
    if isinstance(raw, list):
        return ",".join(m for m in raw if m in ALL_MODULES)
    return ",".join(m.strip() for m in str(raw).split(",") if m.strip() in ALL_MODULES)


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
    import io
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
