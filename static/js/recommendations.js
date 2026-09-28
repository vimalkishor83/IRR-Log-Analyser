/* ── Recommendations page ──────────────────────────────────────────────── */

let lastResults   = [];
let feedbackState = {};

document.addEventListener("DOMContentLoaded", () => {
    const btn   = document.getElementById("searchBtn");
    const query = document.getElementById("queryText");
    const inc   = document.getElementById("incidentNumber");

    btn  .addEventListener("click",   doSearch);
    query.addEventListener("keydown", e => { if (e.key === "Enter") doSearch(); });
    inc  .addEventListener("keydown", e => { if (e.key === "Enter") doSearch(); });

    showIdle();

    // Pre-fill from dashboard log row click (?q=...&app=...)
    const params = new URLSearchParams(window.location.search);
    if (params.get("q")) {
        query.value = params.get("q");
        doSearch();
    }
});

/* ── Idle state ────────────────────────────────────────────────────────── */

function showIdle() {
    document.getElementById("idleState").style.display = "block";
    document.getElementById("resultsArea").innerHTML = "";
    hideLiveBanner();
}

function hideIdle() {
    document.getElementById("idleState").style.display = "none";
}


/* ── Live incident banner ──────────────────────────────────────────────── */

function showLiveBanner(inc) {
    const banner = document.getElementById("liveIncidentBanner");
    const state  = (inc.state || "").toLowerCase();
    const cls    = state.includes("progress") ? "state-in-progress"
                 : state === "new"             ? "state-new"
                 : state === "open"            ? "state-open"
                 :                              "state-other";

    const priorityLabel = inc.priority ? `P${inc.priority}` : "";
    const groupLabel    = inc.group    ? `<span class="meta-chip ms-1"><i class="bi bi-people"></i>${escHtml(inc.group)}</span>` : "";
    const priLabel      = priorityLabel ? `<span class="meta-chip ms-1"><i class="bi bi-flag"></i>${escHtml(priorityLabel)}</span>` : "";

    banner.innerHTML = `
      <div class="live-inc-icon"><i class="bi bi-lightning-charge-fill"></i></div>
      <div class="flex-fill">
        <div class="d-flex align-items-center gap-2 flex-wrap mb-1">
          <span class="fw-bold" style="font-size:.9rem">${escHtml(inc.number)}</span>
          <span class="live-inc-state ${cls}">
            <i class="bi bi-circle-fill" style="font-size:.45rem"></i>${escHtml(inc.state)}
          </span>
          ${priLabel}${groupLabel}
        </div>
        <div style="font-size:.83rem;color:#78350f">${escHtml(inc.description || "No description available")}</div>
        <div class="mt-1" style="font-size:.75rem;color:#92400e">
          <i class="bi bi-info-circle me-1"></i>This incident is not yet resolved — recommendations below are based on its description matched against past resolved incidents and KB articles.
        </div>
      </div>`;
    banner.style.display = "flex";
}

function hideLiveBanner() {
    const banner = document.getElementById("liveIncidentBanner");
    banner.style.display = "none";
    banner.innerHTML = "";
}

/* ── Search ────────────────────────────────────────────────────────────── */

async function doSearch() {
    const queryText       = document.getElementById("queryText").value.trim();
    const incidentNumber  = document.getElementById("incidentNumber").value.trim();
    if (!queryText && !incidentNumber) {
        showEmpty("Enter an error message or incident number to search.");
        return;
    }

    feedbackState = {};
    hideIdle();
    hideLiveBanner();
    showSkeleton();

    try {
        const data = await postJson("/api/recommend", { incident_number: incidentNumber, query_text: queryText });
        lastResults = data.items || [];

        if (data.live_incident) {
            showLiveBanner(data.live_incident);
        }

        if (!lastResults.length) {
            showEmpty("No recommendations found. Try a different error description or load more incidents via Admin → Sync Now.");
        } else {
            renderResults(lastResults);
        }
    } catch (err) {
        document.getElementById("resultsArea").innerHTML =
            `<div class="alert alert-danger"><i class="bi bi-exclamation-circle me-2"></i>${escHtml(err.message)}</div>`;
    }
}

/* ── Render ────────────────────────────────────────────────────────────── */

function renderResults(items) {
    const area = document.getElementById("resultsArea");
    area.innerHTML = "";

    // Summary bar
    const summaryBar = document.createElement("div");
    summaryBar.className = "d-flex align-items-center gap-3 mb-3";
    summaryBar.innerHTML = `
        <button class="btn btn-sm btn-outline-secondary me-2" onclick="showIdle()" style="font-size:.78rem">
          <i class="bi bi-arrow-left me-1"></i>New Search
        </button>
        <span class="text-muted small"><i class="bi bi-list-check me-1"></i><strong>${items.length}</strong> result${items.length !== 1 ? "s" : ""} found</span>
        <span class="text-muted small ms-2">·</span>
        <span class="text-muted small ms-2">Best match: <strong>${confLabel(items[0].confidence)}</strong> confidence</span>
        <div class="ms-auto d-flex gap-2">
          <select class="form-select form-select-sm" id="sortSelect" style="width:auto">
            <option value="confidence">Sort: Confidence</option>
            <option value="similarity">Sort: Similarity</option>
          </select>
        </div>`;
    area.appendChild(summaryBar);
    document.getElementById("sortSelect").addEventListener("change", e => {
        const key = e.target.value;
        const sorted = [...lastResults].sort((a, b) => b[key] - a[key]);
        renderCards(sorted, area);
    });

    renderCards(items, area);
}

function renderCards(items, area) {
    // Remove old cards but keep the summary bar (first child)
    while (area.children.length > 1) area.removeChild(area.lastChild);

    items.forEach((item, index) => {
        const isTop = index === 0;
        const card  = isTop ? buildTopCard(item, index) : buildCard(item, index);
        area.appendChild(card);
    });
}

/* ── Top-match hero card ───────────────────────────────────────────────── */

function buildTopCard(item, index) {
    const wrap = document.createElement("div");
    wrap.className = "top-match-card p-4 mb-3";
    wrap.id = `rec-${index}`;

    const { cls } = confStyle(item.confidence);

    wrap.innerHTML = `
      <div class="d-flex align-items-start gap-3 mb-3">
        <!-- Confidence ring -->
        <div class="conf-ring ${cls}" title="Confidence score">
          ${item.confidence}%
        </div>
        <div class="flex-fill">
          <div class="d-flex align-items-center gap-2 flex-wrap mb-1">
            <span class="top-match-badge"><i class="bi bi-trophy-fill me-1"></i>Top Match</span>
            <span class="badge ${srcClass(item.source)} rounded-pill">${escHtml(item.source)}</span>
            <span class="fw-semibold">${escHtml(item.incident_number)}</span>
          </div>
          <div class="d-flex flex-wrap gap-2">
            <span class="meta-chip"><i class="bi bi-bar-chart-fill text-primary"></i>Similarity ${item.similarity}%</span>
            <span class="meta-chip"><i class="bi bi-check-circle-fill text-success"></i>${item.success_count} resolved</span>
            <span class="meta-chip"><i class="bi bi-people text-secondary"></i>${escHtml(item.assignment_group)}</span>
            <span class="meta-chip text-muted">${escHtml(item.reason)}</span>
          </div>
        </div>
      </div>

      <!-- Similarity bar -->
      <div class="mb-3">
        <div class="d-flex justify-content-between small text-muted mb-1">
          <span>Similarity Match</span><span>${item.similarity}%</span>
        </div>
        <div class="sim-bar-wrap">
          <div class="sim-bar" style="width:${item.similarity}%;background:${simBarColor(item.similarity)}"></div>
        </div>
      </div>

      <!-- Root cause + Resolution -->
      ${item.root_cause ? `
      <div class="mb-3">
        <div class="small fw-semibold text-muted mb-1"><i class="bi bi-exclamation-triangle text-warning me-1"></i>Root Cause</div>
        <div class="root-cause-block">${escHtml(item.root_cause)}</div>
      </div>` : ""}

      <div class="mb-3">
        <div class="small fw-semibold text-muted mb-1"><i class="bi bi-tools text-primary me-1"></i>Resolution Steps</div>
        <div class="resolution-block">${escHtml(item.resolution)}</div>
      </div>

      <!-- Feedback -->
      ${buildFeedbackHtml(index, item)}
    `;

    bindFeedback(wrap, index, item);
    return wrap;
}

/* ── Standard card ─────────────────────────────────────────────────────── */

function buildCard(item, index) {
    const wrap = document.createElement("div");
    wrap.className = "rec-card p-3 mb-3";
    wrap.id = `rec-${index}`;

    const { cls: pillCls } = confStyle(item.confidence);

    wrap.innerHTML = `
      <div class="d-flex align-items-start gap-3">
        <span class="conf-pill ${pillCls} mt-1">${item.confidence}%</span>
        <div class="flex-fill">
          <div class="d-flex align-items-center gap-2 flex-wrap mb-1">
            <span class="badge ${srcClass(item.source)} rounded-pill">${escHtml(item.source)}</span>
            <span class="fw-semibold">${escHtml(item.incident_number)}</span>
            <span class="ms-auto">
              <button class="btn btn-sm btn-link p-0 text-muted toggle-detail" data-idx="${index}">
                <i class="bi bi-chevron-down"></i> Details
              </button>
            </span>
          </div>
          <div class="d-flex flex-wrap gap-2 mb-2">
            <span class="meta-chip"><i class="bi bi-bar-chart-fill text-primary"></i>${item.similarity}% sim</span>
            <span class="meta-chip"><i class="bi bi-check-circle-fill text-success"></i>${item.success_count} resolved</span>
            <span class="meta-chip"><i class="bi bi-people text-secondary"></i>${escHtml(item.assignment_group)}</span>
          </div>
          <!-- Similarity mini bar -->
          <div class="sim-bar-wrap mb-2">
            <div class="sim-bar" style="width:${item.similarity}%;background:${simBarColor(item.similarity)}"></div>
          </div>
        </div>
      </div>

      <!-- Collapsible detail -->
      <div class="detail-section" id="detail-${index}" style="display:none;margin-top:.75rem">
        ${item.root_cause ? `
        <div class="mb-2">
          <div class="small fw-semibold text-muted mb-1"><i class="bi bi-exclamation-triangle text-warning me-1"></i>Root Cause</div>
          <div class="root-cause-block">${escHtml(item.root_cause)}</div>
        </div>` : ""}
        <div class="mb-3">
          <div class="small fw-semibold text-muted mb-1"><i class="bi bi-tools text-primary me-1"></i>Resolution</div>
          <div class="resolution-block">${escHtml(item.resolution)}</div>
        </div>
        ${buildFeedbackHtml(index, item)}
      </div>
    `;

    // Toggle detail
    wrap.querySelector(".toggle-detail").addEventListener("click", function() {
        const detail  = document.getElementById(`detail-${index}`);
        const icon    = this.querySelector("i");
        const open    = detail.style.display !== "none";
        detail.style.display = open ? "none" : "block";
        icon.className = open ? "bi bi-chevron-down" : "bi bi-chevron-up";
        this.innerHTML = (open ? '<i class="bi bi-chevron-down"></i> Details' : '<i class="bi bi-chevron-up"></i> Hide');
    });

    bindFeedback(wrap, index, item);
    return wrap;
}

/* ── Feedback ──────────────────────────────────────────────────────────── */

function buildFeedbackHtml(index, item) {
    return `
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <span class="small text-muted me-1">Was this helpful?</span>
        <button class="btn btn-sm btn-outline-success feedback-btn" data-val="Helpful"         data-idx="${index}"><i class="bi bi-hand-thumbs-up me-1"></i>Helpful</button>
        <button class="btn btn-sm btn-outline-warning feedback-btn" data-val="Partially Helpful" data-idx="${index}">Partially Helpful</button>
        <button class="btn btn-sm btn-outline-danger  feedback-btn" data-val="Not Helpful"     data-idx="${index}"><i class="bi bi-hand-thumbs-down me-1"></i>Not Helpful</button>
        <span class="feedback-msg small ms-1 text-muted" id="fb-msg-${index}"></span>
      </div>`;
}

function bindFeedback(wrap, index, item) {
    wrap.querySelectorAll(".feedback-btn").forEach(btn => {
        btn.addEventListener("click", async () => {
            if (feedbackState[index]) return;  // already rated — ignore second click

            const val = btn.dataset.val;
            const msg = document.getElementById(`fb-msg-${index}`);

            // Disable all buttons immediately so user can't click again while saving
            wrap.querySelectorAll(".feedback-btn").forEach(b => b.disabled = true);

            try {
                await postJson("/api/feedback", {
                    value:           val,
                    incident_number: item.incident_number,
                    source:          item.source,
                });
                feedbackState[index] = val;

                // Highlight the chosen button, grey out others
                wrap.querySelectorAll(".feedback-btn").forEach(b => {
                    b.classList.remove("selected-helpful", "selected-partial", "selected-nothelpful");
                    b.style.opacity = b === btn ? "1" : "0.35";
                });
                const cls = val === "Helpful" ? "selected-helpful"
                          : val === "Partially Helpful" ? "selected-partial"
                          : "selected-nothelpful";
                btn.classList.add(cls);

                // Show thank-you message
                if (msg) {
                    msg.innerHTML = `<i class="bi bi-check-circle-fill text-success me-1"></i>Thanks for your feedback!`;
                    msg.className = "feedback-msg small ms-1 text-success";
                }
            } catch (_) {
                // Re-enable buttons if save failed
                wrap.querySelectorAll(".feedback-btn").forEach(b => b.disabled = false);
                if (msg) {
                    msg.textContent = "Could not save — please try again.";
                    msg.className   = "feedback-msg small ms-1 text-danger";
                }
            }
        });
    });
}

/* ── Helpers ───────────────────────────────────────────────────────────── */

function confStyle(pct) {
    if (pct >= 70) return { cls: "conf-high",  pill: "high" };
    if (pct >= 40) return { cls: "conf-mid",   pill: "mid"  };
    return              { cls: "conf-low",   pill: "low"  };
}

function confLabel(pct) {
    if (pct >= 70) return "High";
    if (pct >= 40) return "Medium";
    return "Low";
}

function simBarColor(pct) {
    if (pct >= 70) return "#16a34a";
    if (pct >= 40) return "#ca8a04";
    return "#dc2626";
}

function srcClass(source) {
    return (source || "").toLowerCase().includes("kb") ? "src-kb" : "src-incident";
}

function showSkeleton() {
    const area = document.getElementById("resultsArea");
    area.innerHTML = `
      <div class="top-match-card p-4 mb-3">
        <div class="d-flex gap-3 mb-3">
          <div class="skeleton" style="width:72px;height:72px;border-radius:50%"></div>
          <div class="flex-fill">
            <div class="skeleton mb-2" style="height:18px;width:40%"></div>
            <div class="skeleton" style="height:14px;width:70%"></div>
          </div>
        </div>
        <div class="skeleton mb-3" style="height:8px"></div>
        <div class="skeleton mb-2" style="height:60px"></div>
        <div class="skeleton" style="height:80px"></div>
      </div>
      ${[1,2].map(() => `
      <div class="rec-card p-3 mb-3">
        <div class="d-flex gap-3">
          <div class="skeleton" style="width:54px;height:28px;border-radius:20px"></div>
          <div class="flex-fill">
            <div class="skeleton mb-2" style="height:14px;width:50%"></div>
            <div class="skeleton" style="height:8px"></div>
          </div>
        </div>
      </div>`).join("")}`;
}

function showEmpty(msg) {
    document.getElementById("resultsArea").innerHTML =
        `<div class="text-center py-5 text-muted">
           <i class="bi bi-inbox fs-1 d-block mb-2"></i>
           <p>${escHtml(msg)}</p>
         </div>`;
}

