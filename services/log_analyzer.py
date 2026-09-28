"""
log_analyzer.py
---------------
Parses uploaded log files entirely in memory — no files are written to disk.

The caller passes Werkzeug FileStorage objects directly from the HTTP request.
We read the bytes, decode them, parse every line, and save results straight
to the database.  The uploads/ folder is no longer needed.

Supported file types: .log  .txt  .out  .csv  .gz
"""

import gzip
import io
import re
from collections import Counter
from datetime import datetime

from core.database import db
from core.models import ErrorSignature, ParsedLog

LOG_PATTERN = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})?.*?"
    r"(?P<severity>CRITICAL|FATAL|ERROR|WARN|WARNING|INFO|DEBUG).*?"
    r"(?P<message>.+)",
    re.IGNORECASE,
)

ERROR_CODE_PATTERN = re.compile(r"\b([A-Z]{2,10}-?\d{3,8}|HTTP\s?[45]\d\d)\b", re.IGNORECASE)
EXCEPTION_PATTERN  = re.compile(r"\b([A-Za-z0-9_.]+Exception|OutOfMemoryError|TimeoutError)\b")

SUPPORTED_EXTENSIONS = {".log", ".txt", ".out", ".csv", ".gz"}


class LogAnalyzer:

    def analyze_uploads(self, file_storage_list):
        """
        Parse a list of Werkzeug FileStorage objects (from request.files).
        Reads each file into memory, parses it, saves to DB, returns a summary.
        No files are written to disk.
        """
        all_entries = []
        messages    = []

        for upload in file_storage_list:
            name = upload.filename or "upload.log"
            ext  = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""

            if ext not in SUPPORTED_EXTENSIONS:
                messages.append(f"Skipped unsupported file: {name}")
                continue

            try:
                raw_bytes = upload.read()  # read once into memory
                lines     = self._decode(raw_bytes, ext)
                entries   = self._parse_lines(lines, name)
                all_entries.extend(entries)
            except Exception as err:
                messages.append(f"Could not read {name}: {err}")

        self._save_to_db(all_entries)
        return self._build_summary(all_entries, messages)

    def analyze_file_bytes(self, raw_bytes, filename):
        """
        Parse a single file given its raw bytes and filename.
        Used for the sample log (read from disk once at startup).
        """
        ext     = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        lines   = self._decode(raw_bytes, ext)
        entries = self._parse_lines(lines, filename)
        self._save_to_db(entries)
        return self._build_summary(entries, [])

    # ── Decoding ──────────────────────────────────────────────────────────────

    def _decode(self, raw_bytes, ext):
        """
        Turn raw bytes into a list of text lines.
        Handles gzip-compressed files transparently.
        """
        if ext == ".gz":
            raw_bytes = gzip.decompress(raw_bytes)
        text = raw_bytes.decode("utf-8", errors="ignore")
        return text.splitlines()

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _parse_lines(self, lines, source_name):
        """Parse a list of text lines and return a list of entry dicts."""
        entries = []
        current = None  # last entry — used to attach stack trace lines

        for line_num, raw in enumerate(lines, start=1):
            line = raw.rstrip("\n")

            # Stack trace lines (Java "at com.example...") attach to the previous entry
            if line.startswith("\tat") and current:
                existing = current.get("stack_trace", "")
                current["stack_trace"] = (existing + "\n" + line).strip()
                continue

            match = LOG_PATTERN.search(line)
            if not match:
                continue

            severity = match.group("severity").upper().replace("WARNING", "WARN")
            message  = match.group("message").strip()
            stem     = source_name.rsplit(".", 1)[0]  # filename without extension

            current = {
                "source_file": source_name,
                "line_number": line_num,
                "timestamp":   self._parse_ts(match.group("timestamp")),
                "severity":    severity,
                "application": self._field(line, "app") or stem,
                "server":      self._field(line, "server") or self._field(line, "host") or "Unknown",
                "thread_id":   self._field(line, "thread") or "",
                "error_code":  self._first(ERROR_CODE_PATTERN, line),
                "exception":   self._first(EXCEPTION_PATTERN, line),
                "message":     message,
                "stack_trace": "",
                "signature":   self._signature(message),
            }
            entries.append(current)

        return entries

    # ── Database ──────────────────────────────────────────────────────────────

    def _save_to_db(self, entries):
        """
        Replace the current parsed_logs table with the new entries.
        Also update error_signatures (frequency counts per unique error pattern).
        Commits once at the end to keep DB writes fast.
        """
        ParsedLog.query.delete()
        ErrorSignature.query.delete()

        for entry in entries:
            db.session.add(ParsedLog(**entry))

            if entry["severity"] in {"ERROR", "FATAL", "CRITICAL"}:
                sig = ErrorSignature.query.filter_by(signature=entry["signature"]).first()
                if sig:
                    sig.frequency += 1
                    sig.last_seen  = entry["timestamp"]
                else:
                    db.session.add(ErrorSignature(
                        signature   = entry["signature"],
                        application = entry["application"],
                        server      = entry["server"],
                        severity    = entry["severity"],
                        last_seen   = entry["timestamp"],
                    ))

        db.session.commit()

    # ── Summary ───────────────────────────────────────────────────────────────

    def _build_summary(self, entries, messages):
        sev_counts = Counter(e["severity"] for e in entries)
        issues     = [e for e in entries if e["severity"] in {"ERROR", "WARN", "FATAL", "CRITICAL"}]
        sig_counts = Counter(e["signature"]   for e in issues)
        app_counts = Counter(e["application"] for e in issues)
        srv_counts = Counter(e["server"]      for e in issues)

        return {
            "messages":            messages,
            "total_lines":         len(entries),
            "error_count":         sev_counts.get("ERROR", 0),
            "warning_count":       sev_counts.get("WARN", 0),
            "critical_count":      sev_counts.get("CRITICAL", 0) + sev_counts.get("FATAL", 0),
            "info_count":          sev_counts.get("INFO", 0),
            "unique_errors":       len(sig_counts),
            "duplicate_errors":    sum(1 for c in sig_counts.values() if c > 1),
            "top_errors":          sig_counts.most_common(10),
            "top_application":     app_counts.most_common(1)[0][0] if app_counts else "None",
            "top_server":          srv_counts.most_common(1)[0][0] if srv_counts else "None",
            "probable_root_cause": self._root_cause(issues),
            "records":             entries[:500],
        }

    # Pattern → human-readable root cause (checked in order; first match wins)
    _ROOT_CAUSE_PATTERNS = [
        # Database
        (r"ora-12541|tns.?no.?listener|listener.*down",         "Database listener is down — restart Oracle listener service"),
        (r"ora-\d{4,5}",                                        "Oracle database error — check alert log for details"),
        (r"deadlock|lock.wait.timeout",                         "Database deadlock or lock wait timeout detected"),
        (r"too many connections|max_connections",               "Database connection pool exhausted"),
        # Memory
        (r"outofmemory|java.lang.outofmemoryerror",            "JVM heap memory exhausted — increase -Xmx or fix memory leak"),
        (r"gc overhead limit exceeded",                         "Excessive garbage collection — JVM running out of heap"),
        (r"stack.*overflow|stackoverflowerror",                 "Stack overflow — likely infinite recursion in application code"),
        # Connectivity
        (r"connection refused|econnrefused",                    "Service or port unreachable — target host/port not accepting connections"),
        (r"connection.?timed?.?out|connect timeout",            "Network connection timeout — service too slow or firewall blocking"),
        (r"no route to host|network unreachable",               "Network routing failure — check firewall or DNS configuration"),
        # SSL/TLS
        (r"ssl.*expired|certificate.*expired|handshake.*fail", "SSL/TLS certificate expired or handshake failure"),
        (r"ssl.*exception|sslhandshakeexception",              "SSL handshake error — certificate mismatch or protocol incompatibility"),
        # Auth
        (r"authentication.*fail|login.*fail|invalid credentials|access denied", "Authentication failure — check credentials or account lockout"),
        (r"permission denied|unauthori[zs]ed|403",             "Authorisation error — insufficient permissions for the requested resource"),
        # Disk / IO
        (r"no space left|disk.?full|disk.?space",              "Disk space exhausted — free up space or expand the volume"),
        (r"read.?only file system|read.?only.*disk",           "Filesystem mounted read-only — check for disk errors or forced remount"),
        (r"ioexception|i/o error|input/output error",          "I/O error — check disk health and file system integrity"),
        # Threads / timeouts
        (r"thread.*pool.*exhausted|no.?thread.*available",     "Thread pool exhausted — application under heavy load or thread leak"),
        (r"timeout|timed.?out",                                "Operation timeout — backend service slow to respond"),
        # Null / NPE
        (r"nullpointerexception|null reference|object reference not set", "Null pointer exception — application attempting to use uninitialised object"),
        # HTTP
        (r"http.*5[0-9]{2}|internal server error",             "HTTP 5xx server error returned from downstream service"),
        (r"http.*4[0-9]{2}",                                   "HTTP 4xx client error — check request payload or authentication"),
        # Batch / ETL
        (r"batch.*fail|etl.*fail|job.*fail",                   "Batch/ETL job failed — check scheduler logs for detailed error"),
        # Config
        (r"configuration.*error|config.*missing|property.*not found", "Configuration error — missing or invalid application property"),
    ]

    def _root_cause(self, entries):
        if not entries:
            return "No errors found."

        # Sort by timestamp; prefer earlier entries (first symptom)
        sorted_entries = sorted(entries, key=lambda e: e["timestamp"] or datetime.min)

        # Try to find a pattern match scanning from the first error
        import re
        for entry in sorted_entries:
            text = (entry["message"] + " " + (entry["exception"] or "") + " " + (entry["error_code"] or "")).lower()
            for pattern, label in self._ROOT_CAUSE_PATTERNS:
                if re.search(pattern, text):
                    return label

        # Fall back to the signature of the most frequent error
        from collections import Counter
        sig_counts = Counter(e["signature"] for e in entries)
        most_common_sig = sig_counts.most_common(1)[0][0]
        return most_common_sig

    # ── Small helpers ─────────────────────────────────────────────────────────

    def _parse_ts(self, value):
        if not value:
            return datetime.utcnow()
        return datetime.strptime(value.replace("T", " "), "%Y-%m-%d %H:%M:%S")

    def _field(self, line, key):
        m = re.search(rf"{key}=([\w.-]+)", line, re.IGNORECASE)
        return m.group(1) if m else None

    def _first(self, pattern, text):
        m = pattern.search(text)
        return m.group(1) if m else ""

    def _signature(self, message):
        """Normalise a message into a fingerprint so duplicates share one signature."""
        s = re.sub(r"\b\d{4,}\b",           "<number>", message)
        s = re.sub(r"\b[0-9a-fA-F-]{20,}\b", "<id>",    s)
        return re.sub(r"\s+", " ", s).strip()[:500]
