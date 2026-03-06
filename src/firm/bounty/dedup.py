"""Vulnerability deduplication engine.

Two-level dedup:
  Level 1 — exact fingerprint match (CWE + asset + endpoint + param)
  Level 2 — fuzzy match (CWE + asset only)

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

from dataclasses import dataclass

from firm.bounty.vulnerability import VulnDatabase, Vulnerability


@dataclass
class DedupResult:
    is_duplicate: bool = False
    level: int = 0          # 0 = unique, 1 = exact, 2 = fuzzy
    existing_id: str = ""


class DeduplicationEngine:
    """Check new findings against the vuln database."""

    def __init__(self, db: VulnDatabase):
        self.db = db
        self._seen_fingerprints: set[str] = set()

    def check(self, vuln: Vulnerability) -> DedupResult:
        """Return dedup result *without* modifying anything."""

        # Level 1 — exact fingerprint
        fp = vuln.fingerprint
        if fp in self._seen_fingerprints:
            existing = self.db.find_by_fingerprint(fp)
            return DedupResult(
                is_duplicate=True,
                level=1,
                existing_id=existing[0].id if existing else "",
            )
        db_hits = self.db.find_by_fingerprint(fp)
        if db_hits:
            return DedupResult(
                is_duplicate=True, level=1, existing_id=db_hits[0].id
            )

        # Level 2 — fuzzy (same CWE + same asset)
        candidates = self.db.search(asset=vuln.asset, limit=500)
        for c in candidates:
            if c.cwe_id == vuln.cwe_id and c.id != vuln.id:
                return DedupResult(
                    is_duplicate=True, level=2, existing_id=c.id
                )

        return DedupResult(is_duplicate=False)

    def check_and_add(self, vuln: Vulnerability) -> DedupResult:
        """Check and, if unique, persist + register the fingerprint."""
        result = self.check(vuln)
        if not result.is_duplicate:
            self._seen_fingerprints.add(vuln.fingerprint)
            self.db.insert(vuln)
        return result
