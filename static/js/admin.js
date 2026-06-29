// Buttons that should be disabled while an action is running
const ACTION_BUTTONS = ["btnSync", "btnRetrain", "btnImport"];

document.addEventListener("DOMContentLoaded", () => {
    loadStatus();
});

// ── Action dispatcher ─────────────────────────────────────────────────────────

async function runAction(action) {
    if (action === "sync")    return await doSync();
    if (action === "retrain") return await doRetrain();
    if (action === "import")  return await doImport();
}

// ── Individual actions ────────────────────────────────────────────────────────

async function doSync() {
    setLoading(true, "btnSync", "Syncing…");
    try {
        const data = await postJson("/api/admin/sync-now");
        showStatus(data.message, "success");
        loadStatus();
    } catch (err) {
        showStatus(err.message, "danger");
    } finally {
        setLoading(false, "btnSync", '<i class="bi bi-cloud-download me-1"></i> Sync Now');
    }
}

async function doRetrain() {
    setLoading(true, "btnRetrain", "Retraining…");
    try {
        const data = await postJson("/api/admin/retrain");
        showStatus(data.message, "success");
        loadStatus();
    } catch (err) {
        showStatus(err.message, "danger");
    } finally {
        setLoading(false, "btnRetrain", '<i class="bi bi-arrow-clockwise me-1"></i> Retrain');
    }
}

async function doImport() {
    const fileInput = document.getElementById("csvFile");
    if (!fileInput.files.length) {
        showStatus("Please choose a CSV file first.", "warning");
        return;
    }

    setLoading(true, "btnImport", "Importing…");
    try {
        const formData = new FormData();
        formData.append("file", fileInput.files[0]);

        const response = await fetch("/api/admin/import-csv", { method: "POST", body: formData });
        const data     = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Import failed.");
        }

        showStatus(data.message, "success");
        fileInput.value = "";
        loadStatus();
    } catch (err) {
        showStatus(err.message, "danger");
    } finally {
        setLoading(false, "btnImport", '<i class="bi bi-file-earmark-spreadsheet me-1"></i> Choose CSV &amp; Import');
    }
}

// ── Index status panel ────────────────────────────────────────────────────────

async function loadStatus() {
    try {
        const data = await getJson("/api/admin/status");

        const indexBadge = data.tfidf_trained
            ? `<span class="badge text-bg-success">Trained &mdash; ${data.tfidf_documents} documents</span>`
            : `<span class="badge text-bg-warning text-dark">Not trained &mdash; click Retrain</span>`;

        const snowBadge = data.snow_configured
            ? `<span class="badge text-bg-success">Configured</span> <span class="small text-secondary">${escapeHtml(data.snow_url)}</span>`
            : `<span class="badge text-bg-danger">Not configured</span>`;

        const syncRow = (label, sync) => {
            if (!sync) return `<div class="col-auto"><span class="text-secondary small">${label}</span><br><span class="text-secondary small">Never synced</span></div>`;
            const badge = sync.status === "Success"
                ? `<span class="badge text-bg-success">Success</span>`
                : `<span class="badge text-bg-danger">Failed</span>`;
            return `
                <div class="col-auto">
                    <span class="text-secondary small">${label}</span><br>
                    ${badge}
                    <span class="small text-secondary ms-1">${escapeHtml(sync.time || "")}</span><br>
                    <span class="small text-secondary">${escapeHtml(sync.message || "")}</span>
                </div>`;
        };

        document.getElementById("indexStatus").innerHTML = `
            <div class="row g-4 mt-0">
                <div class="col-auto">
                    <span class="text-secondary small">TF-IDF Index</span><br>
                    ${indexBadge}
                </div>
                <div class="col-auto">
                    <span class="text-secondary small">Incidents in DB</span><br>
                    <strong>${data.incident_count}</strong>
                </div>
                <div class="col-auto">
                    <span class="text-secondary small">Active KB Articles</span><br>
                    <strong>${data.kb_count}</strong>
                </div>
                <div class="col-auto">
                    <span class="text-secondary small">Knowledge Entries</span><br>
                    <strong>${data.knowledge_count}</strong>
                </div>
            </div>
            <hr class="my-3">
            <div class="row g-4">
                <div class="col-12">
                    <span class="text-secondary small">ServiceNow Connection</span><br>
                    ${snowBadge}
                </div>
                ${syncRow("Last Incident Sync", data.last_sync_incidents)}
                ${syncRow("Last KB Sync", data.last_sync_kb)}
            </div>`;
    } catch (err) {
        document.getElementById("indexStatus").textContent = "Could not load status.";
    }
}

// ── CSV template download ─────────────────────────────────────────────────────

function downloadIncidentTemplate() {
    const headers = [
        "incident_number",
        "application",
        "server",
        "environment",
        "error_description",
        "exception_message",
        "root_cause",
        "resolution",
        "assignment_group",
        "status",
    ];
    const examples = [
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
    ];

    const csvLines = [headers, ...examples].map(row =>
        row.map(cell => `"${String(cell).replaceAll('"', '""')}"`).join(",")
    );
    const csv  = csvLines.join("\r\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url  = URL.createObjectURL(blob);
    const a    = Object.assign(document.createElement("a"), {
        href: url, download: "incident_import_template.csv"
    });
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

function escapeHtml(value) {
    return String(value ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;");
}

// ── UI helpers ────────────────────────────────────────────────────────────────

function showStatus(message, type) {
    // type: "success" | "danger" | "warning" | "info"
    const bar = document.getElementById("statusBar");
    bar.className = `alert alert-${type}`;
    bar.textContent = message;
    bar.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function setLoading(loading, activeButtonId, originalLabel) {
    ACTION_BUTTONS.forEach(id => {
        document.getElementById(id).disabled = loading;
    });

    const btn = document.getElementById(activeButtonId);
    if (loading) {
        btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>${originalLabel}`;
    } else {
        btn.innerHTML = originalLabel;
    }
}

async function postJson(url, body = null) {
    const options = { method: "POST" };
    if (body) {
        options.headers = { "Content-Type": "application/json" };
        options.body    = JSON.stringify(body);
    }
    const response = await fetch(url, options);
    const data     = await response.json();
    if (!response.ok) throw new Error(data.error || "Request failed.");
    return data;
}

async function getJson(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error("Request failed.");
    return response.json();
}
