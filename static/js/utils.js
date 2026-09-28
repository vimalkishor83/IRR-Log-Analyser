/* utils.js — shared helpers loaded before every other page script */

/**
 * Prefix a root-relative API path ("/api/...") with the app's mount prefix
 * (window.SCRIPT_ROOT, set by nav.html from Flask's request.script_root) so
 * requests still resolve correctly when the app is served behind a reverse
 * proxy path prefix, e.g. /research/apps/irr-log-analyser/.
 */
function apiUrl(path) {
    if (!path.startsWith("/")) return path;
    return (window.SCRIPT_ROOT || "") + path;
}

/**
 * GET/POST JSON wrapper.
 * On error, throws with the server's error message.
 * If a showMessage function exists on the page, surfaces the error there too.
 */
async function fetchJson(url, options = {}) {
    const response = await fetch(apiUrl(url), options);
    if (!response.ok) {
        let message = await response.text();
        try { message = JSON.parse(message).error || message; } catch (_) {}
        if (typeof showMessage === "function") showMessage(message);
        throw new Error(message);
    }
    return response.json();
}

/**
 * POST a JSON body and return the parsed response.
 * body can be null for POST-with-no-body (e.g. trigger actions).
 */
async function postJson(url, body = null) {
    const options = { method: "POST" };
    if (body !== null) {
        options.headers = { "Content-Type": "application/json" };
        options.body    = JSON.stringify(body);
    }
    const response = await fetch(apiUrl(url), options);
    const data     = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Request failed.");
    return data;
}

/** Escape a value for safe insertion into HTML. */
function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&",  "&amp;")
        .replaceAll("<",  "&lt;")
        .replaceAll(">",  "&gt;")
        .replaceAll('"',  "&quot;")
        .replaceAll("'",  "&#039;");
}

// recommendations.js used the alias escHtml — keep it pointing to the same function
const escHtml = escapeHtml;
