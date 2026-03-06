"""HackerOne API v4 client.

Handles programme listing, scope retrieval, report submission and
feedback loop.  Requires env vars ``HACKERONE_API_USERNAME`` and
``HACKERONE_API_TOKEN``.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

import os

import httpx

from firm.bounty.scope import TargetScope
from firm.bounty.vulnerability import Vulnerability

_BASE = "https://api.hackerone.com/v1"


class HackerOneClient:
    """Thin async wrapper around the HackerOne API v4 (REST)."""

    def __init__(
        self,
        username: str | None = None,
        token: str | None = None,
    ):
        self.username = username or os.environ.get("HACKERONE_API_USERNAME", "")
        self.token = token or os.environ.get("HACKERONE_API_TOKEN", "")
        if not self.username or not self.token:
            raise ValueError(
                "HackerOne credentials required — set HACKERONE_API_USERNAME "
                "and HACKERONE_API_TOKEN env vars."
            )
        self._auth = (self.username, self.token)

    # ---- helpers ----

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=_BASE,
            auth=self._auth,
            headers={"Accept": "application/json"},
            timeout=30.0,
        )

    # ---- programmes ----

    def list_programs(self, page_size: int = 25) -> list[dict]:
        """List bug-bounty programmes the API key can access."""
        with self._client() as c:
            resp = c.get(
                "/hackers/programs",
                params={"page[size]": page_size},
            )
            resp.raise_for_status()
            return resp.json().get("data", [])

    def get_program(self, handle: str) -> dict:
        """Get programme details by handle."""
        with self._client() as c:
            resp = c.get(f"/hackers/programs/{handle}")
            resp.raise_for_status()
            return resp.json().get("data", {})

    # ---- scope ----

    def get_scope(self, handle: str) -> TargetScope:
        """Fetch and parse the structured scope of a programme."""
        with self._client() as c:
            resp = c.get(
                f"/hackers/programs/{handle}/structured_scopes",
                params={"page[size]": 100},
            )
            resp.raise_for_status()
            raw_scopes = resp.json().get("data", [])

        # Translate H1 format → our TargetScope
        structured: list[dict] = []
        for item in raw_scopes:
            attrs = item.get("attributes", {})
            structured.append({
                "asset_identifier": attrs.get("asset_identifier", ""),
                "asset_type": attrs.get("asset_type", "OTHER"),
                "eligible_for_bounty": attrs.get("eligible_for_bounty", False),
                "eligible_for_submission": attrs.get("eligible_for_submission", True),
                "max_severity_guidelines": attrs.get("max_severity", "critical"),
                "instruction": attrs.get("instruction", ""),
            })
        return TargetScope.from_hackerone_dict({
            "handle": handle,
            "name": handle,
            "structured_scopes": structured,
        })

    # ---- reports ----

    def submit_report(
        self,
        programme_handle: str,
        vuln: Vulnerability,
    ) -> dict:
        """Submit a vulnerability report to HackerOne."""
        payload = {
            "data": {
                "type": "report",
                "attributes": {
                    "team_handle": programme_handle,
                    "title": vuln.title,
                    "vulnerability_information": vuln.to_markdown_report(),
                    "severity_rating": vuln.severity.value,
                    "weakness_id": vuln.cwe_id,
                    "impact": vuln.impact,
                    "structured_scope": {
                        "asset_identifier": vuln.asset,
                    },
                },
            },
        }
        with self._client() as c:
            resp = c.post("/hackers/reports", json=payload)
            resp.raise_for_status()
            return resp.json().get("data", {})

    def get_report(self, report_id: str) -> dict:
        """Fetch a submitted report by ID."""
        with self._client() as c:
            resp = c.get(f"/hackers/reports/{report_id}")
            resp.raise_for_status()
            return resp.json().get("data", {})

    def add_comment(self, report_id: str, message: str) -> dict:
        """Add a comment to an existing report."""
        payload = {
            "data": {
                "type": "activity-comment",
                "attributes": {
                    "message": message,
                    "internal": False,
                },
            },
        }
        with self._client() as c:
            resp = c.post(
                f"/hackers/reports/{report_id}/activities",
                json=payload,
            )
            resp.raise_for_status()
            return resp.json().get("data", {})
