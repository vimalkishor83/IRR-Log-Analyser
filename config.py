import os
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo
from credvault_client import get_credential

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Platform default timezone: AWST (UTC+8)
AWST_TZ = ZoneInfo("Australia/Perth")


def get_now():
    """Current AWST naive datetime for database timestamps."""
    return datetime.now(AWST_TZ).replace(tzinfo=None)


_MSSQL_PARAMS = urllib.parse.quote_plus(
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=EDC-CSQLGT02;"
    "DATABASE=automaton_ams_dev;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

    # SQLite by default; uncomment SQL Server when running on corporate DB
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(BASE_DIR, "data", "irr_app.db"),
    )
    # SQLALCHEMY_DATABASE_URI = f"mssql+pyodbc:///?odbc_connect={_MSSQL_PARAMS}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ServiceNow integration
    SERVICENOW_URL = os.getenv("SERVICENOW_URL", "http://localhost:8080")
    SERVICENOW_USERNAME = os.getenv("SERVICENOW_USERNAME", "")
    SERVICENOW_PASSWORD = get_credential("servicenow_password", os.getenv("SERVICENOW_PASSWORD", ""))
    SERVICENOW_TIMEOUT = int(os.getenv("SERVICENOW_TIMEOUT", "15"))
    SYNC_INTERVAL_HOURS = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))

    # Assignment group filter (comma separated, empty means pull all)
    SERVICENOW_ASSIGNMENT_GROUPS = os.getenv("SERVICENOW_ASSIGNMENT_GROUPS", "")

    # Retention & thresholds
    RESULTS_RETENTION_HOURS = int(os.getenv("RESULTS_RETENTION_HOURS", "72"))
    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "60"))
