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

__version__ = "0.5.0"

from firm.core.agent import Agent, AgentRole
from firm.core.audit import AuditEngine, AuditFinding, AuditReport
from firm.core.authority import AuthorityEngine
from firm.core.constitution import ConstitutionalAgent, Invariant
from firm.core.evolution import EvolutionEngine, EvolutionProposal, ParameterChange
from firm.core.federation import (
    FederationEngine,
    FederationMessage,
    AgentSecondment,
    PeerFirm,
)
from firm.core.governance import GovernanceEngine, Proposal, Vote
from firm.core.human import HumanOverride, OverrideEvent
from firm.core.ledger import ResponsibilityLedger, LedgerEntry
from firm.core.market import MarketEngine, MarketTask, MarketBid, Settlement
from firm.core.memory import MemoryEngine, MemoryEntry
from firm.core.meta import MetaConstitutional, Amendment
from firm.core.reputation import (
    ReputationBridge,
    ReputationAttestation,
    ImportedReputation,
)
from firm.core.roles import RoleEngine, RoleDefinition, RoleAssignment
from firm.core.spawn import SpawnEngine, SpawnEvent
from firm.core.types import AgentId, FirmId, Severity

__all__ = [
    "Agent",
    "AgentRole",
    "AgentSecondment",
    "Amendment",
    "AuditEngine",
    "AuditFinding",
    "AuditReport",
    "AuthorityEngine",
    "ConstitutionalAgent",
    "EvolutionEngine",
    "EvolutionProposal",
    "FederationEngine",
    "FederationMessage",
    "GovernanceEngine",
    "HumanOverride",
    "ImportedReputation",
    "Invariant",
    "LedgerEntry",
    "MarketBid",
    "MarketEngine",
    "MarketTask",
    "MemoryEngine",
    "MemoryEntry",
    "MetaConstitutional",
    "OverrideEvent",
    "ParameterChange",
    "PeerFirm",
    "Proposal",
    "ReputationAttestation",
    "ReputationBridge",
    "ResponsibilityLedger",
    "RoleAssignment",
    "RoleDefinition",
    "RoleEngine",
    "Settlement",
    "SpawnEngine",
    "SpawnEvent",
    "Vote",
    "AgentId",
    "FirmId",
    "Severity",
]
