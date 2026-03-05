"""
firm.core.authority — Authority Engine (Layer 0)

Authority in FIRM is earned, never assigned.
It uses a Hebbian-inspired formula:

    new_authority = old + (learning_rate × activation) - (decay × (1 - activation))

Where:
    - activation = 1.0 on success, 0.0 on failure
    - learning_rate controls how fast authority grows
    - decay controls how fast unused authority fades

Authority directly determines:
    - Voting weight in governance
    - Resource allocation priority
    - Trust level from other agents
    - Proposal approval thresholds

Thresholds:
    - >= 0.8: Can propose structural changes
    - >= 0.6: Can vote on proposals
    - >= 0.4: Standard operations
    - < 0.3: Probation — Constitutional Agent intervenes
    - == 0.0: Terminated
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

from firm.core.agent import Agent
from firm.core.types import AgentId, Severity

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_LEARNING_RATE = 0.05
DEFAULT_DECAY = 0.02
AUTHORITY_MIN = 0.0
AUTHORITY_MAX = 1.0

THRESHOLD_PROPOSE = 0.8
THRESHOLD_VOTE = 0.6
THRESHOLD_STANDARD = 0.4
THRESHOLD_PROBATION = 0.3
THRESHOLD_TERMINATE = 0.05


@dataclass
class AuthorityChange:
    """Record of a single authority change event."""

    agent_id: AgentId
    old_value: float
    new_value: float
    delta: float
    reason: str
    triggered_by: str  # "success", "failure", "decay", "governance", "constitutional"
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "old_value": round(self.old_value, 4),
            "new_value": round(self.new_value, 4),
            "delta": round(self.delta, 4),
            "reason": self.reason,
            "triggered_by": self.triggered_by,
            "timestamp": self.timestamp,
        }


class AuthorityEngine:
    """
    Computes and maintains authority scores for all agents in a FIRM.

    The engine is deterministic: given the same sequence of events,
    it always produces the same authority scores. This is critical
    for auditability and reproducibility.
    """

    def __init__(
        self,
        learning_rate: float = DEFAULT_LEARNING_RATE,
        decay: float = DEFAULT_DECAY,
    ) -> None:
        if not (0.0 < learning_rate <= 1.0):
            raise ValueError(f"learning_rate must be in (0, 1], got {learning_rate}")
        if not (0.0 < decay <= 1.0):
            raise ValueError(f"decay must be in (0, 1], got {decay}")

        self.learning_rate = learning_rate
        self.decay = decay
        self._history: list[AuthorityChange] = []

    # ── Core computation ─────────────────────────────────────────────────

    def compute_delta(
        self,
        activated: bool,
        calibration_bonus: float = 0.0,
    ) -> float:
        """
        Compute the authority delta for a single event.

        Extended Hebbian formula:
            delta = (lr × activation × (1 + calibration_bonus)) - (decay × (1 - activation))

        Where calibration_bonus ∈ [0, 1] comes from the agent's prediction
        market calibration score (0 = no bonus, 1 = double learning).

        Success (activated=True):  delta = +learning_rate × (1 + bonus)
        Failure (activated=False): delta = -decay
        """
        activation = 1.0 if activated else 0.0
        bonus = max(0.0, min(1.0, calibration_bonus))
        return (self.learning_rate * activation * (1.0 + bonus)) - (self.decay * (1.0 - activation))

    def update(
        self,
        agent: Agent,
        success: bool,
        reason: str = "",
        calibration_bonus: float = 0.0,
    ) -> AuthorityChange:
        """
        Update an agent's authority based on a success/failure event.

        The calibration_bonus (from prediction markets) amplifies learning
        for well-calibrated agents.

        Returns the AuthorityChange record.
        """
        old = agent.authority
        delta = self.compute_delta(success, calibration_bonus=calibration_bonus)
        new = max(AUTHORITY_MIN, min(AUTHORITY_MAX, old + delta))
        new = round(new, 4)

        agent.authority = new

        if success:
            agent.record_success()
        else:
            agent.record_failure()

        change = AuthorityChange(
            agent_id=agent.id,
            old_value=old,
            new_value=new,
            delta=round(new - old, 4),
            reason=reason,
            triggered_by="success" if success else "failure",
        )
        self._history.append(change)

        # Check thresholds
        if new < THRESHOLD_PROBATION and old >= THRESHOLD_PROBATION:
            logger.warning(
                "Agent %s dropped below probation threshold (%.4f → %.4f)",
                agent.id, old, new,
            )

        return change

    def apply_decay(self, agents: list[Agent], reason: str = "periodic_decay") -> list[AuthorityChange]:
        """
        Apply decay to all agents that haven't acted recently.

        This prevents authority from being "banked" — you must keep
        contributing to maintain your score.
        """
        changes = []
        for agent in agents:
            if not agent.is_active:
                continue

            old = agent.authority
            new = max(AUTHORITY_MIN, old - self.decay)
            new = round(new, 4)

            if new != old:
                agent.authority = new
                change = AuthorityChange(
                    agent_id=agent.id,
                    old_value=old,
                    new_value=new,
                    delta=round(new - old, 4),
                    reason=reason,
                    triggered_by="decay",
                )
                self._history.append(change)
                changes.append(change)

        return changes

    def set_authority(
        self,
        agent: Agent,
        value: float,
        reason: str,
        triggered_by: str = "governance",
    ) -> AuthorityChange:
        """
        Directly set an agent's authority (governance override).

        This should only be used by governance proposals or the
        Constitutional Agent, never by agents themselves.
        """
        old = agent.authority
        new = max(AUTHORITY_MIN, min(AUTHORITY_MAX, round(value, 4)))
        agent.authority = new

        change = AuthorityChange(
            agent_id=agent.id,
            old_value=old,
            new_value=new,
            delta=round(new - old, 4),
            reason=reason,
            triggered_by=triggered_by,
        )
        self._history.append(change)
        return change

    # ── Queries ──────────────────────────────────────────────────────────

    def can_propose(self, agent: Agent) -> bool:
        """Can this agent submit governance proposals?"""
        return agent.is_active and agent.authority >= THRESHOLD_PROPOSE

    def can_vote(self, agent: Agent) -> bool:
        """Can this agent vote on proposals?"""
        return agent.is_active and agent.authority >= THRESHOLD_VOTE

    def needs_probation(self, agent: Agent) -> bool:
        """Should this agent be placed on probation?"""
        return agent.is_active and agent.authority < THRESHOLD_PROBATION

    def should_terminate(self, agent: Agent) -> bool:
        """Should this agent be terminated?"""
        return agent.authority <= THRESHOLD_TERMINATE

    def get_ranking(self, agents: list[Agent]) -> list[tuple[AgentId, float]]:
        """Rank agents by authority score (descending)."""
        active = [(a.id, a.authority) for a in agents if a.is_active]
        return sorted(active, key=lambda x: x[1], reverse=True)

    @staticmethod
    def sqrt_authority(authority: float) -> float:
        """√authority for anti-oligarchy voting weight.

        An agent with authority 0.81 has voting weight 0.9 — the gap
        between top and bottom is compressed, preventing runaway
        concentration.
        """
        return math.sqrt(max(0.0, authority))

    def effective_vote_weight(
        self,
        agent: Agent,
        calibration_score: float = 1.0,
    ) -> float:
        """Compute vote weight = √authority × calibration_score.

        This is the weight used in governance votes and prediction
        aggregation. Higher calibration amplifies the weight.
        """
        return self.sqrt_authority(agent.authority) * calibration_score

    def get_history(
        self,
        agent_id: AgentId | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get authority change history, optionally filtered by agent."""
        history = self._history
        if agent_id:
            history = [h for h in history if h.agent_id == agent_id]
        return [h.to_dict() for h in history[-limit:]]

    def assess_health(self, agents: list[Agent]) -> dict[str, Any]:
        """
        Assess the overall authority health of the organization.

        Returns warnings if:
        - Too many agents near probation
        - Authority is too concentrated
        - No agents can propose changes
        """
        active = [a for a in agents if a.is_active]
        if not active:
            return {
                "healthy": False,
                "severity": Severity.CRITICAL.value,
                "findings": ["No active agents in the organization"],
            }

        authorities = [a.authority for a in active]
        mean_auth = sum(authorities) / len(authorities)
        max_auth = max(authorities)
        min_auth = min(authorities)

        near_probation = [a for a in active if a.authority < THRESHOLD_PROBATION]
        can_propose = [a for a in active if a.authority >= THRESHOLD_PROPOSE]
        can_vote = [a for a in active if a.authority >= THRESHOLD_VOTE]

        findings: list[dict[str, Any]] = []

        # No proposers
        if not can_propose:
            findings.append({
                "severity": Severity.CRITICAL.value,
                "check": "no_proposers",
                "message": "No agents can propose governance changes",
                "action": "Constitutional Agent should bootstrap governance",
            })

        # No voters
        if not can_vote:
            findings.append({
                "severity": Severity.CRITICAL.value,
                "check": "no_voters",
                "message": "No agents can vote on proposals",
                "action": "Constitutional Agent should raise authority of best performers",
            })

        # Too many on probation
        probation_ratio = len(near_probation) / len(active)
        if probation_ratio > 0.5:
            findings.append({
                "severity": Severity.HIGH.value,
                "check": "mass_probation",
                "message": f"{len(near_probation)}/{len(active)} agents near probation",
                "probation_ratio": round(probation_ratio, 2),
            })

        # Authority concentration (Gini-like)
        if len(active) >= 3 and max_auth - min_auth > 0.6:
            findings.append({
                "severity": Severity.MEDIUM.value,
                "check": "authority_concentration",
                "message": f"Authority gap too wide: max={max_auth:.2f}, min={min_auth:.2f}",
            })

        worst_severity = Severity.INFO
        for f in findings:
            sev = Severity(f["severity"])
            if list(Severity).index(sev) < list(Severity).index(worst_severity):
                worst_severity = sev

        return {
            "healthy": len(findings) == 0,
            "severity": worst_severity.value,
            "agent_count": len(active),
            "mean_authority": round(mean_auth, 4),
            "max_authority": round(max_auth, 4),
            "min_authority": round(min_auth, 4),
            "can_propose_count": len(can_propose),
            "can_vote_count": len(can_vote),
            "near_probation_count": len(near_probation),
            "findings": findings,
        }
