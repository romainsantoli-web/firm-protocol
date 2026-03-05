"""Tests for firm.core.types"""

from firm.core.types import (
    AgentId,
    AgentStatus,
    FirmId,
    LedgerAction,
    ProposalStatus,
    Severity,
    VoteChoice,
)


def test_severity_values():
    assert Severity.CRITICAL.value == "critical"
    assert Severity.HIGH.value == "high"
    assert Severity.MEDIUM.value == "medium"
    assert Severity.LOW.value == "low"
    assert Severity.INFO.value == "info"


def test_agent_status_values():
    assert AgentStatus.ACTIVE.value == "active"
    assert AgentStatus.SUSPENDED.value == "suspended"
    assert AgentStatus.PROBATION.value == "probation"
    assert AgentStatus.TERMINATED.value == "terminated"


def test_proposal_status_lifecycle():
    statuses = [
        ProposalStatus.DRAFT,
        ProposalStatus.SIMULATION_1,
        ProposalStatus.STRESS_TEST,
        ProposalStatus.SIMULATION_2,
        ProposalStatus.VOTING,
        ProposalStatus.COOLDOWN,
        ProposalStatus.APPROVED,
    ]
    assert len(statuses) == 7


def test_vote_choices():
    assert VoteChoice.APPROVE.value == "approve"
    assert VoteChoice.REJECT.value == "reject"
    assert VoteChoice.ABSTAIN.value == "abstain"


def test_ledger_actions():
    assert len(LedgerAction) == 16
    assert LedgerAction.DECISION.value == "decision"
    assert LedgerAction.VIOLATION.value == "violation"
    # S2 actions
    assert LedgerAction.FEDERATION.value == "federation"
    assert LedgerAction.AGENT_SECONDMENT.value == "agent_secondment"
    assert LedgerAction.REPUTATION_ATTESTATION.value == "reputation_attestation"
    # S3 actions
    assert LedgerAction.EVOLUTION.value == "evolution"
    assert LedgerAction.MARKET_TRANSACTION.value == "market_transaction"
    assert LedgerAction.CONSTITUTIONAL_AMENDMENT.value == "constitutional_amendment"
    # v1.0 actions
    assert LedgerAction.PREDICTION.value == "prediction"
    assert LedgerAction.PREDICTION_SETTLEMENT.value == "prediction_settlement"


def test_newtype_identity():
    agent_id = AgentId("test-agent")
    assert agent_id == "test-agent"
    firm_id = FirmId("test-firm")
    assert firm_id == "test-firm"
