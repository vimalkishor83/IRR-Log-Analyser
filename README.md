# IRR + Log Analyser

Flask-based Intelligent Resolution Recommender (IRR) and Log Analyser. Upload application logs to automatically identify errors, group repetitive stack traces, and recommend verified root causes and resolutions based on past ServiceNow incidents and internal knowledge entries.

## Features

- **Log File Analyser (`/`)**: Upload single or multiple log files (`.log`, `.txt`, `.out`, `.csv`, `.gz`) or complete folders. In-memory log parsing extracts severity, exceptions, root causes, and top error signatures without saving files to disk.
- **Incident Recommendations (`/recommendations`)**: Search error queries against historical incidents and knowledge articles using TF-IDF vectorization and cosine similarity. Includes live ServiceNow lookup for in-progress incidents.
- **Knowledge Repository (`/knowledge`)**: Manage manual known-error database records with CRUD controls and activation toggles.
- **Admin Panel (`/admin`)**:
  - User and role management with module-level access control.
  - Manual & scheduled ServiceNow incident/KB sync.
  - Bulk incident import via CSV with downloadable template.
  - Configurable ServiceNow assignment group filtering.
- **Timezone**: All timestamps, upload records, and sync history operate in **AWST** (`Australia/Perth`, UTC+8).

---

## Folder Structure

```text
app.py                  # Main Flask application and scheduler
config.py               # Environment configuration and AWST timezone helper
credvault_client.py     # Secure credential vault integration
db.py                   # SQLAlchemy database binding and schema definition
seed_data.py            # Local database seeding for dev/testing
requirements.txt        # Python dependencies
models/                 # SQLAlchemy database models
routes/                 # Flask route blueprints (admin, auth, dashboard, knowledge, recs)
services/               # Business logic (log analyzer, recommendation engine, TF-IDF, snow client)
templates/              # Jinja2 HTML templates
static/                 # Stylesheet assets
sample_data/            # Sample log and incident CSV files for testing
not_required/           # Archived server change logs and temporary notes
```

---

## Setup & Running

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment (optional):**
   Copy `.env.example` to `.env` and adjust database or ServiceNow connection settings if needed.

3. **Seed initial database (Admin account, sample incidents & KB):**
   ```bash
   python seed_data.py
   ```

4. **Start the application:**
   ```bash
   python app.py
   ```
   Open `http://127.0.0.1:5000` in your browser.

   **Default Admin Login:**
   - **Username:** `admin`
   - **Password:** `Admin@123`
