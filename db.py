from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Schema used for every table on SQL Server; skipped on SQLite (no schema support there)
SQLSERVER_SCHEMA = "IRRLogAnalyser"


def apply_schema(app):
    """Central place to set the DB schema for every table."""
    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        db.metadata.schema = SQLSERVER_SCHEMA
