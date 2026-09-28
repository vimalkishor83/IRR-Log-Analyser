let currentFilter = "all";
let allRows       = [];

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("bulkToolbar").style.display = "none";
    document.getElementById("addKnowledge").addEventListener("click", addKnowledge);
    loadKnowledge();
});

// ── Toast ─────────────────────────────────────────────────────────────────────

let _toastTimer = null;
function showToast(msg, type = "success") {
    const el   = document.getElementById("kbToast");
    const icon = document.getElementById("toastIcon");
    const txt  = document.getElementById("toastMsg");
    icon.textContent = type === "success" ? "✅" : "❌";
    txt.textContent  = msg;
    el.classList.add("show");
    clearTimeout(_toastTimer);
    _toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

// ── Char counter ──────────────────────────────────────────────────────────────

function updateChar(id, max) {
    const len = (document.getElementById(id).value || "").length;
    const el  = document.getElementById(id + "-chars");
    if (el) {
        el.textContent = len;
        el.style.color = len > max * 0.9 ? "#f59e0b" : "";
    }
}

// ── Validation helpers ────────────────────────────────────────────────────────

function setErr(id, msg) {
    const input = document.getElementById(id);
    const errEl = document.getElementById("err-" + id);
    input.classList.add("kb-field-error");
    if (errEl) { errEl.textContent = msg; errEl.classList.add("show"); }
}

function clearErr(id) {
    const input = document.getElementById(id);
    const errEl = document.getElementById("err-" + id);
    input.classList.remove("kb-field-error");
    if (errEl) errEl.classList.remove("show");
}

function resetForm() {
    ["pattern","meaning","resolution","assignmentGroup"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = "";
        clearErr(id);
    });
    ["pattern","meaning","resolution"].forEach(id => updateChar(id, 0));
    document.getElementById("pattern-chars").textContent    = "0";
    document.getElementById("meaning-chars").textContent    = "0";
    document.getElementById("resolution-chars").textContent = "0";
}

// ── Filters ───────────────────────────────────────────────────────────────────

function setFilter(filter) {
    currentFilter = filter;
    ["all","active","inactive"].forEach(f => {
        document.getElementById("filter" + f.charAt(0).toUpperCase() + f.slice(1))
            .classList.toggle("active", f === filter);
    });
    renderFiltered();
}

function clearSearch() {
    document.getElementById("knowledgeSearch").value = "";
    renderFiltered();
}

function renderFiltered() {
    const term = (document.getElementById("knowledgeSearch").value || "").toLowerCase().trim();
    const rows = allRows
        .filter(r => currentFilter === "active"   ?  r.active
                   : currentFilter === "inactive" ? !r.active
                   : true)
        .filter(r => !term || [r.pattern, r.meaning, r.resolution, r.assignment_group]
            .some(f => (f || "").toLowerCase().includes(term)));
    _renderRows(rows);
}

// ── Add ───────────────────────────────────────────────────────────────────────

async function addKnowledge() {
    const pattern    = document.getElementById("pattern").value.trim();
    const meaning    = document.getElementById("meaning").value.trim();
    const resolution = document.getElementById("resolution").value.trim();
    const assignmentGroup = document.getElementById("assignmentGroup").value.trim();

    let valid = true;
    if (!pattern)    { setErr("pattern",    "Error Pattern is required.");        valid = false; }
    if (!meaning)    { setErr("meaning",    "Meaning / Root Cause is required."); valid = false; }
    if (!resolution) { setErr("resolution", "Resolution is required.");           valid = false; }
    if (!valid) return;

    const btn = document.getElementById("addKnowledge");
    btn.classList.add("loading");
    btn.disabled = true;

    try {
        await fetchJson("/api/knowledge", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pattern, meaning, resolution, assignment_group: assignmentGroup })
        });
        resetForm();
        await loadKnowledge();
        showToast("Knowledge entry added successfully.");
        document.getElementById("knowledgeRows").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
        showToast(err.message, "error");
    } finally {
        btn.classList.remove("loading");
        btn.disabled = false;
    }
}

// ── Load & render ─────────────────────────────────────────────────────────────

async function loadKnowledge() {
    allRows = await fetchJson("/api/knowledge");
    renderFiltered();
}

function _renderRows(rows) {
    const container = document.getElementById("knowledgeRows");
    const badge     = document.getElementById("repoCountBadge");

    // Update count badge (always reflects full list, not filtered)
    const total = allRows.length;
    badge.textContent = total === 1 ? "1 entry" : `${total} entries`;

    if (!rows.length) {
        const term = (document.getElementById("knowledgeSearch").value || "").trim();
        const msg  = term ? `No entries match "<strong>${escapeHtml(term)}</strong>".`
                   : currentFilter === "all" ? "No knowledge entries yet. Add one above."
                   : `No ${currentFilter} entries.`;
        container.innerHTML = `<p class="text-secondary py-3 text-center">${msg}</p>`;
        updateBulkToolbar(0);
        return;
    }

    const selectAll = rows.length > 1 ? `
        <div class="d-flex align-items-center gap-2 pb-2 mb-2" style="border-bottom:1px solid #e2e8f0">
            <input type="checkbox" id="selectAll" class="form-check-input mt-0"
                   onchange="toggleSelectAll(this.checked)">
            <label for="selectAll" class="form-check-label small text-secondary mb-0">Select all</label>
        </div>` : "";

    container.innerHTML = selectAll + rows.map(row => renderRow(row, rows.length)).join("");
    updateBulkToolbar(rows.length);
}

function renderRow(row, totalRows) {
    const statusBadge = row.active
        ? `<span class="badge text-bg-success" style="font-size:.7rem">Active</span>`
        : `<span class="badge text-bg-secondary" style="font-size:.7rem">Inactive</span>`;

    const toggleBtn = row.active
        ? `<button class="btn btn-sm btn-outline-warning" style="font-size:.75rem;padding:.2rem .6rem" onclick="toggleActive(${row.id},false)"><i class="bi bi-pause-circle me-1"></i>Deactivate</button>`
        : `<button class="btn btn-sm btn-outline-success"  style="font-size:.75rem;padding:.2rem .6rem" onclick="toggleActive(${row.id},true)"><i class="bi bi-play-circle me-1"></i>Activate</button>`;

    const groupTag = row.assignment_group
        ? `<span class="kb-group-tag ms-1"><i class="bi bi-people me-1"></i>${escapeHtml(row.assignment_group)}</span>`
        : "";

    const checkboxCell = totalRows > 1
        ? `<input type="checkbox" class="form-check-input row-check mt-1 flex-shrink-0" value="${row.id}" onchange="updateBulkToolbar()">`
        : `<span style="width:1rem;display:inline-block"></span>`;

    return `
    <div class="kb-row${row.active ? "" : " inactive-row"}" id="row-${row.id}">
      <div class="d-flex align-items-start gap-3">
        ${checkboxCell}
        <div class="flex-grow-1 min-w-0">
          <div class="d-flex align-items-center gap-2 flex-wrap mb-1">
            <span class="kb-pattern">${escapeHtml(row.pattern)}</span>
            ${statusBadge}
            ${groupTag}
          </div>
          <div class="kb-meaning"><i class="bi bi-lightbulb me-1 text-warning"></i>${escapeHtml(row.meaning)}</div>
          <div class="kb-resolution mt-1"><strong><i class="bi bi-tools me-1"></i>Fix:</strong> ${escapeHtml(row.resolution)}</div>
        </div>
        <div class="d-flex gap-1 flex-shrink-0 flex-wrap">
          ${toggleBtn}
          <button class="btn btn-sm btn-outline-primary"  style="font-size:.75rem;padding:.2rem .6rem" onclick="showEditForm(${row.id})"><i class="bi bi-pencil me-1"></i>Edit</button>
          <button class="btn btn-sm btn-outline-danger"   style="font-size:.75rem;padding:.2rem .6rem" onclick="deleteEntry(${row.id})"><i class="bi bi-trash me-1"></i>Delete</button>
        </div>
      </div>

      <!-- Inline edit form -->
      <div id="edit-form-${row.id}" class="kb-edit-form" style="display:none">
        <div class="row g-2">
          <div class="col-md-3">
            <label class="form-label small fw-semibold">Error Pattern</label>
            <input id="edit-pattern-${row.id}" class="form-control form-control-sm" value="${escapeHtml(row.pattern)}" maxlength="120">
          </div>
          <div class="col-md-3">
            <label class="form-label small fw-semibold">Meaning / Root Cause</label>
            <input id="edit-meaning-${row.id}" class="form-control form-control-sm" value="${escapeHtml(row.meaning)}" maxlength="200">
          </div>
          <div class="col-md-4">
            <label class="form-label small fw-semibold">Resolution</label>
            <textarea id="edit-resolution-${row.id}" class="form-control form-control-sm" rows="2" maxlength="500">${escapeHtml(row.resolution)}</textarea>
          </div>
          <div class="col-md-2">
            <label class="form-label small fw-semibold">Group</label>
            <input id="edit-group-${row.id}" class="form-control form-control-sm" value="${escapeHtml(row.assignment_group || "")}" maxlength="80">
          </div>
        </div>
        <div class="mt-2 d-flex gap-2">
          <button class="btn btn-sm btn-primary"           onclick="saveEdit(${row.id})"><i class="bi bi-check2 me-1"></i>Save</button>
          <button class="btn btn-sm btn-outline-secondary" onclick="hideEditForm(${row.id})">Cancel</button>
        </div>
      </div>
    </div>`;
}

// ── Bulk selection ─────────────────────────────────────────────────────────────

function getSelectedIds() {
    return Array.from(document.querySelectorAll(".row-check:checked")).map(el => Number(el.value));
}

function toggleSelectAll(checked) {
    document.querySelectorAll(".row-check").forEach(el => el.checked = checked);
    updateBulkToolbar();
}

function updateBulkToolbar(totalRows) {
    const total   = totalRows !== undefined ? totalRows : document.querySelectorAll(".row-check").length;
    const checked = getSelectedIds().length;
    const toolbar = document.getElementById("bulkToolbar");
    const label   = document.getElementById("selectionCount");

    if (total > 1 && checked > 0) {
        toolbar.style.display = "flex";
        label.textContent = `${checked} selected`;
    } else {
        toolbar.style.display = "none";
    }

    const sa = document.getElementById("selectAll");
    if (sa) sa.checked = total > 1 && checked === total;
}

async function bulkAction(action) {
    const ids = getSelectedIds();
    if (!ids.length) return;
    if (action === "delete" && !confirm(`Permanently delete ${ids.length} entr${ids.length === 1 ? "y" : "ies"}? This cannot be undone.`)) return;

    try {
        await Promise.all(ids.map(id =>
            action === "delete"
                ? fetchJson(`/api/knowledge/${id}`, { method: "DELETE" })
                : fetchJson(`/api/knowledge/${id}/${action}`, { method: "POST" })
        ));
        await loadKnowledge();
        showToast(`${ids.length} entr${ids.length === 1 ? "y" : "ies"} ${action === "delete" ? "deleted" : action + "d"}.`);
    } catch (err) {
        showToast(err.message, "error");
    }
}

// ── Single-row actions ─────────────────────────────────────────────────────────

function showEditForm(id)  { document.getElementById(`edit-form-${id}`).style.display = "block"; }
function hideEditForm(id)  { document.getElementById(`edit-form-${id}`).style.display = "none";  }

async function saveEdit(id) {
    const pattern    = document.getElementById(`edit-pattern-${id}`).value.trim();
    const meaning    = document.getElementById(`edit-meaning-${id}`).value.trim();
    const resolution = document.getElementById(`edit-resolution-${id}`).value.trim();
    const assignment_group = document.getElementById(`edit-group-${id}`).value.trim();

    if (!pattern || !meaning || !resolution) {
        showToast("Pattern, Meaning, and Resolution are required.", "error");
        return;
    }

    try {
        await fetchJson(`/api/knowledge/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pattern, meaning, resolution, assignment_group })
        });
        await loadKnowledge();
        showToast("Entry updated.");
    } catch (err) {
        showToast(err.message, "error");
    }
}

async function toggleActive(id, activate) {
    try {
        await fetchJson(`/api/knowledge/${id}/${activate ? "activate" : "deactivate"}`, { method: "POST" });
        await loadKnowledge();
        showToast(`Entry ${activate ? "activated" : "deactivated"}.`);
    } catch (err) {
        showToast(err.message, "error");
    }
}

async function deleteEntry(id) {
    if (!confirm("Permanently delete this entry? This cannot be undone.")) return;
    try {
        await fetchJson(`/api/knowledge/${id}`, { method: "DELETE" });
        await loadKnowledge();
        showToast("Entry deleted.");
    } catch (err) {
        showToast(err.message, "error");
    }
}

