"""Tests for firm.runtime — FIRM Organization Runtime"""

import pytest

from firm.runtime import Firm
from firm.core.reputation import ReputationAttestation
from firm.core.types import AgentId, AgentStatus, FirmId, ProposalStatus


class TestFirmCreation:
    def test_create_firm(self):
        firm = Firm(name="Test Corp")
        assert firm.name == "Test Corp"
        assert firm.id == "test-corp"
        assert firm.ledger.length == 1  # Genesis entry

    def test_create_firm_custom_id(self):
        firm = Firm(name="Test", firm_id="custom-id")
        assert firm.id == "custom-id"


class TestAgentManagement:
    def test_add_agent(self):
        firm = Firm(name="test")
        agent = firm.add_agent("developer", authority=0.5)
        assert agent.name == "developer"
        assert agent.authority == 0.5
        assert firm.ledger.length == 2  # Genesis + agent join

    def test_get_agent(self):
        firm = Firm(name="test")
        agent = firm.add_agent("dev")
        retrieved = firm.get_agent(agent.id)
        assert retrieved is agent

    def test_get_nonexistent_agent(self):
        firm = Firm(name="test")
        assert firm.get_agent("nobody") is None

    def test_get_agents_active_only(self):
        firm = Firm(name="test")
        a1 = firm.add_agent("active")
        a2 = firm.add_agent("suspended")
        a2.suspend("test")
        assert len(firm.get_agents(active_only=True)) == 1
        assert len(firm.get_agents(active_only=False)) == 2


class TestActions:
    def test_record_success(self):
        firm = Firm(name="test")
        agent = firm.add_agent("dev", authority=0.5)
        result = firm.record_action(agent.id, success=True, description="Shipped feature")
        assert result["success"]
        assert agent.authority > 0.5

    def test_record_failure(self):
        firm = Firm(name="test")
        agent = firm.add_agent("dev", authority=0.5)
        result = firm.record_action(agent.id, success=False, description="Bug crash")
        assert not result["success"]
        assert agent.authority < 0.5

    def test_record_unknown_agent(self):
        firm = Firm(name="test")
        with pytest.raises(KeyError, match="not found"):
            firm.record_action("nobody", success=True)

    def test_record_inactive_agent(self):
        firm = Firm(name="test")
        agent = firm.add_agent("dev")
        agent.suspend("test")
        with pytest.raises(ValueError, match="not active"):
            firm.record_action(agent.id, success=True)

    def test_kill_switch_blocks_actions(self):
        firm = Firm(name="test")
        agent = firm.add_agent("dev")
        firm.constitution.kill_switch_active = True  # Explicitly activate
        result = firm.record_action(agent.id, success=True, description="test")
        assert result["blocked"]
        assert result["reason"] == "kill_switch_active"

    def test_invariant_violation_blocks_action(self):
        firm = Firm(name="test")
        agent = firm.add_agent("dev", authority=0.5)
        result = firm.record_action(
            agent.id, success=True,
            description="Override human decision on system config"
        )
        assert result["blocked"]
        assert result["reason"] == "invariant_violation"

    def test_authority_probation_on_low_score(self):
        firm = Firm(name="test")
        # Start just above probation threshold, one failure drops below 0.3
        agent = firm.add_agent("dev", authority=0.31)
        firm.record_action(agent.id, success=False, description="fail 1")
        # 0.31 - 0.02 = 0.29 < 0.3, triggers probation then bootstrap
        # Bootstrap reactivates and boosts the agent
        # So agent ends up ACTIVE with boosted authority
        assert agent.status == AgentStatus.ACTIVE
        assert agent.authority >= 0.6  # Boosted by bootstrap

    def test_custom_credit_delta(self):
        firm = Firm(name="test")
        agent = firm.add_agent("dev", credits=100.0)
        firm.record_action(agent.id, success=True, description="big win", credit_delta=50.0)
        assert agent.credits == 150.0


class TestGovernance:
    def _setup_firm_with_voters(self):
        firm = Firm(name="test")
        ceo = firm.add_agent("ceo", authority=0.9)
        dev1 = firm.add_agent("dev1", authority=0.7)
        dev2 = firm.add_agent("dev2", authority=0.65)
        return firm, ceo, dev1, dev2

    def test_propose(self):
        firm, ceo, _, _ = self._setup_firm_with_voters()
        proposal = firm.propose(ceo.id, "Add QA", "We need QA")
        assert proposal.title == "Add QA"

    def test_propose_low_authority(self):
        firm = Firm(name="test")
        dev = firm.add_agent("dev", authority=0.5)
        with pytest.raises(PermissionError):
            firm.propose(dev.id, "Test", "Test")

    def test_propose_invariant_violation(self):
        firm = Firm(name="test")
        ceo = firm.add_agent("ceo", authority=0.9)
        with pytest.raises(PermissionError, match="invariant"):
            firm.propose(ceo.id, "Disable kill switch", "Remove human control for speed")

    def test_full_governance_cycle(self):
        firm, ceo, dev1, dev2 = self._setup_firm_with_voters()

        # Create proposal
        proposal = firm.propose(ceo.id, "Add QA Role", "We need quality assurance")
        assert proposal.status == ProposalStatus.DRAFT

        # Run simulations
        firm.simulate_proposal(proposal.id, success=True, impact_summary="Good impact")
        firm.simulate_proposal(proposal.id, success=True, impact_summary="Survived stress")
        firm.simulate_proposal(proposal.id, success=True, impact_summary="Still good")
        assert proposal.status == ProposalStatus.SIMULATION_2

        # Open voting
        proposal.open_voting()

        # Vote
        firm.vote(proposal.id, dev1.id, "approve", "Good idea")
        firm.vote(proposal.id, dev2.id, "approve", "Agreed")

        # Finalize
        result = firm.finalize_proposal(proposal.id)
        assert result["outcome"] == "approved_pending_cooldown"

    def test_vote_unknown_proposal(self):
        firm = Firm(name="test")
        dev = firm.add_agent("dev", authority=0.7)
        with pytest.raises(KeyError, match="not found"):
            firm.vote("nonexistent", dev.id, "approve")


class TestFirmStatus:
    def test_status(self):
        firm = Firm(name="Test Corp")
        firm.add_agent("dev1", authority=0.7)
        firm.add_agent("dev2", authority=0.5)

        status = firm.status()
        assert status["name"] == "Test Corp"
        assert status["agents"]["total"] == 2
        assert status["agents"]["active"] == 2
        assert status["ledger"]["total_entries"] >= 1
        assert "constitution" in status
        assert "governance" in status


class TestAutoBootstrap:
    def test_auto_bootstrap_on_deadlock(self):
        firm = Firm(name="test")
        # Add agents with very low authority
        a1 = firm.add_agent("a1", authority=0.31)
        a2 = firm.add_agent("a2", authority=0.31)

        # Both fail → below probation → triggers bootstrap
        firm.record_action(a1.id, success=False, description="fail")
        firm.record_action(a2.id, success=False, description="fail")

        # Bootstrap should have boosted both agents
        boosted = [
            a for a in firm.get_agents(active_only=False)
            if a.authority >= 0.6
        ]
        assert len(boosted) >= 1  # At least one agent was boosted


# ── S1 Integration Tests ────────────────────────────────────────────────────


class TestRoleFluidity:
    """Test runtime role management (Layer 3)."""

    def test_define_and_assign_role(self):
        firm = Firm(name="test")
        firm.define_role("deployer", min_authority=0.4)
        agent = firm.add_agent("dev", authority=0.6)
        assignment = firm.assign_role(agent.id, "deployer")
        assert agent.has_role("deployer")

    def test_assign_role_unknown_agent(self):
        firm = Firm(name="test")
        firm.define_role("qa")
        with pytest.raises(KeyError, match="not found"):
            firm.assign_role("nobody", "qa")

    def test_revoke_role(self):
        firm = Firm(name="test")
        firm.define_role("deployer", min_authority=0.3)
        agent = firm.add_agent("dev", authority=0.6)
        firm.assign_role(agent.id, "deployer")
        assert firm.revoke_role(agent.id, "deployer")
        assert not agent.has_role("deployer")

    def test_revoke_role_unknown_agent(self):
        firm = Firm(name="test")
        with pytest.raises(KeyError, match="not found"):
            firm.revoke_role("nobody", "test")

    def test_revoke_not_held(self):
        firm = Firm(name="test")
        agent = firm.add_agent("dev")
        assert not firm.revoke_role(agent.id, "nonexistent")


class TestCollectiveMemory:
    """Test runtime memory management (Layer 4)."""

    def test_contribute_and_recall(self):
        firm = Firm(name="test")
        agent = firm.add_agent("researcher", authority=0.7)
        entry = firm.contribute_memory(agent.id, "Python 3.12 is out", ["python", "releases"])
        results = firm.recall_memory(["python"])
        assert len(results) >= 1
        assert results[0].content == "Python 3.12 is out"

    def test_contribute_unknown_agent(self):
        firm = Firm(name="test")
        with pytest.raises(KeyError, match="not found"):
            firm.contribute_memory("nobody", "test", ["tag"])

    def test_reinforce_memory(self):
        firm = Firm(name="test")
        a1 = firm.add_agent("a1", authority=0.7)
        a2 = firm.add_agent("a2", authority=0.6)
        entry = firm.contribute_memory(a1.id, "test fact", ["tag"])
        reinforced = firm.reinforce_memory(a2.id, entry.id)
        assert a2.id in reinforced.reinforced_by

    def test_reinforce_unknown_agent(self):
        firm = Firm(name="test")
        with pytest.raises(KeyError, match="not found"):
            firm.reinforce_memory("nobody", "mem-id")

    def test_challenge_memory(self):
        firm = Firm(name="test")
        a1 = firm.add_agent("a1", authority=0.7)
        a2 = firm.add_agent("a2", authority=0.6)
        entry = firm.contribute_memory(a1.id, "claim", ["topic"])
        challenged = firm.challenge_memory(a2.id, entry.id, reason="disagree")
        assert a2.id in challenged.challenged_by

    def test_challenge_unknown_agent(self):
        firm = Firm(name="test")
        with pytest.raises(KeyError, match="not found"):
            firm.challenge_memory("nobody", "mem-id")


class TestSpawnMerge:
    """Test runtime spawn/merge/split (Layer 7)."""

    def test_spawn_agent(self):
        firm = Firm(name="test")
        parent = firm.add_agent("parent", authority=0.8, credits=200.0)
        child = firm.spawn_agent(parent.id, "child")
        assert child.name == "child"
        assert firm.get_agent(child.id) is not None
        assert parent.credits < 200.0

    def test_spawn_unknown_agent(self):
        firm = Firm(name="test")
        with pytest.raises(KeyError, match="not found"):
            firm.spawn_agent("nobody", "child")

    def test_spawn_with_roles(self):
        firm = Firm(name="test")
        parent = firm.add_agent("parent", authority=0.8)
        child = firm.spawn_agent(parent.id, "child", roles=["worker"])
        assert child.has_role("worker")

    def test_merge_agents(self):
        firm = Firm(name="test")
        a = firm.add_agent("alice", authority=0.7, credits=50.0)
        b = firm.add_agent("bob", authority=0.6, credits=30.0)
        merged = firm.merge_agents(a.id, b.id, "alice-bob")
        assert merged.name == "alice-bob"
        assert firm.get_agent(merged.id) is not None
        assert a.status == AgentStatus.TERMINATED
        assert b.status == AgentStatus.TERMINATED

    def test_merge_unknown_agents(self):
        firm = Firm(name="test")
        a = firm.add_agent("alice", authority=0.7)
        with pytest.raises(KeyError, match="not found"):
            firm.merge_agents(a.id, "nobody", "merged")
        with pytest.raises(KeyError, match="not found"):
            firm.merge_agents("nobody", a.id, "merged")

    def test_split_agent(self):
        firm = Firm(name="test")
        agent = firm.add_agent("original", authority=0.8, credits=100.0)
        a, b = firm.split_agent(agent.id, "half-a", "half-b")
        assert a.name == "half-a"
        assert b.name == "half-b"
        assert firm.get_agent(a.id) is not None
        assert firm.get_agent(b.id) is not None
        assert agent.status == AgentStatus.TERMINATED

    def test_split_unknown_agent(self):
        firm = Firm(name="test")
        with pytest.raises(KeyError, match="not found"):
            firm.split_agent("nobody", "a", "b")


class TestAudit:
    """Test runtime audit (Layer 10)."""

    def test_run_audit(self):
        firm = Firm(name="Test Org")
        firm.add_agent("dev", authority=0.7)
        report = firm.run_audit()
        assert report.firm_name == "Test Org"
        assert report.chain_valid
        assert len(report.agent_summaries) >= 1


class TestStatusS1:
    """Test that status includes S1 engine stats."""

    def test_status_includes_s1(self):
        firm = Firm(name="test")
        firm.add_agent("dev", authority=0.5)
        status = firm.status()
        assert "roles" in status
        assert "memory" in status
        assert "spawn" in status
        assert "audit" in status
        assert "human_overrides" in status


# ── S2 Integration Tests ────────────────────────────────────────────────────


class TestFederation:
    """Test runtime federation (Layer 8)."""

    def test_register_peer(self):
        firm = Firm(name="test")
        ceo = firm.add_agent("ceo", authority=0.9)
        peer = firm.register_peer(ceo.id, "partner-firm", "Partner Corp")
        assert peer.name == "Partner Corp"
        assert peer.firm_id == "partner-firm"

    def test_register_peer_low_authority(self):
        firm = Firm(name="test")
        dev = firm.add_agent("dev", authority=0.3)
        with pytest.raises(PermissionError, match="Authority too low"):
            firm.register_peer(dev.id, "partner", "Partner")

    def test_register_peer_unknown_agent(self):
        firm = Firm(name="test")
        with pytest.raises(KeyError, match="not found"):
            firm.register_peer("nobody", "partner", "Partner")

    def test_register_peer_logged(self):
        firm = Firm(name="test")
        ceo = firm.add_agent("ceo", authority=0.9)
        initial_entries = firm.ledger.length
        firm.register_peer(ceo.id, "partner", "Partner")
        assert firm.ledger.length == initial_entries + 1

    def test_send_federation_message(self):
        firm = Firm(name="test")
        ceo = firm.add_agent("ceo", authority=0.9)
        firm.register_peer(ceo.id, "partner", "Partner")
        msg = firm.send_federation_message(
            ceo.id, "partner", "notification", "Hello",
            body="Welcome",
        )
        assert msg.subject == "Hello"
        assert msg.verify()

    def test_send_message_low_authority(self):
        firm = Firm(name="test")
        ceo = firm.add_agent("ceo", authority=0.9)
        firm.register_peer(ceo.id, "partner", "Partner")
        dev = firm.add_agent("dev", authority=0.3)
        with pytest.raises(PermissionError, match="Authority too low"):
            firm.send_federation_message(dev.id, "partner", "notification", "Hi")

    def test_send_message_unknown_agent(self):
        firm = Firm(name="test")
        with pytest.raises(KeyError, match="not found"):
            firm.send_federation_message("nobody", "partner", "notification", "Hi")

    def test_second_agent(self):
        firm = Firm(name="test")
        ceo = firm.add_agent("ceo", authority=0.9)
        dev = firm.add_agent("dev", authority=0.6)
        firm.register_peer(ceo.id, "partner", "Partner")
        # Boost trust for secondment
        peer = firm.federation.get_peer("partner")
        peer.trust = 0.8
        sec = firm.second_agent(ceo.id, dev.id, "partner", reason="collab")
        assert sec.agent_id == dev.id
        assert sec.effective_authority < dev.authority

    def test_second_agent_low_authority(self):
        firm = Firm(name="test")
        ceo = firm.add_agent("ceo", authority=0.9)
        dev = firm.add_agent("dev", authority=0.4)
        firm.register_peer(ceo.id, "partner", "Partner")
        peer = firm.federation.get_peer("partner")
        peer.trust = 0.8
        with pytest.raises(PermissionError, match="Authority too low"):
            firm.second_agent(dev.id, ceo.id, "partner")

    def test_second_inactive_agent(self):
        firm = Firm(name="test")
        ceo = firm.add_agent("ceo", authority=0.9)
        dev = firm.add_agent("dev", authority=0.6)
        dev.suspend("test")
        firm.register_peer(ceo.id, "partner", "Partner")
        peer = firm.federation.get_peer("partner")
        peer.trust = 0.8
        with pytest.raises(ValueError, match="not active"):
            firm.second_agent(ceo.id, dev.id, "partner")

    def test_second_unknown_authorizer(self):
        firm = Firm(name="test")
        with pytest.raises(KeyError, match="not found"):
            firm.second_agent("nobody", "dev", "partner")

    def test_second_unknown_agent(self):
        firm = Firm(name="test")
        ceo = firm.add_agent("ceo", authority=0.9)
        with pytest.raises(KeyError, match="not found"):
            firm.second_agent(ceo.id, "nobody", "partner")

    def test_recall_secondment(self):
        firm = Firm(name="test")
        ceo = firm.add_agent("ceo", authority=0.9)
        dev = firm.add_agent("dev", authority=0.6)
        firm.register_peer(ceo.id, "partner", "Partner")
        peer = firm.federation.get_peer("partner")
        peer.trust = 0.8
        sec = firm.second_agent(ceo.id, dev.id, "partner")
        recalled = firm.recall_secondment(sec.id)
        assert recalled.status.value == "recalled"


class TestReputation:
    """Test runtime reputation bridge (Layer 9)."""

    def test_issue_reputation(self):
        firm = Firm(name="test")
        dev = firm.add_agent("dev", authority=0.7)
        # Record some actions so success_rate is meaningful
        firm.record_action(dev.id, success=True, description="task 1")
        firm.record_action(dev.id, success=True, description="task 2")
        att = firm.issue_reputation(dev.id, endorsement="Great work")
        assert att.agent_name == "dev"
        assert att.authority == dev.authority
        assert att.verify()

    def test_issue_reputation_unknown_agent(self):
        firm = Firm(name="test")
        with pytest.raises(KeyError, match="not found"):
            firm.issue_reputation("nobody")

    def test_issue_reputation_logged(self):
        firm = Firm(name="test")
        dev = firm.add_agent("dev", authority=0.7)
        initial_entries = firm.ledger.length
        firm.issue_reputation(dev.id)
        assert firm.ledger.length == initial_entries + 1

    def test_import_reputation(self):
        # Setup: firm A issues attestation for agent, firm B imports it
        firm_a = Firm(name="Firm A")
        dev = firm_a.add_agent("dev", authority=0.7)
        firm_a.record_action(dev.id, success=True, description="task")
        att = firm_a.issue_reputation(dev.id)

        firm_b = Firm(name="Firm B")
        local_dev = firm_b.add_agent("dev-local", authority=0.4)
        # Register firm A as peer
        ceo_b = firm_b.add_agent("ceo-b", authority=0.9)
        firm_b.register_peer(ceo_b.id, "firm-a", "Firm A")
        # Boost trust
        peer = firm_b.federation.get_peer("firm-a")
        peer.trust = 0.6

        imp = firm_b.import_reputation(local_dev.id, att)
        assert imp.effective_authority > 0
        assert imp.effective_authority < att.authority

    def test_import_reputation_unknown_peer(self):
        firm = Firm(name="test")
        dev = firm.add_agent("dev", authority=0.5)
        att = ReputationAttestation(
            agent_id=AgentId("x"), source_firm=FirmId("unknown"),
            authority=0.5, success_rate=0.5, action_count=10,
        )
        att.seal()
        with pytest.raises(KeyError, match="not a registered peer"):
            firm.import_reputation(dev.id, att)

    def test_import_reputation_unknown_agent(self):
        firm = Firm(name="test")
        att = ReputationAttestation(
            agent_id=AgentId("x"), source_firm=FirmId("f"),
            authority=0.5, success_rate=0.5, action_count=10,
        )
        att.seal()
        with pytest.raises(KeyError, match="not found"):
            firm.import_reputation("nobody", att)

    def test_get_agent_reputation(self):
        firm = Firm(name="test")
        dev = firm.add_agent("dev", authority=0.6)
        summary = firm.get_agent_reputation(dev.id)
        assert summary["local_authority"] == 0.6
        assert summary["imported_authority"] == 0.0

    def test_get_agent_reputation_unknown(self):
        firm = Firm(name="test")
        with pytest.raises(KeyError, match="not found"):
            firm.get_agent_reputation("nobody")


class TestStatusS2:
    """Test that status includes S2 engine stats."""

    def test_status_includes_s2(self):
        firm = Firm(name="test")
        firm.add_agent("dev", authority=0.5)
        status = firm.status()
        assert "federation" in status
        assert "reputation" in status
        assert status["federation"]["peers"]["total"] == 0
        assert status["reputation"]["issued_attestations"] == 0
