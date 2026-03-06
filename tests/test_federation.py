"""Tests for firm.core.federation — Inter-Firm Protocol (Layer 8)."""

import time

import pytest

from firm.core.federation import (
    INITIAL_TRUST,
    MAX_SECONDMENT_DURATION,
    SECONDMENT_AUTHORITY_DISCOUNT,
    FederationEngine,
    FederationMessage,
    MessageType,
    PeerFirm,
    PeerStatus,
    SecondmentStatus,
)
from firm.core.types import AgentId, FirmId


@pytest.fixture
def engine():
    return FederationEngine(FirmId("home-firm"), "Home FIRM")


@pytest.fixture
def peer_id():
    return FirmId("peer-alpha")


# ── Peer Management ─────────────────────────────────────────────────────────


class TestPeerManagement:
    def test_register_peer(self, engine, peer_id):
        peer = engine.register_peer(peer_id, "Alpha Corp")
        assert peer.firm_id == peer_id
        assert peer.name == "Alpha Corp"
        assert peer.trust == INITIAL_TRUST
        assert peer.status == PeerStatus.ACTIVE
        assert peer.is_active

    def test_register_self_raises(self, engine):
        with pytest.raises(ValueError, match="Cannot register self"):
            engine.register_peer(FirmId("home-firm"), "Self")

    def test_register_duplicate_raises(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        with pytest.raises(ValueError, match="already registered"):
            engine.register_peer(peer_id, "Alpha Corp Again")

    def test_register_revoked_raises(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        engine.revoke_peer(peer_id, "bad actor")
        with pytest.raises(ValueError, match="was revoked"):
            engine.register_peer(peer_id, "Alpha Corp")

    def test_get_peer(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        assert engine.get_peer(peer_id) is not None
        assert engine.get_peer(FirmId("nonexistent")) is None

    def test_get_peers_active_only(self, engine):
        engine.register_peer(FirmId("a"), "A")
        engine.register_peer(FirmId("b"), "B")
        engine.suspend_peer(FirmId("b"))
        assert len(engine.get_peers(active_only=True)) == 1
        assert len(engine.get_peers(active_only=False)) == 2

    def test_suspend_peer(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        peer = engine.suspend_peer(peer_id, "maintenance")
        assert peer.status == PeerStatus.SUSPENDED
        assert not peer.is_active
        assert peer.metadata["suspension_reason"] == "maintenance"

    def test_suspend_nonexistent_raises(self, engine):
        with pytest.raises(KeyError):
            engine.suspend_peer(FirmId("nope"))

    def test_suspend_inactive_raises(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        engine.suspend_peer(peer_id)
        with pytest.raises(ValueError, match="not active"):
            engine.suspend_peer(peer_id)

    def test_reactivate_peer(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        engine.suspend_peer(peer_id)
        peer = engine.reactivate_peer(peer_id)
        assert peer.status == PeerStatus.ACTIVE
        assert peer.is_active

    def test_reactivate_not_suspended_raises(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        with pytest.raises(ValueError, match="not suspended"):
            engine.reactivate_peer(peer_id)

    def test_reactivate_nonexistent_raises(self, engine):
        with pytest.raises(KeyError):
            engine.reactivate_peer(FirmId("nope"))

    def test_revoke_peer(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        peer = engine.revoke_peer(peer_id, "breach of trust")
        assert peer.status == PeerStatus.REVOKED
        assert peer.trust == 0.0
        assert peer.metadata["revocation_reason"] == "breach of trust"

    def test_revoke_nonexistent_raises(self, engine):
        with pytest.raises(KeyError):
            engine.revoke_peer(FirmId("nope"))

    def test_revoke_recalls_active_secondments(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        # Boost trust for secondment
        peer = engine.get_peer(peer_id)
        peer.trust = 0.8
        sec = engine.second_agent(
            AgentId("a1"), "Agent One", 0.7, peer_id,
        )
        assert sec.status == SecondmentStatus.ACTIVE
        engine.revoke_peer(peer_id)
        assert sec.status == SecondmentStatus.RECALLED

    def test_peer_to_dict(self, engine, peer_id):
        peer = engine.register_peer(peer_id, "Alpha Corp", {"region": "EU"})
        d = peer.to_dict()
        assert d["firm_id"] == peer_id
        assert d["name"] == "Alpha Corp"
        assert d["metadata"]["region"] == "EU"
        assert d["status"] == "active"


# ── Trust Scoring ────────────────────────────────────────────────────────────


class TestTrustScoring:
    def test_trust_increase_on_success(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        old = engine.get_peer(peer_id).trust
        new = engine.update_trust(peer_id, success=True)
        assert new > old

    def test_trust_decrease_on_failure(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        old = engine.get_peer(peer_id).trust
        new = engine.update_trust(peer_id, success=False)
        assert new < old

    def test_trust_bounded_0_1(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        # Many successes
        for _ in range(200):
            engine.update_trust(peer_id, success=True)
        assert engine.get_peer(peer_id).trust <= 1.0

        # Many failures
        for _ in range(200):
            engine.update_trust(peer_id, success=False)
        assert engine.get_peer(peer_id).trust >= 0.0

    def test_trust_tracks_interactions(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        engine.update_trust(peer_id, success=True)
        engine.update_trust(peer_id, success=False)
        peer = engine.get_peer(peer_id)
        assert peer.successful_interactions == 1
        assert peer.failed_interactions == 1
        assert peer.interaction_count == 2
        assert peer.success_rate == 0.5

    def test_trust_nonexistent_raises(self, engine):
        with pytest.raises(KeyError):
            engine.update_trust(FirmId("nope"), success=True)

    def test_apply_trust_decay(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        peer = engine.get_peer(peer_id)
        old = peer.trust
        results = engine.apply_trust_decay()
        assert peer_id in results
        assert peer.trust < old

    def test_trust_weight(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        old = engine.get_peer(peer_id).trust
        # Weight=2 should have larger effect
        new = engine.update_trust(peer_id, success=True, weight=2.0)
        delta_weighted = new - old

        engine2 = FederationEngine(FirmId("h"), "H")
        engine2.register_peer(peer_id, "Alpha Corp")
        old2 = engine2.get_peer(peer_id).trust
        new2 = engine2.update_trust(peer_id, success=True, weight=1.0)
        delta_normal = new2 - old2

        assert delta_weighted > delta_normal


# ── Messaging ────────────────────────────────────────────────────────────────


class TestMessaging:
    def test_send_message(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        msg = engine.send_message(
            to_firm=peer_id,
            sender_agent=AgentId("ceo"),
            message_type=MessageType.NOTIFICATION,
            subject="Hello",
            body="Welcome to the federation",
        )
        assert msg.from_firm == FirmId("home-firm")
        assert msg.to_firm == peer_id
        assert msg.message_type == MessageType.NOTIFICATION
        assert msg.message_hash  # sealed
        assert msg.verify()

    def test_send_message_string_type(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        msg = engine.send_message(
            to_firm=peer_id,
            sender_agent=AgentId("ceo"),
            message_type="request",
            subject="Need resources",
        )
        assert msg.message_type == MessageType.REQUEST

    def test_send_to_nonexistent_raises(self, engine):
        with pytest.raises(KeyError):
            engine.send_message(
                FirmId("nope"), AgentId("a"), MessageType.NOTIFICATION, "Hi",
            )

    def test_send_to_inactive_raises(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        engine.suspend_peer(peer_id)
        with pytest.raises(ValueError, match="not active"):
            engine.send_message(
                peer_id, AgentId("a"), MessageType.NOTIFICATION, "Hi",
            )

    def test_send_empty_subject_raises(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        with pytest.raises(ValueError, match="empty"):
            engine.send_message(
                peer_id, AgentId("a"), MessageType.NOTIFICATION, "  ",
            )

    def test_get_messages_filter_by_peer(self, engine):
        engine.register_peer(FirmId("a"), "A")
        engine.register_peer(FirmId("b"), "B")
        engine.send_message(FirmId("a"), AgentId("x"), MessageType.NOTIFICATION, "Hi A")
        engine.send_message(FirmId("b"), AgentId("x"), MessageType.NOTIFICATION, "Hi B")
        msgs_a = engine.get_messages(peer_id=FirmId("a"))
        assert len(msgs_a) == 1
        assert msgs_a[0].to_firm == FirmId("a")

    def test_get_messages_filter_by_type(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        engine.send_message(peer_id, AgentId("x"), MessageType.NOTIFICATION, "Info")
        engine.send_message(peer_id, AgentId("x"), MessageType.REQUEST, "Need help")
        requests = engine.get_messages(message_type=MessageType.REQUEST)
        assert len(requests) == 1

    def test_message_integrity(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        msg = engine.send_message(
            peer_id, AgentId("x"), MessageType.NOTIFICATION, "Test",
        )
        assert msg.verify()
        # tamper
        msg.body = "tampered"
        assert not msg.verify()

    def test_message_to_dict(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        msg = engine.send_message(
            peer_id, AgentId("ceo"), MessageType.PROPOSAL, "Joint venture",
            body="Let's collaborate", metadata={"priority": "high"},
        )
        d = msg.to_dict()
        assert d["message_type"] == "proposal"
        assert d["metadata"]["priority"] == "high"
        assert d["message_hash"]


# ── Secondment ───────────────────────────────────────────────────────────────


class TestSecondment:
    def _setup_trusted_peer(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        peer = engine.get_peer(peer_id)
        peer.trust = 0.8
        return peer

    def test_second_agent(self, engine, peer_id):
        self._setup_trusted_peer(engine, peer_id)
        sec = engine.second_agent(
            AgentId("dev"), "Developer", 0.7, peer_id,
            reason="skill sharing",
        )
        assert sec.agent_id == AgentId("dev")
        assert sec.home_firm == FirmId("home-firm")
        assert sec.host_firm == peer_id
        assert sec.original_authority == 0.7
        assert sec.effective_authority == 0.7 * SECONDMENT_AUTHORITY_DISCOUNT
        assert sec.status == SecondmentStatus.ACTIVE
        assert sec.is_active

    def test_second_agent_low_trust_raises(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        # Trust is INITIAL_TRUST (0.3) < MIN_TRUST_TO_SECOND (0.5)
        with pytest.raises(PermissionError, match="Trust too low"):
            engine.second_agent(AgentId("dev"), "Dev", 0.7, peer_id)

    def test_second_agent_inactive_peer_raises(self, engine, peer_id):
        self._setup_trusted_peer(engine, peer_id)
        engine.suspend_peer(peer_id)
        with pytest.raises(ValueError, match="not active"):
            engine.second_agent(AgentId("dev"), "Dev", 0.7, peer_id)

    def test_second_agent_nonexistent_peer_raises(self, engine):
        with pytest.raises(KeyError):
            engine.second_agent(AgentId("dev"), "Dev", 0.7, FirmId("nope"))

    def test_double_secondment_raises(self, engine, peer_id):
        self._setup_trusted_peer(engine, peer_id)
        engine.second_agent(AgentId("dev"), "Dev", 0.7, peer_id)
        with pytest.raises(ValueError, match="already on active secondment"):
            engine.second_agent(AgentId("dev"), "Dev", 0.7, peer_id)

    def test_duration_capped(self, engine, peer_id):
        self._setup_trusted_peer(engine, peer_id)
        sec = engine.second_agent(
            AgentId("dev"), "Dev", 0.7, peer_id,
            duration=MAX_SECONDMENT_DURATION * 2,
        )
        assert sec.duration == MAX_SECONDMENT_DURATION

    def test_recall_secondment(self, engine, peer_id):
        self._setup_trusted_peer(engine, peer_id)
        sec = engine.second_agent(AgentId("dev"), "Dev", 0.7, peer_id)
        recalled = engine.recall_secondment(sec.id)
        assert recalled.status == SecondmentStatus.RECALLED
        assert recalled.completed_at is not None
        assert not recalled.is_active

    def test_recall_nonexistent_raises(self, engine):
        with pytest.raises(KeyError):
            engine.recall_secondment("nope")

    def test_recall_already_completed_raises(self, engine, peer_id):
        self._setup_trusted_peer(engine, peer_id)
        sec = engine.second_agent(AgentId("dev"), "Dev", 0.7, peer_id)
        engine.recall_secondment(sec.id)
        with pytest.raises(ValueError, match="not active"):
            engine.recall_secondment(sec.id)

    def test_complete_secondment(self, engine, peer_id):
        self._setup_trusted_peer(engine, peer_id)
        sec = engine.second_agent(AgentId("dev"), "Dev", 0.7, peer_id)
        completed = engine.complete_secondment(sec.id)
        assert completed.status == SecondmentStatus.COMPLETED
        assert completed.completed_at is not None

    def test_complete_nonexistent_raises(self, engine):
        with pytest.raises(KeyError):
            engine.complete_secondment("nope")

    def test_expire_secondments(self, engine, peer_id):
        self._setup_trusted_peer(engine, peer_id)
        sec = engine.second_agent(
            AgentId("dev"), "Dev", 0.7, peer_id, duration=1.0,
        )
        # Manipulate start time to make it expired
        sec.started_at = time.time() - 10.0
        expired = engine.expire_secondments()
        assert len(expired) == 1
        assert expired[0].status == SecondmentStatus.EXPIRED

    def test_get_secondment(self, engine, peer_id):
        self._setup_trusted_peer(engine, peer_id)
        sec = engine.second_agent(AgentId("dev"), "Dev", 0.7, peer_id)
        assert engine.get_secondment(sec.id) is sec
        assert engine.get_secondment("nope") is None

    def test_get_secondments_filters(self, engine, peer_id):
        self._setup_trusted_peer(engine, peer_id)
        sec1 = engine.second_agent(AgentId("a"), "A", 0.7, peer_id)
        engine.second_agent(AgentId("b"), "B", 0.6, peer_id)
        engine.complete_secondment(sec1.id)

        active = engine.get_secondments(active_only=True)
        assert len(active) == 1
        assert active[0].agent_id == AgentId("b")

        all_secs = engine.get_secondments(active_only=False)
        assert len(all_secs) == 2

        by_agent = engine.get_secondments(active_only=False, agent_id=AgentId("a"))
        assert len(by_agent) == 1

    def test_secondment_to_dict(self, engine, peer_id):
        self._setup_trusted_peer(engine, peer_id)
        sec = engine.second_agent(
            AgentId("dev"), "Developer", 0.7, peer_id, reason="collab",
        )
        d = sec.to_dict()
        assert d["agent_id"] == "dev"
        assert d["host_firm"] == peer_id
        assert d["status"] == "active"
        assert d["reason"] == "collab"
        assert "expires_at" in d


# ── Stats ────────────────────────────────────────────────────────────────────


class TestFederationStats:
    def test_stats_empty(self, engine):
        stats = engine.get_stats()
        assert stats["home_firm"] == "home-firm"
        assert stats["peers"]["total"] == 0
        assert stats["messages"]["total"] == 0
        assert stats["secondments"]["total"] == 0

    def test_stats_with_data(self, engine, peer_id):
        engine.register_peer(peer_id, "Alpha Corp")
        engine.send_message(
            peer_id, AgentId("x"), MessageType.NOTIFICATION, "Hi",
        )
        peer = engine.get_peer(peer_id)
        peer.trust = 0.8
        engine.second_agent(AgentId("dev"), "Dev", 0.7, peer_id)

        stats = engine.get_stats()
        assert stats["peers"]["total"] == 1
        assert stats["peers"]["active"] == 1
        assert stats["messages"]["total"] == 1
        assert stats["secondments"]["total"] == 1
        assert stats["secondments"]["active"] == 1


# ── PeerFirm properties ─────────────────────────────────────────────────────


class TestPeerFirmProperties:
    def test_success_rate_zero_interactions(self):
        peer = PeerFirm(firm_id=FirmId("x"), name="X")
        assert peer.success_rate == 0.0
        assert peer.interaction_count == 0

    def test_success_rate_computed(self):
        peer = PeerFirm(firm_id=FirmId("x"), name="X")
        peer.successful_interactions = 3
        peer.failed_interactions = 1
        assert peer.success_rate == 0.75


# ── FederationMessage seal/verify ────────────────────────────────────────────


class TestFederationMessageIntegrity:
    def test_seal_and_verify(self):
        msg = FederationMessage(
            from_firm=FirmId("a"),
            to_firm=FirmId("b"),
            sender_agent=AgentId("ceo"),
            message_type=MessageType.NOTIFICATION,
            subject="Test",
        )
        msg.seal()
        assert msg.message_hash
        assert msg.verify()

    def test_verify_fails_without_seal(self):
        msg = FederationMessage(subject="Test")
        assert not msg.verify()

    def test_verify_fails_on_tamper(self):
        msg = FederationMessage(subject="Original")
        msg.seal()
        msg.subject = "Tampered"
        assert not msg.verify()
