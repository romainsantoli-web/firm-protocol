"""Tests for firm.core.agent"""

import pytest

from firm.core.agent import Agent, AgentRole
from firm.core.types import AgentId, AgentStatus


class TestAgentRole:
    def test_create_role(self):
        role = AgentRole(name="developer", description="Writes code")
        assert role.name == "developer"
        assert role.description == "Writes code"

    def test_role_equality(self):
        r1 = AgentRole(name="developer")
        r2 = AgentRole(name="developer", description="Different desc")
        assert r1 == r2

    def test_role_hash(self):
        r1 = AgentRole(name="dev")
        r2 = AgentRole(name="dev")
        assert hash(r1) == hash(r2)
        assert len({r1, r2}) == 1


class TestAgent:
    def test_create_default_agent(self):
        agent = Agent()
        assert agent.authority == 0.5
        assert agent.credits == 100.0
        assert agent.status == AgentStatus.ACTIVE
        assert agent.is_active
        assert agent.success_rate == 0.0

    def test_create_named_agent(self):
        agent = Agent(name="alice", authority=0.8, credits=200.0)
        assert agent.name == "alice"
        assert agent.authority == 0.8
        assert agent.credits == 200.0

    def test_record_success(self):
        agent = Agent()
        agent.record_success()
        agent.record_success()
        assert agent._action_count == 2
        assert agent._success_count == 2
        assert agent.success_rate == 1.0

    def test_record_failure(self):
        agent = Agent()
        agent.record_success()
        agent.record_failure()
        assert agent._action_count == 2
        assert agent.success_rate == 0.5

    def test_success_rate_no_actions(self):
        agent = Agent()
        assert agent.success_rate == 0.0

    def test_grant_role(self):
        agent = Agent()
        role = AgentRole(name="admin")
        assert agent.grant_role(role)
        assert agent.has_role("admin")

    def test_grant_duplicate_role(self):
        agent = Agent()
        role = AgentRole(name="admin")
        agent.grant_role(role)
        assert not agent.grant_role(role)

    def test_revoke_role(self):
        agent = Agent()
        agent.grant_role(AgentRole(name="admin"))
        assert agent.revoke_role("admin")
        assert not agent.has_role("admin")

    def test_revoke_nonexistent_role(self):
        agent = Agent()
        assert not agent.revoke_role("admin")

    def test_suspend(self):
        agent = Agent()
        agent.suspend("broke the rules")
        assert agent.status == AgentStatus.SUSPENDED
        assert not agent.is_active
        assert agent.metadata["suspension_reason"] == "broke the rules"

    def test_reactivate_on_probation(self):
        agent = Agent()
        agent.suspend("test")
        agent.reactivate()
        assert agent.status == AgentStatus.PROBATION

    def test_reactivate_only_from_suspended(self):
        agent = Agent()
        agent.reactivate()  # No-op when active
        assert agent.status == AgentStatus.ACTIVE

    def test_to_dict(self):
        agent = Agent(name="bob", authority=0.7)
        d = agent.to_dict()
        assert d["name"] == "bob"
        assert d["authority"] == 0.7
        assert d["status"] == "active"
        assert "id" in d
        assert "credits" in d
