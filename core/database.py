"""Sets up the SQLAlchemy database connection."""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def init_db(app):
    """Connect the database to the Flask app and create any missing tables."""
    # SQLite only -- on SQL Server the DB is created server-side, not as a file.
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if uri.startswith("sqlite:///"):
        from pathlib import Path
        Path(uri.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    with app.app_context():
        db.create_all()
        _apply_migrations(db)


def _apply_migrations(db):
    """Add columns/tables introduced after the first release. Safe to run repeatedly.
    Note: SQLite-specific syntax (ADD COLUMN, no INFORMATION_SCHEMA check) -- rewrite for SQL Server.
    """
    migrations = [
        "ALTER TABLE users ADD COLUMN modules TEXT DEFAULT 'dashboard,recommendations'",
        "DROP TABLE IF EXISTS application_health",
        "DROP TABLE IF EXISTS learning_statistics",
        "ALTER TABLE parsed_logs ADD COLUMN uploaded_by VARCHAR(80)",
        "ALTER TABLE error_signatures ADD COLUMN uploaded_by VARCHAR(80)",
        "ALTER TABLE parsed_logs ADD COLUMN uploaded_at DATETIME",
        "ALTER TABLE error_signatures ADD COLUMN uploaded_at DATETIME",
    ]
    with db.engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(db.text(sql))
                conn.commit()
            except Exception:
                pass  # already applied
