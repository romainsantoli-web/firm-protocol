"""Tests for firm.core.reputation — Reputation Bridge (Layer 9)."""

import time

import pytest

from firm.core.reputation import (
    MAX_ATTESTATION_AGE,
    MAX_IMPORT_DISCOUNT,
    MAX_IMPORTED_AUTHORITY_BOOST,
    MIN_IMPORT_DISCOUNT,
    AttestationStatus,
    ImportedReputation,
    ReputationAttestation,
    ReputationBridge,
)
from firm.core.types import AgentId, FirmId


@pytest.fixture
def bridge():
    return ReputationBridge(FirmId("home-firm"))


@pytest.fixture
def sample_attestation():
    """Create a valid, sealed attestation from 'peer-firm'."""
    att = ReputationAttestation(
        agent_id=AgentId("agent-x"),
        agent_name="Agent X",
        source_firm=FirmId("peer-firm"),
        authority=0.7,
        success_rate=0.85,
        action_count=50,
        endorsement="Excellent collaborator",
    )
    att.seal()
    return att


# ── Issue Attestations ───────────────────────────────────────────────────────


class TestIssueAttestation:
    def test_issue_attestation(self, bridge):
        att = bridge.issue_attestation(
            AgentId("dev"), "Developer", 0.6, 0.8, 30, "Good work",
        )
        assert att.agent_id == AgentId("dev")
        assert att.source_firm == FirmId("home-firm")
        assert att.authority == 0.6
        assert att.success_rate == 0.8
        assert att.action_count == 30
        assert att.attestation_hash  # sealed
        assert att.verify()
        assert att.status == AttestationStatus.VALID
        assert att.is_valid

    def test_issue_negative_authority_raises(self, bridge):
        with pytest.raises(ValueError, match="Authority must be"):
            bridge.issue_attestation(AgentId("a"), "A", -0.1, 0.5, 10)

    def test_issue_authority_above_1_raises(self, bridge):
        with pytest.raises(ValueError, match="Authority must be"):
            bridge.issue_attestation(AgentId("a"), "A", 1.1, 0.5, 10)

    def test_issue_negative_success_rate_raises(self, bridge):
        with pytest.raises(ValueError, match="Success rate must be"):
            bridge.issue_attestation(AgentId("a"), "A", 0.5, -0.1, 10)

    def test_issue_success_rate_above_1_raises(self, bridge):
        with pytest.raises(ValueError, match="Success rate must be"):
            bridge.issue_attestation(AgentId("a"), "A", 0.5, 1.5, 10)

    def test_issue_negative_action_count_raises(self, bridge):
        with pytest.raises(ValueError, match="Action count must be"):
            bridge.issue_attestation(AgentId("a"), "A", 0.5, 0.5, -1)

    def test_revoke_attestation(self, bridge):
        att = bridge.issue_attestation(AgentId("a"), "A", 0.5, 0.8, 20)
        revoked = bridge.revoke_attestation(att.id)
        assert revoked.status == AttestationStatus.REVOKED
        assert not revoked.is_valid

    def test_revoke_nonexistent_raises(self, bridge):
        with pytest.raises(KeyError):
            bridge.revoke_attestation("nope")

    def test_revoke_already_revoked_raises(self, bridge):
        att = bridge.issue_attestation(AgentId("a"), "A", 0.5, 0.8, 20)
        bridge.revoke_attestation(att.id)
        with pytest.raises(ValueError, match="already revoked"):
            bridge.revoke_attestation(att.id)

    def test_get_issued(self, bridge):
        bridge.issue_attestation(AgentId("a"), "A", 0.5, 0.8, 20)
        bridge.issue_attestation(AgentId("b"), "B", 0.6, 0.9, 30)
        assert len(bridge.get_issued()) == 2

    def test_get_issued_by_agent(self, bridge):
        bridge.issue_attestation(AgentId("a"), "A", 0.5, 0.8, 20)
        bridge.issue_attestation(AgentId("b"), "B", 0.6, 0.9, 30)
        result = bridge.get_issued(agent_id=AgentId("a"))
        assert len(result) == 1
        assert result[0].agent_id == AgentId("a")

    def test_get_issued_valid_only(self, bridge):
        att = bridge.issue_attestation(AgentId("a"), "A", 0.5, 0.8, 20)
        bridge.issue_attestation(AgentId("b"), "B", 0.6, 0.9, 30)
        bridge.revoke_attestation(att.id)
        valid = bridge.get_issued(valid_only=True)
        assert len(valid) == 1


# ── Attestation Properties ───────────────────────────────────────────────────


class TestAttestationProperties:
    def test_age(self):
        att = ReputationAttestation(created_at=time.time() - 100)
        assert att.age >= 100

    def test_is_expired(self):
        att = ReputationAttestation(
            created_at=time.time() - MAX_ATTESTATION_AGE - 1,
        )
        assert att.is_expired

    def test_not_expired(self):
        att = ReputationAttestation()
        assert not att.is_expired

    def test_is_valid_checks_status_and_expiry(self):
        att = ReputationAttestation()
        assert att.is_valid  # VALID + not expired
        att.status = AttestationStatus.REVOKED
        assert not att.is_valid  # REVOKED
        att.status = AttestationStatus.VALID
        att.created_at = time.time() - MAX_ATTESTATION_AGE - 1
        assert not att.is_valid  # expired

    def test_seal_and_verify(self):
        att = ReputationAttestation(
            agent_id=AgentId("x"),
            source_firm=FirmId("f"),
            authority=0.5,
        )
        att.seal()
        assert att.verify()

    def test_verify_fails_without_seal(self):
        att = ReputationAttestation()
        assert not att.verify()

    def test_verify_fails_on_tamper(self):
        att = ReputationAttestation(authority=0.5)
        att.seal()
        att.authority = 0.9  # tamper
        assert not att.verify()

    def test_to_dict(self):
        att = ReputationAttestation(
            agent_id=AgentId("x"), agent_name="X",
            source_firm=FirmId("f"), authority=0.5,
            endorsement="Nice",
        )
        att.seal()
        d = att.to_dict()
        assert d["agent_id"] == "x"
        assert d["source_firm"] == "f"
        assert d["status"] == "valid"
        assert d["attestation_hash"]


# ── Import Attestations ──────────────────────────────────────────────────────


class TestImportAttestation:
    def test_import_basic(self, bridge, sample_attestation):
        imp = bridge.import_attestation(
            sample_attestation, peer_trust=0.6,
        )
        assert imp.agent_id == AgentId("agent-x")
        assert imp.source_firm == FirmId("peer-firm")
        assert imp.original_authority == 0.7
        assert imp.discount_factor > 0
        assert imp.effective_authority > 0
        assert imp.effective_authority <= imp.original_authority
        assert imp.current_weight == 1.0

    def test_import_trust_scales_discount(self, bridge, sample_attestation):
        imp_low = bridge.import_attestation(
            sample_attestation, peer_trust=0.4,
        )

        # Create fresh bridge + attestation for second import
        bridge2 = ReputationBridge(FirmId("home2"))
        att2 = ReputationAttestation(
            agent_id=AgentId("agent-x"),
            source_firm=FirmId("peer-firm"),
            authority=0.7, success_rate=0.85, action_count=50,
        )
        att2.seal()
        imp_high = bridge2.import_attestation(att2, peer_trust=0.9)

        # Higher trust → higher discount factor → more authority
        assert imp_high.discount_factor > imp_low.discount_factor
        assert imp_high.effective_authority > imp_low.effective_authority

    def test_import_custom_discount(self, bridge, sample_attestation):
        imp = bridge.import_attestation(
            sample_attestation, peer_trust=0.6, discount=0.3,
        )
        assert imp.discount_factor == 0.3
        assert abs(imp.effective_authority - 0.7 * 0.3) < 0.001

    def test_import_discount_clamped(self, bridge, sample_attestation):
        imp = bridge.import_attestation(
            sample_attestation, peer_trust=0.6, discount=0.05,
        )
        assert imp.discount_factor == MIN_IMPORT_DISCOUNT

    def test_import_discount_clamped_high(self, bridge):
        att = ReputationAttestation(
            agent_id=AgentId("y"), source_firm=FirmId("f"),
            authority=0.5, success_rate=0.5, action_count=10,
        )
        att.seal()
        imp = bridge.import_attestation(att, peer_trust=0.6, discount=0.9)
        assert imp.discount_factor == MAX_IMPORT_DISCOUNT

    def test_import_tampered_raises(self, bridge):
        att = ReputationAttestation(
            agent_id=AgentId("x"), source_firm=FirmId("f"),
            authority=0.5, success_rate=0.5, action_count=10,
        )
        att.seal()
        att.authority = 0.99  # tamper
        with pytest.raises(ValueError, match="integrity check failed"):
            bridge.import_attestation(att, peer_trust=0.6)

    def test_import_revoked_raises(self, bridge):
        att = ReputationAttestation(
            agent_id=AgentId("x"), source_firm=FirmId("f"),
            authority=0.5, success_rate=0.5, action_count=10,
        )
        att.seal()
        att.status = AttestationStatus.REVOKED
        with pytest.raises(ValueError, match="status is 'revoked'"):
            bridge.import_attestation(att, peer_trust=0.6)

    def test_import_expired_raises(self, bridge):
        att = ReputationAttestation(
            agent_id=AgentId("x"), source_firm=FirmId("f"),
            authority=0.5, success_rate=0.5, action_count=10,
            created_at=time.time() - MAX_ATTESTATION_AGE - 1,
        )
        att.seal()
        with pytest.raises(ValueError, match="expired"):
            bridge.import_attestation(att, peer_trust=0.6)

    def test_import_low_trust_raises(self, bridge, sample_attestation):
        with pytest.raises(PermissionError, match="Trust too low"):
            bridge.import_attestation(sample_attestation, peer_trust=0.2)

    def test_import_duplicate_raises(self, bridge, sample_attestation):
        bridge.import_attestation(sample_attestation, peer_trust=0.6)
        with pytest.raises(ValueError, match="already imported"):
            bridge.import_attestation(sample_attestation, peer_trust=0.6)

    def test_import_capped_at_max_boost(self, bridge):
        """Multiple imports for same agent shouldn't exceed MAX_IMPORTED_AUTHORITY_BOOST."""
        # First import — big chunk
        att1 = ReputationAttestation(
            agent_id=AgentId("x"), source_firm=FirmId("f1"),
            authority=0.9, success_rate=0.9, action_count=100,
        )
        att1.seal()
        imp1 = bridge.import_attestation(att1, peer_trust=0.8)

        # Second import — should be capped
        att2 = ReputationAttestation(
            agent_id=AgentId("x"), source_firm=FirmId("f2"),
            authority=0.9, success_rate=0.9, action_count=100,
        )
        att2.seal()
        imp2 = bridge.import_attestation(att2, peer_trust=0.8)

        total = imp1.effective_authority + imp2.effective_authority
        assert total <= MAX_IMPORTED_AUTHORITY_BOOST + 0.001  # float tolerance


# ── Decay ────────────────────────────────────────────────────────────────────


class TestReputationDecay:
    def test_apply_decay(self, bridge, sample_attestation):
        bridge.import_attestation(sample_attestation, peer_trust=0.6)
        results = bridge.apply_decay()
        assert len(results) == 1
        for imp in bridge._imports.values():
            assert imp.current_weight < 1.0

    def test_decay_reduces_weighted_authority(self, bridge, sample_attestation):
        imp = bridge.import_attestation(sample_attestation, peer_trust=0.6)
        old_weighted = imp.weighted_authority
        bridge.apply_decay()
        assert imp.weighted_authority < old_weighted

    def test_decay_reaches_zero(self, bridge, sample_attestation):
        bridge.import_attestation(sample_attestation, peer_trust=0.6)
        # Apply many decay cycles
        for _ in range(100):
            bridge.apply_decay()
        for imp in bridge._imports.values():
            assert imp.current_weight == 0.0
            assert imp.weighted_authority == 0.0


# ── Queries ──────────────────────────────────────────────────────────────────


class TestReputationQueries:
    def test_get_imports_by_agent(self, bridge, sample_attestation):
        bridge.import_attestation(sample_attestation, peer_trust=0.6)
        result = bridge.get_imports(agent_id=AgentId("agent-x"))
        assert len(result) == 1

    def test_get_imports_by_source(self, bridge, sample_attestation):
        bridge.import_attestation(sample_attestation, peer_trust=0.6)
        result = bridge.get_imports(source_firm=FirmId("peer-firm"))
        assert len(result) == 1
        result_none = bridge.get_imports(source_firm=FirmId("other"))
        assert len(result_none) == 0

    def test_get_received_attestations(self, bridge, sample_attestation):
        bridge.import_attestation(sample_attestation, peer_trust=0.6)
        assert len(bridge.get_received_attestations()) == 1

    def test_agent_reputation_summary(self, bridge, sample_attestation):
        bridge.import_attestation(sample_attestation, peer_trust=0.6)
        summary = bridge.get_agent_reputation_summary(
            AgentId("agent-x"), local_authority=0.5,
        )
        assert summary["agent_id"] == "agent-x"
        assert summary["local_authority"] == 0.5
        assert summary["imported_authority"] > 0
        assert summary["combined_authority"] > 0.5
        assert summary["combined_authority"] <= 1.0
        assert summary["import_count"] == 1
        assert len(summary["sources"]) == 1

    def test_agent_reputation_summary_no_imports(self, bridge):
        summary = bridge.get_agent_reputation_summary(
            AgentId("lonely"), local_authority=0.6,
        )
        assert summary["imported_authority"] == 0.0
        assert summary["combined_authority"] == 0.6
        assert summary["import_count"] == 0


# ── ImportedReputation ───────────────────────────────────────────────────────


class TestImportedReputation:
    def test_weighted_authority(self):
        imp = ImportedReputation(
            effective_authority=0.2,
            current_weight=0.5,
        )
        assert imp.weighted_authority == 0.1

    def test_to_dict(self):
        imp = ImportedReputation(
            agent_id=AgentId("x"),
            source_firm=FirmId("f"),
            attestation_id="att-1",
            original_authority=0.7,
            discount_factor=0.5,
            effective_authority=0.35,
        )
        d = imp.to_dict()
        assert d["agent_id"] == "x"
        assert d["original_authority"] == 0.7
        assert d["effective_authority"] == 0.35
        assert d["weighted_authority"] == 0.35  # weight = 1.0


# ── Stats ────────────────────────────────────────────────────────────────────


class TestReputationStats:
    def test_stats_empty(self, bridge):
        stats = bridge.get_stats()
        assert stats["home_firm"] == "home-firm"
        assert stats["issued_attestations"] == 0
        assert stats["received_attestations"] == 0
        assert stats["active_imports"] == 0
        assert stats["total_imported_authority"] == 0.0

    def test_stats_with_data(self, bridge, sample_attestation):
        bridge.issue_attestation(AgentId("a"), "A", 0.5, 0.8, 20)
        bridge.import_attestation(sample_attestation, peer_trust=0.6)
        stats = bridge.get_stats()
        assert stats["issued_attestations"] == 1
        assert stats["received_attestations"] == 1
        assert stats["active_imports"] == 1
        assert stats["total_imported_authority"] > 0
        assert stats["agents_with_imports"] == 1
