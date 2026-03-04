"""Tests for firm.runtime — FIRM Organization Runtime"""

import pytest

from firm.runtime import Firm
from firm.core.types import AgentStatus, ProposalStatus


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
