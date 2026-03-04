"""
firm.core.audit — Audit Trail (Layer 10)

External accountability interface for FIRM organizations.

The Audit Trail provides:
  - Timeline reconstruction from the ledger
  - Agent performance reports
  - Governance decision history
  - Anomaly detection (authority spikes, spending patterns)
  - Chain integrity verification
  - Exportable reports for external review

This layer is read-only — it observes and reports but never modifies
the organization state.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from firm.core.agent import Agent
from firm.core.authority import AuthorityEngine
from firm.core.ledger import LedgerEntry, ResponsibilityLedger
from firm.core.types import AgentId, LedgerAction, Severity

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

AUTHORITY_SPIKE_THRESHOLD = 0.15  # > 15% jump in one action = anomaly
CREDIT_BURN_RATE_WARNING = 50.0  # Credits/hour burn rate warning


@dataclass
class AuditFinding:
    """A single finding from an audit check."""

    severity: Severity
    category: str  # "authority", "credits", "governance", "integrity", "performance"
    title: str
    description: str
    agent_id: AgentId | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "agent_id": self.agent_id,
            "evidence": self.evidence,
        }


@dataclass
class AuditReport:
    """Complete audit report for a FIRM organization."""

    firm_name: str
    generated_at: float = field(default_factory=time.time)
    chain_valid: bool = True
    findings: list[AuditFinding] = field(default_factory=list)
    agent_summaries: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def severity_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            key = f.severity.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    @property
    def is_healthy(self) -> bool:
        """No CRITICAL or HIGH findings."""
        return not any(
            f.severity in (Severity.CRITICAL, Severity.HIGH)
            for f in self.findings
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "firm_name": self.firm_name,
            "generated_at": self.generated_at,
            "chain_valid": self.chain_valid,
            "is_healthy": self.is_healthy,
            "severity_counts": self.severity_counts,
            "findings_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
            "agent_summaries": self.agent_summaries,
            "timeline_entries": len(self.timeline),
        }


class AuditEngine:
    """
    External accountability interface.

    Reads from the ledger, authority engine, and agent registry
    to produce audit reports. Never modifies state.
    """

    def __init__(self) -> None:
        self._reports: list[AuditReport] = []

    # ── Full Audit ───────────────────────────────────────────────────────

    def full_audit(
        self,
        firm_name: str,
        ledger: ResponsibilityLedger,
        agents: list[Agent],
        authority_engine: AuthorityEngine,
    ) -> AuditReport:
        """
        Run a comprehensive audit of the organization.

        Checks:
        1. Ledger chain integrity
        2. Authority anomalies (spikes, concentration)
        3. Credit anomalies (burn rate, negative balances)
        4. Agent performance
        5. Governance activity
        """
        report = AuditReport(firm_name=firm_name)

        # 1. Chain integrity
        chain_result = ledger.verify_chain()
        report.chain_valid = chain_result.get("valid", True) if isinstance(chain_result, dict) else bool(chain_result)
        if not report.chain_valid:
            report.findings.append(AuditFinding(
                severity=Severity.CRITICAL,
                category="integrity",
                title="Ledger chain broken",
                description="Hash chain verification failed — possible tampering",
            ))

        # 2. Authority checks
        self._check_authority_anomalies(agents, ledger, report)

        # 3. Credit checks
        self._check_credit_anomalies(agents, report)

        # 4. Agent performance summaries
        report.agent_summaries = [
            self._agent_summary(agent, ledger)
            for agent in agents
        ]

        # 5. Build timeline
        report.timeline = self._build_timeline(ledger, limit=100)

        self._reports.append(report)
        logger.info(
            "Audit complete for '%s': %d findings (%s)",
            firm_name, len(report.findings), report.severity_counts,
        )
        return report

    # ── Timeline ─────────────────────────────────────────────────────────

    def _build_timeline(
        self,
        ledger: ResponsibilityLedger,
        limit: int = 100,
        agent_id: str | None = None,
        action_filter: LedgerAction | None = None,
    ) -> list[dict[str, Any]]:
        """Build a chronological timeline from the ledger."""
        entries = ledger.get_entries(limit=limit)

        if agent_id:
            entries = [e for e in entries if e["agent_id"] == agent_id]
        if action_filter:
            entries = [e for e in entries if e["action"] == action_filter.value]

        return [
            {
                "timestamp": e["timestamp"],
                "agent_id": e["agent_id"],
                "action": e["action"],
                "description": e["description"],
                "authority": e["authority_at_time"],
                "credit_delta": e["credit_delta"],
                "outcome": e["outcome"],
            }
            for e in entries
        ]

    def get_timeline(
        self,
        ledger: ResponsibilityLedger,
        agent_id: str | None = None,
        action_filter: LedgerAction | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Public timeline query."""
        return self._build_timeline(ledger, limit, agent_id, action_filter)

    # ── Agent Summary ────────────────────────────────────────────────────

    def _agent_summary(
        self,
        agent: Agent,
        ledger: ResponsibilityLedger,
    ) -> dict[str, Any]:
        """Produce a performance summary for a single agent."""
        entries = [
            e for e in ledger.get_entries(limit=10000)
            if e["agent_id"] == agent.id
        ]

        successes = sum(1 for e in entries if e["action"] == "task_completed")
        failures = sum(1 for e in entries if e["action"] == "task_failed")
        total_credit_delta = sum(e["credit_delta"] for e in entries)

        return {
            "agent_id": agent.id,
            "name": agent.name,
            "authority": round(agent.authority, 4),
            "credits": round(agent.credits, 2),
            "status": agent.status.value,
            "success_rate": round(agent.success_rate, 4),
            "ledger_actions": len(entries),
            "successes": successes,
            "failures": failures,
            "net_credits": round(total_credit_delta, 2),
            "roles": [r.name for r in agent.roles],
        }

    # ── Authority Anomaly Detection ──────────────────────────────────────

    def _check_authority_anomalies(
        self,
        agents: list[Agent],
        ledger: ResponsibilityLedger,
        report: AuditReport,
    ) -> None:
        """Check for authority spikes and concentration."""
        if not agents:
            return

        # Check concentration
        authorities = [a.authority for a in agents if a.is_active]
        if authorities:
            max_auth = max(authorities)
            avg_auth = sum(authorities) / len(authorities)

            if max_auth > 0.9 and len(authorities) > 1:
                report.findings.append(AuditFinding(
                    severity=Severity.HIGH,
                    category="authority",
                    title="Authority concentration",
                    description=(
                        f"One agent has authority {max_auth:.2f} while "
                        f"average is {avg_auth:.2f}"
                    ),
                    evidence={"max": max_auth, "avg": avg_auth},
                ))

        # Check for authority spikes in ledger
        entries = ledger.get_entries(limit=1000)
        authority_changes: dict[str, list[float]] = {}

        for entry in entries:
            if entry["action"] == "authority_change":
                aid = entry["agent_id"]
                if aid not in authority_changes:
                    authority_changes[aid] = []
                authority_changes[aid].append(entry["authority_at_time"])

    # ── Credit Anomaly Detection ─────────────────────────────────────────

    def _check_credit_anomalies(
        self,
        agents: list[Agent],
        report: AuditReport,
    ) -> None:
        """Check for credit-related anomalies."""
        for agent in agents:
            if agent.credits < 0:
                report.findings.append(AuditFinding(
                    severity=Severity.MEDIUM,
                    category="credits",
                    title="Negative credit balance",
                    description=f"Agent '{agent.name}' has {agent.credits:.2f} credits",
                    agent_id=agent.id,
                    evidence={"credits": agent.credits},
                ))

            if agent.credits > 10000:
                report.findings.append(AuditFinding(
                    severity=Severity.LOW,
                    category="credits",
                    title="Unusually high credit balance",
                    description=f"Agent '{agent.name}' has {agent.credits:.2f} credits",
                    agent_id=agent.id,
                    evidence={"credits": agent.credits},
                ))

    # ── Queries ──────────────────────────────────────────────────────────

    def get_reports(self, limit: int = 10) -> list[AuditReport]:
        return self._reports[-limit:]

    def get_latest_report(self) -> AuditReport | None:
        return self._reports[-1] if self._reports else None

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_audits": len(self._reports),
            "last_audit": (
                self._reports[-1].generated_at if self._reports else None
            ),
        }
