"""Knowledge Repository page and its CRUD API."""

from flask import Blueprint, jsonify, render_template, request, session

from core.auth import login_required, module_required
from core.database import db
from core.models import AuditLog
from services.knowledge_service import KnowledgeService

knowledge_bp = Blueprint("knowledge", __name__)


def _audit(action, details=""):
    db.session.add(AuditLog(username=session.get("username", "system"), action=action, details=details))
    db.session.commit()


@knowledge_bp.get("/knowledge")
@module_required("knowledge")
def knowledge_page():
    return render_template("knowledge.html")


@knowledge_bp.get("/api/knowledge")
@login_required
def list_knowledge():
    svc   = KnowledgeService()
    items = svc.list_all()
    return jsonify([{
        "id":               e.id,
        "pattern":          e.pattern,
        "meaning":          e.meaning,
        "resolution":       e.resolution,
        "assignment_group": e.assignment_group,
        "frequency":        e.frequency,
        "active":           e.active,
    } for e in items])


@knowledge_bp.post("/api/knowledge")
@login_required
def add_knowledge():
    data = request.get_json(silent=True) or {}
    if not data.get("pattern"):
        return jsonify({"error": "Pattern is required"}), 400
    entry = KnowledgeService().add(data)
    _audit("add_knowledge", entry.pattern)
    return jsonify({"message": "Entry added", "id": entry.id}), 201


@knowledge_bp.put("/api/knowledge/<int:entry_id>")
@login_required
def update_knowledge(entry_id):
    data  = request.get_json(silent=True) or {}
    entry = KnowledgeService().update(entry_id, data)
    if not entry:
        return jsonify({"error": "Not found"}), 404
    _audit("update_knowledge", entry.pattern)
    return jsonify({"message": "Updated"})


@knowledge_bp.delete("/api/knowledge/<int:entry_id>")
@login_required
def delete_knowledge(entry_id):
    if not KnowledgeService().delete(entry_id):
        return jsonify({"error": "Not found"}), 404
    _audit("delete_knowledge", str(entry_id))
    return jsonify({"message": "Deleted"})


@knowledge_bp.post("/api/knowledge/<int:entry_id>/activate")
@login_required
def activate_knowledge(entry_id):
    entry = KnowledgeService().set_active(entry_id, True)
    if not entry:
        return jsonify({"error": "Not found"}), 404
    _audit("activate_knowledge", str(entry_id))
    return jsonify({"message": "Activated"})


@knowledge_bp.post("/api/knowledge/<int:entry_id>/deactivate")
@login_required
def deactivate_knowledge(entry_id):
    entry = KnowledgeService().set_active(entry_id, False)
    if not entry:
        return jsonify({"error": "Not found"}), 404
    _audit("deactivate_knowledge", str(entry_id))
    return jsonify({"message": "Deactivated"})
