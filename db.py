from flask_sqlalchemy import SQLAlchemy
from config import AWST_TZ, get_now

db = SQLAlchemy()
SQLSERVER_SCHEMA = "IRRLogAnalyser"


def apply_schema(app):
    """Set the database schema for SQL Server tables."""
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        db.metadata.schema = SQLSERVER_SCHEMA
