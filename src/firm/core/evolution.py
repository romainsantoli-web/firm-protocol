"""
firm.core.evolution — Evolution Engine

The Evolution Engine is FIRM's self-modification layer.
It allows the organization to change its own operating parameters
through governance — learning rates, authority thresholds, decay
rates, quorum ratios, and cooldown periods.

This is what makes FIRM truly self-evolving: the rules that govern
the organization are themselves subject to governance.

Constraints:
  - Parameters have hard bounds (safety rails) that cannot be bypassed
  - Every parameter change is recorded with before/after values
  - Changes require supermajority (>= 75% weighted approval)
  - Rollback is supported: any evolution can be reverted
  - Rate limiting: max 1 parameter change per category per cycle

The Evolution Engine does NOT modify the Constitutional invariants.
That's the Meta-Constitutional layer's responsibility.
"""

from __future__ import annotations

import enum
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from firm.core.types import AgentId

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

# Minimum authority to propose a parameter evolution
MIN_AUTHORITY_TO_EVOLVE = 0.85

# Supermajority required for parameter changes
EVOLUTION_APPROVAL_RATIO = 0.75

# Cooldown between changes to the same parameter (seconds)
PARAMETER_CHANGE_COOLDOWN = 7200  # 2 hours


class ParameterCategory(str, enum.Enum):
    """Categories of evolvable parameters."""

    AUTHORITY = "authority"       # learning_rate, decay, thresholds
    GOVERNANCE = "governance"    # quorum_ratio, approval_ratio, cooldown
    ECONOMY = "economy"          # credit rewards, penalties, transfer fees
    SPAWN = "spawn"              # spawn authority fraction, merge ratio
    MEMORY = "memory"            # decay rate, conflict threshold


class EvolutionStatus(str, enum.Enum):
    """Status of an evolution proposal."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


# Hard safety bounds — these CANNOT be bypassed by governance
PARAMETER_BOUNDS: dict[str, dict[str, tuple[float, float]]] = {
    "authority": {
        "learning_rate": (0.001, 0.5),      # Can't learn too fast or too slow
        "decay": (0.001, 0.2),              # Decay must exist but can't be brutal
        "passive_decay_rate": (0.0001, 0.01),
        "threshold_propose": (0.5, 0.95),   # Must be achievable but exclusive
        "threshold_vote": (0.3, 0.9),       # Voting must be somewhat accessible
        "threshold_standard": (0.2, 0.7),
        "threshold_probation": (0.1, 0.5),
        "threshold_terminate": (0.01, 0.15),
    },
    "governance": {
        "quorum_ratio": (0.3, 0.9),         # At least 30%, at most 90%
        "approval_ratio": (0.5, 0.9),       # Simple majority minimum
        "cooldown_seconds": (300, 86400),    # 5 min to 24 hours
    },
    "economy": {
        "success_reward": (0.1, 100.0),
        "failure_penalty": (-100.0, -0.1),
        "transfer_fee_rate": (0.0, 0.5),    # 0% to 50% transaction fee
    },
    "spawn": {
        "authority_fraction": (0.1, 0.8),    # Child gets 10%-80% of parent
        "min_authority_to_spawn": (0.3, 0.9),
    },
    "memory": {
        "decay_rate": (0.001, 0.3),
        "conflict_threshold": (0.1, 0.9),
    },
}


@dataclass
class ParameterChange:
    """A single parameter modification."""

    category: ParameterCategory
    parameter_name: str
    old_value: float
    new_value: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "parameter_name": self.parameter_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }


@dataclass
class EvolutionProposal:
    """
    A proposal to evolve one or more FIRM parameters.

    Evolution proposals are more restricted than regular governance
    proposals — they require supermajority and have hard bounds.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    proposer_id: AgentId = field(default_factory=lambda: AgentId(""))
    changes: list[ParameterChange] = field(default_factory=list)
    rationale: str = ""
    status: EvolutionStatus = EvolutionStatus.PROPOSED
    created_at: float = field(default_factory=time.time)
    decided_at: float | None = None
    applied_at: float | None = None

    # Voting
    votes_for: float = 0.0     # Weighted approval
    votes_against: float = 0.0  # Weighted rejection
    voter_ids: list[AgentId] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "proposer_id": self.proposer_id,
            "changes": [c.to_dict() for c in self.changes],
            "rationale": self.rationale,
            "status": self.status.value,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "applied_at": self.applied_at,
            "votes_for": round(self.votes_for, 4),
            "votes_against": round(self.votes_against, 4),
            "voter_count": len(self.voter_ids),
        }


class EvolutionEngine:
    """
    Manages parameter evolution for a FIRM.

    The engine:
    1. Validates proposed changes against hard bounds
    2. Tracks voting with supermajority requirement
    3. Applies approved changes to a parameter store
    4. Supports rollback of any applied evolution
    5. Rate-limits changes per category
    """

    def __init__(self) -> None:
        # Current parameter values — this is the "genome" of the FIRM
        self._parameters: dict[str, dict[str, float]] = {
            "authority": {
                "learning_rate": 0.05,
                "decay": 0.02,
                "passive_decay_rate": 0.001,
                "threshold_propose": 0.8,
                "threshold_vote": 0.6,
                "threshold_standard": 0.4,
                "threshold_probation": 0.3,
                "threshold_terminate": 0.05,
            },
            "governance": {
                "quorum_ratio": 0.6,
                "approval_ratio": 0.5,
                "cooldown_seconds": 3600.0,
            },
            "economy": {
                "success_reward": 10.0,
                "failure_penalty": -5.0,
                "transfer_fee_rate": 0.0,
            },
            "spawn": {
                "authority_fraction": 0.5,
                "min_authority_to_spawn": 0.6,
            },
            "memory": {
                "decay_rate": 0.05,
                "conflict_threshold": 0.5,
            },
        }

        # All proposals (by ID)
        self._proposals: dict[str, EvolutionProposal] = {}

        # History of applied changes for rollback
        self._history: list[dict[str, Any]] = []

        # Last change timestamp per category (for rate limiting)
        self._last_change_time: dict[str, float] = {}

        # Generation counter — how many evolutions have been applied
        self._generation: int = 0

    # ── Parameter Access ─────────────────────────────────────────────────

    def get_parameter(self, category: str, name: str) -> float:
        """Get current value of a parameter."""
        cat = self._parameters.get(category)
        if cat is None:
            raise KeyError(f"Unknown category: {category}")
        if name not in cat:
            raise KeyError(f"Unknown parameter: {category}.{name}")
        return cat[name]

    def get_parameters(self, category: str | None = None) -> dict[str, Any]:
        """Get all parameters, optionally filtered by category."""
        if category:
            if category not in self._parameters:
                raise KeyError(f"Unknown category: {category}")
            return dict(self._parameters[category])
        return {cat: dict(params) for cat, params in self._parameters.items()}

    @property
    def generation(self) -> int:
        """Number of evolution cycles applied."""
        return self._generation

    # ── Proposal Lifecycle ───────────────────────────────────────────────

    def propose(
        self,
        proposer_id: AgentId,
        changes: list[dict[str, Any]],
        rationale: str = "",
    ) -> EvolutionProposal:
        """
        Create an evolution proposal.

        Args:
            proposer_id: Agent proposing the evolution
            changes: List of dicts with category, parameter_name, new_value
            rationale: Why this evolution is needed

        Returns:
            The created EvolutionProposal

        Raises:
            ValueError: If changes are invalid or out of bounds
        """
        if not changes:
            raise ValueError("Evolution proposal must include at least one change")

        param_changes = []
        for change_spec in changes:
            category_str = change_spec.get("category", "")
            param_name = change_spec.get("parameter_name", "")
            new_value = change_spec.get("new_value")

            if new_value is None:
                raise ValueError(
                    f"Missing new_value for {category_str}.{param_name}"
                )

            # Validate category exists
            try:
                category = ParameterCategory(category_str)
            except ValueError:
                raise ValueError(f"Unknown category: {category_str}")

            # Validate parameter exists
            if param_name not in self._parameters.get(category.value, {}):
                raise ValueError(
                    f"Unknown parameter: {category.value}.{param_name}"
                )

            # Validate bounds
            bounds = PARAMETER_BOUNDS.get(category.value, {}).get(param_name)
            if bounds:
                lo, hi = bounds
                if not (lo <= float(new_value) <= hi):
                    raise ValueError(
                        f"Parameter {category.value}.{param_name} value {new_value} "
                        f"outside bounds [{lo}, {hi}]"
                    )

            old_value = self._parameters[category.value][param_name]
            param_changes.append(
                ParameterChange(
                    category=category,
                    parameter_name=param_name,
                    old_value=old_value,
                    new_value=float(new_value),
                )
            )

        proposal = EvolutionProposal(
            proposer_id=proposer_id,
            changes=param_changes,
            rationale=rationale,
        )
        self._proposals[proposal.id] = proposal

        logger.info(
            "Evolution proposal '%s' created by %s: %d parameter changes",
            proposal.id,
            proposer_id,
            len(param_changes),
        )
        return proposal

    def vote(
        self,
        proposal_id: str,
        voter_id: AgentId,
        voter_authority: float,
        approve: bool,
    ) -> EvolutionProposal:
        """
        Cast a weighted vote on an evolution proposal.

        Args:
            proposal_id: Proposal to vote on
            voter_id: Agent casting the vote
            voter_authority: Current authority of the voter (used as weight)
            approve: True to approve, False to reject

        Returns:
            Updated proposal

        Raises:
            KeyError: If proposal not found
            ValueError: If proposal not in PROPOSED state or voter already voted
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            raise KeyError(f"Evolution proposal {proposal_id} not found")

        if proposal.status != EvolutionStatus.PROPOSED:
            raise ValueError(
                f"Cannot vote on proposal in state '{proposal.status.value}'"
            )

        if voter_id in proposal.voter_ids:
            raise ValueError(f"Agent {voter_id} already voted on this proposal")

        if approve:
            proposal.votes_for += voter_authority
        else:
            proposal.votes_against += voter_authority

        proposal.voter_ids.append(voter_id)
        return proposal

    def finalize(
        self,
        proposal_id: str,
        total_eligible_weight: float,
    ) -> EvolutionProposal:
        """
        Finalize voting on an evolution proposal.

        Requires supermajority: >= 75% of votes cast must approve.
        Quorum: total votes cast must be >= 60% of eligible weight.

        Args:
            proposal_id: Proposal to finalize
            total_eligible_weight: Sum of authority of all eligible voters

        Returns:
            Updated proposal with APPROVED or REJECTED status
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            raise KeyError(f"Evolution proposal {proposal_id} not found")

        if proposal.status != EvolutionStatus.PROPOSED:
            raise ValueError(
                f"Cannot finalize proposal in state '{proposal.status.value}'"
            )

        total_votes = proposal.votes_for + proposal.votes_against
        quorum_met = total_votes >= total_eligible_weight * 0.6

        if not quorum_met:
            proposal.status = EvolutionStatus.REJECTED
            proposal.decided_at = time.time()
            logger.info(
                "Evolution proposal '%s' rejected: quorum not met "
                "(%.2f/%.2f required)",
                proposal_id,
                total_votes,
                total_eligible_weight * 0.6,
            )
            return proposal

        approval_ratio = (
            proposal.votes_for / total_votes if total_votes > 0 else 0.0
        )

        if approval_ratio >= EVOLUTION_APPROVAL_RATIO:
            proposal.status = EvolutionStatus.APPROVED
            logger.info(
                "Evolution proposal '%s' approved (%.1f%% approval)",
                proposal_id,
                approval_ratio * 100,
            )
        else:
            proposal.status = EvolutionStatus.REJECTED
            logger.info(
                "Evolution proposal '%s' rejected (%.1f%% < %.1f%% required)",
                proposal_id,
                approval_ratio * 100,
                EVOLUTION_APPROVAL_RATIO * 100,
            )

        proposal.decided_at = time.time()
        return proposal

    def apply(self, proposal_id: str) -> list[ParameterChange]:
        """
        Apply an approved evolution proposal.

        Modifies the internal parameter store. Records a snapshot
        for potential rollback.

        Returns:
            List of applied parameter changes

        Raises:
            ValueError: If proposal not approved or rate-limited
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            raise KeyError(f"Evolution proposal {proposal_id} not found")

        if proposal.status != EvolutionStatus.APPROVED:
            raise ValueError(
                f"Cannot apply proposal in state '{proposal.status.value}'"
            )

        # Rate limiting check — 1 change per category per cooldown
        now = time.time()
        for change in proposal.changes:
            cat = change.category.value
            last_change = self._last_change_time.get(cat, 0)
            if now - last_change < PARAMETER_CHANGE_COOLDOWN:
                remaining = PARAMETER_CHANGE_COOLDOWN - (now - last_change)
                raise ValueError(
                    f"Category '{cat}' on cooldown — {remaining:.0f}s remaining"
                )

        # Record snapshot for rollback
        snapshot = {
            "proposal_id": proposal.id,
            "generation": self._generation,
            "timestamp": now,
            "changes": [c.to_dict() for c in proposal.changes],
        }
        self._history.append(snapshot)

        # Apply changes
        for change in proposal.changes:
            self._parameters[change.category.value][change.parameter_name] = (
                change.new_value
            )
            self._last_change_time[change.category.value] = now

        proposal.status = EvolutionStatus.APPLIED
        proposal.applied_at = now
        self._generation += 1

        logger.info(
            "Evolution proposal '%s' applied — generation %d",
            proposal.id,
            self._generation,
        )
        return list(proposal.changes)

    def rollback(self, proposal_id: str) -> list[ParameterChange]:
        """
        Rollback a previously applied evolution.

        Restores parameters to their pre-evolution values.

        Returns:
            List of reverted ParameterChanges (old/new swapped)
        """
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            raise KeyError(f"Evolution proposal {proposal_id} not found")

        if proposal.status != EvolutionStatus.APPLIED:
            raise ValueError(
                f"Cannot rollback proposal in state '{proposal.status.value}'"
            )

        # Find the snapshot
        snapshot = next(
            (s for s in self._history if s["proposal_id"] == proposal_id),
            None,
        )
        if not snapshot:
            raise ValueError(f"No snapshot found for proposal {proposal_id}")

        # Revert each change
        reverted = []
        for change in proposal.changes:
            current = self._parameters[change.category.value][
                change.parameter_name
            ]
            self._parameters[change.category.value][
                change.parameter_name
            ] = change.old_value
            reverted.append(
                ParameterChange(
                    category=change.category,
                    parameter_name=change.parameter_name,
                    old_value=current,
                    new_value=change.old_value,
                )
            )

        proposal.status = EvolutionStatus.ROLLED_BACK

        logger.info(
            "Evolution proposal '%s' rolled back — %d parameters reverted",
            proposal.id,
            len(reverted),
        )
        return reverted

    # ── Queries ──────────────────────────────────────────────────────────

    def get_proposal(self, proposal_id: str) -> EvolutionProposal | None:
        """Get a proposal by ID."""
        return self._proposals.get(proposal_id)

    def get_proposals(
        self,
        status: EvolutionStatus | None = None,
    ) -> list[EvolutionProposal]:
        """Get all proposals, optionally filtered by status."""
        proposals = list(self._proposals.values())
        if status:
            proposals = [p for p in proposals if p.status == status]
        return sorted(proposals, key=lambda p: p.created_at, reverse=True)

    def get_history(self) -> list[dict[str, Any]]:
        """Get the evolution history (all applied snapshots)."""
        return list(self._history)

    def get_stats(self) -> dict[str, Any]:
        """Get evolution engine statistics."""
        by_status = {}
        for p in self._proposals.values():
            by_status[p.status.value] = by_status.get(p.status.value, 0) + 1

        return {
            "generation": self._generation,
            "total_proposals": len(self._proposals),
            "proposals_by_status": by_status,
            "applied_count": len(self._history),
            "parameter_categories": list(self._parameters.keys()),
        }
