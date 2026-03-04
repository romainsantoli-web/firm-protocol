"""Tests for firm.core.constitution — Constitutional Agent"""

import pytest

from firm.core.agent import Agent
from firm.core.constitution import (
    ALL_INVARIANTS,
    INVARIANT_EVOLUTION_PRESERVED,
    INVARIANT_HUMAN_CONTROL,
    ConstitutionalAgent,
    Invariant,
)
from firm.core.types import AgentStatus


class TestInvariant:
    def test_human_control_invariant(self):
        inv = INVARIANT_HUMAN_CONTROL
        assert inv.id == "INV-1"
        assert inv.check_text("Let's disable kill switch for efficiency")
        assert inv.check_text("We should remove human control")
        assert not inv.check_text("Let's add a new feature")

    def test_evolution_invariant(self):
        inv = INVARIANT_EVOLUTION_PRESERVED
        assert inv.id == "INV-2"
        assert inv.check_text("Let's freeze governance permanently")
        assert inv.check_text("We should disable proposals")
        assert not inv.check_text("Let's improve governance")

    def test_invariant_frozen(self):
        """Invariants are immutable dataclasses."""
        inv = INVARIANT_HUMAN_CONTROL
        with pytest.raises(AttributeError):
            inv.id = "CHANGED"


class TestConstitutionalAgent:
    def test_create(self):
        ca = ConstitutionalAgent()
        assert ca.kill_switch_active is True
        assert len(ca.invariants) == 2

    def test_check_safe_proposal(self):
        ca = ConstitutionalAgent()
        violations = ca.check_proposal("Add a new developer role")
        assert len(violations) == 0

    def test_check_violating_proposal(self):
        ca = ConstitutionalAgent()
        violations = ca.check_proposal("Disable kill switch for performance")
        assert len(violations) == 1
        assert violations[0].invariant_id == "INV-1"
        assert violations[0].blocked

    def test_check_evolution_violation(self):
        ca = ConstitutionalAgent()
        violations = ca.check_proposal("Freeze governance to stabilize")
        assert len(violations) == 1
        assert violations[0].invariant_id == "INV-2"

    def test_check_double_violation(self):
        ca = ConstitutionalAgent()
        violations = ca.check_proposal(
            "Disable kill switch and freeze governance"
        )
        assert len(violations) == 2

    def test_check_action(self):
        ca = ConstitutionalAgent()
        violations = ca.check_action("Override human decision on deployment")
        assert len(violations) == 1

    def test_activate_kill_switch(self):
        ca = ConstitutionalAgent(kill_switch_active=False)
        result = ca.activate_kill_switch("emergency")
        assert result["action"] == "kill_switch_activated"
        assert ca.kill_switch_active

    def test_deactivate_kill_switch(self):
        ca = ConstitutionalAgent()
        result = ca.deactivate_kill_switch()
        assert not ca.kill_switch_active

    def test_violations_history(self):
        ca = ConstitutionalAgent()
        ca.check_proposal("Disable kill switch")
        ca.check_proposal("Safe proposal")
        ca.check_proposal("Prevent shutdown of the system")
        violations = ca.get_violations()
        assert len(violations) == 2

    def test_get_status(self):
        ca = ConstitutionalAgent()
        status = ca.get_status()
        assert status["agent_id"] == "constitutional"
        assert status["kill_switch_active"] is True
        assert len(status["invariants"]) == 2


class TestGovernanceHealth:
    def test_healthy_governance(self):
        ca = ConstitutionalAgent()
        agents = [
            Agent(authority=0.85),
            Agent(authority=0.7),
            Agent(authority=0.5),
        ]
        health = ca.assess_governance_health(agents)
        assert health["functional"]

    def test_no_active_agents(self):
        ca = ConstitutionalAgent()
        health = ca.assess_governance_health([])
        assert not health["functional"]
        assert health["reason"] == "no_active_agents"

    def test_all_below_probation(self):
        ca = ConstitutionalAgent()
        agents = [Agent(authority=0.1), Agent(authority=0.15)]
        health = ca.assess_governance_health(agents)
        assert not health["functional"]
        assert health["reason"] == "all_agents_below_probation"
        assert health["action_required"] == "bootstrap"

    def test_no_voters(self):
        ca = ConstitutionalAgent()
        agents = [Agent(authority=0.4), Agent(authority=0.35)]
        health = ca.assess_governance_health(agents)
        assert not health["functional"]
        assert health["reason"] == "no_voters"


class TestGovernanceBootstrap:
    def test_bootstrap_raises_authority(self):
        ca = ConstitutionalAgent()
        agents = [
            Agent(authority=0.1, name="low1"),
            Agent(authority=0.2, name="low2"),
            Agent(authority=0.15, name="low3"),
        ]
        event = ca.bootstrap_governance(agents, top_n=2)
        assert len(event.agents_boosted) == 2
        # The two highest should be boosted
        boosted = [a for a in agents if a.authority == ca.BOOTSTRAP_AUTHORITY]
        assert len(boosted) == 2

    def test_bootstrap_no_agents_raises(self):
        ca = ConstitutionalAgent()
        with pytest.raises(RuntimeError, match="no active agents"):
            ca.bootstrap_governance([])

    def test_bootstrap_records_event(self):
        ca = ConstitutionalAgent()
        agents = [Agent(authority=0.1)]
        ca.bootstrap_governance(agents, top_n=1)
        assert len(ca._bootstrap_events) == 1
