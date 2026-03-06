"""Tests for firm.core.authority — Authority Engine"""

import pytest

from firm.core.agent import Agent
from firm.core.authority import (
    AUTHORITY_MAX,
    AUTHORITY_MIN,
    DEFAULT_DECAY,
    DEFAULT_LEARNING_RATE,
    AuthorityEngine,
)


class TestAuthorityComputation:
    def test_success_delta(self):
        engine = AuthorityEngine()
        delta = engine.compute_delta(activated=True)
        assert delta == pytest.approx(DEFAULT_LEARNING_RATE)

    def test_failure_delta(self):
        engine = AuthorityEngine()
        delta = engine.compute_delta(activated=False)
        assert delta == pytest.approx(-DEFAULT_DECAY)

    def test_custom_rates(self):
        engine = AuthorityEngine(learning_rate=0.1, decay=0.05)
        assert engine.compute_delta(True) == pytest.approx(0.1)
        assert engine.compute_delta(False) == pytest.approx(-0.05)

    def test_invalid_learning_rate(self):
        with pytest.raises(ValueError, match="learning_rate"):
            AuthorityEngine(learning_rate=0.0)
        with pytest.raises(ValueError, match="learning_rate"):
            AuthorityEngine(learning_rate=1.5)

    def test_invalid_decay(self):
        with pytest.raises(ValueError, match="decay"):
            AuthorityEngine(decay=0.0)


class TestAuthorityUpdate:
    def test_success_increases_authority(self):
        engine = AuthorityEngine()
        agent = Agent(authority=0.5)
        change = engine.update(agent, success=True, reason="did good")
        assert agent.authority > 0.5
        assert change.delta > 0

    def test_failure_decreases_authority(self):
        engine = AuthorityEngine()
        agent = Agent(authority=0.5)
        change = engine.update(agent, success=False, reason="messed up")
        assert agent.authority < 0.5
        assert change.delta < 0

    def test_authority_capped_at_max(self):
        engine = AuthorityEngine(learning_rate=0.5)
        agent = Agent(authority=0.9)
        engine.update(agent, success=True)
        assert agent.authority <= AUTHORITY_MAX

    def test_authority_floored_at_min(self):
        engine = AuthorityEngine(decay=0.5)
        agent = Agent(authority=0.1)
        engine.update(agent, success=False)
        assert agent.authority >= AUTHORITY_MIN

    def test_records_history(self):
        engine = AuthorityEngine()
        agent = Agent(authority=0.5)
        engine.update(agent, success=True, reason="test")
        history = engine.get_history(agent_id=agent.id)
        assert len(history) == 1
        assert history[0]["reason"] == "test"

    def test_tracks_agent_actions(self):
        engine = AuthorityEngine()
        agent = Agent()
        engine.update(agent, success=True)
        engine.update(agent, success=False)
        assert agent._action_count == 2
        assert agent._success_count == 1
        assert agent._failure_count == 1


class TestAuthorityDecay:
    def test_decay_reduces_authority(self):
        engine = AuthorityEngine()
        agents = [Agent(authority=0.7), Agent(authority=0.3)]
        changes = engine.apply_decay(agents)
        assert len(changes) == 2
        assert all(c.delta < 0 for c in changes)

    def test_decay_skips_inactive(self):
        engine = AuthorityEngine()
        agent = Agent(authority=0.7)
        agent.suspend("test")
        changes = engine.apply_decay([agent])
        assert len(changes) == 0

    def test_decay_respects_minimum(self):
        engine = AuthorityEngine(decay=0.5)
        agent = Agent(authority=0.01)
        engine.apply_decay([agent])
        assert agent.authority >= AUTHORITY_MIN


class TestAuthorityThresholds:
    def test_can_propose(self):
        engine = AuthorityEngine()
        high = Agent(authority=0.85)
        low = Agent(authority=0.5)
        assert engine.can_propose(high)
        assert not engine.can_propose(low)

    def test_can_vote(self):
        engine = AuthorityEngine()
        high = Agent(authority=0.65)
        low = Agent(authority=0.3)
        assert engine.can_vote(high)
        assert not engine.can_vote(low)

    def test_needs_probation(self):
        engine = AuthorityEngine()
        low = Agent(authority=0.2)
        ok = Agent(authority=0.5)
        assert engine.needs_probation(low)
        assert not engine.needs_probation(ok)

    def test_should_terminate(self):
        engine = AuthorityEngine()
        dead = Agent(authority=0.02)
        alive = Agent(authority=0.3)
        assert engine.should_terminate(dead)
        assert not engine.should_terminate(alive)


class TestAuthorityRanking:
    def test_ranking_order(self):
        engine = AuthorityEngine()
        agents = [
            Agent(authority=0.3, name="low"),
            Agent(authority=0.9, name="high"),
            Agent(authority=0.6, name="mid"),
        ]
        ranking = engine.get_ranking(agents)
        assert ranking[0][1] == 0.9
        assert ranking[-1][1] == 0.3


class TestAuthorityHealth:
    def test_healthy_organization(self):
        engine = AuthorityEngine()
        agents = [
            Agent(authority=0.85),
            Agent(authority=0.7),
            Agent(authority=0.6),
        ]
        health = engine.assess_health(agents)
        assert health["healthy"]

    def test_no_active_agents(self):
        engine = AuthorityEngine()
        health = engine.assess_health([])
        assert not health["healthy"]
        assert health["severity"] == "critical"

    def test_mass_probation_warning(self):
        engine = AuthorityEngine()
        agents = [Agent(authority=0.1), Agent(authority=0.15), Agent(authority=0.2)]
        health = engine.assess_health(agents)
        assert not health["healthy"]

    def test_no_proposers_critical(self):
        engine = AuthorityEngine()
        agents = [Agent(authority=0.5), Agent(authority=0.6)]
        health = engine.assess_health(agents)
        findings = [f for f in health["findings"] if f["check"] == "no_proposers"]
        assert len(findings) == 1
