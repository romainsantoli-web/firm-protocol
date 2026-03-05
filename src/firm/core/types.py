"""
firm.core.types — Foundational types for FIRM Protocol

All primitive types and enumerations used across the protocol.
"""

from __future__ import annotations

import enum
from typing import NewType

# ── Identity types ───────────────────────────────────────────────────────────

AgentId = NewType("AgentId", str)
FirmId = NewType("FirmId", str)
ProposalId = NewType("ProposalId", str)
EntryId = NewType("EntryId", str)


# ── Enumerations ─────────────────────────────────────────────────────────────


class Severity(str, enum.Enum):
    """Severity levels for findings, violations, and events."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AgentStatus(str, enum.Enum):
    """Lifecycle status of an agent within a FIRM."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    PROBATION = "probation"
    TERMINATED = "terminated"


class ProposalStatus(str, enum.Enum):
    """Lifecycle of a governance proposal."""

    DRAFT = "draft"
    SIMULATION_1 = "simulation_1"
    STRESS_TEST = "stress_test"
    SIMULATION_2 = "simulation_2"
    VOTING = "voting"
    COOLDOWN = "cooldown"
    APPROVED = "approved"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class VoteChoice(str, enum.Enum):
    """Possible votes on a governance proposal."""

    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


class LedgerAction(str, enum.Enum):
    """Types of actions recorded in the Responsibility Ledger."""

    DECISION = "decision"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    AUTHORITY_CHANGE = "authority_change"
    GOVERNANCE_VOTE = "governance_vote"
    RESTRUCTURE = "restructure"
    VIOLATION = "violation"
    CREDIT_TRANSFER = "credit_transfer"
    # S2 — Inter-Firm Protocol & Reputation Bridge
    FEDERATION = "federation"
    AGENT_SECONDMENT = "agent_secondment"
    REPUTATION_ATTESTATION = "reputation_attestation"
    # S3 — Evolution, Market, Meta-Constitutional
    EVOLUTION = "evolution"
    MARKET_TRANSACTION = "market_transaction"
    CONSTITUTIONAL_AMENDMENT = "constitutional_amendment"
    # S4 — Prediction Markets
    PREDICTION = "prediction"
    PREDICTION_SETTLEMENT = "prediction_settlement"
