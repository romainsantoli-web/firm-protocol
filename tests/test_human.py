"""Tests for Human Override Interface (Layer 11)."""
import pytest
from firm.core.agent import Agent, AgentRole
from firm.core.constitution import ConstitutionalAgent
from firm.core.governance import GovernanceEngine, Proposal
from firm.core.human import HumanOverride, HUMAN_AGENT_ID, OverrideEvent
from firm.core.ledger import ResponsibilityLedger
from firm.core.types import AgentStatus, ProposalStatus


def _make_override() -> tuple[HumanOverride, ConstitutionalAgent, ResponsibilityLedger]:
    constitution = ConstitutionalAgent(kill_switch_active=False)
    ledger = ResponsibilityLedger()
    human = HumanOverride(constitution, ledger)
    return human, constitution, ledger


class TestKillSwitch:
    def test_activate(self):
        human, constitution, ledger = _make_override()
        event = human.activate_kill_switch(reason="emergency")
        assert constitution.kill_switch_active
        assert event.action == "kill_switch_on"
        assert event.reason == "emergency"
        # Logged to ledger
        entries = ledger.get_entries(limit=10)
        assert any("Kill switch activated" in e["description"] for e in entries)

    def test_deactivate(self):
        human, constitution, ledger = _make_override()
        human.activate_kill_switch()
        event = human.deactivate_kill_switch(reason="all clear")
        assert not constitution.kill_switch_active
        assert event.action == "kill_switch_off"


class TestAuthorityOverride:
    def test_set_authority(self):
        human, _, ledger = _make_override()
        agent = Agent(name="dev", authority=0.5)
        event = human.set_authority(agent, 0.9, reason="promotion")
        assert agent.authority == 0.9
        assert event.details["old_authority"] == 0.5

    def test_set_authority_clamps(self):
        human, _, _ = _make_override()
        agent = Agent(name="dev", authority=0.5)
        human.set_authority(agent, 1.5)
        assert agent.authority == 1.0
        human.set_authority(agent, -0.5)
        assert agent.authority == 0.0

    def test_set_authority_zero_terminates(self):
        human, _, _ = _make_override()
        agent = Agent(name="dev", authority=0.5)
        human.set_authority(agent, 0.0)
        assert agent.status == AgentStatus.TERMINATED

    def test_set_authority_reactivates_probation(self):
        human, _, _ = _make_override()
        agent = Agent(name="dev", authority=0.2, status=AgentStatus.PROBATION)
        human.set_authority(agent, 0.6)
        assert agent.status == AgentStatus.ACTIVE

    def test_set_authority_logged(self):
        human, _, ledger = _make_override()
        agent = Agent(name="dev", authority=0.5)
        human.set_authority(agent, 0.9)
        entries = ledger.get_entries(limit=10)
        assert any("HUMAN OVERRIDE" in e["description"] for e in entries)


class TestStatusOverride:
    def test_force_status(self):
        human, _, _ = _make_override()
        agent = Agent(name="dev", authority=0.5)
        event = human.force_status(agent, AgentStatus.SUSPENDED, reason="investigation")
        assert agent.status == AgentStatus.SUSPENDED
        assert event.details["old_status"] == "active"
        assert event.details["new_status"] == "suspended"

    def test_force_reactivate_terminated(self):
        human, _, _ = _make_override()
        agent = Agent(name="dev", authority=0.5, status=AgentStatus.TERMINATED)
        human.force_status(agent, AgentStatus.ACTIVE, reason="reprieve")
        assert agent.status == AgentStatus.ACTIVE


class TestRoleOverride:
    def test_force_grant_role(self):
        human, _, ledger = _make_override()
        agent = Agent(name="dev", authority=0.2)  # Low authority
        role = AgentRole(name="admin")
        event = human.force_grant_role(agent, role, reason="emergency")
        assert agent.has_role("admin")
        # Logged
        entries = ledger.get_entries(limit=10)
        assert any("admin" in e["description"] and "HUMAN OVERRIDE" in e["description"]
                    for e in entries)

    def test_force_revoke_role(self):
        human, _, _ = _make_override()
        agent = Agent(name="dev", authority=0.5)
        agent.grant_role(AgentRole(name="deployer"))
        event = human.force_revoke_role(agent, "deployer", reason="access review")
        assert not agent.has_role("deployer")
        assert event.action == "force_revoke_role"


class TestGovernanceOverride:
    def test_force_approve_proposal(self):
        human, _, ledger = _make_override()
        gov = GovernanceEngine()
        proposer = Agent(name="ceo", authority=0.9)
        proposal = gov.create_proposal(proposer, "New policy", "Details")
        event = human.force_approve_proposal(proposal, reason="urgent")
        assert proposal.status == ProposalStatus.APPROVED
        assert event.details["proposal_title"] == "New policy"
        # Logged
        entries = ledger.get_entries(limit=10)
        assert any("force-approved" in e["description"] for e in entries)

    def test_force_reject_proposal(self):
        human, _, _ = _make_override()
        gov = GovernanceEngine()
        proposer = Agent(name="ceo", authority=0.9)
        proposal = gov.create_proposal(proposer, "Bad idea", "Details")
        event = human.force_reject_proposal(proposal, reason="too risky")
        assert proposal.status == ProposalStatus.REJECTED
        assert event.details["old_status"] == "draft"


class TestCreditsOverride:
    def test_set_credits(self):
        human, _, ledger = _make_override()
        agent = Agent(name="dev", authority=0.5, credits=100.0)
        event = human.set_credits(agent, 500.0, reason="bonus")
        assert agent.credits == 500.0
        assert event.details["old_credits"] == 100.0
        assert event.details["new_credits"] == 500.0
        # Check ledger recorded the delta
        entries = ledger.get_entries(limit=10)
        assert any(e["credit_delta"] == 400.0 for e in entries)


class TestOverrideQueries:
    def test_get_events(self):
        human, _, _ = _make_override()
        agent = Agent(name="dev", authority=0.5)
        human.set_authority(agent, 0.8)
        human.activate_kill_switch()
        events = human.get_events()
        assert len(events) == 2

    def test_get_stats(self):
        human, _, _ = _make_override()
        agent = Agent(name="dev", authority=0.5)
        human.set_authority(agent, 0.8)
        human.activate_kill_switch()
        stats = human.get_stats()
        assert stats["total_overrides"] == 2
        assert stats["kill_switch_active"] is True
        assert "authority_override" in stats["action_counts"]

    def test_override_event_to_dict(self):
        event = OverrideEvent(action="test_action", reason="test reason")
        d = event.to_dict()
        assert d["action"] == "test_action"
        assert d["reason"] == "test reason"
        assert "timestamp" in d
