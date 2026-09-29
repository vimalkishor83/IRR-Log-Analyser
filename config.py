import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    # Database lives in data/ so it stays with the other data files
    # SQL SERVER MIGRATION NOTE: the default below is a SQLite file URI. On
    # SQL Server, set DATABASE_URL to a driver-based URI instead, e.g.
    # 'mssql+pyodbc://<user>:<password>@<host>/<db>?driver=ODBC+Driver+17+for+SQL+Server'
    # (requires the pyodbc package and an installed ODBC driver).
    _db_default = BASE_DIR / "data" / "irr_app.db"
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{_db_default}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ServiceNow connection. No hardcoded credential defaults -- if
    # SERVICENOW_USERNAME/SERVICENOW_PASSWORD aren't set, ServiceNowClient
    # .is_configured() returns False and sync is skipped (with a log
    # warning) rather than attempting a connection with a guessed default.
    SERVICENOW_URL      = os.getenv("SERVICENOW_URL", "http://localhost:8080")
    SERVICENOW_USERNAME = os.getenv("SERVICENOW_USERNAME", "")
    SERVICENOW_PASSWORD = os.getenv("SERVICENOW_PASSWORD", "")
    SERVICENOW_TIMEOUT  = int(os.getenv("SERVICENOW_TIMEOUT", "15"))
    SYNC_INTERVAL_HOURS = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))

    # Comma-separated assignment groups to filter synced incidents.
    # Leave empty to pull all resolved/closed incidents.
    SERVICENOW_ASSIGNMENT_GROUPS = os.getenv("SERVICENOW_ASSIGNMENT_GROUPS", "")

    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "60"))

    # How long an uploaded log analysis (parsed_logs/error_signatures) is kept
    # before the background cleanup job auto-deletes it, if the user never
    # cleared it or replaced it with a new upload. Keeps the database from
    # growing indefinitely from forgotten/abandoned uploads.
    RESULTS_RETENTION_HOURS = int(os.getenv("RESULTS_RETENTION_HOURS", "72"))

    # Paths
    DATA_DIR = BASE_DIR / "data"
    LOG_DIR  = BASE_DIR / "logs"

    # Log rotation (read by logger_config.py)
    # LOG_MAX_BYTES    — max file size before rotation, default 5 MB
    # LOG_BACKUP_COUNT — number of rotated files to keep, default 10
    # LOG_ROTATE_WHEN  — time-based rotation: "midnight", "h", "m" etc.
    #                    when set, takes priority over size-based rotation
