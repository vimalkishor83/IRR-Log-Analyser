# Changes made on the server copy (not in the original local folder)
1. app.py: ProxyFix so the app works behind a path prefix (no effect at root).
2. templates/*.html (9 files): href/src="/static/..." -> "static/..." (relative), so CSS/JS/icons load under /research/apps/irr-log-analyser/ and still work at root. Originals backed up as *.html.orig on the server only.
Known: the background ServiceNow sync scheduler (app.py _start_scheduler) starts automatically and will fail every SYNC_INTERVAL_HOURS in this sandbox (no network egress) -- logged as a warning, does not crash the app.
