import gzip
import re
from collections import Counter
from datetime import datetime, timedelta

from db import db, get_now
from models.error_signature import ErrorSignature
from models.parsed_log import ParsedLog

LOG_PATTERN = re.compile(
    r"(?P<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})?.*?"
    r"(?P<severity>CRITICAL|FATAL|ERROR|WARN|WARNING|INFO|DEBUG).*?"
    r"(?P<message>.+)",
    re.IGNORECASE,
)

ERROR_CODE_PATTERN = re.compile(r"\b([A-Z]{2,10}-?\d{3,8}|HTTP\s?[45]\d\d)\b", re.IGNORECASE)
EXCEPTION_PATTERN = re.compile(r"\b([A-Za-z0-9_.]+Exception|OutOfMemoryError|TimeoutError)\b")
SUPPORTED_EXTENSIONS = {".log", ".txt", ".out", ".csv", ".gz"}


class LogAnalyzer:
    def analyze_uploads(self, file_storage_list, uploaded_by):
        all_entries = []
        messages = []

        for upload in file_storage_list:
            name = upload.filename or "upload.log"
            ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""

            if ext not in SUPPORTED_EXTENSIONS:
                messages.append(f"Skipped unsupported file: {name}")
                continue

            try:
                raw_bytes = upload.read()
                lines = self._decode(raw_bytes, ext)
                entries = self._parse_lines(lines, name)
                all_entries.extend(entries)
            except Exception as err:
                messages.append(f"Could not read {name}: {err}")

        self._save_to_db(all_entries, uploaded_by)
        return self._build_summary(all_entries, messages)

    def _decode(self, raw_bytes, ext):
        if ext == ".gz":
            raw_bytes = gzip.decompress(raw_bytes)
        text = raw_bytes.decode("utf-8", errors="ignore")
        return text.splitlines()

    def _parse_lines(self, lines, source_name):
        entries = []
        current = None

        for line_num, raw in enumerate(lines, start=1):
            line = raw.rstrip("\n")

            if line.startswith("\tat") and current:
                existing = current.get("stack_trace", "")
                current["stack_trace"] = (existing + "\n" + line).strip()
                continue

            match = LOG_PATTERN.search(line)
            if not match:
                continue

            severity = match.group("severity").upper().replace("WARNING", "WARN")
            message = match.group("message").strip()
            stem = source_name.rsplit(".", 1)[0]

            current = {
                "source_file": source_name,
                "line_number": line_num,
                "timestamp": self._parse_ts(match.group("timestamp")),
                "severity": severity,
                "application": self._field(line, "app") or stem,
                "server": self._field(line, "server") or self._field(line, "host") or "Unknown",
                "thread_id": self._field(line, "thread") or "",
                "error_code": self._first(ERROR_CODE_PATTERN, line),
                "exception": self._first(EXCEPTION_PATTERN, line),
                "message": message,
                "stack_trace": "",
                "signature": self._signature(message),
            }
            entries.append(current)

        return entries

    def _save_to_db(self, entries, uploaded_by):
        now = get_now()
        ParsedLog.query.filter_by(uploaded_by=uploaded_by).delete()
        ErrorSignature.query.filter_by(uploaded_by=uploaded_by).delete()

        for entry in entries:
            db.session.add(ParsedLog(uploaded_by=uploaded_by, uploaded_at=now, **entry))

            if entry["severity"] in {"ERROR", "FATAL", "CRITICAL"}:
                sig = ErrorSignature.query.filter_by(
                    uploaded_by=uploaded_by, signature=entry["signature"]
                ).first()
                if sig:
                    sig.frequency += 1
                    sig.last_seen = entry["timestamp"]
                    sig.uploaded_at = now
                else:
                    db.session.add(
                        ErrorSignature(
                            uploaded_by=uploaded_by,
                            uploaded_at=now,
                            signature=entry["signature"],
                            application=entry["application"],
                            server=entry["server"],
                            severity=entry["severity"],
                            last_seen=entry["timestamp"],
                        )
                    )

        db.session.commit()

    def delete_expired(self, retention_hours):
        cutoff = get_now() - timedelta(hours=retention_hours)
        ParsedLog.query.filter(ParsedLog.uploaded_at < cutoff).delete()
        ErrorSignature.query.filter(ErrorSignature.uploaded_at < cutoff).delete()
        db.session.commit()

    def _build_summary(self, entries, messages):
        sev_counts = Counter(e["severity"] for e in entries)
        issues = [e for e in entries if e["severity"] in {"ERROR", "WARN", "FATAL", "CRITICAL"}]
        sig_counts = Counter(e["signature"] for e in issues)
        app_counts = Counter(e["application"] for e in issues)
        srv_counts = Counter(e["server"] for e in issues)

        return {
            "messages": messages,
            "total_lines": len(entries),
            "error_count": sev_counts.get("ERROR", 0),
            "warning_count": sev_counts.get("WARN", 0),
            "critical_count": sev_counts.get("CRITICAL", 0) + sev_counts.get("FATAL", 0),
            "info_count": sev_counts.get("INFO", 0),
            "unique_errors": len(sig_counts),
            "duplicate_errors": sum(1 for c in sig_counts.values() if c > 1),
            "top_errors": sig_counts.most_common(10),
            "top_application": app_counts.most_common(1)[0][0] if app_counts else "None",
            "top_server": srv_counts.most_common(1)[0][0] if srv_counts else "None",
            "probable_root_cause": self._root_cause(issues),
            "records": entries[:500],
        }

    _ROOT_CAUSE_PATTERNS = [
        (r"ora-12541|tns.?no.?listener|listener.*down", "Database listener is down — restart Oracle listener service"),
        (r"ora-\d{4,5}", "Oracle database error — check alert log for details"),
        (r"deadlock|lock.wait.timeout", "Database deadlock or lock wait timeout detected"),
        (r"too many connections|max_connections", "Database connection pool exhausted"),
        (r"outofmemory|java.lang.outofmemoryerror", "JVM heap memory exhausted — increase -Xmx or fix memory leak"),
        (r"gc overhead limit exceeded", "Excessive garbage collection — JVM running out of heap"),
        (r"stack.*overflow|stackoverflowerror", "Stack overflow — likely infinite recursion in application code"),
        (r"connection refused|econnrefused", "Service or port unreachable — target host/port not accepting connections"),
        (r"connection.?timed?.?out|connect timeout", "Network connection timeout — service too slow or firewall blocking"),
        (r"no route to host|network unreachable", "Network routing failure — check firewall or DNS configuration"),
        (r"ssl.*expired|certificate.*expired|handshake.*fail", "SSL/TLS certificate expired or handshake failure"),
        (r"ssl.*exception|sslhandshakeexception", "SSL handshake error — certificate mismatch or protocol incompatibility"),
        (r"authentication.*fail|login.*fail|invalid credentials|access denied", "Authentication failure — check credentials or account lockout"),
        (r"permission denied|unauthori[zs]ed|403", "Authorisation error — insufficient permissions for the requested resource"),
        (r"no space left|disk.?full|disk.?space", "Disk space exhausted — free up space or expand the volume"),
        (r"read.?only file system|read.?only.*disk", "Filesystem mounted read-only — check for disk errors or forced remount"),
        (r"ioexception|i/o error|input/output error", "I/O error — check disk health and file system integrity"),
        (r"thread.*pool.*exhausted|no.?thread.*available", "Thread pool exhausted — application under heavy load or thread leak"),
        (r"timeout|timed.?out", "Operation timeout — backend service slow to respond"),
        (r"nullpointerexception|null reference|object reference not set", "Null pointer exception — application attempting to use uninitialised object"),
        (r"http.*5[0-9]{2}|internal server error", "HTTP 5xx server error returned from downstream service"),
        (r"http.*4[0-9]{2}", "HTTP 4xx client error — check request payload or authentication"),
        (r"batch.*fail|etl.*fail|job.*fail", "Batch/ETL job failed — check scheduler logs for detailed error"),
        (r"configuration.*error|config.*missing|property.*not found", "Configuration error — missing or invalid application property"),
    ]

    def _root_cause(self, entries):
        if not entries:
            return "No errors found."

        sorted_entries = sorted(entries, key=lambda e: e["timestamp"] or datetime.min)

        for entry in sorted_entries:
            text = (entry["message"] + " " + (entry["exception"] or "") + " " + (entry["error_code"] or "")).lower()
            for pattern, label in self._ROOT_CAUSE_PATTERNS:
                if re.search(pattern, text):
                    return label

        sig_counts = Counter(e["signature"] for e in entries)
        return sig_counts.most_common(1)[0][0]

    def _parse_ts(self, value):
        if not value:
            return get_now()
        return datetime.strptime(value.replace("T", " "), "%Y-%m-%d %H:%M:%S")

    def _field(self, line, key):
        m = re.search(rf"{key}=([\w.-]+)", line, re.IGNORECASE)
        return m.group(1) if m else None

    def _first(self, pattern, text):
        m = pattern.search(text)
        return m.group(1) if m else ""

    def _signature(self, message):
        s = re.sub(r"\b\d{4,}\b", "<number>", message)
        s = re.sub(r"\b[0-9a-fA-F-]{20,}\b", "<id>", s)
        return re.sub(r"\s+", " ", s).strip()[:500]
