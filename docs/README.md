# Enterprise IRR + Log Analyzer

This is a complete, simple Flask-based Intelligent Resolution Recommender and Log Analyzer application.

## Features

- Login with roles foundation: Admin, Analyst
- Local log analyzer for `.log`, `.txt`, `.out`, `.csv`, `.gz`
- File, multi-file, and folder selection from browser
- Temporary processing only; uploaded files are deleted immediately after analysis
- Dashboard KPIs and Chart.js charts
- Detailed log viewer with search and severity filter
- Root cause suggestion from correlated log events
- Error signature repository
- Recommendation page with top 5 recommendations
- Historical incident and KB matching
- Manual knowledge repository page
- Feedback capture
- ServiceNow client and scheduled sync service structure
- APScheduler background jobs
- SQLite now, configurable database URL for Oracle or SQL Server later
- Rotating application logs
- SQL schema and sample CSV templates

## Folder Structure

```text
app.py
config.py
database.py
models.py
log_analyzer.py
recommendation_engine.py
snow_client.py
sync_service.py
feedback_service.py
knowledge_service.py
auth_service.py
logger_config.py
templates/
static/
data/
logs/
sql/
uploads/
```

## Setup

```powershell
cd "C:\Users\vimal\Downloads\New folder"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

Default login:

```text
Username: admin
Password: admin123
```

## First Run

1. Login.
2. Click `Load Sample Data`.
3. Select `data/sample_app.log` or choose the `data` folder.
4. Click `Start Analysis`.
5. Go to `Recommendations` and search for `ORA-12541` or `OutOfMemoryError`.

## Configuration

All configurable values are in `.env.example` and loaded through `config.py`:

- Database URL
- ServiceNow URL
- ServiceNow credentials
- Sync schedule
- Confidence threshold
- Temporary upload folder

SQLite is the default:

```text
sqlite:///irr_app.db
```

For Oracle or SQL Server later, update `DATABASE_URL` and install the relevant SQLAlchemy driver.

## API Examples

Analyze logs:

```http
POST /api/analyze
multipart/form-data files=<log files>
```

Search recommendations:

```http
POST /api/recommend
Content-Type: application/json

{
  "incident_number": "",
  "query_text": "ORA-12541 TNS no listener"
}
```

Add knowledge:

```http
POST /api/knowledge
Content-Type: application/json

{
  "pattern": "ORA-12541",
  "meaning": "Listener Down",
  "resolution": "Restart Oracle listener",
  "assignment_group": "DBA Team"
}
```

## Notes

The code intentionally avoids complex architecture. It uses simple modules so support engineers can explain and maintain it easily.
