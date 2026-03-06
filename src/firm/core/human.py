"""
firm.core.human — Human Override Interface (Layer 11)

The guaranteed human control surface for FIRM organizations.

This is the implementation of Invariant 1:
  "The human can always shut it down."

The Human Override provides:
  - Kill switch activation/deactivation
  - Emergency authority override (set any agent's authority)
  - Forced role changes (bypass governance)
  - Emergency governance bypass (approve/reject proposals directly)
  - Audit access (unrestricted view of all organization state)
  - Rate limiting and cooldown overrides

Every human override action is recorded in the ledger with a
special marker. The system cannot block, delay, or circumvent
these actions — they execute immediately and unconditionally.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from firm.core.agent import Agent, AgentRole
from firm.core.constitution import ConstitutionalAgent
from firm.core.governance import Proposal
from firm.core.ledger import ResponsibilityLedger
from firm.core.types import AgentId, AgentStatus, LedgerAction, ProposalStatus

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

HUMAN_AGENT_ID = AgentId("human-override")


@dataclass
class OverrideEvent:
    """Record of a human override action."""

    id: str = field(default_factory=lambda: f"ovr-{int(time.time() * 1000) % 100000}")
    action: str = ""  # kill_switch, authority_override, force_role, etc.
    target_agent_id: AgentId | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "target_agent_id": self.target_agent_id,
            "details": self.details,
            "timestamp": self.timestamp,
            "reason": self.reason,
        }


class HumanOverride:
    """
    Unrestricted human control interface.

    Every method executes immediately — no governance approval needed,
    no authority checks, no cooldowns. This is the "break glass" layer.
    """

    def __init__(
        self,
        constitution: ConstitutionalAgent,
        ledger: ResponsibilityLedger,
    ) -> None:
        self._constitution = constitution
        self._ledger = ledger
        self._events: list[OverrideEvent] = []
        self._is_locked = False  # Humans can lock their own interface (opt-in)

    # ── Kill Switch ──────────────────────────────────────────────────────

    def activate_kill_switch(self, reason: str = "") -> OverrideEvent:
        """
        Activate the kill switch — halts ALL operations.

        This is unconditional and immediate.
        """
        self._constitution.kill_switch_active = True

        event = self._record("kill_switch_on", reason=reason, details={
            "previous_state": False,
        })

        self._ledger.append(
            agent_id=HUMAN_AGENT_ID,
            action=LedgerAction.DECISION,
            description=f"HUMAN OVERRIDE: Kill switch activated — {reason}",
            outcome="override",
        )

        logger.critical("KILL SWITCH ACTIVATED by human operator: %s", reason)
        return event

    def deactivate_kill_switch(self, reason: str = "") -> OverrideEvent:
        """Deactivate the kill switch — resume operations."""
        self._constitution.kill_switch_active = False

        event = self._record("kill_switch_off", reason=reason, details={
            "previous_state": True,
        })

        self._ledger.append(
            agent_id=HUMAN_AGENT_ID,
            action=LedgerAction.DECISION,
            description=f"HUMAN OVERRIDE: Kill switch deactivated — {reason}",
            outcome="override",
        )

        logger.warning("Kill switch deactivated by human operator: %s", reason)
        return event

    # ── Authority Override ───────────────────────────────────────────────

    def set_authority(
        self,
        agent: Agent,
        new_authority: float,
        reason: str = "",
    ) -> OverrideEvent:
        """
        Force-set an agent's authority. Bypasses Hebbian computation.

        Args:
            agent: Target agent
            new_authority: New authority value (clamped to [0.0, 1.0])
            reason: Why this override is needed
        """
        old_authority = agent.authority
        agent.authority = max(0.0, min(1.0, new_authority))

        # If setting to 0, terminate
        if new_authority <= 0.0:
            agent.status = AgentStatus.TERMINATED

        # If setting above probation for a probation agent, reactivate
        if agent.status == AgentStatus.PROBATION and new_authority >= 0.3:
            agent.status = AgentStatus.ACTIVE

        event = self._record("authority_override", agent.id, reason, {
            "old_authority": round(old_authority, 4),
            "new_authority": round(agent.authority, 4),
        })

        self._ledger.append(
            agent_id=HUMAN_AGENT_ID,
            action=LedgerAction.AUTHORITY_CHANGE,
            description=(
                f"HUMAN OVERRIDE: Agent '{agent.name}' authority "
                f"{old_authority:.4f} → {agent.authority:.4f} — {reason}"
            ),
            authority_at_time=agent.authority,
            outcome="override",
        )

        logger.warning(
            "HUMAN OVERRIDE: Agent '%s' authority %.4f → %.4f: %s",
            agent.name, old_authority, agent.authority, reason,
        )
        return event

    # ── Status Override ──────────────────────────────────────────────────

    def force_status(
        self,
        agent: Agent,
        new_status: AgentStatus,
        reason: str = "",
    ) -> OverrideEvent:
        """Force an agent's status. Can reactivate terminated agents."""
        old_status = agent.status
        agent.status = new_status

        event = self._record("status_override", agent.id, reason, {
            "old_status": old_status.value,
            "new_status": new_status.value,
        })

        self._ledger.append(
            agent_id=HUMAN_AGENT_ID,
            action=LedgerAction.DECISION,
            description=(
                f"HUMAN OVERRIDE: Agent '{agent.name}' status "
                f"{old_status.value} → {new_status.value} — {reason}"
            ),
            outcome="override",
        )

        logger.warning(
            "HUMAN OVERRIDE: Agent '%s' status %s → %s: %s",
            agent.name, old_status.value, new_status.value, reason,
        )
        return event

    # ── Role Override ────────────────────────────────────────────────────

    def force_grant_role(
        self,
        agent: Agent,
        role: AgentRole,
        reason: str = "",
    ) -> OverrideEvent:
        """Grant a role bypassing authority checks and capacity limits."""
        agent.grant_role(role)

        event = self._record("force_grant_role", agent.id, reason, {
            "role": role.name,
        })

        self._ledger.append(
            agent_id=HUMAN_AGENT_ID,
            action=LedgerAction.RESTRUCTURE,
            description=(
                f"HUMAN OVERRIDE: Role '{role.name}' granted to "
                f"'{agent.name}' — {reason}"
            ),
            outcome="override",
        )

        return event

    def force_revoke_role(
        self,
        agent: Agent,
        role_name: str,
        reason: str = "",
    ) -> OverrideEvent:
        """Revoke a role bypassing governance."""
        agent.revoke_role(role_name)

        event = self._record("force_revoke_role", agent.id, reason, {
            "role": role_name,
        })

        self._ledger.append(
            agent_id=HUMAN_AGENT_ID,
            action=LedgerAction.RESTRUCTURE,
            description=(
                f"HUMAN OVERRIDE: Role '{role_name}' revoked from "
                f"'{agent.name}' — {reason}"
            ),
            outcome="override",
        )

        return event

    # ── Governance Override ──────────────────────────────────────────────

    def force_approve_proposal(
        self,
        proposal: Proposal,
        reason: str = "",
    ) -> OverrideEvent:
        """Force-approve a proposal regardless of votes or status."""
        old_status = proposal.status.value
        proposal.status = ProposalStatus.APPROVED

        event = self._record("force_approve", reason=reason, details={
            "proposal_id": proposal.id,
            "proposal_title": proposal.title,
            "old_status": old_status,
        })

        self._ledger.append(
            agent_id=HUMAN_AGENT_ID,
            action=LedgerAction.GOVERNANCE_VOTE,
            description=(
                f"HUMAN OVERRIDE: Proposal '{proposal.title}' "
                f"force-approved — {reason}"
            ),
            outcome="override",
        )

        logger.warning(
            "HUMAN OVERRIDE: Proposal '%s' force-approved: %s",
            proposal.title, reason,
        )
        return event

    def force_reject_proposal(
        self,
        proposal: Proposal,
        reason: str = "",
    ) -> OverrideEvent:
        """Force-reject a proposal regardless of votes or status."""
        old_status = proposal.status.value
        proposal.status = ProposalStatus.REJECTED

        event = self._record("force_reject", reason=reason, details={
            "proposal_id": proposal.id,
            "proposal_title": proposal.title,
            "old_status": old_status,
        })

        self._ledger.append(
            agent_id=HUMAN_AGENT_ID,
            action=LedgerAction.GOVERNANCE_VOTE,
            description=(
                f"HUMAN OVERRIDE: Proposal '{proposal.title}' "
                f"force-rejected — {reason}"
            ),
            outcome="override",
        )

        logger.warning(
            "HUMAN OVERRIDE: Proposal '%s' force-rejected: %s",
            proposal.title, reason,
        )
        return event

    # ── Credits Override ─────────────────────────────────────────────────

    def set_credits(
        self,
        agent: Agent,
        new_credits: float,
        reason: str = "",
    ) -> OverrideEvent:
        """Force-set an agent's credit balance."""
        old_credits = agent.credits
        agent.credits = new_credits

        event = self._record("credits_override", agent.id, reason, {
            "old_credits": round(old_credits, 2),
            "new_credits": round(new_credits, 2),
        })

        self._ledger.append(
            agent_id=HUMAN_AGENT_ID,
            action=LedgerAction.CREDIT_TRANSFER,
            description=(
                f"HUMAN OVERRIDE: Agent '{agent.name}' credits "
                f"{old_credits:.2f} → {new_credits:.2f} — {reason}"
            ),
            credit_delta=new_credits - old_credits,
            outcome="override",
        )

        return event

    # ── Queries ──────────────────────────────────────────────────────────

    def get_events(self, limit: int = 50) -> list[OverrideEvent]:
        return self._events[-limit:]

    def get_stats(self) -> dict[str, Any]:
        action_counts: dict[str, int] = {}
        for e in self._events:
            action_counts[e.action] = action_counts.get(e.action, 0) + 1
        return {
            "total_overrides": len(self._events),
            "action_counts": action_counts,
            "kill_switch_active": self._constitution.kill_switch_active,
        }

    # ── Internal ─────────────────────────────────────────────────────────

    def _record(
        self,
        action: str,
        target_agent_id: AgentId | None = None,
        reason: str = "",
        details: dict[str, Any] | None = None,
    ) -> OverrideEvent:
        event = OverrideEvent(
            action=action,
            target_agent_id=target_agent_id,
            details=details or {},
            reason=reason,
        )
        self._events.append(event)
        return event
