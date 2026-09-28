# IRR + Log Analyser — Deep Code Walkthrough

A line-by-line trace of the codebase in the **exact order Python executes it**,
starting from process launch. This is not organized by folder — it is organized
by execution order: when `app.py` imports a module, that module's full contents
are explained right there, then execution returns to `app.py`.

Companion document: `docs/CODE_GUIDE.md` gives a plain-English, per-file summary.
This document goes far deeper and follows real control flow, including every
route handler and every service function it calls, in request order.

---

## Table of Contents

1. [Phase 1 — Process Launch & Top-Level Imports (`app.py`)](#phase-1)
2. [Phase 2 — Configuration Load (`config.py`)](#phase-2)
3. [Phase 3 — `create_app()`: Flask App Construction](#phase-3)
4. [Phase 4 — Logging Setup (`core/logger.py`)](#phase-4)
5. [Phase 5 — Database Initialization (`core/database.py`)](#phase-5)
6. [Phase 6 — Table Definitions (`core/models.py`)](#phase-6)
7. [Phase 7 — Blueprint Registration (`_register_blueprints`)](#phase-7)
   - 7.1 [`routes/auth_routes.py` at import time](#phase-7-1)
   - 7.2 [`routes/dashboard_routes.py` at import time](#phase-7-2)
   - 7.3 [`routes/recommendation_routes.py` at import time](#phase-7-3)
   - 7.4 [`routes/admin_routes.py` at import time](#phase-7-4)
   - 7.5 [`routes/knowledge_routes.py` at import time](#phase-7-5)
8. [Phase 8 — Default Admin Creation (`core/auth.py`)](#phase-8)
9. [Phase 9 — Background Scheduler Startup](#phase-9)
10. [Phase 10 — Dev Server Launch (`if __name__ == "__main__"`)](#phase-10)
11. [Phase 11 — Request Lifecycle: `auth_routes.py` end-to-end](#phase-11)
12. [Phase 12 — Request Lifecycle: `dashboard_routes.py` end-to-end](#phase-12)
    - Deep dive: `services/log_analyzer.py`
13. [Phase 13 — Request Lifecycle: `recommendation_routes.py` end-to-end](#phase-13)
    - Deep dive: `services/recommendation.py`
    - Deep dive: `services/tfidf_engine.py`
    - Deep dive: `services/snow_client.py`
14. [Phase 14 — Request Lifecycle: `knowledge_routes.py` end-to-end](#phase-14)
    - Deep dive: `services/knowledge_service.py`
15. [Phase 15 — Request Lifecycle: `admin_routes.py` end-to-end](#phase-15)
    - Deep dive: `services/sync_service.py`
16. [Phase 16 — Background Sync Trigger Path](#phase-16)
17. [Phase 17 — Templates & Static JS Connection Notes](#phase-17)

---

<a id="phase-1"></a>
## Phase 1 — Process Launch & Top-Level Imports (`app.py`)

When you run `python app.py` (or a WSGI server imports `app` from `app.py`),
the Python interpreter loads `app.py` as the `__main__` module (or as `app`
under a WSGI server) and executes its top-level statements **in file order**.
There is no other entrypoint in this project — there is no `wsgi.py`,
`manage.py`, or `run.py`; `app.py` is it.

```python
import logging
from apscheduler.schedulers.background import BackgroundScheduler

from config import Config
from core.database import init_db
from core.logger import setup_logging
from core.auth import create_default_admin
```

Explanation, line by line, in the order Python actually processes them:

- `import logging` — loads Python's standard logging module. This module is
  used almost everywhere in the codebase (`logging.getLogger(__name__)` in
  nearly every file) to emit structured log lines. Without it, none of the
  `log.info(...)` / `log.error(...)` calls throughout the app would exist.

- `from apscheduler.schedulers.background import BackgroundScheduler` —
  imports the `BackgroundScheduler` class from the third-party `APScheduler`
  library. This is what runs the periodic ServiceNow sync jobs on a separate
  thread, independent of Flask's request-handling thread(s). If this import
  failed (e.g. the package were missing), the whole app would fail to start,
  since `app.py` cannot run without it — this is the first hard external
  dependency check.

- `from config import Config` — this line **triggers execution of
  `config.py`** at this exact point. See **Phase 2** below for a full
  line-by-line trace of that file. Execution of `app.py` pauses here,
  `config.py` runs top to bottom, then control returns to `app.py` with the
  `Config` class object bound to the name `Config`.

- `from core.database import init_db` — this triggers import of the
  `core` package first (running `core/__init__.py`, which — confirmed by
  inspection — is empty, so nothing observable happens), then
  `core/database.py` is executed top to bottom. See **Phase 5**. Only the
  `init_db` function name is pulled into `app.py`'s namespace, but the whole
  module (including the module-level `db = SQLAlchemy()` object) is executed
  and cached in `sys.modules` at this point — this is critical, because every
  other file that later does `from core.database import db` gets the *same*
  singleton `db` object created right here.

- `from core.logger import setup_logging` — triggers execution of
  `core/logger.py` top to bottom (mostly function/constant definitions, no
  side effects at import time — see **Phase 4**). Only `setup_logging` is
  imported into `app.py`.

- `from core.auth import create_default_admin` — triggers execution of
  `core/auth.py` top to bottom. Because `core/auth.py` itself does
  `from core.database import db` and `from core.models import User`, this
  import chain **also** triggers execution of `core/models.py` at this exact
  moment (Python imports are cached, so if `core.database` was already
  imported above it is not re-executed, but `core.models` has not been
  imported yet by anything up to this point, so it executes fully here). See
  **Phase 6** for the full model definitions, then return to **Phase 8**-ish
  content inside `core/auth.py`'s own top-level code (constants, function
  defs — no side effects yet at import time).

```python
log = logging.getLogger(__name__)
```

Creates a module-level logger named `"app"` (since `__name__` is `"app"` when
run as a script imported as `app`, or `"__main__"` when run directly with
`python app.py`). This logger is used later in `_start_scheduler()`.

---

<a id="phase-2"></a>
## Phase 2 — Configuration Load (`config.py`)

Triggered by `from config import Config` in Phase 1. Full contents:

```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
```

- `import os` — needed for `os.getenv()` calls below, which read environment
  variables (and anything loaded from a `.env` file, if `python-dotenv` or
  similar is active elsewhere — note: this project's `config.py` itself does
  **not** call `load_dotenv()`; if a `.env` file is being picked up, it is
  because something else in the environment (e.g. `flask` CLI machinery, or
  the shell) loaded it, or the variables are just not present and defaults
  are used).
- `from pathlib import Path` — used for building filesystem paths in an
  OS-independent way.
- `BASE_DIR = Path(__file__).resolve().parent` — computes the absolute path
  of the project root (the directory containing `config.py`). `__file__` is
  the path to `config.py` itself; `.resolve()` makes it absolute and resolves
  symlinks; `.parent` strips the filename, leaving the containing directory.
  This is the anchor for every other path in the app (`DATA_DIR`, `LOG_DIR`,
  the default SQLite file location).

```python
class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
```

`Config` is a plain class (not instantiated — Flask's `app.config.from_object()`
reads class-level attributes directly). `SECRET_KEY` is read from the
environment; if not set, falls back to `"dev-secret-key"`, an insecure
placeholder used for local development. Flask uses this key to
cryptographically sign session cookies — this is exactly what `core/auth.py`
relies on later when writing `session["username"]` etc.

```python
    _db_default = BASE_DIR / "data" / "irr_app.db"
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", f"sqlite:///{_db_default}")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
```

- `_db_default` — computes the default SQLite file path:
  `<project_root>/data/irr_app.db`.
- `SQLALCHEMY_DATABASE_URI` — the connection string Flask-SQLAlchemy will use.
  Defaults to a local SQLite file, but can be swapped for any SQLAlchemy-
  compatible URI (Oracle, SQL Server, Postgres) via the `DATABASE_URL` env var
  without touching code.
- `SQLALCHEMY_TRACK_MODIFICATIONS = False` — disables a Flask-SQLAlchemy
  feature that emits a signal on every object change; it's expensive and
  deprecated, so this is the standard way to silence its startup warning and
  save memory.

```python
    SERVICENOW_URL      = os.getenv("SERVICENOW_URL",      "http://localhost:8080")
    SERVICENOW_USERNAME = os.getenv("SERVICENOW_USERNAME", "admin")
    SERVICENOW_PASSWORD = os.getenv("SERVICENOW_PASSWORD", "admin123")
    SERVICENOW_TIMEOUT  = int(os.getenv("SERVICENOW_TIMEOUT", "15"))
    SYNC_INTERVAL_HOURS = int(os.getenv("SYNC_INTERVAL_HOURS", "24"))
```

Five ServiceNow connection settings, all read from environment variables with
sane defaults. `SERVICENOW_TIMEOUT` and `SYNC_INTERVAL_HOURS` are explicitly
cast to `int` — `os.getenv` always returns a string or `None`, so without the
`int(...)` wrapper, later arithmetic (e.g. `hours=hours` passed to
APScheduler's `interval` trigger) would fail or behave incorrectly (string
concatenation instead of numeric interval).

```python
    SERVICENOW_ASSIGNMENT_GROUPS = os.getenv("SERVICENOW_ASSIGNMENT_GROUPS", "")
```

A comma-separated string of ServiceNow assignment group names used to filter
which incidents get synced. Empty string means "no filter — pull everything."
Parsed later in `services/sync_service.py`'s `__init__`.

```python
    CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "60"))
```

Read but — notably — **not referenced anywhere else in the codebase** as
verified during this walkthrough (`services/recommendation.py` computes and
returns confidence scores but never filters by this threshold before
returning results; the frontend may filter display-side, but that is outside
Python). Documented here as a currently-unused configuration knob, not
fabricated behavior.

```python
    DATA_DIR = BASE_DIR / "data"
    LOG_DIR  = BASE_DIR / "logs"

    SAMPLE_INCIDENTS_CSV = DATA_DIR / "sample_incidents.csv"
    SAMPLE_KB_CSV        = DATA_DIR / "sample_kb_articles.csv"
```

Path constants. `LOG_DIR` is passed to `setup_logging()` in Phase 4.
`DATA_DIR` is where the SQLite file and any sample CSVs live.
`SAMPLE_INCIDENTS_CSV` / `SAMPLE_KB_CSV` are defined here but — as verified —
there is **no route in the current `dashboard_routes.py` that loads them**
(the `/api/load-sample-data` route mentioned in `CODE_GUIDE.md` does not
exist in the code as read; this appears to be stale documentation from an
earlier version of the app, or sample-loading was removed). This walkthrough
reflects the code as it currently exists.

No further code in `config.py` — the class body ends, `config.py`'s module
execution finishes, and `Config` (the class object) is returned to `app.py`.

---

<a id="phase-3"></a>
## Phase 3 — `create_app()`: Flask App Construction

Back in `app.py`, after all four imports complete, the next top-level
statement executed is:

```python
log = logging.getLogger(__name__)
```

(Already covered in Phase 1 — placed here in file order after the imports.)

Then Python defines (but does not yet call) three functions:
`create_app()`, `_register_blueprints(app)`, `_start_scheduler(app)`, and
`_run_in_context(app, func)`. Function *definitions* execute immediately
(the `def` statement runs, binding the function object to a name) but the
function *bodies* only execute when called. The actual call sequence that
matters is at the bottom of the file:

```python
app = create_app()
_start_scheduler(app)
```

This is where real execution begins. Let's step into `create_app()`:

```python
def create_app():
    """Build and configure the Flask application."""
    from flask import Flask
```

A **local import** — `Flask` is imported here rather than at module top-level.
This is a deliberate lazy-import pattern (possibly to reduce app.py's
top-level import surface, or to avoid circular-import issues since
`core/database.py` and blueprint modules also import Flask machinery). Its
effect: `Flask` is only loaded into memory when `create_app()` first runs,
not at module-import time.

```python
    app = Flask(__name__)
```

Creates the actual Flask WSGI application object. `__name__` here is
`"app"`, used by Flask to locate the `templates/` and `static/` folders
relative to this file's location (both live at the project root, one level
up from nothing since `app.py` is itself at the project root — Flask's
default `template_folder="templates"` and `static_folder="static"` resolve
correctly because `app.py` sits in the project root next to those folders).

```python
    app.config.from_object(Config)
```

Copies every uppercase class attribute from `Config` (see Phase 2) into
`app.config`, a dict-like object. From this point on, `current_app.config["SECRET_KEY"]`,
`current_app.config["SQLALCHEMY_DATABASE_URI"]`, etc. are all available
throughout the app via Flask's application context.

```python
    # Set up log file rotation before anything else logs
    setup_logging(app.config["LOG_DIR"])
```

Calls the `setup_logging` function imported in Phase 1. Execution jumps into
`core/logger.py`'s `setup_logging` function body — full trace in **Phase 4**.
Comment explains the ordering rationale: logging must be wired up before any
other part of the app starts producing log lines, or those lines would go
only to the default (unconfigured) root logger / stderr.

```python
    # Connect SQLAlchemy to this app and run any pending migrations
    init_db(app)
```

Calls `init_db`, imported in Phase 1 from `core/database.py`. Full trace in
**Phase 5**. This is where `db.create_all()` and the ad-hoc migration
statements run — the database schema is fully established by the time this
line returns.

```python
    # Register all route blueprints
    _register_blueprints(app)
```

Calls the sibling function defined later in the same file. Jump to
**Phase 7** for the full blueprint registration trace (this is also where
`core/models.py`'s remaining consumers and all five `routes/*.py` files get
imported for the first time, if not already imported transitively).

```python
    # Create default admin account on very first startup
    with app.app_context():
        create_default_admin()
```

`app.app_context()` is a Flask context manager that makes `current_app` and,
critically, the SQLAlchemy `db` session bindable to *this* app (needed
because Flask-SQLAlchemy's queries like `User.query` need an active app
context to know which app/database to talk to). Inside that context,
`create_default_admin()` (imported from `core/auth.py` in Phase 1) is called
— full trace in **Phase 8**. Without the `with app.app_context():` wrapper,
`User.query.filter_by(...)` inside `create_default_admin()` would raise a
`RuntimeError: Working outside of application context`.

```python
    return app
```

Returns the fully configured Flask app object. Back in the module-level code,
this return value is bound to `app = create_app()`.

---

<a id="phase-4"></a>
## Phase 4 — Logging Setup (`core/logger.py`)

Entered from `setup_logging(app.config["LOG_DIR"])` in Phase 3. Full file:

```python
import logging
import os
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
```

Standard library imports. `RotatingFileHandler` creates a new log file once
the current one exceeds a byte-size threshold, keeping N old files.
`TimedRotatingFileHandler` instead rotates on a wall-clock schedule
(midnight, hourly, etc.). Only one of the two will actually be instantiated,
chosen at runtime based on an environment variable.

```python
def setup_logging(log_dir: Path):
    """Set up file logging. Call this once at application startup."""
    log_dir.mkdir(exist_ok=True)
```

`log_dir` is `Config.LOG_DIR`, i.e. `<project_root>/logs`. `mkdir(exist_ok=True)`
creates that folder if it doesn't exist yet; `exist_ok=True` means no error is
raised if it already exists (idempotent — safe to call on every restart).

```python
    max_bytes    = int(os.getenv("LOG_MAX_BYTES", str(5 * 1024 * 1024)))  # default 5 MB
    backup_count = int(os.getenv("LOG_BACKUP_COUNT", "10"))
    rotate_when  = os.getenv("LOG_ROTATE_WHEN", "")  # e.g. "midnight", "h"
```

Three settings read directly from environment variables (note: **not** from
`app.config` — these bypass `Config` entirely and read `os.getenv` directly,
which is a slightly different pattern than the rest of the settings but
functionally equivalent since both ultimately read the process environment).
`max_bytes` defaults to 5,242,880 (5 MB). `backup_count` defaults to 10 old
files retained. `rotate_when` defaults to empty string, meaning size-based
rotation is used unless explicitly overridden.

```python
    log_file = log_dir / "application.log"

    if rotate_when:
        # Time-based: new file every midnight, every hour, etc.
        handler = TimedRotatingFileHandler(
            log_file, when=rotate_when, backupCount=backup_count, encoding="utf-8"
        )
    else:
        # Size-based: new file after max_bytes
        handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
```

Branching logic: if `LOG_ROTATE_WHEN` env var is set to any truthy string
(e.g. `"midnight"`), a `TimedRotatingFileHandler` is created — new file
rotated at that interval. Otherwise (the `else` branch, the default path for
a fresh install with no `.env` overrides), a `RotatingFileHandler` is used,
rotating once `application.log` exceeds `max_bytes`. Both write to the same
target file path, `logs/application.log`, with UTF-8 encoding so non-ASCII
log messages (e.g. from error text containing special characters) don't
crash the logger.

```python
    handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
```

Sets the line format for every log record written through this handler:
timestamp, then the level (left-padded to 8 chars, e.g. `INFO    `), then the
logger name (e.g. `services.sync_service`), then the message. This is why
every log line in `logs/application.log` shows which module emitted it — each
file does `log = logging.getLogger(__name__)`, so `__name__` (e.g.
`"services.sync_service"`) becomes `%(name)s`.

```python
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        root.addHandler(handler)
```

Gets the **root logger** (no name argument = the top of the logger
hierarchy). Sets its minimum level to `INFO` (so `DEBUG`-level calls
anywhere in the app, e.g. `log.debug(...)` in `sync_service.py`, are
suppressed by default). The `if not root.handlers:` guard prevents adding a
duplicate handler if `setup_logging()` were ever called twice (e.g. under a
reloader) — without this guard, every log line would be written twice
(or more) to the file. Because all other loggers in the app (`logging.getLogger(__name__)`
in each module) propagate up to the root logger by default, attaching the
handler here at the root is sufficient to capture logging from every module
in the codebase.

Function returns `None` implicitly. Control returns to `create_app()` in
`app.py`, continuing at `init_db(app)`.

---

<a id="phase-5"></a>
## Phase 5 — Database Initialization (`core/database.py`)

Two distinct moments matter for this file: (a) **import time**, when
`from core.database import init_db` first ran back in Phase 1, and (b)
**call time**, when `init_db(app)` is invoked from `create_app()` in Phase 3.
Both are covered here together since they're contiguous in the file.

### Import-time execution (happened during Phase 1)

```python
from flask_sqlalchemy import SQLAlchemy

# This is the single shared database object used everywhere.
# It is created here and initialised later in init_db().
db = SQLAlchemy()
```

`SQLAlchemy()` is instantiated with **no app argument** — this is the
"factory pattern" supported by Flask-SQLAlchemy, allowing the extension
object to be created before any Flask `app` exists, then bound to a specific
app later via `db.init_app(app)`. Crucially, `db = SQLAlchemy()` executes
exactly **once**, at first import, and because Python caches modules in
`sys.modules`, every subsequent `from core.database import db` anywhere else
in the codebase (in `core/models.py`, every `routes/*.py` file, every
`services/*.py` file) receives a reference to this exact same object. This is
what makes `db` behave as an application-wide singleton — there's no need for
dependency injection because the module system itself acts as the container.

`init_db` and `_apply_migrations` are function *definitions* — no side
effects yet.

### Call-time execution: `init_db(app)`

```python
def init_db(app):
    """Connect the database to the Flask app and create any missing tables."""
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if uri.startswith("sqlite:///"):
        from pathlib import Path
        Path(uri.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
```

Reads the configured database URI back out of `app.config` (set in Phase 3
via `app.config.from_object(Config)`). If it's a SQLite URI (the default),
strips the `sqlite:///` prefix to recover the filesystem path, then ensures
the **parent directory** of that file exists (`parents=True` creates any
missing intermediate directories too, `exist_ok=True` makes it idempotent).
This is necessary because SQLite will not auto-create the containing
directory — only the file itself, and only if the directory already exists.
Without this line, first-run on a machine without a pre-existing `data/`
folder would crash with a SQLite "unable to open database file" error.

```python
    db.init_app(app)
```

Binds the previously-created `db` singleton to this specific Flask `app`
instance — registers teardown handlers, wires `app.config["SQLALCHEMY_DATABASE_URI"]`
into the SQLAlchemy engine, etc. After this call, `db.session`, `db.engine`,
and all `Model.query` calls work correctly **as long as** they run inside an
app context (or an active request, which implicitly provides one).

```python
    with app.app_context():
        db.create_all()
        _apply_migrations(db)
```

Opens an app context so the calls below can resolve `current_app`/`db`
correctly (see Phase 3's explanation of `app_context()`).

- `db.create_all()` — inspects every `db.Model` subclass that has been
  imported by this point (this is why `core/models.py` must be imported
  before or during this call — see below for how that happens) and issues
  `CREATE TABLE IF NOT EXISTS` for each one. Existing tables are left
  untouched; this is not a migration tool, it only adds tables that don't
  exist yet. **Important nuance:** at the moment `init_db(app)` runs (called
  from `create_app()` before `_register_blueprints(app)`), has
  `core/models.py` actually been imported yet? Tracing the import chain: yes
  — `core/models.py` was already fully imported during Phase 1, as a
  transitive result of `from core.auth import create_default_admin`
  (`core/auth.py` does `from core.models import User`, and Python import
  machinery executes the entire target module the first time it's
  referenced). Because Python caches modules, by the time `db.create_all()`
  runs, all of `core/models.py`'s classes (`User`, `Incident`, `KBArticle`,
  etc.) are already registered against `db.Model`'s metadata, so all 10
  tables get created correctly on a first run.

- `_apply_migrations(db)` — see immediately below.

```python
def _apply_migrations(db):
    """
    Add columns that were introduced after the first release.
    Each statement is safe to run multiple times — if the column
    already exists the error is silently ignored.
    """
    migrations = [
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
```

A hand-rolled, no-framework "migration" mechanism (no Alembic in this
project). `db.engine.connect()` opens a raw DB-API connection (not the ORM
session). For each hardcoded SQL string in `migrations`:
1. `ALTER TABLE users ADD COLUMN modules ...` — adds the `modules` column to
   pre-existing `users` tables from before this column existed in the model.
   On a brand-new database, `db.create_all()` already created `users` with
   the `modules` column (since it's declared in the current `User` model), so
   this `ALTER TABLE` will fail with a "duplicate column" error — which is
   caught by the bare `except Exception: pass` and silently ignored. On an
   *old* database missing that column, this statement succeeds and patches
   the schema in place.
2. `DROP TABLE IF EXISTS application_health` / `learning_statistics` — removes
   two tables that apparently existed in an earlier version of the app and
   are no longer defined in `core/models.py`. `IF EXISTS` makes these safe
   no-ops on fresh databases.

Each statement is wrapped in its own `try/except` so that one failing
migration does not prevent the rest from running. `conn.commit()` is called
per-statement (not batched), consistent with SQLite's typically-autocommit-
adjacent behavior under SQLAlchemy 2.x's explicit transaction model.

Control returns to `create_app()` in `app.py`. Next line: `_register_blueprints(app)`.

---

<a id="phase-6"></a>
## Phase 6 — Table Definitions (`core/models.py`)

As established in Phase 5, this file's *first actual execution* happens
during Phase 1's import chain (`core.auth` → `core.models`), before
`init_db()` is even called — but conceptually it belongs here, right before
`db.create_all()` uses it, so it's fully explained in this phase.

```python
from datetime import datetime
from core.database import db
```

`datetime` supplies default timestamp values (`datetime.utcnow`, passed as a
callable — not called with `()` — so SQLAlchemy invokes it fresh at each row
insert, giving each row its own creation time rather than one shared value
computed once at class-definition time). `db` is the same singleton
instantiated in Phase 5 — imported here so each model class can inherit from
`db.Model` and use `db.Column`, `db.Integer`, etc.

### `class User(db.Model)`

```python
class User(db.Model):
    __tablename__ = "users"

    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role     = db.Column(db.String(20), default="Analyst")
    modules  = db.Column(db.Text, default="dashboard,recommendations")
```

- `__tablename__ = "users"` — explicit SQL table name (otherwise SQLAlchemy
  would derive one automatically from the class name).
- `id` — integer primary key, auto-incrementing by SQLite convention.
- `username` — up to 80 chars, must be unique (enforced at the DB level via a
  unique index — attempting to insert a duplicate raises an `IntegrityError`),
  cannot be null.
- `password` — stores a **hash**, not plaintext (see `core/auth.py`'s use of
  `generate_password_hash`/`check_password_hash`), up to 120 chars (bcrypt/
  werkzeug hashes fit comfortably within this).
- `role` — `"Admin"` or `"Analyst"` (as a free-text string, not an enum —
  nothing in the schema enforces only these two values; validation happens
  in application code, e.g. `admin_routes.py`'s `_modules_str`).
- `modules` — comma-separated string of module keys this user can access,
  e.g. `"dashboard,recommendations"`. Stored as free text rather than a
  proper join table — simple but means module membership is parsed/joined as
  strings throughout (`core/auth.py`'s `get_current_modules()`).

### `class Incident(db.Model)`

```python
class Incident(db.Model):
    __tablename__ = "incidents"

    id                = db.Column(db.Integer, primary_key=True)
    incident_number   = db.Column(db.String(40),  unique=True, index=True)
    application       = db.Column(db.String(120), index=True)
    server            = db.Column(db.String(120), index=True)
    environment       = db.Column(db.String(50),  index=True)
    error_description = db.Column(db.Text)
    exception_message = db.Column(db.Text)
    root_cause        = db.Column(db.Text)
    resolution        = db.Column(db.Text)
    assignment_group  = db.Column(db.String(120))
    status            = db.Column(db.String(40))
    success_count     = db.Column(db.Integer, default=1)
    updated_at        = db.Column(db.DateTime, default=datetime.utcnow)
```

This is the primary corpus the recommendation engine searches. Every field
that's queried/filtered elsewhere (`incident_number`, `application`,
`server`, `environment`) has `index=True` for fast lookups — this matters
directly for `Incident.query.filter_by(incident_number=...)` calls made in
`recommendation_routes.py` and `sync_service.py`, and for the group-by
queries in `dashboard_routes.py`'s `dashboard_data()`. `success_count`
defaults to 1 and is used as a usage-frequency signal in the confidence-score
formula in `services/recommendation.py`. `updated_at` uses `datetime.utcnow`
(unbound, no parens) so SQLAlchemy calls it per-row at insert time.

### `class KBArticle(db.Model)`

```python
class KBArticle(db.Model):
    __tablename__ = "kb_articles"

    id               = db.Column(db.Integer, primary_key=True)
    title            = db.Column(db.String(200))
    error_pattern    = db.Column(db.String(300), index=True)
    root_cause       = db.Column(db.Text)
    resolution       = db.Column(db.Text)
    assignment_group = db.Column(db.String(120))
    active           = db.Column(db.Boolean, default=True)
```

KB articles synced from ServiceNow's `kb_knowledge` table. `active` gates
whether an article participates in TF-IDF indexing and fuzzy search — see
`_rebuild_index()` in `admin_routes.py`, which explicitly filters
`.filter_by(active=True)`.

### `class KnowledgeEntry(db.Model)`

```python
class KnowledgeEntry(db.Model):
    __tablename__ = "knowledge_repository"

    id               = db.Column(db.Integer, primary_key=True)
    pattern          = db.Column(db.String(300), index=True)
    meaning          = db.Column(db.Text)
    resolution       = db.Column(db.Text)
    assignment_group = db.Column(db.String(120))
    frequency        = db.Column(db.Integer, default=0)
    active           = db.Column(db.Boolean, default=True)
    last_seen        = db.Column(db.DateTime)
```

Manually-entered entries via the Knowledge page, entirely independent of
ServiceNow. `frequency` is analogous to `Incident.success_count` and feeds
into the same confidence formula (as `entry.frequency or 1`). `last_seen` is
defined in the schema but — as verified by reading `knowledge_service.py` —
is **never actually set** anywhere in the CRUD methods (`add`/`update` don't
touch it); it stays `NULL` unless something else populates it.

### `class ErrorSignature(db.Model)`

```python
class ErrorSignature(db.Model):
    __tablename__ = "error_signatures"

    id          = db.Column(db.Integer, primary_key=True)
    signature   = db.Column(db.String(500), unique=True, index=True)
    application = db.Column(db.String(120))
    server      = db.Column(db.String(120))
    severity    = db.Column(db.String(30))
    frequency   = db.Column(db.Integer, default=1)
    last_seen   = db.Column(db.DateTime, default=datetime.utcnow)
```

Built and maintained by `services/log_analyzer.py`'s `_save_to_db()`. One
row per unique normalized error fingerprint found in uploaded logs;
`frequency` increments each time the same signature reappears.

### `class ParsedLog(db.Model)`

```python
class ParsedLog(db.Model):
    __tablename__ = "parsed_logs"

    id          = db.Column(db.Integer, primary_key=True)
    source_file = db.Column(db.String(255))
    line_number = db.Column(db.Integer)
    timestamp   = db.Column(db.DateTime, index=True)
    severity    = db.Column(db.String(30),  index=True)
    application = db.Column(db.String(120), index=True)
    server      = db.Column(db.String(120), index=True)
    thread_id   = db.Column(db.String(80))
    error_code  = db.Column(db.String(80))
    exception   = db.Column(db.String(200))
    message     = db.Column(db.Text)
    stack_trace = db.Column(db.Text)
    signature   = db.Column(db.String(500), index=True)
```

Every parsed line of the most recently uploaded log batch. Fully wiped and
re-inserted on each new upload (`ParsedLog.query.delete()` in
`log_analyzer.py`), so this table's size is bounded by one batch, not
cumulative history. Every column used in a `WHERE`/`GROUP BY` elsewhere
(`severity`, `application`, `server`, `signature`, `timestamp`) is indexed.

### `class Feedback(db.Model)`

```python
class Feedback(db.Model):
    __tablename__ = "feedback"

    id                = db.Column(db.Integer, primary_key=True)
    recommendation_id = db.Column(db.Integer)
    value             = db.Column(db.String(40))   # "Helpful" or "Not Helpful"
    comments          = db.Column(db.Text)
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)
```

`recommendation_id` is stored as a plain integer with **no foreign-key
constraint** to any other table — it's whatever `recommendation_id` value the
frontend sends in `/api/feedback`'s JSON body, not enforced against
`RecommendationHistory` or any incident ID. `value` is free text
(`"Helpful"`/`"Not Helpful"`), counted directly by string equality in
`RecommendationEngine.search()`.

### `class SyncHistory(db.Model)`

```python
class SyncHistory(db.Model):
    __tablename__ = "sync_history"

    id             = db.Column(db.Integer, primary_key=True)
    source         = db.Column(db.String(80))    # "servicenow_incidents" or "servicenow_kb"
    last_sync_time = db.Column(db.DateTime)
    status         = db.Column(db.String(40))    # "Success" or "Failed"
    message        = db.Column(db.Text)
```

Written once per sync attempt by `SyncService._record_sync()`, read by
`admin_routes.py`'s `/api/admin/status` and `/api/admin/sync-history`
endpoints to show the last sync outcome in the Admin UI.

### `class AuditLog(db.Model)`

```python
class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id        = db.Column(db.Integer, primary_key=True)
    username  = db.Column(db.String(80))
    action    = db.Column(db.String(120))
    details   = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # named 'timestamp' to match query in admin_routes
```

Written by every route file's local `_audit(action, details)` helper
function (each `routes/*.py` file defines its own copy of this helper rather
than sharing one — a small duplication noted for accuracy, not a bug). The
inline comment explicitly documents that the column is named `timestamp`
(not `created_at`, unlike other tables) because `admin_routes.py`'s
`audit_log()` route queries `AuditLog.timestamp.desc()`.

### `class ServiceNowGroup(db.Model)`

```python
class ServiceNowGroup(db.Model):
    __tablename__ = "servicenow_groups"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(200), unique=True, nullable=False)
    active     = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
```

A DB-backed alternative/companion to the `SERVICENOW_ASSIGNMENT_GROUPS` env
var — full CRUD exposed via `/api/admin/snow-groups` in `admin_routes.py`.
Note: as verified by reading `sync_service.py`, `SyncService.__init__` reads
its group filter **only** from `config.get("SERVICENOW_ASSIGNMENT_GROUPS")`
(the env var / `Config` value), not from the `ServiceNowGroup` table — so
this table currently exists as an editable list in the Admin UI but is not
wired into the actual sync filtering logic. Documented as observed, not
assumed.

**Note on the module docstring at the top of `models.py`:** it lists 10
tables and mentions `servicenow_groups` but does **not** list
`recommendation_history` or `search_history` as classes — and indeed,
reading the actual class definitions confirms there is **no**
`RecommendationHistory` or `SearchHistory` model class in the current
`core/models.py`, despite `CODE_GUIDE.md` describing both. This walkthrough
documents the 10 model classes that actually exist in code today: `User`,
`Incident`, `KBArticle`, `KnowledgeEntry`, `ErrorSignature`, `ParsedLog`,
`Feedback`, `SyncHistory`, `AuditLog`, `ServiceNowGroup`.

Module execution ends. Control returns to whichever import triggered it
(originally `core/auth.py`, during Phase 1).

---

Continuing in the next section: **Phase 7 (Blueprint Registration)** through
**Phase 17**.

<a id="phase-7"></a>
## Phase 7 — Rest of `core/auth.py` (Import-Time) & Blueprint Registration

Before continuing app.py execution, finish tracing `core/auth.py`'s
top-level code (constants and function definitions), since import of that
file (Phase 1) executed after `core/models.py` finished (Phase 6).

```python
from functools import wraps
from flask import redirect, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from core.database import db
from core.models import User
```

`wraps` preserves the wrapped function's `__name__`/docstring when building
decorators below (without it, Flask's URL routing, which keys view
functions partly by `__name__`, could misbehave with multiple decorated
views sharing a generic wrapper name). `redirect`/`session`/`url_for` are
Flask request-context helpers. `check_password_hash`/`generate_password_hash`
are Werkzeug's salted-hash utilities. Passwords are never stored or compared
in plaintext anywhere in this codebase.

```python
ALL_MODULES = ["dashboard", "recommendations", "knowledge", "admin"]

MODULE_LABELS = {
    "dashboard":       "Log Analyzer",
    "recommendations": "Recommendations",
    "knowledge":       "Knowledge Repository",
    "admin":           "Admin Panel",
}

DEFAULT_ANALYST_MODULES = "dashboard,recommendations"
ADMIN_MODULES = ",".join(ALL_MODULES)
```

Four module-level constants, evaluated once at import time. `ADMIN_MODULES`
is computed by joining `ALL_MODULES`, evaluating to
`"dashboard,recommendations,knowledge,admin"` — used whenever an Admin user's
session or a newly created Admin account needs full module access without
hardcoding the string twice.

```python
def create_default_admin():
    """Create the built-in admin account on first startup if it doesn't exist."""
    if not User.query.filter_by(username="admin").first():
        db.session.add(User(
            username="admin",
            password=generate_password_hash("admin123"),
            role="Admin",
            modules=ADMIN_MODULES,
        ))
        db.session.commit()
```

Function definition only at this point (no call yet). `User.query.filter_by(username="admin").first()`
returns `None` if no admin user exists, or the existing `User` row if it
does. The `if not ...` branch only creates the account when it is missing,
which makes the function idempotent and safe to call on every startup — and
it is called on every startup (see Phase 8).

```python
def login_user(username, password):
    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password, password):
        return False

    session["username"] = user.username
    session["role"]     = user.role
    session["modules"]  = ADMIN_MODULES if user.role == "Admin" else (user.modules or "")
    return True
```

`login_user` — called from `auth_routes.py`'s `/login` POST handler (Phase
11). Looks up the user by username; if none found, or if
`check_password_hash` (comparing the submitted plaintext `password` against
the stored hash) fails, returns `False` immediately without ever touching
`session`. On success, three keys are written into Flask's `session`
(a signed cookie, encrypted using `SECRET_KEY` from Phase 2) — this is the
entirety of what "being logged in" means in this app: no server-side session
store, no JWT, just a signed cookie. `session["modules"]` is set to
`ADMIN_MODULES` unconditionally for Admins (bypassing whatever is actually
stored in `user.modules` for admin accounts), or to the user's own `modules`
string (or empty string if `None`) for Analysts.

```python
def get_current_modules():
    """Return the logged-in user's allowed modules as a list."""
    raw = session.get("modules", "")
    return [m.strip() for m in raw.split(",") if m.strip()]
```

Reads back the `modules` session key set during login, splits on commas,
strips whitespace from each piece, and filters out any empty strings (guards
against trailing commas or an empty `raw` string producing `[""]`).

```python
def login_required(view):
    """Redirect to login page if the user is not logged in."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapper
```

`login_required(view)` is called once, at route-definition time (when Python
processes `@login_required` above a route function in, say,
`dashboard_routes.py`), returning `wrapper`, a closure over `view`, which
replaces the original view function in the module namespace. Every time a
request hits that route, Flask actually calls `wrapper(*args, **kwargs)`, not
the original function directly. `wrapper` checks `"username" not in session`
first; if the user never logged in (no `session["username"]` key), it
redirects to `auth.login` (built via `url_for`, which resolves to `/login`
using the Blueprint-qualified endpoint name `auth.login`; see Phase 11 for
where that endpoint is defined) instead of running the real view logic at
all. Otherwise it calls through to the original `view(*args, **kwargs)`,
passing along any URL-pattern arguments Flask captured (e.g. `<int:entry_id>`
in knowledge routes).

```python
def role_required(role):
    """Only users with the given role can access this route."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "username" not in session:
                return redirect(url_for("auth.login"))
            if session.get("role") != role:
                return redirect(url_for("dashboard.index"))
            return view(*args, **kwargs)
        return wrapper
    return decorator
```

This one is a true decorator factory: `role_required("Admin")` is called
with an argument at decoration time, returning `decorator`, which is then
immediately applied to the view function (this is why the syntax is
`@role_required("Admin")` rather than `@role_required`; the parentheses
matter). `decorator(view)` closes over both `view` and `role` (from the
enclosing `role_required` call), and returns `wrapper`, which performs two
checks in order: first, logged in at all? If not, redirect to login.
Second, does `session["role"]` match the required `role` string exactly? If
not (e.g. an Analyst hitting an Admin-only route), redirect to the dashboard
homepage rather than showing a 403 — a "silently redirect away" pattern
rather than an explicit access-denied page for role mismatches (contrast
with `module_required` below, which does show an access-denied page).

```python
def admin_required(view):
    """Only Admin users can access this route."""
    return role_required("Admin")(view)
```

A convenience shorthand: immediately calls `role_required("Admin")` to get
the `decorator` closure, then immediately applies it to `view`. Functionally
identical to writing `@role_required("Admin")` directly above a route, just
shorter to type. Note: as verified by reading all five route files, none of
them actually use `@admin_required`; they all use `@role_required("Admin")`
directly instead. `admin_required` exists in the codebase but is currently
unused from the route files' perspective, though it remains available.

```python
def module_required(module_key):
    """
    Only users who have the given module can access this route.
    Admin users always pass through.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "username" not in session:
                return redirect(url_for("auth.login"))
            if session.get("role") == "Admin":
                return view(*args, **kwargs)
            if module_key not in get_current_modules():
                return redirect(url_for("auth.access_denied"))
            return view(*args, **kwargs)
        return wrapper
    return decorator
```

Also a decorator factory, parameterized by `module_key` (e.g. `"dashboard"`).
Three-way branch inside `wrapper`: first, not logged in leads to a redirect
to login. Second, role is exactly `"Admin"` bypasses the module check
entirely and runs the view; Admins always have full access regardless of
their stored `modules` field. Third, otherwise (an Analyst), call
`get_current_modules()` (defined above) and check whether `module_key` is
present in that list; if not, redirect to the `auth.access_denied` page (a
real page with a 403 status, unlike `role_required`'s silent dashboard
redirect). If the module check passes, call through to the real view.

Module execution of `core/auth.py` ends here. Control returns to `app.py`'s
top-level import statement (`from core.auth import create_default_admin`),
completing Phase 1's import chain, and `app.py` proceeds to define
`create_app()` etc. (Phase 3), which then calls `init_db(app)` (Phase 5) and
finally `_register_blueprints(app)`, where we resume now.

### `_register_blueprints(app)` — called from `create_app()`

```python
def _register_blueprints(app):
    """Attach each group of routes to the app."""
    from routes.auth_routes        import auth_bp
    from routes.dashboard_routes   import dashboard_bp
    from routes.recommendation_routes import rec_bp
    from routes.admin_routes       import admin_bp
    from routes.knowledge_routes   import knowledge_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(rec_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(knowledge_bp)
```

Five local imports, executed top to bottom. Each import statement triggers
full execution of the corresponding `routes/*.py` module for the first time
(none of these were imported earlier; `core/auth.py` and `core/models.py`
have no dependency on the routes layer, only the reverse). This is the exact
order route files get imported and therefore the order their
`@blueprint.route(...)` decorators run, registering each URL rule into that
Blueprint object (not yet attached to `app`; that happens on the next five
lines via `app.register_blueprint(...)`, in the same order: `auth_bp`,
`dashboard_bp`, `rec_bp`, `admin_bp`, `knowledge_bp`). Each import line is
traced fully below, in this exact order, before returning to finish
`_register_blueprints`.

<a id="phase-7-1"></a>
### 7.1 `routes/auth_routes.py` — import-time trace

```python
from flask import Blueprint, redirect, render_template, request, session, url_for
from core.auth import login_user
from core.database import db
from core.models import AuditLog

auth_bp = Blueprint("auth", __name__)
```

Standard Flask imports plus `login_user` (Phase 7 above), `db`, and the
`AuditLog` model. `Blueprint("auth", __name__)` creates a Blueprint object
named `"auth"`. This name becomes the prefix for every route's endpoint name
(e.g. the route function `login` becomes endpoint `"auth.login"`, which is
exactly the string passed to every `url_for("auth.login")` call seen in
Phase 7's decorators above). No URL prefix is passed as a second argument, so
all routes registered on `auth_bp` keep their literal paths (`/login`, not
`/auth/login`).

```python
def _audit(action, details=""):
    db.session.add(AuditLog(username=session.get("username", "system"), action=action, details=details))
    db.session.commit()
```

A local helper, re-implemented identically, with minor variation, in every
`routes/*.py` file (not shared via a common module). Builds one `AuditLog`
row: `username` defaults to `"system"` if no one is logged in (relevant for
actions that can happen pre-login, though in practice `_audit` in this file
is only called after a successful login). `db.session.add(...)` stages the
new row; `db.session.commit()` immediately flushes and commits it. Every
call to `_audit` is its own transaction.

```python
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if login_user(username, password):
            _audit("login", "Successful login")
            return redirect(url_for("dashboard.index"))
        return render_template("login.html", error="Invalid username or password")
    return render_template("login.html")
```

Registers URL `/login` for both `GET` and `POST` under one function. At
decoration time (during this import), `@auth_bp.route(...)` just records the
rule on the Blueprint; the function body only runs per actual HTTP request
(traced fully in Phase 11).

```python
@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/access-denied")
def access_denied():
    return render_template("access_denied.html"), 403


@auth_bp.route("/help")
def help_page():
    return render_template("help.html")
```

Three more route registrations. `/logout` defaults to `GET` only (Flask's
default when `methods` is not specified). `/access-denied` returns a tuple
`(rendered_html, 403)`; Flask interprets a 2-tuple return as
`(body, status_code)`, so this response carries an HTTP 403 Forbidden status
alongside the rendered page. `/help` has no auth decorator at all; it is
reachable by anyone, logged in or not (confirmed by reading the function: no
`@login_required` or similar above it).

Module execution of `auth_routes.py` ends; `auth_bp` (fully populated with 4
routes) is returned to `_register_blueprints`, which binds it to the name
`auth_bp` there.

<a id="phase-7-2"></a>
### 7.2 `routes/dashboard_routes.py` — import-time trace

```python
import csv
import io
import logging

from flask import Blueprint, Response, jsonify, render_template, request, session
from sqlalchemy import func

from core.auth import login_required, module_required
from core.database import db
from core.models import AuditLog, ErrorSignature, Incident, KBArticle, ParsedLog
from services.log_analyzer import LogAnalyzer

log = logging.getLogger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)
```

`csv`/`io` support the CSV export route. `sqlalchemy.func` gives access to
SQL aggregate functions (`func.count()`) used in the dashboard KPI queries.
`from services.log_analyzer import LogAnalyzer` is the point where
`services/log_analyzer.py` is imported for the first time in the whole
process; its full contents are traced in the Phase 12 deep dive below, at
the point `LogAnalyzer()` is actually instantiated and called (inside the
`/api/analyze` route), which is more useful than tracing it here at bare
import time since the file has no meaningful import-time side effects beyond
compiling its module-level regex patterns (`LOG_PATTERN`, `ERROR_CODE_PATTERN`,
`EXCEPTION_PATTERN`) and defining the `LogAnalyzer` class.

`dashboard_bp = Blueprint("dashboard", __name__)` — Blueprint name
`"dashboard"`, so its index route's endpoint is `"dashboard.index"`,
matching every `url_for("dashboard.index")` call seen in `core/auth.py`'s
`role_required` wrapper and `auth_routes.py`'s `/login` success path.

Routes registered, in file order (decoration time only; bodies traced in
Phase 12): `/` (`index`), `/api/dashboard` (`dashboard_data`), `/api/logs`
(`get_logs`), `/api/logs/top-issues` (`top_issues`), `/api/logs/export`
(`export_logs`), `/api/logs/count` (`logs_count`), `/api/analyze`
(`analyze_logs`), `/api/clear-analysis` (`clear_analysis`).

<a id="phase-7-3"></a>
### 7.3 `routes/recommendation_routes.py` — import-time trace

```python
import logging

from flask import Blueprint, jsonify, render_template, request, session

from core.auth import login_required, module_required
from core.database import db
from core.models import AuditLog, Feedback, Incident
from services.recommendation import RecommendationEngine
from services.snow_client import ServiceNowClient

log = logging.getLogger(__name__)
rec_bp = Blueprint("recommendations", __name__)
```

`from services.recommendation import RecommendationEngine` triggers the
first import of `services/recommendation.py`, which itself does
`from services import tfidf_engine`, triggering the first import of
`services/tfidf_engine.py` (its module-level `_vectorizer = None`,
`_matrix = None`, `_documents = []` are initialized at this exact moment;
these three names live for the entire life of the process as the in-memory
search index; see the Phase 13 deep dive). `from services.snow_client import ServiceNowClient`
triggers first import of `services/snow_client.py` (mostly class/constant
definitions, no meaningful import-time side effects). Blueprint name
`"recommendations"`.

Routes registered: `/recommendations` (`recommendations_page`),
`/api/recommend` (`recommend`), `/api/feedback` (`feedback`).

<a id="phase-7-4"></a>
### 7.4 `routes/admin_routes.py` — import-time trace

```python
import csv
import logging
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, session
from werkzeug.security import generate_password_hash

from core.auth import login_required, role_required
from core.database import db
from core.models import AuditLog, Incident, KBArticle, ServiceNowGroup, SyncHistory, User

log = logging.getLogger(__name__)
admin_bp = Blueprint("admin", __name__)
```

Note `services/sync_service.py` is not imported at module top-level here; it
is imported lazily, inside the `trigger_sync()` function body (`from
services.sync_service import SyncService`), and inside `_start_scheduler` in
`app.py`. This means `services/sync_service.py`'s first-ever import happens
either during Phase 9 (scheduler startup) or later, on the first actual
request to `/api/admin/sync`/`/api/admin/sync-now`, whichever happens first
at runtime. Both call sites are traced in full later (Phase 15 and Phase
16).

Routes registered, in file order: `/admin` (`admin_page`), `/admin/users`
(`users_page`), `/api/admin/modules` (`list_modules`), `/api/admin/users`
GET (`list_users`), `/api/admin/users` POST (`create_user`),
`/api/admin/users/<int:user_id>` PUT (`update_user`),
`/api/admin/users/<int:user_id>` DELETE (`delete_user`),
`/api/admin/sync` and `/api/admin/sync-now` both POST, both mapped to the
same function `trigger_sync` (two stacked `@admin_bp.post(...)` decorators
applied to one function; this is the "alias" mentioned in the inline comment
`# alias used by the admin JS`), `/api/admin/retrain` POST (`retrain`),
`/api/admin/import-csv` POST (`import_csv`), `/api/admin/status` GET
(`status`), `/api/admin/sync-history` GET (`sync_history`),
`/api/admin/audit-log` GET (`audit_log`), `/api/admin/snow-groups` GET/POST
(`list_snow_groups`/`create_snow_group`),
`/api/admin/snow-groups/<int:group_id>` PUT/DELETE
(`update_snow_group`/`delete_snow_group`), `/api/admin/stats` GET (`stats`).

<a id="phase-7-5"></a>
### 7.5 `routes/knowledge_routes.py` — import-time trace

```python
from flask import Blueprint, jsonify, render_template, request, session

from core.auth import login_required, module_required
from core.database import db
from core.models import AuditLog
from services.knowledge_service import KnowledgeService

knowledge_bp = Blueprint("knowledge", __name__)
```

`from services.knowledge_service import KnowledgeService`, the first import
of `services/knowledge_service.py` (pure class definition, no import-time
side effects; traced fully in the Phase 14 deep dive).

Routes registered: `/knowledge` (`knowledge_page`), `/api/knowledge` GET
(`list_knowledge`), `/api/knowledge` POST (`add_knowledge`),
`/api/knowledge/<int:entry_id>` PUT (`update_knowledge`),
`/api/knowledge/<int:entry_id>` DELETE (`delete_knowledge`),
`/api/knowledge/<int:entry_id>/activate` POST (`activate_knowledge`),
`/api/knowledge/<int:entry_id>/deactivate` POST (`deactivate_knowledge`).

### Back in `_register_blueprints` — the five `register_blueprint` calls

```python
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(rec_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(knowledge_bp)
```

Each call merges that Blueprint's accumulated URL rules into the main Flask
`app`'s URL map, in this exact order. Order here does not affect routing
behavior for non-overlapping paths (which is the case here; no two
blueprints define the same URL), but it does determine the order routes
appear in `app.url_map` if ever inspected. Function returns `None`
implicitly; control returns to `create_app()`, which proceeds to the
`with app.app_context(): create_default_admin()` block — Phase 8.

---

<a id="phase-8"></a>
## Phase 8 — Default Admin Creation

Already shown as a function definition in Phase 7 (`core/auth.py`); this
phase covers its execution, which happens inside `create_app()`:

```python
    with app.app_context():
        create_default_admin()
```

Inside the app context, `create_default_admin()` runs:
`User.query.filter_by(username="admin").first()` issues
`SELECT * FROM users WHERE username = 'admin' LIMIT 1` against the database
that `db.create_all()` plus migrations just finished setting up in Phase 5.
On a brand-new database, this returns `None`, so the `if not ...` branch is
taken: a new `User` row is staged with username `admin`, a bcrypt/werkzeug
hash of the literal string `"admin123"`, role `"Admin"`, and
`modules=ADMIN_MODULES` (`"dashboard,recommendations,knowledge,admin"`), then
committed. On a restart against an existing database that already has an
`admin` user, the query returns a row, the `if not` is `False`, and nothing
happens; no duplicate account, no password reset. This is the mechanism by
which the well-known default credentials `admin` / `admin123` come to exist
on every fresh install, and why `CODE_GUIDE.md` explicitly warns to change
them in production.

`create_app()` returns `app`. Back in `app.py`'s module-level code:

```python
app = create_app()
```

completes, binding the fully built Flask app to the module-level name `app`.

---

<a id="phase-9"></a>
## Phase 9 — Background Scheduler Startup

Next module-level statement in `app.py`:

```python
_start_scheduler(app)
```

Steps into:

```python
def _start_scheduler(app):
    """
    Start the background job that syncs incidents and KB articles
    from ServiceNow every N hours (set SYNC_INTERVAL_HOURS in .env).
    """
    from services.sync_service import SyncService

    hours = app.config.get("SYNC_INTERVAL_HOURS", 6)
    svc   = SyncService(app.config)

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(lambda: _run_in_context(app, svc.sync_incidents),   "interval", hours=hours)
    scheduler.add_job(lambda: _run_in_context(app, svc.sync_kb_articles), "interval", hours=hours)
    scheduler.start()
    log.info("Background sync scheduler started (every %s hours)", hours)
```

`from services.sync_service import SyncService` is the actual first-ever
import of `services/sync_service.py` in the normal startup path (assuming no
request to `/api/admin/sync` has raced ahead of this, which cannot happen —
this line runs before the dev server even starts accepting connections).
Full trace of the file's contents is in the Phase 15/16 deep dive below,
since it is more useful explained next to where its methods are actually
called.

`hours = app.config.get("SYNC_INTERVAL_HOURS", 6)` reads back the config
value set in Phase 2 (default `24` if unset via env var), but note the
`.get(..., 6)` fallback here is a second, different default value, 6, which
would only ever be used if `SYNC_INTERVAL_HOURS` were missing from
`app.config` entirely, which it never is because `Config` always sets it.
This fallback is effectively dead code but documented as-is for accuracy.

`svc = SyncService(app.config)` instantiates one `SyncService`, passing the
whole Flask config object (which behaves dict-like, satisfying
`SyncService.__init__`'s `config.get(...)` calls). This object is closed
over by the two lambdas below and reused for both sync jobs' entire
lifetime; one shared `ServiceNowClient` (created inside
`SyncService.__init__`, see Phase 15/16) persists across every scheduled
run, meaning any cached JWT token (`self._token` in `ServiceNowClient`)
survives between sync cycles too.

`scheduler = BackgroundScheduler(daemon=True)` creates an APScheduler
scheduler that runs jobs on its own background thread(s), separate from
Flask's request-handling. `daemon=True` means this thread will not prevent
the Python process from exiting when the main thread stops.

The two `scheduler.add_job(...)` calls register `"interval"`-triggered
jobs, each firing every `hours` hours. Each job's target is a lambda
wrapping `_run_in_context(app, svc.sync_incidents)` /
`_run_in_context(app, svc.sync_kb_articles)`; the lambda is necessary
because `add_job` needs a zero-argument callable, but `_run_in_context`
itself needs two arguments (`app` and the target function); the lambda
captures both via closure. Both jobs use the same `hours` interval, so in
practice they fire back to back on the same schedule (incidents sync, then
KB sync — the order they were added, though APScheduler does not strictly
guarantee simultaneous jobs fire in registration order; they are independent
scheduled jobs).

`scheduler.start()` begins the scheduler's internal thread; from this
moment on, both jobs will fire automatically every `hours` hours, for the
lifetime of the process, with no further code in `app.py` needed to keep
them running.

`log.info(...)` writes one confirmation line via the `log` object created
in Phase 1 (`logging.getLogger("app")` or `"__main__"`), routed through the
root logger's file handler set up in Phase 4.

```python
def _run_in_context(app, func):
    """Run a function inside the Flask application context."""
    with app.app_context():
        func()
```

Called by each lambda above, on APScheduler's background thread, not
Flask's request thread. Because the sync functions (`svc.sync_incidents`,
`svc.sync_kb_articles`) use SQLAlchemy queries and `db.session`, they need an
active Flask app context to resolve which app's database to talk to, exactly
as explained in Phase 3; without this wrapper, calling `Incident.query...`
from a background thread with no app context would raise a `RuntimeError`.
This function is the reason background sync can safely touch the database
from a thread Flask itself never created.

---

<a id="phase-10"></a>
## Phase 10 — Dev Server Launch

Final lines of `app.py`:

```python
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
```

`if __name__ == "__main__":` is only `True` when `app.py` is executed
directly (`python app.py`), not when imported by a WSGI server (e.g.
`gunicorn app:app`, which would import `app.py` as a module named `"app"`,
so this block is skipped and only the module-level `app = create_app()` /
`_start_scheduler(app)` lines run, which is exactly the desired behavior
under a production WSGI server: build the app and start the scheduler, but
let the WSGI server itself handle request serving instead of Flask's
built-in dev server).

When run directly, `app.run(...)` starts Flask's built-in Werkzeug
development server, binding to `127.0.0.1:5000` (localhost only; `0.0.0.0`
would be needed for external access) with `debug=True`. Debug mode enables
the interactive debugger on unhandled exceptions and, importantly, the
auto-reloader, which by default re-executes the entire `app.py` module
(including every phase above: config load, logging setup, DB init, blueprint
registration, default admin creation, and a second `_start_scheduler(app)`
call) in a subprocess whenever a `.py` file changes on disk. This is worth
flagging: the reloader spawns a child process that re-runs all of Phase 1
through 9 from scratch, which is a well-known source of "scheduler jobs
registered twice" bugs in Flask plus APScheduler apps if not guarded; this
codebase does not add an explicit guard (e.g. checking `WERKZEUG_RUN_MAIN`
before starting the scheduler), meaning under the reloader's parent watcher
process the scheduler technically starts once in the watcher and once in the
actual child worker process; only the child process actually serves requests
and matters in practice, but this is documented here as an observed
characteristic of the current code rather than an assumption.

This concludes the startup/import phase. Everything from here on is
request-time execution — what happens when a browser actually sends an HTTP
request to the now-running server.
