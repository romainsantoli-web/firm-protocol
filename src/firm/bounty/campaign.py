"""Campaign orchestrator — manages a full bug-bounty engagement.

A campaign has phases (RECON → SCAN → EXPLOIT → REPORT → FEEDBACK),
budget limits, duration limits, and automatic deduplication + triage.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from firm.bounty.dedup import DeduplicationEngine
from firm.bounty.triage import TriageDecision, TriagePipeline, TriageResult
from firm.bounty.vulnerability import Vulnerability, VulnDatabase, VulnStatus


class CampaignPhase(str, Enum):
    INIT = "init"
    RECON = "recon"
    SCAN = "scan"
    EXPLOIT = "exploit"
    REPORT = "report"
    FEEDBACK = "feedback"
    COMPLETE = "complete"


@dataclass
class CampaignStats:
    total_findings: int = 0
    unique_findings: int = 0
    duplicates: int = 0
    submitted: int = 0
    accepted: int = 0
    rejected: int = 0
    total_bounty_usd: float = 0.0
    elapsed_seconds: float = 0.0


@dataclass
class Campaign:
    """Manages a single bug-bounty engagement lifecycle."""

    programme_handle: str = ""
    max_duration_hours: float = 4.0
    max_findings: int = 100
    budget_usd: float = 0.0        # max spend on API calls

    # ---- internal state ----
    phase: CampaignPhase = CampaignPhase.INIT
    stats: CampaignStats = field(default_factory=CampaignStats)
    findings: list[Vulnerability] = field(default_factory=list)
    _start_time: float = 0.0

    # ---- wired components (set by factory / caller) ----
    _db: Optional[VulnDatabase] = field(default=None, repr=False)
    _dedup: Optional[DeduplicationEngine] = field(default=None, repr=False)
    _triage: Optional[TriagePipeline] = field(default=None, repr=False)

    def wire(
        self,
        db: VulnDatabase,
        dedup: DeduplicationEngine,
        triage: TriagePipeline,
    ) -> None:
        """Attach pipeline components."""
        self._db = db
        self._dedup = dedup
        self._triage = triage

    # ---- lifecycle ----

    def start(self) -> None:
        self.phase = CampaignPhase.RECON
        self._start_time = time.monotonic()

    def advance_phase(self) -> CampaignPhase:
        """Move to the next phase in the pipeline."""
        order = list(CampaignPhase)
        idx = order.index(self.phase)
        if idx < len(order) - 1:
            self.phase = order[idx + 1]
        return self.phase

    # ---- findings ----

    def add_finding(self, vuln: Vulnerability) -> TriageResult | None:
        """Deduplicate, triage, and store a new finding.

        Returns the triage result, or None if duplicate.
        """
        self.stats.total_findings += 1

        if self._dedup:
            dr = self._dedup.check_and_add(vuln)
            if dr.is_duplicate:
                vuln.status = VulnStatus.DUPLICATE
                self.stats.duplicates += 1
                return None
        elif self._db:
            self._db.insert(vuln)

        self.stats.unique_findings += 1
        self.findings.append(vuln)

        if self._triage:
            result = self._triage.evaluate(vuln)
            if result.decision == TriageDecision.AUTO_SUBMIT:
                vuln.status = VulnStatus.TRIAGED
            elif result.decision == TriageDecision.ARCHIVE:
                vuln.status = VulnStatus.INFORMATIVE
            return result

        return None

    def submit_finding(self, vuln: Vulnerability) -> None:
        """Mark a finding as submitted."""
        vuln.status = VulnStatus.SUBMITTED
        self.stats.submitted += 1
        if self._db:
            self._db.insert(vuln)  # update

    def process_feedback(
        self,
        vuln: Vulnerability,
        h1_state: str,
        bounty: float = 0.0,
    ) -> dict:
        """Process HackerOne feedback for prediction market resolution."""
        from firm.bounty.triage import TriagePipeline

        result = TriagePipeline.process_hackerone_feedback(vuln, h1_state, bounty)
        if result.get("resolution") is True:
            self.stats.accepted += 1
            self.stats.total_bounty_usd += bounty
        elif result.get("resolution") is False:
            self.stats.rejected += 1
        if self._db:
            self._db.insert(vuln)  # update status
        return result

    # ---- stopping conditions ----

    def should_stop(self) -> bool:
        """Check if the campaign should end."""
        if self.phase == CampaignPhase.COMPLETE:
            return True

        elapsed = time.monotonic() - self._start_time if self._start_time else 0
        self.stats.elapsed_seconds = elapsed

        if elapsed > self.max_duration_hours * 3600:
            return True
        if self.stats.unique_findings >= self.max_findings:
            return True
        return False

    # ---- summary ----

    def summary(self) -> dict:
        """Return campaign statistics as a dict."""
        return {
            "programme": self.programme_handle,
            "phase": self.phase.value,
            "total_findings": self.stats.total_findings,
            "unique_findings": self.stats.unique_findings,
            "duplicates": self.stats.duplicates,
            "submitted": self.stats.submitted,
            "accepted": self.stats.accepted,
            "rejected": self.stats.rejected,
            "total_bounty_usd": self.stats.total_bounty_usd,
            "elapsed_hours": round(self.stats.elapsed_seconds / 3600, 2),
        }
