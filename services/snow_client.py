"""
snow_client.py
--------------
Talks to ServiceNow (real or mock) over HTTP.

Auth:  tries JWT token first (the mock supports this).
       Falls back to Basic Auth if token is not available.

Usage:
    client = ServiceNowClient(app.config)
    incidents = client.get_closed_incidents()
    incident  = client.get_incident_by_number("INC0001234")
    articles  = client.get_kb_articles()
"""

import logging

import requests
from requests.auth import HTTPBasicAuth

log = logging.getLogger(__name__)

# These are the states we treat as "done" and worth syncing
RESOLVED_STATES = ["Resolved", "Closed"]

# How many records to pull per API call
PAGE_SIZE = 100


class ServiceNowClient:

    def __init__(self, config):
        self.base_url = config.get("SERVICENOW_URL", "").rstrip("/")
        self.username = config.get("SERVICENOW_USERNAME", "")
        self.password = config.get("SERVICENOW_PASSWORD", "")
        self.timeout  = int(config.get("SERVICENOW_TIMEOUT", 15))
        self._token   = None  # JWT token, cached after first successful login

    def is_configured(self):
        """Return True if URL and credentials are all provided."""
        return bool(self.base_url and self.username and self.password)

    # ── Fetching incidents ────────────────────────────────────────────────────

    def get_closed_incidents(self, assignment_groups=None):
        """
        Return all Resolved / Closed incidents.
        Pass a list of group names to filter by assignment group.
        """
        if not self.is_configured():
            log.warning("ServiceNow not configured — skipping sync")
            return []

        self._ensure_token()

        all_incidents = []
        seen_numbers  = set()  # avoid duplicates if groups overlap

        for query in self._build_queries(assignment_groups):
            batch = self._get_all_pages(
                "/api/now/table/incident",
                extra_params={"sysparm_query": query},
            )
            for inc in batch:
                number = inc.get("number", "")
                if number and number not in seen_numbers:
                    seen_numbers.add(number)
                    all_incidents.append(inc)
            log.info("Pulled %d incidents for query: %s", len(batch), query)

        log.info("Total unique incidents: %d", len(all_incidents))
        return all_incidents

    def get_incident_by_number(self, number):
        """
        Fetch one incident by number (works for ANY state — New, In Progress, etc.)
        Returns a dict or None if not found.
        Used to look up open/in-progress incidents for recommendations.
        """
        if not self.is_configured():
            return None

        self._ensure_token()

        try:
            records = self._get_all_pages(
                "/api/now/table/incident",
                extra_params={"sysparm_query": f"number={number}"},
            )
            return records[0] if records else None
        except Exception as err:
            log.warning("Could not fetch incident %s: %s", number, err)
            return None

    def get_kb_articles(self):
        """Return all KB articles. Returns [] if the endpoint does not exist."""
        if not self.is_configured():
            return []

        self._ensure_token()

        try:
            articles = self._get_all_pages("/api/now/table/kb_knowledge")
            log.info("Pulled %d KB articles", len(articles))
            return articles
        except requests.HTTPError as err:
            if err.response is not None and err.response.status_code == 404:
                log.warning("KB endpoint not found (404) — this is normal for the mock")
                return []
            raise

    # ── Query builder ─────────────────────────────────────────────────────────

    def _build_queries(self, assignment_groups):
        """
        Build the list of sysparm_query strings to send.

        No group filter:
            ["state=Resolved", "state=Closed"]

        With groups:
            ["state=Resolved^assignment_group=App Team",
             "state=Closed^assignment_group=App Team", ...]
        """
        groups = [g.strip() for g in (assignment_groups or []) if g.strip()]
        queries = []

        if groups:
            for group in groups:
                for state in RESOLVED_STATES:
                    queries.append(f"state={state}^assignment_group={group}")
        else:
            for state in RESOLVED_STATES:
                queries.append(f"state={state}")

        return queries

    # ── Pagination ────────────────────────────────────────────────────────────

    def _get_all_pages(self, endpoint, extra_params=None):
        """Keep fetching pages until we get a partial page (= last page)."""
        all_records = []
        offset = 0

        while True:
            params = {"sysparm_limit": PAGE_SIZE, "sysparm_offset": offset}
            if extra_params:
                params.update(extra_params)

            batch = self._get(endpoint, params)
            all_records.extend(batch)

            if len(batch) < PAGE_SIZE:
                break  # reached the last page

            offset += PAGE_SIZE

        return all_records

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _ensure_token(self):
        """Try to get a JWT token. Silently skip if the endpoint doesn't exist."""
        if self._token:
            return  # already have one

        try:
            resp = requests.post(
                f"{self.base_url}/api/auth/token",
                auth=HTTPBasicAuth(self.username, self.password),
                timeout=self.timeout,
            )
            if resp.ok:
                self._token = resp.json().get("result", {}).get("access_token")
                if self._token:
                    log.info("JWT token obtained")
        except Exception as err:
            log.debug("JWT token not available — using Basic Auth. Reason: %s", err)

    def _auth_headers(self):
        """Return (auth_object, headers_dict) for the next request."""
        if self._token:
            return None, {"Authorization": f"Bearer {self._token}"}
        return HTTPBasicAuth(self.username, self.password), {}

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _get(self, endpoint, params):
        """Make a GET request and return the result list."""
        auth, headers = self._auth_headers()
        resp = requests.get(
            f"{self.base_url}{endpoint}",
            params=params,
            auth=auth,
            headers=headers,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json().get("result", [])
