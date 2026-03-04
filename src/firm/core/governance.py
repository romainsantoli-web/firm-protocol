"""
firm.core.governance — Governance Engine (Layer 6)

Governance in FIRM is emergent — it's not a fixed voting system,
it's a protocol for collective decision-making that evolves.

The 2-cycle validation process:
  1. Draft → Simulation #1 (what happens if we apply this?)
  2. Stress Test (what if it goes wrong?)
  3. Simulation #2 (does it still make sense after stress?)
  4. Voting (authority-weighted)
  5. Cooldown (observation period)
  6. Rollback Watch (can we undo if needed?)

Proposals can change:
  - Agent roles and permissions
  - Authority thresholds
  - Resource allocation
  - Organizational structure
  - Governance rules themselves (meta-governance)

The Constitutional Agent can veto any proposal that violates invariants.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from firm.core.agent import Agent
from firm.core.types import AgentId, ProposalId, ProposalStatus, VoteChoice

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_QUORUM_RATIO = 0.6  # 60% of eligible voters must participate
DEFAULT_APPROVAL_RATIO = 0.5  # Simple majority
COOLDOWN_SECONDS = 3600  # 1 hour cooldown after approval (configurable)
SIMULATION_TIMEOUT_S = 300  # 5 min max for simulations


# ── Vote ─────────────────────────────────────────────────────────────────────


@dataclass
class Vote:
    """A single vote on a governance proposal."""

    voter_id: AgentId
    choice: VoteChoice
    authority_weight: float  # Authority at time of voting
    reason: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def weighted_value(self) -> float:
        """Vote value weighted by authority."""
        if self.choice == VoteChoice.APPROVE:
            return self.authority_weight
        elif self.choice == VoteChoice.REJECT:
            return -self.authority_weight
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "voter_id": self.voter_id,
            "choice": self.choice.value,
            "authority_weight": round(self.authority_weight, 4),
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


# ── Proposal ─────────────────────────────────────────────────────────────────


@dataclass
class SimulationResult:
    """Result of simulating a proposal's effects."""

    success: bool
    impact_summary: str
    risk_score: float  # 0.0 (safe) to 1.0 (dangerous)
    side_effects: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "impact_summary": self.impact_summary,
            "risk_score": round(self.risk_score, 3),
            "side_effects": self.side_effects,
            "duration_ms": round(self.duration_ms, 1),
        }


@dataclass
class Proposal:
    """
    A governance proposal in the FIRM.

    Proposals go through the 2-cycle validation:
    draft → sim1 → stress → sim2 → voting → cooldown → approved/rejected
    """

    id: ProposalId = field(default_factory=lambda: ProposalId(str(uuid.uuid4())[:8]))
    proposer_id: AgentId = field(default_factory=lambda: AgentId(""))
    title: str = ""
    description: str = ""
    proposal_type: str = "general"  # "general", "role_change", "restructure", "meta_governance"
    status: ProposalStatus = ProposalStatus.DRAFT
    created_at: float = field(default_factory=time.time)

    # 2-cycle results
    simulation_1: SimulationResult | None = None
    stress_test: SimulationResult | None = None
    simulation_2: SimulationResult | None = None

    # Voting
    votes: list[Vote] = field(default_factory=list)
    quorum_ratio: float = DEFAULT_QUORUM_RATIO
    approval_ratio: float = DEFAULT_APPROVAL_RATIO

    # Lifecycle
    approved_at: float | None = None
    cooldown_until: float | None = None
    rolled_back: bool = False
    rollback_reason: str = ""
    constitutional_veto: bool = False
    veto_reason: str = ""

    # ── Lifecycle transitions ────────────────────────────────────────────

    def advance_to_simulation_1(self, result: SimulationResult) -> None:
        if self.status != ProposalStatus.DRAFT:
            raise ValueError(f"Cannot advance from {self.status} to simulation_1")
        self.simulation_1 = result
        self.status = ProposalStatus.SIMULATION_1

    def advance_to_stress_test(self, result: SimulationResult) -> None:
        if self.status != ProposalStatus.SIMULATION_1:
            raise ValueError(f"Cannot advance from {self.status} to stress_test")
        self.stress_test = result
        self.status = ProposalStatus.STRESS_TEST

    def advance_to_simulation_2(self, result: SimulationResult) -> None:
        if self.status != ProposalStatus.STRESS_TEST:
            raise ValueError(f"Cannot advance from {self.status} to simulation_2")
        self.simulation_2 = result
        self.status = ProposalStatus.SIMULATION_2

    def open_voting(self) -> None:
        if self.status != ProposalStatus.SIMULATION_2:
            raise ValueError(f"Cannot open voting from {self.status}")
        self.status = ProposalStatus.VOTING

    def cast_vote(self, vote: Vote) -> None:
        """Cast a vote. One vote per agent."""
        if self.status != ProposalStatus.VOTING:
            raise ValueError(f"Cannot vote on proposal in status {self.status}")

        # Check for duplicate votes
        existing = [v for v in self.votes if v.voter_id == vote.voter_id]
        if existing:
            raise ValueError(f"Agent {vote.voter_id} has already voted on this proposal")

        self.votes.append(vote)

    def tally_votes(self, eligible_voters: int) -> dict[str, Any]:
        """
        Tally votes and determine outcome.

        Returns the tally result without changing status.
        Uses authority-weighted voting.
        """
        if not self.votes:
            return {
                "quorum_met": False,
                "approved": False,
                "total_votes": 0,
                "eligible_voters": eligible_voters,
            }

        participation = len(self.votes) / max(eligible_voters, 1)
        quorum_met = participation >= self.quorum_ratio

        total_approve_weight = sum(
            v.authority_weight for v in self.votes if v.choice == VoteChoice.APPROVE
        )
        total_reject_weight = sum(
            v.authority_weight for v in self.votes if v.choice == VoteChoice.REJECT
        )
        total_weight = total_approve_weight + total_reject_weight

        approval_pct = total_approve_weight / max(total_weight, 0.001)
        approved = quorum_met and approval_pct >= self.approval_ratio

        return {
            "quorum_met": quorum_met,
            "approved": approved,
            "participation": round(participation, 3),
            "total_votes": len(self.votes),
            "eligible_voters": eligible_voters,
            "approve_weight": round(total_approve_weight, 4),
            "reject_weight": round(total_reject_weight, 4),
            "approval_percentage": round(approval_pct, 3),
        }

    def finalize(self, eligible_voters: int, cooldown_seconds: float = COOLDOWN_SECONDS) -> dict[str, Any]:
        """Finalize voting and transition to approved/rejected."""
        if self.status != ProposalStatus.VOTING:
            raise ValueError(f"Cannot finalize from {self.status}")

        if self.constitutional_veto:
            self.status = ProposalStatus.REJECTED
            return {
                "outcome": "rejected",
                "reason": "constitutional_veto",
                "veto_reason": self.veto_reason,
            }

        tally = self.tally_votes(eligible_voters)

        if tally["approved"]:
            self.status = ProposalStatus.COOLDOWN
            self.approved_at = time.time()
            self.cooldown_until = self.approved_at + cooldown_seconds
            return {
                "outcome": "approved_pending_cooldown",
                "cooldown_until": self.cooldown_until,
                **tally,
            }
        else:
            self.status = ProposalStatus.REJECTED
            return {"outcome": "rejected", **tally}

    def complete_cooldown(self) -> bool:
        """Check if cooldown is over and finalize approval."""
        if self.status != ProposalStatus.COOLDOWN:
            return False
        if self.cooldown_until and time.time() >= self.cooldown_until:
            self.status = ProposalStatus.APPROVED
            return True
        return False

    def rollback(self, reason: str) -> None:
        """Roll back an approved proposal."""
        if self.status not in (ProposalStatus.APPROVED, ProposalStatus.COOLDOWN):
            raise ValueError(f"Cannot rollback from {self.status}")
        self.status = ProposalStatus.ROLLED_BACK
        self.rolled_back = True
        self.rollback_reason = reason

    def veto(self, reason: str) -> None:
        """Constitutional veto — blocks the proposal permanently."""
        self.constitutional_veto = True
        self.veto_reason = reason
        if self.status == ProposalStatus.VOTING:
            self.status = ProposalStatus.REJECTED

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "proposer_id": self.proposer_id,
            "title": self.title,
            "description": self.description[:500],
            "proposal_type": self.proposal_type,
            "status": self.status.value,
            "created_at": self.created_at,
            "vote_count": len(self.votes),
            "constitutional_veto": self.constitutional_veto,
        }
        if self.simulation_1:
            result["simulation_1"] = self.simulation_1.to_dict()
        if self.stress_test:
            result["stress_test"] = self.stress_test.to_dict()
        if self.simulation_2:
            result["simulation_2"] = self.simulation_2.to_dict()
        if self.approved_at:
            result["approved_at"] = self.approved_at
        if self.rolled_back:
            result["rollback_reason"] = self.rollback_reason
        return result


# ── Governance Engine ────────────────────────────────────────────────────────


class GovernanceEngine:
    """
    Manages the lifecycle of governance proposals in a FIRM.

    Orchestrates the 2-cycle validation process and ensures
    all proposals pass Constitutional review.
    """

    def __init__(
        self,
        quorum_ratio: float = DEFAULT_QUORUM_RATIO,
        approval_ratio: float = DEFAULT_APPROVAL_RATIO,
        cooldown_seconds: float = COOLDOWN_SECONDS,
    ) -> None:
        self.quorum_ratio = quorum_ratio
        self.approval_ratio = approval_ratio
        self.cooldown_seconds = cooldown_seconds
        self._proposals: dict[str, Proposal] = {}

    def create_proposal(
        self,
        proposer: Agent,
        title: str,
        description: str,
        proposal_type: str = "general",
        min_authority: float = 0.8,
    ) -> Proposal:
        """
        Create a new governance proposal.

        Only agents with sufficient authority can propose.
        """
        if proposer.authority < min_authority:
            raise PermissionError(
                f"Agent {proposer.id} authority ({proposer.authority:.4f}) "
                f"below proposal threshold ({min_authority})"
            )

        proposal = Proposal(
            proposer_id=proposer.id,
            title=title,
            description=description,
            proposal_type=proposal_type,
            quorum_ratio=self.quorum_ratio,
            approval_ratio=self.approval_ratio,
        )
        self._proposals[proposal.id] = proposal
        logger.info(
            "Proposal %s created by %s: %s", proposal.id, proposer.id, title,
        )
        return proposal

    def simulate(self, proposal: Proposal, result: SimulationResult) -> None:
        """Advance a proposal through its simulation phases."""
        if proposal.status == ProposalStatus.DRAFT:
            proposal.advance_to_simulation_1(result)
        elif proposal.status == ProposalStatus.SIMULATION_1:
            proposal.advance_to_stress_test(result)
        elif proposal.status == ProposalStatus.STRESS_TEST:
            proposal.advance_to_simulation_2(result)
        else:
            raise ValueError(f"Cannot simulate from status {proposal.status}")

    def open_voting(self, proposal: Proposal) -> None:
        """Open a proposal for voting after simulation passes."""
        proposal.open_voting()

    def vote(
        self,
        proposal: Proposal,
        voter: Agent,
        choice: VoteChoice,
        reason: str = "",
        min_authority: float = 0.6,
    ) -> Vote:
        """Cast an authority-weighted vote."""
        if voter.authority < min_authority:
            raise PermissionError(
                f"Agent {voter.id} authority ({voter.authority:.4f}) "
                f"below voting threshold ({min_authority})"
            )

        v = Vote(
            voter_id=voter.id,
            choice=choice,
            authority_weight=voter.authority,
            reason=reason,
        )
        proposal.cast_vote(v)
        return v

    def finalize(self, proposal: Proposal, eligible_voters: int) -> dict[str, Any]:
        """Finalize voting on a proposal."""
        return proposal.finalize(eligible_voters, self.cooldown_seconds)

    def get_proposal(self, proposal_id: str) -> Proposal | None:
        return self._proposals.get(proposal_id)

    def get_active_proposals(self) -> list[dict[str, Any]]:
        """Get all non-terminal proposals."""
        terminal = {ProposalStatus.APPROVED, ProposalStatus.REJECTED, ProposalStatus.ROLLED_BACK}
        return [
            p.to_dict()
            for p in self._proposals.values()
            if p.status not in terminal
        ]

    def get_all_proposals(self, limit: int = 50) -> list[dict[str, Any]]:
        proposals = list(self._proposals.values())
        proposals.sort(key=lambda p: p.created_at, reverse=True)
        return [p.to_dict() for p in proposals[:limit]]
