"""Reward engine — distributes credits to agents after a bounty payout.

Severity multipliers + contribution shares + authority boost.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from firm.bounty.vulnerability import Vulnerability, VulnSeverity


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_CREDITS_PER_USD = 10.0

SEVERITY_MULTIPLIERS: dict[VulnSeverity, float] = {
    VulnSeverity.CRITICAL: 4.0,
    VulnSeverity.HIGH: 2.5,
    VulnSeverity.MEDIUM: 1.5,
    VulnSeverity.LOW: 1.0,
    VulnSeverity.INFO: 0.0,
}

# Default contribution shares (must sum to 1.0)
DEFAULT_SHARES: dict[str, float] = {
    "hunter": 0.60,
    "recon": 0.15,
    "triage": 0.10,
    "writer": 0.10,
    "coordinator": 0.05,
}


# ---------------------------------------------------------------------------
# Reward result
# ---------------------------------------------------------------------------

@dataclass
class RewardAllocation:
    agent_name: str
    role: str
    base_credits: float
    authority_bonus: float
    total_credits: float


@dataclass
class RewardDistribution:
    vuln_id: str
    bounty_usd: float
    total_credits: float
    allocations: list[RewardAllocation] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class RewardEngine:
    """Compute and distribute FIRM credits when a bounty is paid."""

    def __init__(
        self,
        credits_per_usd: float = BASE_CREDITS_PER_USD,
        severity_multipliers: dict[VulnSeverity, float] | None = None,
        shares: dict[str, float] | None = None,
    ):
        self.credits_per_usd = credits_per_usd
        self.multipliers = severity_multipliers or SEVERITY_MULTIPLIERS
        self.shares = shares or DEFAULT_SHARES

    def distribute(
        self,
        vuln: Vulnerability,
        bounty_usd: float,
        contributors: dict[str, str] | None = None,
        authority_scores: dict[str, float] | None = None,
    ) -> RewardDistribution:
        """Distribute credits for a single bounty payout.

        Args:
            vuln:              The accepted vulnerability.
            bounty_usd:        Dollar amount paid by the programme.
            contributors:      Mapping ``{role: agent_name}`` (e.g. ``{"hunter": "web-hunter"}``).
            authority_scores:  Current authority of each agent (0-1), used as bonus multiplier.
        """
        sev_mult = self.multipliers.get(vuln.severity, 1.0)
        total_credits = bounty_usd * self.credits_per_usd * sev_mult

        contributors = contributors or {"hunter": vuln.discovered_by}
        authority_scores = authority_scores or {}

        allocations: list[RewardAllocation] = []
        for role, share in self.shares.items():
            agent = contributors.get(role, "")
            if not agent:
                continue
            base = total_credits * share
            auth = authority_scores.get(agent, 0.5)
            # authority bonus: +0% at 0.5, +50% at 1.0, -50% at 0.0
            bonus = base * (auth - 0.5)
            allocations.append(
                RewardAllocation(
                    agent_name=agent,
                    role=role,
                    base_credits=round(base, 2),
                    authority_bonus=round(bonus, 2),
                    total_credits=round(base + bonus, 2),
                )
            )

        return RewardDistribution(
            vuln_id=vuln.id,
            bounty_usd=bounty_usd,
            total_credits=round(total_credits, 2),
            allocations=allocations,
        )

    def penalty(
        self,
        agent_name: str,
        reason: str = "duplicate",
        amount: float = 5.0,
    ) -> dict[str, Any]:
        """Apply a credit penalty for low-quality submissions."""
        return {
            "agent": agent_name,
            "penalty_credits": -amount,
            "reason": reason,
        }
