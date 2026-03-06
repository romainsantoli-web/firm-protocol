"""Security findings data model and in-memory SQLite database.

A ``Finding`` captures a single vulnerability discovered during a scan.
``FindingsDB`` stores, deduplicates, and queries findings.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Optional

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class FindingStatus(str, Enum):
    NEW = "new"
    CONFIRMED = "confirmed"
    FALSE_POSITIVE = "false_positive"
    DUPLICATE = "duplicate"


# Severity ordering for sorting (lowest index = most severe)
_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """A single security vulnerability or issue."""

    title: str
    description: str
    severity: Severity
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    code_snippet: str = ""
    cwe_id: int = 0
    cvss_vector: str = ""
    cvss_score: float = 0.0
    impact: str = ""
    reproduction_steps: str = ""
    remediation: str = ""
    found_by: str = ""
    confirmed_by: list[str] = field(default_factory=list)
    status: FindingStatus = FindingStatus.NEW
    tags: list[str] = field(default_factory=list)
    raw_output: str = ""
    timestamp: float = field(default_factory=time.time)
    id: str = ""

    def __post_init__(self) -> None:
        if isinstance(self.severity, str):
            self.severity = Severity(self.severity.lower())
        if isinstance(self.status, str):
            self.status = FindingStatus(self.status.lower())
        if not self.id:
            self.id = self.fingerprint[:12]

    @property
    def fingerprint(self) -> str:
        """SHA-256 fingerprint for deduplication.

        Based on: title + file_path + line_start + cwe_id.
        """
        payload = f"{self.title}|{self.file_path}|{self.line_start}|{self.cwe_id}"
        return hashlib.sha256(payload.encode()).hexdigest()

    @property
    def severity_rank(self) -> int:
        return _SEVERITY_ORDER.get(self.severity, 99)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["status"] = self.status.value
        d["fingerprint"] = self.fingerprint
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Finding:
        d = dict(d)
        d.pop("fingerprint", None)
        if "confirmed_by" in d and isinstance(d["confirmed_by"], str):
            d["confirmed_by"] = json.loads(d["confirmed_by"]) if d["confirmed_by"] else []
        if "tags" in d and isinstance(d["tags"], str):
            d["tags"] = json.loads(d["tags"]) if d["tags"] else []
        return cls(**d)


# ---------------------------------------------------------------------------
# Findings database (SQLite in-memory)
# ---------------------------------------------------------------------------

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS findings (
    id            TEXT PRIMARY KEY,
    fingerprint   TEXT UNIQUE,
    title         TEXT NOT NULL,
    description   TEXT,
    severity      TEXT NOT NULL,
    file_path     TEXT,
    line_start    INTEGER DEFAULT 0,
    line_end      INTEGER DEFAULT 0,
    code_snippet  TEXT,
    cwe_id        INTEGER DEFAULT 0,
    cvss_vector   TEXT,
    cvss_score    REAL DEFAULT 0.0,
    impact        TEXT,
    reproduction_steps TEXT,
    remediation   TEXT,
    found_by      TEXT,
    confirmed_by  TEXT,
    status        TEXT DEFAULT 'new',
    tags          TEXT,
    raw_output    TEXT,
    timestamp     REAL
)
"""


class FindingsDB:
    """In-memory SQLite store for security findings with dedup."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()

    # ── Insert ──────────────────────────────────────────────────────

    def add(self, finding: Finding) -> bool:
        """Insert a finding.  Returns False if duplicate (same fingerprint)."""
        try:
            self._conn.execute(
                "INSERT INTO findings "
                "(id, fingerprint, title, description, severity, file_path, "
                " line_start, line_end, code_snippet, cwe_id, cvss_vector, "
                " cvss_score, impact, reproduction_steps, remediation, "
                " found_by, confirmed_by, status, tags, raw_output, timestamp) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    finding.id,
                    finding.fingerprint,
                    finding.title,
                    finding.description,
                    finding.severity.value,
                    finding.file_path,
                    finding.line_start,
                    finding.line_end,
                    finding.code_snippet,
                    finding.cwe_id,
                    finding.cvss_vector,
                    finding.cvss_score,
                    finding.impact,
                    finding.reproduction_steps,
                    finding.remediation,
                    finding.found_by,
                    json.dumps(finding.confirmed_by),
                    finding.status.value,
                    json.dumps(finding.tags),
                    finding.raw_output,
                    finding.timestamp,
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Duplicate fingerprint — mark as duplicate
            self._conn.execute(
                "UPDATE findings SET status = 'duplicate' "
                "WHERE fingerprint = ? AND id != ?",
                (finding.fingerprint, finding.id),
            )
            self._conn.commit()
            return False

    def add_many(self, findings: list[Finding]) -> tuple[int, int]:
        """Insert many findings.  Returns (inserted, duplicates)."""
        inserted = 0
        duplicates = 0
        for f in findings:
            if self.add(f):
                inserted += 1
            else:
                duplicates += 1
        return inserted, duplicates

    # ── Query ───────────────────────────────────────────────────────

    def get(self, finding_id: str) -> Optional[Finding]:
        row = self._conn.execute(
            "SELECT * FROM findings WHERE id = ?", (finding_id,),
        ).fetchone()
        return self._row_to_finding(row) if row else None

    def all(self, exclude_status: Optional[list[str]] = None) -> list[Finding]:
        """Return all findings, optionally excluding certain statuses."""
        if exclude_status:
            placeholders = ",".join("?" for _ in exclude_status)
            rows = self._conn.execute(
                f"SELECT * FROM findings WHERE status NOT IN ({placeholders}) "
                "ORDER BY severity, file_path",
                exclude_status,
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM findings ORDER BY severity, file_path",
            ).fetchall()
        return [self._row_to_finding(r) for r in rows]

    def by_severity(self, severity: Severity | str) -> list[Finding]:
        if isinstance(severity, Severity):
            severity = severity.value
        rows = self._conn.execute(
            "SELECT * FROM findings WHERE severity = ? AND status != 'duplicate' "
            "ORDER BY file_path",
            (severity,),
        ).fetchall()
        return [self._row_to_finding(r) for r in rows]

    def by_agent(self, agent_name: str) -> list[Finding]:
        rows = self._conn.execute(
            "SELECT * FROM findings WHERE found_by = ? ORDER BY severity",
            (agent_name,),
        ).fetchall()
        return [self._row_to_finding(r) for r in rows]

    # ── Stats ───────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Return summary statistics."""
        total = self._conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
        dupes = self._conn.execute(
            "SELECT COUNT(*) FROM findings WHERE status = 'duplicate'",
        ).fetchone()[0]
        by_sev = {}
        for sev in Severity:
            by_sev[sev.value] = self._conn.execute(
                "SELECT COUNT(*) FROM findings "
                "WHERE severity = ? AND status != 'duplicate'",
                (sev.value,),
            ).fetchone()[0]
        by_agent = {}
        for row in self._conn.execute(
            "SELECT found_by, COUNT(*) as cnt FROM findings "
            "WHERE status != 'duplicate' GROUP BY found_by",
        ).fetchall():
            by_agent[row["found_by"]] = row["cnt"]
        return {
            "total": total,
            "unique": total - dupes,
            "duplicates": dupes,
            "by_severity": by_sev,
            "by_agent": by_agent,
        }

    # ── Update ──────────────────────────────────────────────────────

    def confirm(self, finding_id: str, agent_name: str) -> None:
        """Mark a finding as confirmed by an agent."""
        finding = self.get(finding_id)
        if finding and agent_name not in finding.confirmed_by:
            finding.confirmed_by.append(agent_name)
            finding.status = FindingStatus.CONFIRMED
            self._conn.execute(
                "UPDATE findings SET status = ?, confirmed_by = ? WHERE id = ?",
                ("confirmed", json.dumps(finding.confirmed_by), finding_id),
            )
            self._conn.commit()

    def mark_false_positive(self, finding_id: str) -> None:
        self._conn.execute(
            "UPDATE findings SET status = 'false_positive' WHERE id = ?",
            (finding_id,),
        )
        self._conn.commit()

    # ── Helpers ─────────────────────────────────────────────────────

    def _row_to_finding(self, row: sqlite3.Row) -> Finding:
        d = dict(row)
        d.pop("fingerprint", None)
        return Finding.from_dict(d)

    def close(self) -> None:
        self._conn.close()
