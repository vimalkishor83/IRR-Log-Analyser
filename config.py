import os
import urllib.parse
from credvault_client import get_credential

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

_MSSQL_PARAMS = urllib.parse.quote_plus(
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=EDC-CSQLGT02;"
    "DATABASE=automaton_ams_dev;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    # SQLite by default; set the SQL Server line below to switch
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'data', 'irr_app.db')
    # SQLALCHEMY_DATABASE_URI = f'mssql+pyodbc:///?odbc_connect={_MSSQL_PARAMS}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # No hardcoded ServiceNow credentials -- sync is skipped if unset
    SERVICENOW_URL      = os.getenv("SERVICENOW_URL", "http://localhost:8080")
    SERVICENOW_USERNAME = os.getenv("SERVICENOW_USERNAME", "")
    SERVICENOW_PASSWORD = get_credential("servicenow_password", os.getenv("SERVICENOW_PASSWORD", ""))
    SERVICENOW_TIMEOUT  = int(os.getenv("SERVICENOW_TIMEOUT", "15"))
    SYNC_INTERVAL_HOURS = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))

    # Comma-separated assignment groups to filter synced incidents.
    # Leave empty to pull all resolved/closed incidents.
    SERVICENOW_ASSIGNMENT_GROUPS = os.getenv("SERVICENOW_ASSIGNMENT_GROUPS", "")

    # Auto-delete uploaded log analysis after this many hours
    RESULTS_RETENTION_HOURS = int(os.getenv("RESULTS_RETENTION_HOURS", "72"))

    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "60"))

    # LOG_ROTATE_WHEN (e.g. "midnight", "h") takes priority over size-based rotation when set
