"""Sets up rotating file logs. Size-based by default, or time-based via LOG_ROTATE_WHEN."""

import logging
import os
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path


def setup_logging(log_dir: Path):
    """Set up file logging. Call this once at application startup."""
    log_dir.mkdir(exist_ok=True)

    max_bytes    = int(os.getenv("LOG_MAX_BYTES", str(5 * 1024 * 1024)))  # default 5 MB
    backup_count = int(os.getenv("LOG_BACKUP_COUNT", "10"))
    rotate_when  = os.getenv("LOG_ROTATE_WHEN", "")  # e.g. "midnight", "h"

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

    handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not root.handlers:
        root.addHandler(handler)
