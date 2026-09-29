"""Knowledge Repository page and its CRUD routes."""

from flask import Blueprint, redirect, render_template, request, url_for

from core.audit import log_action as _audit
from core.auth import module_required
from services.knowledge_service import KnowledgeService

knowledge_bp = Blueprint("knowledge", __name__)


def _back_to_list(status=None, error=None, edit_id=None):
    """Redirect back to the knowledge list, preserving the filter/search the form was submitted from."""
    return redirect(url_for(
        "knowledge.knowledge_page",
        filter=request.form.get("filter", "all"),
        search=request.form.get("search", ""),
        status=status, error=error, edit=edit_id,
    ))


@knowledge_bp.get("/knowledge")
@module_required("knowledge")
def knowledge_page():
    status_filter = request.args.get("filter", "all")
    search        = request.args.get("search", "").strip()
    entries       = KnowledgeService().list_all(status=status_filter, search=search)
    return render_template(
        "knowledge.html",
        entries=entries,
        total_count=len(KnowledgeService().list_all()),
        status_filter=status_filter,
        search=search,
        edit_id=request.args.get("edit", type=int),
        status=request.args.get("status"),
        error=request.args.get("error"),
    )


@knowledge_bp.post("/knowledge/add")
@module_required("knowledge")
def add_knowledge():
    pattern    = (request.form.get("pattern") or "").strip()
    meaning    = (request.form.get("meaning") or "").strip()
    resolution = (request.form.get("resolution") or "").strip()

    if not (pattern and meaning and resolution):
        return _back_to_list(error="Error Pattern, Meaning, and Resolution are required.")

    entry = KnowledgeService().add({
        "pattern": pattern,
        "meaning": meaning,
        "resolution": resolution,
        "assignment_group": (request.form.get("assignment_group") or "").strip(),
    })
    _audit("add_knowledge", entry.pattern)
    return _back_to_list(status="Knowledge entry added successfully.")


@knowledge_bp.post("/knowledge/<int:entry_id>/edit")
@module_required("knowledge")
def update_knowledge(entry_id):
    pattern    = (request.form.get("pattern") or "").strip()
    meaning    = (request.form.get("meaning") or "").strip()
    resolution = (request.form.get("resolution") or "").strip()

    if not (pattern and meaning and resolution):
        return _back_to_list(error="Error Pattern, Meaning, and Resolution are required.", edit_id=entry_id)

    entry = KnowledgeService().update(entry_id, {
        "pattern": pattern,
        "meaning": meaning,
        "resolution": resolution,
        "assignment_group": (request.form.get("assignment_group") or "").strip(),
    })
    if not entry:
        return _back_to_list(error="Entry not found.")
    _audit("update_knowledge", entry.pattern)
    return _back_to_list(status="Entry updated.")


@knowledge_bp.post("/knowledge/<int:entry_id>/delete")
@module_required("knowledge")
def delete_knowledge(entry_id):
    if not KnowledgeService().delete(entry_id):
        return _back_to_list(error="Entry not found.")
    _audit("delete_knowledge", str(entry_id))
    return _back_to_list(status="Entry deleted.")


@knowledge_bp.post("/knowledge/<int:entry_id>/activate")
@module_required("knowledge")
def activate_knowledge(entry_id):
    entry = KnowledgeService().set_active(entry_id, True)
    if not entry:
        return _back_to_list(error="Entry not found.")
    _audit("activate_knowledge", str(entry_id))
    return _back_to_list(status="Entry activated.")


@knowledge_bp.post("/knowledge/<int:entry_id>/deactivate")
@module_required("knowledge")
def deactivate_knowledge(entry_id):
    entry = KnowledgeService().set_active(entry_id, False)
    if not entry:
        return _back_to_list(error="Entry not found.")
    _audit("deactivate_knowledge", str(entry_id))
    return _back_to_list(status="Entry deactivated.")
