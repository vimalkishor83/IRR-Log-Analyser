// All available modules — loaded from the server on page load
let ALL_MODULES = [];

// Native <dialog> element reference
const userDialog = () => document.getElementById("userDialog");

function openModal()  { userDialog().showModal(); }
function closeModal() { userDialog().close(); }

document.addEventListener("DOMContentLoaded", async () => {
    // Close dialog when clicking on the backdrop (outside the box)
    userDialog().addEventListener("click", e => {
        const rect = userDialog().getBoundingClientRect();
        if (e.clientX < rect.left || e.clientX > rect.right ||
            e.clientY < rect.top  || e.clientY > rect.bottom) {
            closeModal();
        }
    });
    await loadModules();
    await loadUsers();
});

// ── Load data ─────────────────────────────────────────────────────────────────

async function loadModules() {
    ALL_MODULES = await fetchJson("/api/admin/modules");
}

async function loadUsers() {
    try {
        const users = await fetchJson("/api/admin/users");
        // Normalise: allowed_modules is a comma-separated string → split to array
        users.forEach(u => {
            u.modules = u.role === "Admin"
                ? ALL_MODULES.map(m => m.key)
                : (u.allowed_modules || "").split(",").map(s => s.trim()).filter(Boolean);
        });
        renderUsersTable(users);
    } catch (err) {
        showStatus(err.message, "danger");
    }
}

// ── Render table ──────────────────────────────────────────────────────────────

function renderUsersTable(users) {
    const tbody = document.getElementById("usersTableBody");

    if (!users.length) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-secondary text-center py-4">No users found.</td></tr>`;
        return;
    }

    tbody.innerHTML = users.map(user => {
        // Build module badge list
        const moduleBadges = user.role === "Admin"
            ? `<span class="badge text-bg-primary me-1">All Modules</span>`
            : (user.modules.length
                ? user.modules.map(m => `<span class="badge text-bg-secondary me-1">${escapeHtml(moduleLabel(m))}</span>`).join("")
                : `<span class="text-secondary small">No modules assigned</span>`);

        const roleBadge = user.role === "Admin"
            ? `<span class="badge text-bg-danger">Admin</span>`
            : `<span class="badge text-bg-secondary">Analyst</span>`;

        // Prevent deleting the built-in admin
        const deleteBtn = user.username === "admin"
            ? `<button class="btn btn-sm btn-outline-danger" disabled title="Built-in admin cannot be deleted">Delete</button>`
            : `<button class="btn btn-sm btn-outline-danger" onclick="confirmDelete(${user.id}, '${escapeHtml(user.username)}')">Delete</button>`;

        return `
            <tr>
                <td>
                    <i class="bi bi-person-circle me-1 text-secondary"></i>
                    <strong>${escapeHtml(user.username)}</strong>
                </td>
                <td>${roleBadge}</td>
                <td>${moduleBadges}</td>
                <td class="text-end">
                    <button class="btn btn-sm btn-outline-primary me-1" onclick="openEditModal(${JSON.stringify(user).replaceAll('"', '&quot;')})">
                        <i class="bi bi-pencil me-1"></i>Edit
                    </button>
                    ${deleteBtn}
                </td>
            </tr>`;
    }).join("");
}

function moduleLabel(key) {
    const found = ALL_MODULES.find(m => m.key === key);
    return found ? found.label : key;
}

// ── Modal: Add ────────────────────────────────────────────────────────────────

function openAddModal() {
    document.getElementById("modalTitle").textContent     = "Add User";
    document.getElementById("editUserId").value           = "";
    document.getElementById("inputUsername").value        = "";
    document.getElementById("inputUsername").disabled     = false;
    document.getElementById("inputPassword").value        = "";
    document.getElementById("inputRole").value            = "Analyst";
    document.getElementById("passwordLabel").innerHTML    = `Password <span class="text-danger">*</span>`;
    document.getElementById("passwordHint").classList.add("d-none");

    renderModuleCheckboxes([]);   // Default: no modules selected
    onRoleChange();
    openModal();
}

// ── Modal: Edit ───────────────────────────────────────────────────────────────

function openEditModal(user) {
    document.getElementById("modalTitle").textContent     = `Edit User — ${user.username}`;
    document.getElementById("editUserId").value           = user.id;
    document.getElementById("inputUsername").value        = user.username;
    document.getElementById("inputUsername").disabled     = true;   // Username cannot be changed
    document.getElementById("inputPassword").value        = "";
    document.getElementById("inputRole").value            = user.role;
    document.getElementById("passwordLabel").innerHTML    = "Password";
    document.getElementById("passwordHint").classList.remove("d-none");

    renderModuleCheckboxes(user.modules);
    onRoleChange();
    openModal();
}

// ── Module checkboxes ─────────────────────────────────────────────────────────

function renderModuleCheckboxes(selectedModules) {
    const container = document.getElementById("moduleCheckboxes");
    container.innerHTML = ALL_MODULES.map(mod => `
        <div class="form-check">
            <input class="form-check-input module-check"
                   type="checkbox"
                   id="mod_${mod.key}"
                   value="${mod.key}"
                   ${selectedModules.includes(mod.key) ? "checked" : ""}>
            <label class="form-check-label" for="mod_${mod.key}">
                ${escapeHtml(mod.label)}
            </label>
        </div>`).join("");
}

function onRoleChange() {
    const isAdmin = document.getElementById("inputRole").value === "Admin";
    // Disable checkboxes for Admin (they always have full access)
    document.querySelectorAll(".module-check").forEach(cb => {
        cb.checked  = isAdmin ? true : cb.checked;
        cb.disabled = isAdmin;
    });
    document.getElementById("moduleCheckboxes").style.opacity = isAdmin ? "0.5" : "1";
    document.getElementById("adminModuleNote").classList.toggle("d-none", !isAdmin);
}

function getSelectedModules() {
    return Array.from(document.querySelectorAll(".module-check:checked")).map(cb => cb.value);
}

// ── Save (create or update) ───────────────────────────────────────────────────

async function saveUser() {
    const userId   = document.getElementById("editUserId").value;
    const username = document.getElementById("inputUsername").value.trim();
    const password = document.getElementById("inputPassword").value.trim();
    const role     = document.getElementById("inputRole").value;
    const modules  = getSelectedModules();

    if (!userId && (!username || !password)) {
        showStatus("Username and password are required.", "warning");
        return;
    }

    const body = { role, modules };
    if (!userId) body.username = username;   // Only set on create
    if (password) body.password = password;  // Only set if provided

    try {
        const url    = userId ? `/api/admin/users/${userId}` : "/api/admin/users";
        const method = userId ? "PUT" : "POST";
        await fetchJson(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        closeModal();
        showStatus(userId ? "User updated successfully." : `User '${username}' created successfully.`, "success");
        loadUsers();
    } catch (err) {
        showStatus(err.message, "warning");
    }
}

// ── Delete ────────────────────────────────────────────────────────────────────

async function confirmDelete(userId, username) {
    if (!confirm(`Delete user '${username}'? This cannot be undone.`)) return;
    try {
        await fetchJson(`/api/admin/users/${userId}`, { method: "DELETE" });
        showStatus(`User '${username}' deleted.`, "success");
        loadUsers();
    } catch (err) {
        showStatus(err.message, "danger");
    }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function showStatus(message, type) {
    const bar = document.getElementById("statusBar");
    bar.className = `alert alert-${type}`;
    bar.textContent = message;
    bar.classList.remove("d-none");
    // Auto-hide success messages after 4 seconds
    if (type === "success") setTimeout(() => bar.classList.add("d-none"), 4000);
}

