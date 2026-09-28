# IRR + Log Analyzer

Flask-based Intelligent Resolution Recommender and Log Analyzer: upload application
logs, search historical ServiceNow incidents and a manually maintained knowledge
base for likely root causes and resolutions.

## Features

- Login with role-based modules (Admin, Analyst)
- Log analyzer for `.log`, `.txt`, `.out`, `.csv`, `.gz` — single file, multi-file, or folder upload
- Uploaded files are processed in memory and not saved to disk
- Dashboard KPIs and Chart.js charts
- Recommendation search against synced ServiceNow incidents and the manual knowledge base (TF-IDF matching)
- Manual knowledge repository page (add/edit entries directly, no ServiceNow needed)
- Background ServiceNow sync service (APScheduler) with a manual "Sync Now" / "Retrain" option in Admin
- SQLite by default; `DATABASE_URL` in `.env` can point elsewhere
- Rotating application logs

## Folder Structure

```text
app.py              # entry point — builds the Flask app, registers blueprints
config.py           # settings, loaded from .env
core/
  auth.py           # login/logout, default admin creation
  database.py       # SQLAlchemy init + migrations
  logger.py         # log rotation setup
  models.py         # DB models
routes/
  auth_routes.py
  dashboard_routes.py
  recommendation_routes.py
  admin_routes.py
  knowledge_routes.py
services/
  log_analyzer.py
  recommendation.py
  tfidf_engine.py
  snow_client.py     # ServiceNow API client
  sync_service.py     # background sync job
  knowledge_service.py
templates/
static/
data/                # DB file lives here by default (sqlite)
logs/                # rotating application log files
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Open `http://127.0.0.1:5000`.

Default login (created automatically on first run if no admin exists):

```text
Username: admin
Password: Admin@123
```

## Configuration

All configurable values are in `.env.example` and loaded through `config.py`, including
ServiceNow connection details, sync interval, and log rotation settings.
