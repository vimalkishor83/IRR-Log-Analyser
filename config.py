import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    # Database lives in data/ so it stays with the other data files
    _db_default = BASE_DIR / "data" / "irr_app.db"
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{_db_default}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ServiceNow connection
    SERVICENOW_URL      = os.getenv("SERVICENOW_URL",      "http://localhost:8080")
    SERVICENOW_USERNAME = os.getenv("SERVICENOW_USERNAME", "admin")
    SERVICENOW_PASSWORD = os.getenv("SERVICENOW_PASSWORD", "admin123")
    SERVICENOW_TIMEOUT  = int(os.getenv("SERVICENOW_TIMEOUT", "15"))
    SYNC_INTERVAL_HOURS = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))

    # Comma-separated assignment groups to filter synced incidents.
    # Leave empty to pull all resolved/closed incidents.
    SERVICENOW_ASSIGNMENT_GROUPS = os.getenv("SERVICENOW_ASSIGNMENT_GROUPS", "")

    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "60"))

    # Paths
    DATA_DIR = BASE_DIR / "data"
    LOG_DIR  = BASE_DIR / "logs"

    SAMPLE_INCIDENTS_CSV = DATA_DIR / "sample_incidents.csv"
    SAMPLE_KB_CSV        = DATA_DIR / "sample_kb_articles.csv"

    # Log rotation (read by logger_config.py)
    # LOG_MAX_BYTES    — max file size before rotation, default 5 MB
    # LOG_BACKUP_COUNT — number of rotated files to keep, default 10
    # LOG_ROTATE_WHEN  — time-based rotation: "midnight", "h", "m" etc.
    #                    when set, takes priority over size-based rotation
