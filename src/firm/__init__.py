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

__version__ = "1.1.0"

from firm.core.agent import Agent, AgentRole
from firm.core.audit import AuditEngine, AuditFinding, AuditReport
from firm.core.authority import AuthorityEngine
from firm.core.constitution import ConstitutionalAgent, Invariant
from firm.core.events import Event, EventBus
from firm.core.evolution import EvolutionEngine, EvolutionProposal, ParameterChange
from firm.core.federation import (
    AgentSecondment,
    FederationEngine,
    FederationMessage,
    PeerFirm,
)
from firm.core.governance import GovernanceEngine, Proposal, Vote
from firm.core.human import HumanOverride, OverrideEvent
from firm.core.ledger import LedgerEntry, ResponsibilityLedger
from firm.core.market import MarketBid, MarketEngine, MarketTask, Settlement
from firm.core.memory import MemoryEngine, MemoryEntry
from firm.core.meta import Amendment, MetaConstitutional
from firm.core.plugins import FirmPlugin, PluginManager
from firm.core.prediction import (
    MarketStatus,
    Position,
    PositionSide,
    PredictionEngine,
    PredictionMarket,
    PredictionSettlement,
)
from firm.core.reputation import (
    ImportedReputation,
    PredictionAccuracyAttestation,
    ReputationAttestation,
    ReputationBridge,
    global_authority,
)
from firm.core.roles import RoleAssignment, RoleDefinition, RoleEngine
from firm.core.serialization import diff_snapshots, load_firm, save_firm, snapshot
from firm.core.spawn import AutoRestructurer, RestructureRecommendation, SpawnEngine, SpawnEvent
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
    "Event",
    "EventBus",
    "EvolutionEngine",
    "EvolutionProposal",
    "FederationEngine",
    "FederationMessage",
    "FirmPlugin",
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
    "PluginManager",
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
    "PredictionEngine",
    "PredictionMarket",
    "PredictionSettlement",
    "Position",
    "MarketStatus",
    "PositionSide",
    "PredictionAccuracyAttestation",
    "global_authority",
    "AutoRestructurer",
    "RestructureRecommendation",
    "save_firm",
    "load_firm",
    "snapshot",
    "diff_snapshots",
]
