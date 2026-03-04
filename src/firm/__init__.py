"""
FIRM Protocol — Self-Evolving Autonomous Organization Runtime

The first protocol that defines the physics of self-evolving autonomous organizations.
Authority is earned, not assigned. Memory is a debate, not a database.
Structure is liquid, not fixed. Errors have economic consequences.
Evolution is not optional.

Two invariants, non-negotiable:
  1. The human can always shut it down.
  2. The system cannot erase its own capacity to evolve.

Everything else is negotiable. Including the protocol itself.
"""

__version__ = "0.1.0"

from firm.core.agent import Agent, AgentRole
from firm.core.authority import AuthorityEngine
from firm.core.ledger import ResponsibilityLedger, LedgerEntry
from firm.core.constitution import ConstitutionalAgent, Invariant
from firm.core.governance import GovernanceEngine, Proposal, Vote
from firm.core.types import AgentId, FirmId, Severity

__all__ = [
    "Agent",
    "AgentRole",
    "AuthorityEngine",
    "ResponsibilityLedger",
    "LedgerEntry",
    "ConstitutionalAgent",
    "Invariant",
    "GovernanceEngine",
    "Proposal",
    "Vote",
    "AgentId",
    "FirmId",
    "Severity",
]
