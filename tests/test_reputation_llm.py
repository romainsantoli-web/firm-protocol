import pytest

from firm.core.reputation import ReputationAttestation, ReputationBridge
from firm.core.types import AgentId, FirmId


def test_reputation_bridge_initialization():
    """Test initialization of ReputationBridge."""
    home_firm_id = FirmId("test_firm")
    bridge = ReputationBridge(home_firm_id)
    assert bridge._home_id == home_firm_id
    assert len(bridge._issued) == 0
    assert len(bridge._received) == 0
    assert len(bridge._imports) == 0
    assert len(bridge._agent_imports) == 0

def test_issue_attestation():
    """Test issuing an attestation."""
    home_firm_id = FirmId("test_firm")
    bridge = ReputationBridge(home_firm_id)
    agent_id = AgentId("test_agent")
    attestation = bridge.issue_attestation(
        agent_id=agent_id,
        agent_name="test_agent",
        authority=0.8,
        success_rate=0.9,
        action_count=100,
        endorsement="Excellent performance",
    )
    assert attestation.agent_id == agent_id
    assert attestation.source_firm == home_firm_id
    assert attestation.authority == 0.8
    assert attestation.success_rate == 0.9
    assert attestation.action_count == 100
    assert attestation.endorsement == "Excellent performance"
    assert attestation.verify()
    assert len(bridge._issued) == 1

def test_import_attestation():
    """Test importing an attestation."""
    home_firm_id = FirmId("test_firm")
    bridge = ReputationBridge(home_firm_id)
    agent_id = AgentId("test_agent")
    source_firm_id = FirmId("source_firm")
    attestation = ReputationAttestation(
        agent_id=agent_id,
        agent_name="test_agent",
        source_firm=source_firm_id,
        authority=0.8,
        success_rate=0.9,
        action_count=100,
        endorsement="Excellent performance",
    )
    attestation.seal()
    peer_trust = 0.5
    imported_reputation = bridge.import_attestation(
        attestation=attestation,
        peer_trust=peer_trust,
    )
    assert imported_reputation.agent_id == agent_id
    assert imported_reputation.source_firm == source_firm_id
    assert imported_reputation.original_authority == 0.8
    assert imported_reputation.discount_factor == 0.4  # 0.1 + (0.7-0.1)*0.5
    assert imported_reputation.effective_authority == pytest.approx(0.3, abs=0.01)  # 0.8 * 0.4 (capped)
    assert len(bridge._received) == 1
    assert len(bridge._imports) == 1

def test_import_attestation_low_trust():
    """Test importing an attestation with low trust."""
    home_firm_id = FirmId("test_firm")
    bridge = ReputationBridge(home_firm_id)
    agent_id = AgentId("test_agent")
    source_firm_id = FirmId("source_firm")
    attestation = ReputationAttestation(
        agent_id=agent_id,
        agent_name="test_agent",
        source_firm=source_firm_id,
        authority=0.8,
        success_rate=0.9,
        action_count=100,
        endorsement="Excellent performance",
    )
    attestation.seal()
    peer_trust = 0.3  # Below MIN_TRUST_TO_IMPORT
    with pytest.raises(PermissionError):
        bridge.import_attestation(
            attestation=attestation,
            peer_trust=peer_trust,
        )

def test_apply_decay():
    """Test applying decay to imported reputations."""
    home_firm_id = FirmId("test_firm")
    bridge = ReputationBridge(home_firm_id)
    agent_id = AgentId("test_agent")
    source_firm_id = FirmId("source_firm")
    attestation = ReputationAttestation(
        agent_id=agent_id,
        agent_name="test_agent",
        source_firm=source_firm_id,
        authority=0.8,
        success_rate=0.9,
        action_count=100,
        endorsement="Excellent performance",
    )
    attestation.seal()
    peer_trust = 0.5
    imported_reputation = bridge.import_attestation(
        attestation=attestation,
        peer_trust=peer_trust,
    )
    initial_weighted_authority = imported_reputation.weighted_authority
    decay_results = bridge.apply_decay()
    assert len(decay_results) == 1
    assert imported_reputation.id in decay_results
    assert decay_results[imported_reputation.id] < initial_weighted_authority

