"""
database.py
-----------
Sets up the SQLAlchemy database connection.

Usage:
    from core.database import db, init_db
    init_db(app)       # call once at startup
    db.session.add(...)
"""

from flask_sqlalchemy import SQLAlchemy

# This is the single shared database object used everywhere.
# It is created here and initialised later in init_db().
db = SQLAlchemy()


def init_db(app):
    """Connect the database to the Flask app and create any missing tables."""
    # Make sure the data/ folder exists so SQLite can create the DB file there
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if uri.startswith("sqlite:///"):
        from pathlib import Path
        Path(uri.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    with app.app_context():
        db.create_all()
        _apply_migrations(db)


def _apply_migrations(db):
    """
    Add columns that were introduced after the first release.
    Each statement is safe to run multiple times — if the column
    already exists the error is silently ignored.
    """
    migrations = [
        # Safety net for databases that existed before the modular restructure.
        # Each statement is safe to run on a fresh DB — errors are silently ignored.
        "ALTER TABLE users ADD COLUMN modules TEXT DEFAULT 'dashboard,recommendations'",
        "DROP TABLE IF EXISTS application_health",
        "DROP TABLE IF EXISTS learning_statistics",
    ]
    with db.engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(db.text(sql))
                conn.commit()
            except Exception:
                pass  # column already exists — fine
