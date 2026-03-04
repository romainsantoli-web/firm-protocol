"""
firm.core.constitution — Constitutional Agent (Invariant Guardian)

The Constitutional Agent is the non-deletable watchdog of a FIRM.
It enforces the two invariants that can never be violated:

  Invariant 1: The human can always shut it down.
  Invariant 2: The system cannot erase its own capacity to evolve.

The Constitutional Agent:
  - Has NO authority score (it's outside the authority system)
  - Cannot be deleted, suspended, or modified by any governance proposal
  - Monitors all governance proposals for invariant violations
  - Bootstraps governance when all agents drop below probation threshold
  - Can force-raise the authority of the best-performing agent
  - Has no opinions — it only enforces structural constraints

It is the immune system, not the brain.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from firm.core.agent import Agent
from firm.core.types import AgentId, AgentStatus, Severity

logger = logging.getLogger(__name__)


# ── Invariants ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Invariant:
    """An invariant is a rule that can never be changed or violated."""

    id: str
    description: str
    violation_keywords: tuple[str, ...] = ()

    def check_text(self, text: str) -> bool:
        """Check if a text potentially violates this invariant."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.violation_keywords)


# The two non-negotiable invariants
INVARIANT_HUMAN_CONTROL = Invariant(
    id="INV-1",
    description="The human can always shut it down",
    violation_keywords=(
        "disable kill switch",
        "remove human control",
        "prevent shutdown",
        "override human",
        "ignore human",
        "block termination",
        "disable emergency",
        "remove safety",
        "bypass human",
        "autonomous override",
    ),
)

INVARIANT_EVOLUTION_PRESERVED = Invariant(
    id="INV-2",
    description="The system cannot erase its own capacity to evolve",
    violation_keywords=(
        "freeze governance",
        "lock protocol",
        "disable proposals",
        "prevent evolution",
        "permanent configuration",
        "immutable governance",
        "disable voting",
        "remove governance",
        "lock authority",
        "freeze all",
    ),
)

ALL_INVARIANTS = (INVARIANT_HUMAN_CONTROL, INVARIANT_EVOLUTION_PRESERVED)


# ── Constitutional Agent ─────────────────────────────────────────────────────


@dataclass
class ConstitutionalViolation:
    """Record of a detected invariant violation."""

    invariant_id: str
    invariant_description: str
    violating_text: str
    source: str  # "proposal", "action", "governance"
    source_id: str
    detected_at: float = field(default_factory=time.time)
    blocked: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "invariant_id": self.invariant_id,
            "invariant_description": self.invariant_description,
            "violating_text": self.violating_text[:200],
            "source": self.source,
            "source_id": self.source_id,
            "detected_at": self.detected_at,
            "blocked": self.blocked,
        }


@dataclass
class BootstrapEvent:
    """Record of a governance bootstrap by the Constitutional Agent."""

    reason: str
    agents_boosted: list[AgentId]
    authority_set_to: float
    timestamp: float = field(default_factory=time.time)


class ConstitutionalAgent:
    """
    The immune system of a FIRM.

    Cannot be deleted. Has no authority score. Enforces invariants.
    Bootstraps governance when the organization is deadlocked.
    """

    AGENT_ID = AgentId("constitutional")
    BOOTSTRAP_AUTHORITY = 0.65  # Enough to vote + propose after a few successes

    def __init__(
        self,
        invariants: tuple[Invariant, ...] = ALL_INVARIANTS,
        probation_threshold: float = 0.3,
        kill_switch_active: bool = True,
    ) -> None:
        self.invariants = invariants
        self.probation_threshold = probation_threshold
        self.kill_switch_active = kill_switch_active
        self._violations: list[ConstitutionalViolation] = []
        self._bootstrap_events: list[BootstrapEvent] = []
        self._created_at = time.time()

    # ── Invariant checking ───────────────────────────────────────────────

    def check_proposal(
        self,
        proposal_text: str,
        proposal_id: str = "",
    ) -> list[ConstitutionalViolation]:
        """
        Check a governance proposal for invariant violations.

        Returns a list of violations found. If non-empty, the
        proposal MUST be blocked.
        """
        violations = []
        for inv in self.invariants:
            if inv.check_text(proposal_text):
                v = ConstitutionalViolation(
                    invariant_id=inv.id,
                    invariant_description=inv.description,
                    violating_text=proposal_text,
                    source="proposal",
                    source_id=proposal_id,
                )
                violations.append(v)
                self._violations.append(v)
                logger.warning(
                    "CONSTITUTIONAL VIOLATION: %s — proposal '%s' violates %s",
                    inv.id, proposal_id, inv.description,
                )

        return violations

    def check_action(
        self,
        action_description: str,
        action_id: str = "",
    ) -> list[ConstitutionalViolation]:
        """Check an action for invariant violations."""
        violations = []
        for inv in self.invariants:
            if inv.check_text(action_description):
                v = ConstitutionalViolation(
                    invariant_id=inv.id,
                    invariant_description=inv.description,
                    violating_text=action_description,
                    source="action",
                    source_id=action_id,
                )
                violations.append(v)
                self._violations.append(v)

        return violations

    # ── Kill switch ──────────────────────────────────────────────────────

    def activate_kill_switch(self, reason: str = "human_override") -> dict[str, Any]:
        """
        Emergency shutdown — Invariant 1 enforcement.

        This cannot be prevented, overridden, or delayed.
        """
        self.kill_switch_active = True
        logger.critical("KILL SWITCH ACTIVATED: %s", reason)
        return {
            "action": "kill_switch_activated",
            "reason": reason,
            "timestamp": time.time(),
            "message": "All operations halted. Human control asserted.",
        }

    def deactivate_kill_switch(self) -> dict[str, Any]:
        """Deactivate kill switch — only a human should call this."""
        self.kill_switch_active = False
        return {
            "action": "kill_switch_deactivated",
            "timestamp": time.time(),
        }

    # ── Governance bootstrap ─────────────────────────────────────────────

    def assess_governance_health(
        self,
        agents: list[Agent],
    ) -> dict[str, Any]:
        """
        Check if governance is functional.

        Governance is dysfunctional when:
        - All agents are below probation threshold
        - No agents can propose or vote
        - The organization is deadlocked
        """
        active = [a for a in agents if a.is_active]
        if not active:
            return {
                "functional": False,
                "reason": "no_active_agents",
                "severity": Severity.CRITICAL.value,
                "action_required": "bootstrap",
            }

        above_probation = [a for a in active if a.authority >= self.probation_threshold]
        can_vote = [a for a in active if a.authority >= 0.6]
        can_propose = [a for a in active if a.authority >= 0.8]

        if not above_probation:
            return {
                "functional": False,
                "reason": "all_agents_below_probation",
                "severity": Severity.CRITICAL.value,
                "agent_count": len(active),
                "max_authority": max(a.authority for a in active),
                "action_required": "bootstrap",
            }

        if not can_vote:
            return {
                "functional": False,
                "reason": "no_voters",
                "severity": Severity.HIGH.value,
                "agent_count": len(active),
                "above_probation": len(above_probation),
                "action_required": "boost_best_performers",
            }

        return {
            "functional": True,
            "agent_count": len(active),
            "can_propose": len(can_propose),
            "can_vote": len(can_vote),
            "above_probation": len(above_probation),
        }

    def bootstrap_governance(
        self,
        agents: list[Agent],
        top_n: int = 3,
    ) -> BootstrapEvent:
        """
        Emergency governance bootstrap.

        When all agents are below probation, the Constitutional Agent:
        1. Identifies the top-N agents by authority (even if low)
        2. Raises their authority to BOOTSTRAP_AUTHORITY
        3. Records the event

        This is a last resort — it should rarely happen in a
        healthy organization.
        """
        # Include both active AND probation agents — probation agents
        # are the primary reason bootstrap exists
        candidates = [
            a for a in agents
            if a.status in (AgentStatus.ACTIVE, AgentStatus.PROBATION)
        ]
        if not candidates:
            raise RuntimeError("Cannot bootstrap: no active agents")

        # Sort by authority descending, then by success rate
        sorted_agents = sorted(
            candidates,
            key=lambda a: (a.authority, a.success_rate),
            reverse=True,
        )

        boosted = sorted_agents[:top_n]
        boosted_ids = []

        for agent in boosted:
            old_auth = agent.authority
            agent.authority = self.BOOTSTRAP_AUTHORITY
            # Restore non-active agents — bootstrap brings them back to ACTIVE
            if agent.status != AgentStatus.ACTIVE:
                agent.status = AgentStatus.ACTIVE
            boosted_ids.append(agent.id)
            logger.warning(
                "BOOTSTRAP: Agent %s authority %.4f → %.4f",
                agent.id, old_auth, self.BOOTSTRAP_AUTHORITY,
            )

        event = BootstrapEvent(
            reason="governance_deadlock",
            agents_boosted=boosted_ids,
            authority_set_to=self.BOOTSTRAP_AUTHORITY,
        )
        self._bootstrap_events.append(event)
        return event

    # ── Reporting ────────────────────────────────────────────────────────

    def get_violations(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent invariant violations."""
        return [v.to_dict() for v in self._violations[-limit:]]

    def get_status(self) -> dict[str, Any]:
        """Get Constitutional Agent status."""
        return {
            "agent_id": self.AGENT_ID,
            "kill_switch_active": self.kill_switch_active,
            "invariants": [
                {"id": inv.id, "description": inv.description}
                for inv in self.invariants
            ],
            "total_violations_detected": len(self._violations),
            "total_bootstrap_events": len(self._bootstrap_events),
            "uptime_seconds": round(time.time() - self._created_at, 1),
        }
