# IRR + Log Analyser — Code Guide

A plain-English reference for every module in the project.
Use this to understand what each file does, what it talks to, and where to look when something needs changing.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Folder Structure](#2-folder-structure)
3. [How a Request Flows Through the App](#3-how-a-request-flows-through-the-app)
4. [Entry Point — `app.py`](#4-entry-point--apppy)
5. [Configuration — `config.py`](#5-configuration--configpy)
6. [Core Layer (`core/`)](#6-core-layer-core)
   - [database.py](#61-databasepy)
   - [models.py](#62-modelspy)
   - [auth.py](#63-authpy)
   - [logger.py](#64-loggerpy)
7. [Routes Layer (`routes/`)](#7-routes-layer-routes)
   - [auth_routes.py](#71-auth_routespy)
   - [dashboard_routes.py](#72-dashboard_routespy)
   - [recommendation_routes.py](#73-recommendation_routespy)
   - [knowledge_routes.py](#74-knowledge_routespy)
   - [admin_routes.py](#75-admin_routespy)
8. [Services Layer (`services/`)](#8-services-layer-services)
   - [log_analyzer.py](#81-log_analyzerpy)
   - [recommendation.py](#82-recommendationpy)
   - [tfidf_engine.py](#83-tfidf_enginepy)
   - [knowledge_service.py](#84-knowledge_servicepy)
   - [snow_client.py](#85-snow_clientpy)
   - [sync_service.py](#86-sync_servicepy)
9. [Frontend — Templates (`templates/`)](#9-frontend--templates-templates)
10. [Frontend — JavaScript (`static/js/`)](#10-frontend--javascript-staticjs)
11. [Frontend — CSS (`static/css/styles.css`)](#11-frontend--css-staticcssstylescss)
12. [Database Tables at a Glance](#12-database-tables-at-a-glance)
13. [Environment Variables Reference](#13-environment-variables-reference)
14. [Where to Make Common Changes](#14-where-to-make-common-changes)

---

## 1. Project Overview

IRR (Intelligent Resolution Recommender) is a Flask web application for support engineers. It does two things:

**Log Analysis** — Upload one or more log files. The app parses every line, classifies severity, extracts error codes and exceptions, detects the probable root cause, and shows the results in a searchable table with charts.

**Resolution Recommendations** — Type an error message or an incident number. The app searches a local database of historical incidents, KB articles, and manually entered knowledge entries, then ranks the top 5 matches by confidence score.

Data comes from two sources:
- **ServiceNow** — incidents and KB articles are synced automatically every N hours.
- **Manual entry** — support engineers add knowledge entries directly through the Knowledge page.

---

## 2. Folder Structure

```
IRR + Log Analyser/
│
├── app.py                  ← Application entry point
├── config.py               ← All configuration (reads from .env)
│
├── core/                   ← Shared building blocks
│   ├── auth.py             ← Login, session, route protection decorators
│   ├── database.py         ← SQLAlchemy setup
│   ├── logger.py           ← Log file rotation setup
│   └── models.py           ← All database table definitions
│
├── routes/                 ← URL handlers (one file per feature area)
│   ├── auth_routes.py      ← /login  /logout  /access-denied  /help
│   ├── dashboard_routes.py ← /  and all /api/logs/* endpoints
│   ├── recommendation_routes.py ← /recommendations  /api/recommend  /api/feedback
│   ├── knowledge_routes.py ← /knowledge  and all /api/knowledge/* endpoints
│   └── admin_routes.py     ← /admin  and all /api/admin/* endpoints
│
├── services/               ← Business logic (no HTTP awareness)
│   ├── log_analyzer.py     ← Parses uploaded log files
│   ├── recommendation.py   ← Finds best-matching resolutions
│   ├── tfidf_engine.py     ← In-memory TF-IDF search index
│   ├── knowledge_service.py← CRUD helpers for knowledge entries
│   ├── snow_client.py      ← HTTP client for ServiceNow REST API
│   └── sync_service.py     ← Validates and saves ServiceNow data
│
├── templates/              ← Jinja2 HTML pages (one per page)
├── static/
│   ├── css/styles.css      ← All custom styling
│   ├── js/                 ← One JS file per page
│   └── lib/                ← Local copies of Bootstrap, Chart.js, Bootstrap Icons
│
└── data/                   ← SQLite database + sample CSV files
```

---

## 3. How a Request Flows Through the App

```
Browser
  │
  │  HTTP request (e.g. GET /recommendations)
  ▼
Flask router
  │
  │  Matches the URL to a Blueprint route function
  ▼
Route function (routes/*.py)
  │
  ├── Checks auth (login_required / module_required decorators from core/auth.py)
  ├── Reads from DB directly via SQLAlchemy models  (core/models.py)
  └── Calls a service for heavy logic              (services/*.py)
        │
        ├── log_analyzer.py  — parses files
        ├── recommendation.py + tfidf_engine.py — finds matches
        ├── sync_service.py + snow_client.py   — fetches from ServiceNow
        └── knowledge_service.py               — CRUD on knowledge entries
  │
  ▼
Route returns either:
  • render_template("page.html")   → full HTML page
  • jsonify({...})                 → JSON for the JS frontend to use
  │
  ▼
Browser renders the page / JS updates the DOM
```

---

## 4. Entry Point — `app.py`

**What it does:** Bootstraps the entire application in the correct order and starts background jobs.

**Startup order:**
1. Read configuration from `config.py`
2. Set up rotating log files (`core/logger.py`)
3. Create Flask app and connect the database (`core/database.py`)
4. Register all five route Blueprints
5. Create default admin account on first run (`core/auth.py`)
6. Start the background scheduler that syncs ServiceNow data every N hours
7. If run directly (`python app.py`), start the dev server on `127.0.0.1:5000`

**Key function:** `create_app()` — returns a configured Flask app. Keep this function clean; business logic belongs in `services/`.

**Background scheduler:** Uses APScheduler. Two jobs run on a timer:
- `SyncService.sync_incidents()` — pulls resolved incidents from ServiceNow
- `SyncService.sync_kb_articles()` — pulls KB articles from ServiceNow

Both run inside a Flask app context (`_run_in_context`) so they can use the database.

---

## 5. Configuration — `config.py`

**What it does:** One `Config` class that holds every configurable value. Values are read from environment variables (or a `.env` file), with safe defaults for local development.

| Setting | Default | What it controls |
|---|---|---|
| `SECRET_KEY` | `dev-secret-key` | Flask session encryption — change in production |
| `DATABASE_URL` | SQLite in `data/` | Switch to Oracle or SQL Server by changing this |
| `SERVICENOW_URL` | `http://localhost:8080` | Your ServiceNow instance URL |
| `SERVICENOW_USERNAME` | `admin` | ServiceNow API username |
| `SERVICENOW_PASSWORD` | `admin123` | ServiceNow API password |
| `SERVICENOW_TIMEOUT` | `15` seconds | HTTP timeout for ServiceNow calls |
| `SYNC_INTERVAL_HOURS` | `24` | How often background sync runs |
| `SERVICENOW_ASSIGNMENT_GROUPS` | _(empty = all)_ | Comma-separated group names to filter synced incidents |
| `CONFIDENCE_THRESHOLD` | `60` | Minimum score to show a recommendation |
| `LOG_MAX_BYTES` | `5 MB` | Max log file size before rotation |
| `LOG_BACKUP_COUNT` | `10` | How many old log files to keep |
| `LOG_ROTATE_WHEN` | _(empty)_ | Set to `midnight` or `h` for time-based rotation |

**To add a new setting:** Add it to `Config`, read it with `os.getenv("NAME", "default")`, then access it anywhere via `current_app.config["NAME"]`.

---

## 6. Core Layer (`core/`)

These are shared utilities used by routes and services. They have no knowledge of HTTP requests.

### 6.1 `database.py`

**What it does:** Creates the single shared SQLAlchemy `db` object and the `init_db()` function that connects it to the Flask app.

**Key call:** `db.create_all()` inside `init_db()` — creates any missing tables on startup. New model classes are picked up automatically; no migration scripts needed for simple additions.

**Used by:** Every other file that reads or writes to the database imports `db` from here.

---

### 6.2 `models.py`

**What it does:** Defines all 11 database tables as Python classes. SQLAlchemy maps each class to a SQL table automatically.

| Class | Table | Purpose |
|---|---|---|
| `User` | `users` | Login accounts — username, hashed password, role, allowed modules |
| `Incident` | `incidents` | Resolved incidents from ServiceNow — the main search corpus |
| `KBArticle` | `kb_articles` | KB articles from ServiceNow |
| `KnowledgeEntry` | `knowledge_repository` | Manually entered patterns and fixes |
| `ErrorSignature` | `error_signatures` | Unique error fingerprints from uploaded logs |
| `ParsedLog` | `parsed_logs` | Individual log lines from the most recent upload (replaced each time) |
| `RecommendationHistory` | `recommendation_history` | Which recommendation was shown first per search |
| `Feedback` | `feedback` | User ratings (Helpful / Not Helpful) |
| `SyncHistory` | `sync_history` | Result of each ServiceNow sync run |
| `AuditLog` | `audit_logs` | Security log — who did what and when |
| `SearchHistory` | `search_history` | What users searched for (analytics) |

**Important:** `ParsedLog` is **fully replaced** on every new log upload. It only holds the most recently analysed batch.

---

### 6.3 `auth.py`

**What it does:** Handles login, logout, and access control via Python decorators.

**Roles:**
- `Admin` — full access to all pages, no restrictions
- `Analyst` — can only access pages listed in their `modules` field (stored in the `User` record)

**The four decorators** — place these above route functions to protect them:

| Decorator | Who can pass |
|---|---|
| `@login_required` | Any logged-in user |
| `@role_required("Admin")` | Admin role only |
| `@admin_required` | Shorthand for `role_required("Admin")` |
| `@module_required("dashboard")` | Admins always pass; Analysts only if they have that module |

**Session contents** — after login, the session holds:
- `session["username"]` — the logged-in username
- `session["role"]` — `"Admin"` or `"Analyst"`
- `session["modules"]` — comma-separated list of allowed module keys

**Default admin account** — created once at startup by `create_default_admin()`.
Username: `admin` | Password: `admin123` — **change this immediately in production**.

**Module keys** (used in `module_required` and stored in `User.modules`):

| Key | Page |
|---|---|
| `dashboard` | Log Analyzer |
| `recommendations` | Recommendations |
| `knowledge` | Knowledge Repository |
| `admin` | Admin Panel |

---

### 6.4 `logger.py`

**What it does:** Sets up a rotating log file for the application's own runtime logs (not the uploaded log files). Controlled by environment variables.

Two rotation modes:
- **Size-based** (default) — creates a new file after `LOG_MAX_BYTES` (default 5 MB)
- **Time-based** — creates a new file at `midnight`, `h` (hourly), etc. — set `LOG_ROTATE_WHEN` to enable

Log files are written to the `logs/` folder. Each route file and service creates its own named logger (`logging.getLogger(__name__)`) so log lines are prefixed with the module name.

---

## 7. Routes Layer (`routes/`)

Each file is a Flask **Blueprint** — a group of related URL handlers. The Blueprint is registered in `app.py` and has no prefix, so routes are exactly as written.

Every route that changes data writes an `AuditLog` entry via the local `_audit()` helper.

---

### 7.1 `auth_routes.py`

**Blueprint name:** `auth`

| URL | Method | What it does |
|---|---|---|
| `/login` | GET | Show login form |
| `/login` | POST | Check credentials, start session, redirect to `/` |
| `/logout` | GET | Clear session, redirect to login |
| `/access-denied` | GET | Show access denied page |
| `/help` | GET | Show help/FAQ page |

**Login flow:** `login_user()` from `core/auth.py` checks the password hash. On success the session is populated and the user is redirected to `/`. On failure the login form is shown again with an error message.

---

### 7.2 `dashboard_routes.py`

**Blueprint name:** `dashboard`

This is the most complex route file — it handles the main page and all log analysis API calls.

| URL | Method | What it does |
|---|---|---|
| `/` | GET | Render the dashboard page |
| `/api/dashboard` | GET | Return KPI counts for the dashboard cards |
| `/api/logs` | GET | Return paginated log rows (100 per page, `?page=N`) |
| `/api/logs/count` | GET | Return total number of log rows (for pagination) |
| `/api/logs/timeline` | GET | Return error counts grouped by hour (for the timeline chart) |
| `/api/logs/export` | GET | Download all current logs as a CSV file |
| `/api/analyze` | POST | Accept uploaded files, run `LogAnalyzer`, return summary |
| `/api/clear-analysis` | POST | Delete all parsed logs and error signatures |
| `/api/load-sample-data` | POST | Load the bundled sample CSV files and retrain the TF-IDF index |

**Pagination:** `GET /api/logs` accepts a `?page=` query parameter. It returns 100 rows per page using SQL `OFFSET`. The JS fetches the count from `/api/logs/count` in parallel to build the Prev/Next controls.

**Sample data:** `load_sample_data()` reads `data/sample_incidents.csv` and `data/sample_kb_articles.csv` using `_load_incidents_csv()` and `_load_kb_csv()`, saves them to the database, then calls `tfidf_engine.retrain()` so the recommendation engine is immediately usable.

---

### 7.3 `recommendation_routes.py`

**Blueprint name:** `recommendations`

| URL | Method | What it does |
|---|---|---|
| `/recommendations` | GET | Render the recommendations page |
| `/api/recommend` | POST | Search for matching resolutions, return ranked list |
| `/api/feedback` | POST | Save a Helpful / Not Helpful rating |

**Search flow (`/api/recommend`):**
1. Receive `query_text` and/or `incident_number` from the browser.
2. If `incident_number` is given and **not** in the local DB, fetch it live from ServiceNow (`ServiceNowClient`) and use its description as the search text.
3. Call `RecommendationEngine.search()` — returns up to 5 ranked results.
4. Save the top result to `RecommendationHistory`.
5. Return results + live incident banner data as JSON.

---

### 7.4 `knowledge_routes.py`

**Blueprint name:** `knowledge`

| URL | Method | What it does |
|---|---|---|
| `/knowledge` | GET | Render the knowledge management page |
| `/api/knowledge` | GET | Return all knowledge entries |
| `/api/knowledge` | POST | Add a new knowledge entry |
| `/api/knowledge/<id>` | PUT | Update an existing entry |
| `/api/knowledge/<id>` | DELETE | Delete an entry |
| `/api/knowledge/<id>/activate` | POST | Mark entry as active |
| `/api/knowledge/<id>/deactivate` | POST | Mark entry as inactive |

All write operations call `tfidf_engine.retrain()` afterwards so new/changed entries are immediately searchable.

---

### 7.5 `admin_routes.py`

**Blueprint name:** `admin` — all routes require `Admin` role.

| URL | Method | What it does |
|---|---|---|
| `/admin` | GET | Render admin panel page |
| `/api/admin/users` | GET | List all users |
| `/api/admin/users` | POST | Create a new user |
| `/api/admin/users/<id>` | PUT | Update user (role, modules, password) |
| `/api/admin/users/<id>` | DELETE | Delete a user |
| `/api/admin/sync` | POST | Trigger a manual ServiceNow sync now |
| `/api/admin/sync-status` | GET | Return last sync result and timestamp |
| `/api/admin/import-csv` | POST | Upload and import a CSV of incidents |
| `/api/admin/audit-log` | GET | Return recent audit log entries |
| `/api/admin/stats` | GET | Return aggregate counts for the admin dashboard |

**CSV import (`/api/admin/import-csv`):** Accepts a CSV file upload, reads it in memory, validates each row (required fields + minimum length), and saves valid rows to the `incidents` table. After import it retrains the TF-IDF index.

---

## 8. Services Layer (`services/`)

Services contain the business logic. They do not know about Flask routes or HTTP — they just receive data, process it, and return results. This makes them easy to test in isolation.

---

### 8.1 `log_analyzer.py`

**What it does:** Parses uploaded log files entirely in memory. No temporary files are written to disk.

**Two public methods:**

`analyze_uploads(file_storage_list)` — called by the `/api/analyze` route. Accepts a list of Werkzeug `FileStorage` objects directly from the HTTP request.

`analyze_file_bytes(raw_bytes, filename)` — called by `/api/load-sample-data` with bytes read from disk once.

**Parsing pipeline (per file):**
1. **Decode** — if `.gz`, decompress first. Decode bytes as UTF-8 (bad bytes ignored).
2. **Parse lines** — apply `LOG_PATTERN` regex to each line to extract: timestamp, severity, message. Attach `\tat` lines (Java stack traces) to the previous entry.
3. **Extract fields** — `ERROR_CODE_PATTERN` finds codes like `ORA-12541`, `HTTP 500`. `EXCEPTION_PATTERN` finds Java/Python exception class names.
4. **Signature** — strip numbers and IDs from the message to create a normalised fingerprint. Duplicate errors share one signature.
5. **Save** — fully replace `ParsedLog` and `ErrorSignature` tables with new results.
6. **Summary** — count by severity, find top errors/apps/servers, determine probable root cause.

**Root cause detection:** `_root_cause()` loops through `_ROOT_CAUSE_PATTERNS` (24 regex → label pairs covering database, memory, network, SSL, auth, disk, and timeout errors). First match wins. Falls back to the most frequent error signature if nothing matches.

**Supported file types:** `.log` `.txt` `.out` `.csv` `.gz`

---

### 8.2 `recommendation.py`

**What it does:** Finds the best matching resolved incidents and knowledge entries for a user's query.

**`RecommendationEngine.search(query_text, incident_number)`** — main entry point.

**Three-stage search in order:**

| Stage | Method | When used |
|---|---|---|
| 1. Exact match | direct DB lookup | When `incident_number` is provided and found locally |
| 2. TF-IDF search | `tfidf_engine.search()` | When the index has been trained (`tfidf_engine.is_trained()` is True) |
| 3. Fuzzy fallback | `SequenceMatcher` | When the index is empty (no data loaded yet) |

**Confidence score formula:**
```
confidence = (similarity × 0.75) + usage_bonus + feedback_bonus

usage_bonus    = min(15,  success_count × 1.5)
feedback_bonus = max(-10, min(10, helpful_count - not_helpful_count))
```
- `similarity` — 0–100 from TF-IDF cosine similarity or string comparison
- `usage_bonus` — rewards entries that have been resolved many times
- `feedback_bonus` — goes up when users click Helpful, down for Not Helpful

Results are deduplicated (same incident keeps highest score) and the top 5 are returned.

---

### 8.3 `tfidf_engine.py`

**What it does:** Holds a TF-IDF search index in memory. It is a module-level singleton — there is one shared index for the whole application.

**Three module-level variables:**
- `_vectorizer` — a `TfidfVectorizer` that learned the vocabulary from training data
- `_matrix` — a sparse matrix of TF-IDF vectors, one row per document
- `_documents` — list of metadata dicts matching the rows of `_matrix`

**Key functions:**

`retrain(incidents, kb_articles, knowledge_entries)` — rebuilds the entire index from scratch. Called after any data import or knowledge entry change. Returns the number of documents indexed.

`search(query_text, top_n=10)` — transforms the query to a vector, computes cosine similarity against all document vectors, returns the top N matches sorted by score. Returns `[]` if not trained.

`is_trained()` — returns `True` if `retrain()` has been called at least once with data.

**Why it's a separate module (not inside `recommendation.py`):** The index variables need to live at module scope so they persist across requests. Putting them in a class or inside `recommendation.py` would make them either reset per-request or cause import complexity.

---

### 8.4 `knowledge_service.py`

**What it does:** Simple CRUD operations on `KnowledgeEntry` records. Keeps the route file clean by putting all DB interaction here.

**Methods:** `add()`, `get_all()`, `get_by_id()`, `update()`, `delete()`, `set_active()`. Each validates required fields and raises `ValueError` with a user-friendly message if validation fails.

---

### 8.5 `snow_client.py`

**What it does:** HTTP client for the ServiceNow REST API. Handles authentication, pagination, and network errors. The rest of the app never calls `requests` directly — it all goes through this class.

**Authentication:** Tries JWT token login first (POST to `/api/auth/login`). Falls back to HTTP Basic Auth if that fails or if no token endpoint exists.

**Key methods:**

`get_closed_incidents(assignment_groups=None)` — fetches all Resolved/Closed incidents, paginated at 100 records per call. Optionally filters by assignment group.

`get_incident_by_number(number)` — fetches a single incident by number. Used for live lookup when the user searches for an incident that is not yet in the local DB (e.g. it is still open).

`get_kb_articles()` — fetches all active KB articles.

`is_configured()` — returns `True` if URL and credentials are set. Used to skip sync silently when ServiceNow is not configured.

---

### 8.6 `sync_service.py`

**What it does:** Takes raw data from `ServiceNowClient` and applies six validation rules before saving to the database. Bad records are counted and skipped rather than silently accepted.

**Six validation rules** (all must pass):
1. Required fields present — `incident_number`, `error_description`, `resolution`
2. Minimum length — description ≥ 10 chars, resolution ≥ 20 chars
3. No junk text — rejects placeholders like `"done"`, `"n/a"`, `"fixed"`, `"as per call"`
4. No duplicate resolutions — skips if 5+ incidents already share the identical resolution text
5. Valid state — must be `Resolved` or `Closed`
6. Assignment group filter — if `SERVICENOW_ASSIGNMENT_GROUPS` is set, rejects non-matching records

**After a successful sync:** Calls `tfidf_engine.retrain()` so new incidents are immediately searchable. Records the result in `SyncHistory`.

---

## 9. Frontend — Templates (`templates/`)

All templates use Jinja2 and include `nav.html` for the navigation bar. Bootstrap CSS is used for layout; Bootstrap JS has been fully removed and replaced with native browser APIs.

| File | Page | Notes |
|---|---|---|
| `login.html` | Login screen | No nav bar; standalone page |
| `nav.html` | Navigation bar | Included by all other pages via `{% include 'nav.html' %}`. Nav collapse uses vanilla JS + CSS (no Bootstrap JS) |
| `dashboard.html` | Log Analyzer | KPI cards, three Chart.js charts, log table with pagination and CSV export, root cause banner |
| `recommendations.html` | Recommendations | Search box, recent searches history, live incident banner, result cards with confidence bars, feedback buttons |
| `knowledge.html` | Knowledge Repository | Add entry form with validation, filterable/searchable entry list, bulk actions |
| `admin.html` | Admin Panel | User management, sync controls, CSV import, audit log viewer |
| `help.html` | Help / FAQ | 13 FAQ items using native `<details>/<summary>` (no Bootstrap accordion JS) |
| `users.html` | User Management | Uses native `<dialog>` element for the Add/Edit modal (no Bootstrap modal JS) |
| `access_denied.html` | Access Denied | Shown when a user tries to access a module they don't have permission for |

**No Bootstrap JS** — the three features that needed it were replaced:
- Modal → `<dialog>` element (`users.html`)
- Accordion → `<details>/<summary>` (`help.html`)
- Nav collapse → custom CSS classes + `classList.toggle()` (`nav.html`, `styles.css`)

**Local assets only** — all CSS and JS libraries are served from `static/lib/`. Zero CDN calls at runtime.

---

## 10. Frontend — JavaScript (`static/js/`)

One JS file per page. They communicate with the Flask backend exclusively through `fetch()` calls to the JSON API endpoints.

### `app.js` — Dashboard / Log Analyzer

**State variables:** `currentPage`, `totalLogCount`, `PER_PAGE = 100`

**Key functions:**

| Function | What it does |
|---|---|
| `analyzeLogs()` | Collects file picker selections, POSTs to `/api/analyze`, calls `loadDashboard()` and `loadLogs()` |
| `loadSampleData()` | POSTs to `/api/load-sample-data`, then refreshes dashboard and logs |
| `loadDashboard()` | Fetches `/api/dashboard` and `/api/logs/timeline` in parallel; renders KPI cards and all three charts |
| `loadLogs()` | Fetches current page of logs + total count in parallel; renders the log table |
| `updatePagination()` | Shows page info text, enables/disables Prev/Next buttons |
| `renderTimelineChart(data)` | Draws the "Errors Over Time" line chart using Chart.js |
| `exportCsv()` | Triggers a file download via `window.location.href = '/api/logs/export'` |
| `showRootCause(text)` | Shows the amber banner with the probable root cause |
| `setAnalysisLoading(on)` | Toggles spinner on the Analyse and Load Sample buttons |

---

### `recommendations.js` — Recommendations Page

**Key functions:**

| Function | What it does |
|---|---|
| `doSearch()` | POSTs to `/api/recommend`, renders result cards |
| `renderResults(items)` | Splits results into top card + supporting cards |
| `buildTopCard(item, index)` | Builds the highlighted first result with confidence ring |
| `buildCard(item, index)` | Builds a supporting result card |
| `showLiveBanner(inc)` | Shows the yellow "Live Incident" banner when a live SNOW incident is found |
| `saveToHistory(text)` | Saves search text to `localStorage` for the Recent Searches feature |
| `renderRecentSearches()` | Loads and displays up to 5 recent searches as clickable chips |
| `bindFeedback(wrap, index, item)` | Attaches Helpful / Not Helpful button click handlers; POSTs to `/api/feedback` |

---

### `knowledge.js` — Knowledge Repository Page

| Function | What it does |
|---|---|
| `addKnowledge()` | Validates form, POSTs to `/api/knowledge`, shows toast on success |
| `loadKnowledge()` | Fetches all entries, stores in `allRows`, calls `renderFiltered()` |
| `renderFiltered()` | Applies active/inactive filter + search term, calls `_renderRows()` |
| `setFilter(filter)` | Switches between All / Active / Inactive view |
| `saveEdit(id)` | PUTs updated fields to `/api/knowledge/<id>` |
| `toggleActive(id, activate)` | POSTs to `/api/knowledge/<id>/activate` or `/deactivate` |
| `deleteEntry(id)` | DELETEs `/api/knowledge/<id>` after confirmation |
| `bulkAction(action)` | Runs activate/deactivate/delete on all checked rows in parallel |
| `showToast(msg, type)` | Slides in a success or error notification from the bottom-right corner |
| `updateChar(id, max)` | Updates the live character counter under a field; turns amber near the limit |

---

### `users.js` — User Management Page

| Function | What it does |
|---|---|
| `openAddModal()` | Resets form to Add mode, calls `openModal()` |
| `showEditForm(user)` | Populates form with existing user data, switches to Edit mode |
| `openModal()` | Calls `document.getElementById("userDialog").showModal()` |
| `closeModal()` | Calls `dialog.close()` |
| `saveUser()` | POST (add) or PUT (edit) to `/api/admin/users` or `/api/admin/users/<id>` |
| `deleteUser(id)` | DELETEs user after confirmation |
| `onRoleChange()` | Shows or hides the module checkboxes depending on selected role |

---

### `admin.js` — Admin Panel Page

Handles the Admin page's four sections: Users (re-uses `users.js` functions), Sync controls, CSV import, and Audit log viewer.

Key interactions:
- **Trigger sync** — POST to `/api/admin/sync`, polls `/api/admin/sync-status` for result
- **Import CSV** — POST file to `/api/admin/import-csv`, shows import count
- **Audit log** — GET from `/api/admin/audit-log`, renders paginated table

---

## 11. Frontend — CSS (`static/css/styles.css`)

All custom styles are in one file (305 lines). Bootstrap CSS handles layout and form controls. Custom CSS covers:

| Section | What it styles |
|---|---|
| Navbar | Dark sidebar-style nav, brand logo, user chip, logout button, mobile collapse |
| `.irr-main` | Max-width container for all page content |
| `.irr-card` | White card with border and shadow — used everywhere |
| `.irr-card-accent-*` | Coloured left border variants (blue, indigo, amber, red) |
| KPI grid | 4-column responsive grid of coloured stat cards |
| `.chart-wrap` | Fixed-height container for Chart.js canvases |
| `.badge-severity` | Colour-coded severity labels (CRITICAL = dark red → DEBUG = grey) |
| Log table | Hover highlight, coloured header row, stack trace `<pre>` block |
| Upload panel | Dark gradient header strip on the file picker card |
| Forms | Blue focus ring on all inputs/selects |
| `.panel` | Legacy card class used on non-dashboard pages |

**No Bootstrap JS** — nav collapse is handled by `.irr-nav-collapse` / `.irr-nav-open` classes toggled by vanilla JS.

---

## 12. Database Tables at a Glance

```
users                   — who can log in and what they can see
incidents               — resolved ServiceNow incidents (main search corpus)
kb_articles             — ServiceNow KB articles
knowledge_repository    — manually entered patterns + fixes
error_signatures        — unique error fingerprints from uploaded logs
parsed_logs             — log lines from the most recent upload (replaced each run)
recommendation_history  — which result was shown first per search (analytics)
feedback                — Helpful / Not Helpful ratings per recommendation
sync_history            — last sync result per ServiceNow source
audit_logs              — every significant action with username + timestamp
search_history          — what users typed in the search box (analytics)
```

All tables are created automatically by `db.create_all()` on first startup. The database file lives at `data/irr_app.db`.

---

## 13. Environment Variables Reference

Create a `.env` file in the project root. Flask will read it automatically.

```env
# Security
SECRET_KEY=change-me-in-production

# Database (leave blank to use SQLite)
DATABASE_URL=sqlite:///data/irr_app.db

# ServiceNow
SERVICENOW_URL=https://your-instance.service-now.com
SERVICENOW_USERNAME=api_user
SERVICENOW_PASSWORD=api_password
SERVICENOW_TIMEOUT=15
SYNC_INTERVAL_HOURS=6
SERVICENOW_ASSIGNMENT_GROUPS=DBA Team,Network Team

# Recommendations
CONFIDENCE_THRESHOLD=60

# Log rotation
LOG_MAX_BYTES=5242880
LOG_BACKUP_COUNT=10
LOG_ROTATE_WHEN=midnight
```

---

## 14. Where to Make Common Changes

| Task | File(s) to edit |
|---|---|
| Add a new page / URL | Create a route in the relevant `routes/*.py` file, add a template in `templates/`, add a JS file in `static/js/` |
| Add a new database table | Add a class to `core/models.py` — it is created automatically on next startup |
| Add a new user role | Update `ALL_MODULES` in `core/auth.py`; add logic to `module_required()` |
| Change recommendation scoring | Edit `_confidence()` in `services/recommendation.py` |
| Add a new root cause pattern | Add a `(regex, label)` tuple to `_ROOT_CAUSE_PATTERNS` in `services/log_analyzer.py` |
| Add a new ServiceNow field | Update `snow_client.py` to include the field in the API query, then update `sync_service.py` to map it to the model, and add a column to the model in `core/models.py` |
| Change sync frequency | Set `SYNC_INTERVAL_HOURS` in `.env` |
| Change who gets access to a module | Edit the user's `modules` field in the Admin → User Management page |
| Change how nav links look | Edit `.irr-nav-link` / `.irr-nav-active` in `static/css/styles.css` |
| Add a new FAQ | Add a `<details class="faq-item">` block in `templates/help.html` |
