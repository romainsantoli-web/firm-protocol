"""Triage pipeline — decides whether to submit, review, or archive.

Decision matrix:
  CRITICAL/HIGH               → human_review
  INFO                        → archive
  LOW  + confidence < 0.5     → archive
  MEDIUM + confidence ≥ 0.7   → auto_submit
  else                        → human_review

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from firm.bounty.vulnerability import Vulnerability, VulnSeverity, VulnStatus


class TriageDecision(str, Enum):
    AUTO_SUBMIT = "auto_submit"
    HUMAN_REVIEW = "human_review"
    ARCHIVE = "archive"


@dataclass
class TriageResult:
    decision: TriageDecision
    reason: str
    confidence_override: Optional[float] = None


class TriagePipeline:
    """Decide the fate of each finding."""

    def __init__(
        self,
        auto_submit_threshold: float = 0.7,
        archive_threshold: float = 0.5,
        require_human_for_high: bool = True,
    ):
        self.auto_submit_threshold = auto_submit_threshold
        self.archive_threshold = archive_threshold
        self.require_human_for_high = require_human_for_high

    def evaluate(self, vuln: Vulnerability) -> TriageResult:
        sev = vuln.severity
        conf = vuln.confidence

        # HIGH/CRITICAL always require human validation before submission
        if sev in (VulnSeverity.CRITICAL, VulnSeverity.HIGH):
            if self.require_human_for_high:
                return TriageResult(
                    decision=TriageDecision.HUMAN_REVIEW,
                    reason=f"{sev.value} severity — human validation required.",
                )

        # INFO vulns are always archived
        if sev == VulnSeverity.INFO:
            return TriageResult(
                decision=TriageDecision.ARCHIVE,
                reason="Informational finding — archived.",
            )

        # LOW with low confidence → archive
        if sev == VulnSeverity.LOW and conf < self.archive_threshold:
            return TriageResult(
                decision=TriageDecision.ARCHIVE,
                reason=f"Low severity + confidence {conf:.2f} < {self.archive_threshold} — archived.",
            )

        # MEDIUM+ with high confidence → auto-submit
        if conf >= self.auto_submit_threshold:
            return TriageResult(
                decision=TriageDecision.AUTO_SUBMIT,
                reason=f"Confidence {conf:.2f} ≥ {self.auto_submit_threshold} — auto-submitting.",
            )

        # Fallback: human review
        return TriageResult(
            decision=TriageDecision.HUMAN_REVIEW,
            reason=f"Confidence {conf:.2f} below threshold — needs human review.",
        )

    # ---- H1 feedback loop ----

    @staticmethod
    def process_hackerone_feedback(
        vuln: Vulnerability,
        h1_state: str,
        bounty: float = 0.0,
    ) -> dict:
        """Map a HackerOne state change back to internal status + market data.

        Returns a dict suitable for ``prediction.resolve_market()``.
        """
        state_map = {
            "new": VulnStatus.SUBMITTED,
            "triaged": VulnStatus.TRIAGED,
            "bounty": VulnStatus.ACCEPTED,
            "resolved": VulnStatus.RESOLVED,
            "informative": VulnStatus.INFORMATIVE,
            "duplicate": VulnStatus.DUPLICATE,
            "not-applicable": VulnStatus.NOT_APPLICABLE,
            "spam": VulnStatus.NOT_APPLICABLE,
        }
        new_status = state_map.get(h1_state.lower(), VulnStatus.SUBMITTED)
        vuln.status = new_status
        vuln.bounty_amount = bounty

        # Prediction market resolution
        if new_status in (VulnStatus.ACCEPTED, VulnStatus.RESOLVED):
            resolution = True   # vulnerability confirmed
        elif new_status in (
            VulnStatus.DUPLICATE,
            VulnStatus.INFORMATIVE,
            VulnStatus.NOT_APPLICABLE,
        ):
            resolution = False  # vulnerability rejected / not useful
        else:
            resolution = None   # still pending

        return {
            "vuln_id": vuln.id,
            "new_status": new_status.value,
            "resolution": resolution,
            "bounty_usd": bounty,
            "agent": vuln.discovered_by,
        }
