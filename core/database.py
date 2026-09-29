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
    # Make sure the data/ folder exists so SQLite can create the DB file there.
    # SQL SERVER MIGRATION NOTE: this block is SQLite-only (a SQL Server URI
    # never starts with "sqlite:///"), so it becomes a no-op on SQL Server --
    # no equivalent step is needed there since the database itself is created
    # server-side, not as a local file.
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

    SQL SERVER MIGRATION NOTE: this whole approach (raw ALTER TABLE run on
    every startup, relying on the DB driver to error out when a column
    already exists) is SQLite-idiomatic. On SQL Server:
    - "ALTER TABLE ... ADD COLUMN" is SQLite syntax; SQL Server uses
      "ALTER TABLE users ADD modules VARCHAR(MAX) DEFAULT 'dashboard,recommendations'"
      (no "COLUMN" keyword, and TEXT should become VARCHAR(MAX)/NVARCHAR(MAX)),
      and re-running it will raise a real error (column already exists) rather
      than something safe to blanket try/except -- check
      INFORMATION_SCHEMA.COLUMNS first instead of relying on exception swallowing.
    - "DROP TABLE IF EXISTS" is supported as-is on SQL Server 2016+.
    - Prefer a real migration tool (e.g. Flask-Migrate/Alembic) over this
      idempotent-by-retry pattern once on a database that isn't file-based.
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
