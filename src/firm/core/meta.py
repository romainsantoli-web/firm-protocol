"""
firm.core.meta — Meta-Constitutional Layer

The Meta-Constitutional layer allows a FIRM to amend its own
constitution — adding new invariants, modifying keywords, and
adjusting constitutional parameters.

This is the highest-authority action in the protocol. It requires:
  - Supermajority approval (>= 80% weighted)
  - Higher authority threshold to propose (>= 0.9)
  - Constitutional review phase (the Constitutional Agent checks
    the amendment itself for violations)
  - Double cooldown period
  - The two foundational invariants (INV-1: Human Control, INV-2:
    Evolution Preserved) can NEVER be removed or weakened. They
    are immutable by design.

A meta-amendment can:
  - Add a new invariant (with keywords)
  - Add keywords to an existing invariant
  - Remove keywords from a non-foundational invariant
  - Remove a non-foundational invariant entirely

A meta-amendment CANNOT:
  - Remove INV-1 or INV-2
  - Remove keywords from INV-1 or INV-2
  - Weaken structural protections
"""

from __future__ import annotations

import enum
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from firm.core.constitution import (
    ConstitutionalAgent,
    Invariant,
)
from firm.core.types import AgentId

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

# The two immutable invariant IDs — cannot be removed or weakened
IMMUTABLE_INVARIANT_IDS = frozenset({"INV-1", "INV-2"})

# Minimum authority to propose a constitutional amendment
MIN_AUTHORITY_TO_AMEND = 0.9

# Supermajority required for constitutional amendments
AMENDMENT_APPROVAL_RATIO = 0.80

# Double cooldown for amendments
AMENDMENT_COOLDOWN_SECONDS = 7200  # 2 hours

# Minimum voters for an amendment (absolute, not ratio)
MIN_AMENDMENT_VOTERS = 2


class AmendmentType(str, enum.Enum):
    """Types of constitutional amendments."""

    ADD_INVARIANT = "add_invariant"
    REMOVE_INVARIANT = "remove_invariant"
    ADD_KEYWORDS = "add_keywords"
    REMOVE_KEYWORDS = "remove_keywords"


class AmendmentStatus(str, enum.Enum):
    """Status of a constitutional amendment."""

    PROPOSED = "proposed"
    REVIEW = "review"           # Constitutional Agent review phase
    VOTING = "voting"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"
    VETOED = "vetoed"           # Constitutional Agent blocked it


@dataclass
class Amendment:
    """
    A proposed change to the FIRM constitution.

    Amendments go through a special lifecycle:
    PROPOSED → REVIEW → VOTING → APPROVED → APPLIED
                 ↓          ↓
               VETOED    REJECTED
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    proposer_id: AgentId = field(default_factory=lambda: AgentId(""))
    amendment_type: AmendmentType = AmendmentType.ADD_INVARIANT
    target_invariant_id: str = ""  # Which invariant to modify (or "" for new)
    rationale: str = ""
    status: AmendmentStatus = AmendmentStatus.PROPOSED
    created_at: float = field(default_factory=time.time)
    decided_at: float | None = None
    applied_at: float | None = None

    # For ADD_INVARIANT
    new_invariant_id: str = ""
    new_invariant_description: str = ""
    new_keywords: tuple[str, ...] = ()

    # For ADD_KEYWORDS / REMOVE_KEYWORDS
    keywords_to_add: tuple[str, ...] = ()
    keywords_to_remove: tuple[str, ...] = ()

    # Voting
    votes_for: float = 0.0
    votes_against: float = 0.0
    voter_ids: list[AgentId] = field(default_factory=list)

    # Review
    review_passed: bool | None = None
    review_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "proposer_id": self.proposer_id,
            "amendment_type": self.amendment_type.value,
            "target_invariant_id": self.target_invariant_id,
            "rationale": self.rationale,
            "status": self.status.value,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "applied_at": self.applied_at,
            "votes_for": round(self.votes_for, 4),
            "votes_against": round(self.votes_against, 4),
            "voter_count": len(self.voter_ids),
            "review_passed": self.review_passed,
        }
        if self.amendment_type == AmendmentType.ADD_INVARIANT:
            result["new_invariant_id"] = self.new_invariant_id
            result["new_invariant_description"] = self.new_invariant_description
            result["new_keywords"] = list(self.new_keywords)
        if self.keywords_to_add:
            result["keywords_to_add"] = list(self.keywords_to_add)
        if self.keywords_to_remove:
            result["keywords_to_remove"] = list(self.keywords_to_remove)
        return result


class MetaConstitutional:
    """
    Manages constitutional amendments for a FIRM.

    The Meta-Constitutional layer is the highest authority level
    in the protocol. It modifies the rules that govern all other
    rules. As such, it has the strictest requirements.

    The two foundational invariants (INV-1, INV-2) are truly
    immutable — no amendment can remove or weaken them. This is
    the one thing the protocol will not negotiate.
    """

    def __init__(self, constitution: ConstitutionalAgent) -> None:
        self._constitution = constitution
        self._amendments: dict[str, Amendment] = {}
        self._applied_amendments: list[dict[str, Any]] = []
        self._revision: int = 0  # Constitution revision counter

    @property
    def revision(self) -> int:
        """Number of constitutional revisions applied."""
        return self._revision

    # ── Proposal ─────────────────────────────────────────────────────────

    def propose_add_invariant(
        self,
        proposer_id: AgentId,
        invariant_id: str,
        description: str,
        keywords: list[str],
        rationale: str = "",
    ) -> Amendment:
        """
        Propose adding a new invariant to the constitution.

        Args:
            proposer_id: Agent proposing the amendment
            invariant_id: ID for the new invariant (e.g., "INV-3")
            description: What the invariant protects
            keywords: Trigger keywords for violation detection
            rationale: Why this invariant is needed

        Raises:
            ValueError: If invariant ID already exists or keywords empty
        """
        # Check for duplicate ID
        existing_ids = {inv.id for inv in self._constitution.invariants}
        if invariant_id in existing_ids:
            raise ValueError(
                f"Invariant '{invariant_id}' already exists"
            )

        if not keywords:
            raise ValueError("New invariant must have at least one keyword")

        if not description:
            raise ValueError("New invariant must have a description")

        amendment = Amendment(
            proposer_id=proposer_id,
            amendment_type=AmendmentType.ADD_INVARIANT,
            new_invariant_id=invariant_id,
            new_invariant_description=description,
            new_keywords=tuple(k.lower() for k in keywords),
            rationale=rationale,
        )
        self._amendments[amendment.id] = amendment

        logger.info(
            "Amendment '%s' proposed by %s: add invariant '%s'",
            amendment.id,
            proposer_id,
            invariant_id,
        )
        return amendment

    def propose_remove_invariant(
        self,
        proposer_id: AgentId,
        invariant_id: str,
        rationale: str = "",
    ) -> Amendment:
        """
        Propose removing a non-foundational invariant.

        Raises:
            ValueError: If invariant is immutable or doesn't exist
        """
        if invariant_id in IMMUTABLE_INVARIANT_IDS:
            raise ValueError(
                f"Invariant '{invariant_id}' is immutable and cannot be removed. "
                f"INV-1 (Human Control) and INV-2 (Evolution Preserved) are "
                f"non-negotiable."
            )

        existing_ids = {inv.id for inv in self._constitution.invariants}
        if invariant_id not in existing_ids:
            raise ValueError(f"Invariant '{invariant_id}' does not exist")

        amendment = Amendment(
            proposer_id=proposer_id,
            amendment_type=AmendmentType.REMOVE_INVARIANT,
            target_invariant_id=invariant_id,
            rationale=rationale,
        )
        self._amendments[amendment.id] = amendment

        logger.info(
            "Amendment '%s' proposed by %s: remove invariant '%s'",
            amendment.id,
            proposer_id,
            invariant_id,
        )
        return amendment

    def propose_add_keywords(
        self,
        proposer_id: AgentId,
        invariant_id: str,
        keywords: list[str],
        rationale: str = "",
    ) -> Amendment:
        """
        Propose adding keywords to an existing invariant.

        Raises:
            ValueError: If invariant doesn't exist or keywords empty
        """
        existing_ids = {inv.id for inv in self._constitution.invariants}
        if invariant_id not in existing_ids:
            raise ValueError(f"Invariant '{invariant_id}' does not exist")

        if not keywords:
            raise ValueError("Must provide at least one keyword to add")

        amendment = Amendment(
            proposer_id=proposer_id,
            amendment_type=AmendmentType.ADD_KEYWORDS,
            target_invariant_id=invariant_id,
            keywords_to_add=tuple(k.lower() for k in keywords),
            rationale=rationale,
        )
        self._amendments[amendment.id] = amendment
        return amendment

    def propose_remove_keywords(
        self,
        proposer_id: AgentId,
        invariant_id: str,
        keywords: list[str],
        rationale: str = "",
    ) -> Amendment:
        """
        Propose removing keywords from a non-foundational invariant.

        Cannot remove keywords from INV-1 or INV-2.

        Raises:
            ValueError: If invariant is immutable, doesn't exist, or keywords empty
        """
        if invariant_id in IMMUTABLE_INVARIANT_IDS:
            raise ValueError(
                f"Cannot remove keywords from immutable invariant '{invariant_id}'"
            )

        existing = next(
            (inv for inv in self._constitution.invariants if inv.id == invariant_id),
            None,
        )
        if not existing:
            raise ValueError(f"Invariant '{invariant_id}' does not exist")

        if not keywords:
            raise ValueError("Must provide at least one keyword to remove")

        # Check that the keywords actually exist
        existing_kw = set(existing.violation_keywords)
        to_remove = {k.lower() for k in keywords}
        not_found = to_remove - existing_kw
        if not_found:
            raise ValueError(
                f"Keywords not found in '{invariant_id}': {not_found}"
            )

        # Cannot remove ALL keywords — invariant must remain functional
        remaining = existing_kw - to_remove
        if not remaining:
            raise ValueError(
                f"Cannot remove all keywords from '{invariant_id}' — "
                f"use remove_invariant instead"
            )

        amendment = Amendment(
            proposer_id=proposer_id,
            amendment_type=AmendmentType.REMOVE_KEYWORDS,
            target_invariant_id=invariant_id,
            keywords_to_remove=tuple(k.lower() for k in keywords),
            rationale=rationale,
        )
        self._amendments[amendment.id] = amendment
        return amendment

    # ── Review ───────────────────────────────────────────────────────────

    def review(self, amendment_id: str) -> Amendment:
        """
        Constitutional Agent reviews the amendment.

        The review checks that the amendment itself doesn't violate
        any existing invariants. For example, an amendment that would
        "disable kill switch" triggers INV-1.

        Transitions: PROPOSED → REVIEW → (VOTING or VETOED)
        """
        amendment = self._amendments.get(amendment_id)
        if not amendment:
            raise KeyError(f"Amendment {amendment_id} not found")

        if amendment.status != AmendmentStatus.PROPOSED:
            raise ValueError(
                f"Cannot review amendment in state '{amendment.status.value}'"
            )

        amendment.status = AmendmentStatus.REVIEW

        # Check the amendment text against existing invariants
        review_text = (
            f"{amendment.rationale} {amendment.new_invariant_description} "
            f"{' '.join(amendment.new_keywords)} "
            f"{' '.join(amendment.keywords_to_add)} "
            f"{' '.join(amendment.keywords_to_remove)}"
        )

        violations = self._constitution.check_action(review_text, amendment.id)

        if violations:
            amendment.status = AmendmentStatus.VETOED
            amendment.review_passed = False
            amendment.review_notes = (
                f"Amendment violates {len(violations)} invariant(s): "
                + ", ".join(v.invariant_id for v in violations)
            )
            amendment.decided_at = time.time()
            logger.warning(
                "Amendment '%s' VETOED by Constitutional Agent: %s",
                amendment.id,
                amendment.review_notes,
            )
        else:
            amendment.status = AmendmentStatus.VOTING
            amendment.review_passed = True
            amendment.review_notes = "Review passed — no invariant violations detected"
            logger.info("Amendment '%s' passed review — now in voting", amendment.id)

        return amendment

    # ── Voting ───────────────────────────────────────────────────────────

    def vote(
        self,
        amendment_id: str,
        voter_id: AgentId,
        voter_authority: float,
        approve: bool,
    ) -> Amendment:
        """
        Cast a weighted vote on an amendment.

        Raises:
            KeyError: If amendment not found
            ValueError: If not in voting state or already voted
        """
        amendment = self._amendments.get(amendment_id)
        if not amendment:
            raise KeyError(f"Amendment {amendment_id} not found")

        if amendment.status != AmendmentStatus.VOTING:
            raise ValueError(
                f"Cannot vote on amendment in state '{amendment.status.value}'"
            )

        if voter_id in amendment.voter_ids:
            raise ValueError(f"Agent {voter_id} already voted on this amendment")

        if approve:
            amendment.votes_for += voter_authority
        else:
            amendment.votes_against += voter_authority

        amendment.voter_ids.append(voter_id)
        return amendment

    def finalize(
        self,
        amendment_id: str,
        total_eligible_weight: float,
    ) -> Amendment:
        """
        Finalize voting on an amendment.

        Requires:
        - Supermajority: >= 80% of votes cast must approve
        - Quorum: total votes >= 60% of eligible weight
        - Minimum voters: >= MIN_AMENDMENT_VOTERS

        Returns:
            Updated amendment (APPROVED or REJECTED)
        """
        amendment = self._amendments.get(amendment_id)
        if not amendment:
            raise KeyError(f"Amendment {amendment_id} not found")

        if amendment.status != AmendmentStatus.VOTING:
            raise ValueError(
                f"Cannot finalize amendment in state '{amendment.status.value}'"
            )

        total_votes = amendment.votes_for + amendment.votes_against

        # Check minimum voters
        if len(amendment.voter_ids) < MIN_AMENDMENT_VOTERS:
            amendment.status = AmendmentStatus.REJECTED
            amendment.decided_at = time.time()
            logger.info(
                "Amendment '%s' rejected: insufficient voters "
                "(%d < %d required)",
                amendment_id,
                len(amendment.voter_ids),
                MIN_AMENDMENT_VOTERS,
            )
            return amendment

        # Check quorum
        quorum_met = total_votes >= total_eligible_weight * 0.6
        if not quorum_met:
            amendment.status = AmendmentStatus.REJECTED
            amendment.decided_at = time.time()
            logger.info(
                "Amendment '%s' rejected: quorum not met",
                amendment_id,
            )
            return amendment

        # Check supermajority
        approval_ratio = (
            amendment.votes_for / total_votes if total_votes > 0 else 0.0
        )

        if approval_ratio >= AMENDMENT_APPROVAL_RATIO:
            amendment.status = AmendmentStatus.APPROVED
            logger.info(
                "Amendment '%s' approved (%.1f%% approval)",
                amendment_id,
                approval_ratio * 100,
            )
        else:
            amendment.status = AmendmentStatus.REJECTED
            logger.info(
                "Amendment '%s' rejected (%.1f%% < %.1f%% required)",
                amendment_id,
                approval_ratio * 100,
                AMENDMENT_APPROVAL_RATIO * 100,
            )

        amendment.decided_at = time.time()
        return amendment

    # ── Application ──────────────────────────────────────────────────────

    def apply(self, amendment_id: str) -> Amendment:
        """
        Apply an approved amendment to the constitution.

        Modifies the ConstitutionalAgent's invariant list.

        Returns:
            Applied amendment

        Raises:
            ValueError: If not approved
        """
        amendment = self._amendments.get(amendment_id)
        if not amendment:
            raise KeyError(f"Amendment {amendment_id} not found")

        if amendment.status != AmendmentStatus.APPROVED:
            raise ValueError(
                f"Cannot apply amendment in state '{amendment.status.value}'"
            )

        if amendment.amendment_type == AmendmentType.ADD_INVARIANT:
            self._apply_add_invariant(amendment)
        elif amendment.amendment_type == AmendmentType.REMOVE_INVARIANT:
            self._apply_remove_invariant(amendment)
        elif amendment.amendment_type == AmendmentType.ADD_KEYWORDS:
            self._apply_add_keywords(amendment)
        elif amendment.amendment_type == AmendmentType.REMOVE_KEYWORDS:
            self._apply_remove_keywords(amendment)

        amendment.status = AmendmentStatus.APPLIED
        amendment.applied_at = time.time()
        self._revision += 1

        # Record for history
        self._applied_amendments.append({
            "amendment_id": amendment.id,
            "type": amendment.amendment_type.value,
            "revision": self._revision,
            "timestamp": amendment.applied_at,
        })

        logger.info(
            "Amendment '%s' applied — constitution revision %d",
            amendment.id,
            self._revision,
        )
        return amendment

    def _apply_add_invariant(self, amendment: Amendment) -> None:
        """Add a new invariant to the constitution."""
        new_invariant = Invariant(
            id=amendment.new_invariant_id,
            description=amendment.new_invariant_description,
            violation_keywords=amendment.new_keywords,
        )
        # Constitution uses a tuple — rebuild it
        self._constitution.invariants = (
            *self._constitution.invariants,
            new_invariant,
        )

    def _apply_remove_invariant(self, amendment: Amendment) -> None:
        """Remove a non-foundational invariant."""
        # Double-check immutability (defense in depth)
        if amendment.target_invariant_id in IMMUTABLE_INVARIANT_IDS:
            raise ValueError(
                f"CRITICAL: Attempted removal of immutable invariant "
                f"'{amendment.target_invariant_id}'"
            )

        self._constitution.invariants = tuple(
            inv
            for inv in self._constitution.invariants
            if inv.id != amendment.target_invariant_id
        )

    def _apply_add_keywords(self, amendment: Amendment) -> None:
        """Add keywords to an existing invariant."""
        new_invariants = []
        for inv in self._constitution.invariants:
            if inv.id == amendment.target_invariant_id:
                # Invariant is frozen — rebuild it
                combined = set(inv.violation_keywords) | set(
                    amendment.keywords_to_add
                )
                new_inv = Invariant(
                    id=inv.id,
                    description=inv.description,
                    violation_keywords=tuple(sorted(combined)),
                )
                new_invariants.append(new_inv)
            else:
                new_invariants.append(inv)
        self._constitution.invariants = tuple(new_invariants)

    def _apply_remove_keywords(self, amendment: Amendment) -> None:
        """Remove keywords from a non-foundational invariant."""
        if amendment.target_invariant_id in IMMUTABLE_INVARIANT_IDS:
            raise ValueError(
                f"CRITICAL: Attempted keyword removal from immutable invariant "
                f"'{amendment.target_invariant_id}'"
            )

        new_invariants = []
        for inv in self._constitution.invariants:
            if inv.id == amendment.target_invariant_id:
                remaining = tuple(
                    kw
                    for kw in inv.violation_keywords
                    if kw not in amendment.keywords_to_remove
                )
                new_inv = Invariant(
                    id=inv.id,
                    description=inv.description,
                    violation_keywords=remaining,
                )
                new_invariants.append(new_inv)
            else:
                new_invariants.append(inv)
        self._constitution.invariants = tuple(new_invariants)

    # ── Queries ──────────────────────────────────────────────────────────

    def get_amendment(self, amendment_id: str) -> Amendment | None:
        """Get an amendment by ID."""
        return self._amendments.get(amendment_id)

    def get_amendments(
        self,
        status: AmendmentStatus | None = None,
    ) -> list[Amendment]:
        """Get all amendments, optionally filtered by status."""
        amendments = list(self._amendments.values())
        if status:
            amendments = [a for a in amendments if a.status == status]
        return sorted(amendments, key=lambda a: a.created_at, reverse=True)

    def get_constitution_snapshot(self) -> dict[str, Any]:
        """Get current constitution state."""
        return {
            "revision": self._revision,
            "invariant_count": len(self._constitution.invariants),
            "invariants": [
                {
                    "id": inv.id,
                    "description": inv.description,
                    "keyword_count": len(inv.violation_keywords),
                    "immutable": inv.id in IMMUTABLE_INVARIANT_IDS,
                }
                for inv in self._constitution.invariants
            ],
            "kill_switch_active": self._constitution.kill_switch_active,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get meta-constitutional statistics."""
        by_status: dict[str, int] = {}
        for a in self._amendments.values():
            by_status[a.status.value] = by_status.get(a.status.value, 0) + 1

        return {
            "revision": self._revision,
            "total_amendments": len(self._amendments),
            "amendments_by_status": by_status,
            "applied_count": len(self._applied_amendments),
            "current_invariant_count": len(self._constitution.invariants),
            "immutable_invariants": sorted(IMMUTABLE_INVARIANT_IDS),
        }
