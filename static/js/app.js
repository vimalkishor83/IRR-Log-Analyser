const charts = {};
let currentPage = 1;
let totalLogCount = 0;
const PER_PAGE = 100;

document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("startAnalysis").addEventListener("click", analyzeLogs);
    document.getElementById("clearAnalysis").addEventListener("click", clearAnalysis);
    document.getElementById("loadSample").addEventListener("click", loadSampleData);
    document.getElementById("severityFilter").addEventListener("change", () => { currentPage = 1; loadLogs(); });
    document.getElementById("logSearch").addEventListener("input",  () => { currentPage = 1; loadLogs(); });
    document.getElementById("exportCsv").addEventListener("click", exportCsv);
    document.getElementById("prevPage").addEventListener("click", () => { if (currentPage > 1) { currentPage--; loadLogs(); } });
    document.getElementById("nextPage").addEventListener("click", () => {
        if (currentPage * PER_PAGE < totalLogCount) { currentPage++; loadLogs(); }
    });
    document.getElementById("filePicker").addEventListener("change", updateSelectedText);
    document.getElementById("folderPicker").addEventListener("change", updateSelectedText);
    loadDashboard();
    loadLogs();
    loadTopIssues();
});

// ── Analysis ─────────────────────────────────────────────────────────────────

async function analyzeLogs() {
    const selected = getSelectedFiles();
    if (!selected.length) {
        showMessage("Please select log files or a folder before starting analysis.");
        return;
    }
    const formData = new FormData();
    selected.forEach(file => formData.append("files", file, file.webkitRelativePath || file.name));

    setAnalysisLoading(true);
    const data = await fetchJson("/api/analyze", { method: "POST", body: formData }).finally(() => setAnalysisLoading(false));
    const msg  = (data.messages || []).join("<br>") || `Analysis completed. ${data.total_lines} log rows parsed.`;
    showMessage(msg);
    if (data.probable_root_cause && data.probable_root_cause !== "No errors found.") {
        showRootCause(data.probable_root_cause);
    }
    currentPage = 1;
    await Promise.all([loadDashboard(), loadLogs(), loadTopIssues()]);
}

async function clearAnalysis() {
    const data = await fetchJson("/api/clear-analysis", { method: "POST" });
    document.getElementById("filePicker").value = "";
    document.getElementById("folderPicker").value = "";
    document.getElementById("filePickerText").textContent = "Supported: .log, .txt, .out, .csv, .gz";
    document.getElementById("folderPickerText").textContent = "Logs inside a single folder";
    document.getElementById("rootCauseBanner").style.display = "none";
    showMessage(data.message);
    currentPage = 1;
    await Promise.all([loadDashboard(), loadLogs(), loadTopIssues()]);
}

async function loadSampleData() {
    setAnalysisLoading(true);
    const data = await fetchJson("/api/load-sample-data", { method: "POST" }).finally(() => setAnalysisLoading(false));
    showMessage(data.message);
    if (data.probable_root_cause && data.probable_root_cause !== "No errors found.") {
        showRootCause(data.probable_root_cause);
    }
    currentPage = 1;
    await Promise.all([loadDashboard(), loadLogs(), loadTopIssues()]);
}

// ── Loading state ─────────────────────────────────────────────────────────────

function setAnalysisLoading(on) {
    const btn = document.getElementById("startAnalysis");
    const lbl = document.getElementById("loadSample");
    if (on) {
        btn.disabled = true;
        btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>Analysing…`;
        lbl.disabled = true;
    } else {
        btn.disabled = false;
        btn.innerHTML = `<i class="bi bi-play-fill me-1"></i>Analyse`;
        lbl.disabled = false;
    }
}

// ── Root cause banner ─────────────────────────────────────────────────────────

function showRootCause(text) {
    document.getElementById("rootCauseText").textContent = text;
    document.getElementById("rootCauseBanner").style.display = "block";
}

// ── Dashboard data ────────────────────────────────────────────────────────────

async function loadDashboard() {
    const [data, timeline] = await Promise.all([
        fetchJson("/api/dashboard"),
        fetchJson("/api/logs/timeline").catch(() => null),
    ]);
    const k = data.kpis;
    setText("totalLogs",          k.total_logs);
    setText("totalErrors",        k.total_errors);
    setText("uniqueErrors",       k.unique_errors);
    setText("criticalErrors",     k.critical_errors);
    setText("warningCount",       k.warning_count);
    setText("topApplication",     k.top_application);
    setText("topServer",          k.top_server);
    setText("recommendationCount", k.knowledge_base_size);
    renderChart("severityChart", "doughnut", data.charts.severity);
    renderChart("appChart",      "bar",      data.charts.applications);
    if (timeline) renderTimelineChart(timeline);
}

// ── Top Issues ────────────────────────────────────────────────────────────────

async function loadTopIssues() {
    const [errRows, critRows] = await Promise.all([
        fetchJson("/api/logs?severity=ERROR&search=").catch(() => []),
        fetchJson("/api/logs?severity=CRITICAL&search=").catch(() => []),
    ]);
    const allRows = [...errRows, ...critRows];

    const counts = {};
    allRows.forEach(row => {
        const key = row.exception || row.error_code || (row.message || "").slice(0, 60);
        if (!key) return;
        if (!counts[key]) counts[key] = { key, count: 0, severity: row.severity, app: row.application, example: row.message };
        counts[key].count++;
    });

    const sorted = Object.values(counts).sort((a, b) => b.count - a.count).slice(0, 5);
    const panel  = document.getElementById("topIssues");
    const hint   = document.getElementById("topIssuesHint");
    const badge  = document.getElementById("topIssuesCount");

    if (!sorted.length) {
        panel.innerHTML = `<p class="text-muted small mb-0">No errors found in current logs.</p>`;
        hint.style.display = "none";
        badge.textContent  = "";
        return;
    }

    badge.textContent  = `${sorted.length} pattern${sorted.length !== 1 ? "s" : ""}`;
    hint.style.display = "block";

    const sevColour = { CRITICAL: "#7c2d12", ERROR: "#dc2626", WARN: "#d97706", INFO: "#2563eb" };

    panel.innerHTML = sorted.map(issue => {
        const colour = sevColour[issue.severity] || "#6b7280";
        const q      = encodeURIComponent([issue.key, issue.example].filter(Boolean).join(" "));
        return `
          <div class="d-flex align-items-start gap-2 mb-2 p-2 rounded top-issue-row"
               style="cursor:pointer;border:1px solid #e2e8f0;background:#f8fafc"
               onclick="window.location='/recommendations?q=${q}'">
            <span class="badge mt-1 flex-shrink-0"
                  style="background:${colour};font-size:.65rem;min-width:52px;text-align:center">
              ${escapeHtml(issue.severity)}
            </span>
            <div class="flex-fill overflow-hidden">
              <div class="fw-semibold small text-truncate" title="${escapeHtml(issue.key)}">${escapeHtml(issue.key)}</div>
              <div class="text-muted" style="font-size:.72rem">
                ${issue.count}× occurrence${issue.count !== 1 ? "s" : ""}
                ${issue.app ? ` &bull; ${escapeHtml(issue.app)}` : ""}
              </div>
            </div>
            <i class="bi bi-arrow-right text-muted mt-1 flex-shrink-0" style="font-size:.8rem"></i>
          </div>`;
    }).join("");
}

// ── Log viewer ────────────────────────────────────────────────────────────────

async function loadLogs() {
    const params = new URLSearchParams({
        severity: document.getElementById("severityFilter").value,
        search:   document.getElementById("logSearch").value,
        page:     currentPage,
    });

    const [rows, countData] = await Promise.all([
        fetchJson(`/api/logs?${params}`),
        fetchJson(`/api/logs/count?${params}`).catch(() => ({ count: 0 })),
    ]);

    totalLogCount = countData.count;
    const body = document.getElementById("logRows");
    body.innerHTML = "";
    rows.forEach(row => {
        const tr = document.createElement("tr");
        tr.style.cursor = "pointer";
        tr.title = "Click to find resolution recommendations";
        tr.innerHTML = `
            <td>${escapeHtml(row.timestamp)}</td>
            <td><span class="badge badge-severity sev-${escapeHtml(row.severity)}">${escapeHtml(row.severity)}</span></td>
            <td>${escapeHtml(row.application)}</td>
            <td>${escapeHtml(row.server)}</td>
            <td>${escapeHtml(row.error_code)}</td>
            <td>${escapeHtml(row.exception)}</td>
            <td>
                ${escapeHtml(row.message)}${row.stack_trace ? `<pre class="stack mt-2">${escapeHtml(row.stack_trace)}</pre>` : ""}
                <span class="badge bg-primary ms-2 float-end" style="font-size:.65rem;opacity:.7">
                    <i class="bi bi-search"></i> Find Fix
                </span>
            </td>`;
        tr.addEventListener("click", () => {
            const q = [row.exception, row.error_code, row.message].filter(Boolean).join(" ").trim();
            window.location.href = `/recommendations?q=${encodeURIComponent(q)}&app=${encodeURIComponent(row.application || "")}`;
        });
        body.appendChild(tr);
    });

    // Update pagination
    updatePagination();
}

function updatePagination() {
    const bar      = document.getElementById("paginationBar");
    const info     = document.getElementById("pageInfo");
    const prevBtn  = document.getElementById("prevPage");
    const nextBtn  = document.getElementById("nextPage");

    if (totalLogCount === 0) {
        bar.style.display = "none";
        return;
    }

    bar.style.cssText = "display:flex!important";
    const totalPages  = Math.ceil(totalLogCount / PER_PAGE);
    const start       = (currentPage - 1) * PER_PAGE + 1;
    const end         = Math.min(currentPage * PER_PAGE, totalLogCount);
    info.textContent  = `Showing ${start}–${end} of ${totalLogCount} rows`;
    prevBtn.disabled  = currentPage <= 1;
    nextBtn.disabled  = currentPage >= totalPages;
}

// ── CSV export ────────────────────────────────────────────────────────────────

function exportCsv() {
    const params = new URLSearchParams({
        severity: document.getElementById("severityFilter").value,
        search:   document.getElementById("logSearch").value,
    });
    window.location.href = `/api/logs/export?${params}`;
}

// ── Charts ────────────────────────────────────────────────────────────────────

function renderChart(id, type, values) {
    if (charts[id]) charts[id].destroy();
    const COLOURS = ["#2563eb", "#dc2626", "#f59e0b", "#059669", "#7c3aed", "#64748b", "#0891b2", "#d97706"];
    charts[id] = new Chart(document.getElementById(id), {
        type,
        data: {
            labels:   Object.keys(values),
            datasets: [{
                data:            Object.values(values),
                backgroundColor: COLOURS,
                borderRadius:    type === "bar" ? 6 : 0,
                borderWidth:     type === "doughnut" ? 2 : 0,
                borderColor:     "#fff",
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: "bottom", labels: { boxWidth: 10, padding: 10, font: { size: 11 } } }
            },
            scales: type === "doughnut" ? {} : {
                y: { beginAtZero: true, ticks: { font: { size: 11 } }, grid: { color: "#f1f5f9" } },
                x: { ticks: { font: { size: 11 } }, grid: { display: false } }
            }
        }
    });
}

function renderTimelineChart(data) {
    if (charts["timelineChart"]) charts["timelineChart"].destroy();
    if (!data.labels || !data.labels.length) return;

    // Shorten labels to HH:MM
    const labels = data.labels.map(l => l.slice(11, 16) || l.slice(0, 10));

    charts["timelineChart"] = new Chart(document.getElementById("timelineChart"), {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label:       "Errors",
                    data:        data.errors,
                    borderColor: "#dc2626",
                    backgroundColor: "rgba(220,38,38,.12)",
                    fill:        true,
                    tension:     0.4,
                    pointRadius: 3,
                    borderWidth: 2,
                },
                {
                    label:       "Warnings",
                    data:        data.warnings,
                    borderColor: "#f59e0b",
                    backgroundColor: "rgba(245,158,11,.08)",
                    fill:        true,
                    tension:     0.4,
                    pointRadius: 3,
                    borderWidth: 2,
                },
                {
                    label:       "Critical",
                    data:        data.critical,
                    borderColor: "#7c2d12",
                    backgroundColor: "rgba(124,45,18,.1)",
                    fill:        true,
                    tension:     0.4,
                    pointRadius: 3,
                    borderWidth: 2,
                },
            ]
        },
        options: {
            responsive:          true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: "bottom", labels: { boxWidth: 10, padding: 8, font: { size: 10 } } }
            },
            scales: {
                y: { beginAtZero: true, ticks: { font: { size: 10 }, stepSize: 1 }, grid: { color: "#f1f5f9" } },
                x: { ticks: { font: { size: 10 }, maxTicksLimit: 8 }, grid: { display: false } }
            }
        }
    });
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function getSelectedFiles() {
    return [
        ...Array.from(document.getElementById("filePicker").files || []),
        ...Array.from(document.getElementById("folderPicker").files || [])
    ];
}

function updateSelectedText() {
    const fileCount   = document.getElementById("filePicker").files.length;
    const folderFiles = Array.from(document.getElementById("folderPicker").files || []);
    document.getElementById("filePickerText").textContent = fileCount ? `${fileCount} file(s) selected.` : "Supported: .log, .txt, .out, .csv, .gz";
    if (folderFiles.length) {
        const folderName = (folderFiles[0].webkitRelativePath || "Selected folder").split("/")[0];
        document.getElementById("folderPickerText").textContent = `${folderName}: ${folderFiles.length} file(s) selected.`;
    } else {
        document.getElementById("folderPickerText").textContent = "Logs inside a single folder";
    }
}

function showMessage(text) { document.getElementById("messages").innerHTML = text; }
function setText(id, value) { document.getElementById(id).textContent = value ?? ""; }

