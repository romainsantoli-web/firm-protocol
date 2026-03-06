"""Tests for Role Fluidity Engine (Layer 3)."""
import time

import pytest

from firm.core.agent import Agent
from firm.core.roles import (
    MIN_AUTHORITY_FOR_CRITICAL_ROLE,
    RoleEngine,
)
from firm.core.types import AgentStatus


class TestRoleDefinition:
    def test_define_role(self):
        engine = RoleEngine()
        defn = engine.define_role("deployer", min_authority=0.5, description="Deploy code")
        assert defn.role.name == "deployer"
        assert defn.min_authority == 0.5
        assert not defn.is_critical

    def test_critical_role_minimum_authority(self):
        engine = RoleEngine()
        defn = engine.define_role("admin", is_critical=True, min_authority=0.3)
        assert defn.min_authority == MIN_AUTHORITY_FOR_CRITICAL_ROLE
        assert defn.is_critical

    def test_list_definitions(self):
        engine = RoleEngine()
        engine.define_role("a")
        engine.define_role("b")
        assert len(engine.list_definitions()) == 2

    def test_get_definition(self):
        engine = RoleEngine()
        engine.define_role("tester")
        assert engine.get_definition("tester") is not None
        assert engine.get_definition("nonexistent") is None

    def test_definition_to_dict(self):
        engine = RoleEngine()
        defn = engine.define_role("qa", max_holders=2)
        d = defn.to_dict()
        assert d["name"] == "qa"
        assert d["max_holders"] == 2


class TestRoleAssignment:
    def test_assign_role(self):
        engine = RoleEngine()
        engine.define_role("deployer", min_authority=0.4)
        agent = Agent(name="dev", authority=0.6)
        assignment = engine.assign(agent, "deployer")
        assert agent.has_role("deployer")
        assert assignment.agent_id == agent.id

    def test_assign_insufficient_authority(self):
        engine = RoleEngine()
        engine.define_role("admin", min_authority=0.8)
        agent = Agent(name="junior", authority=0.3)
        with pytest.raises(PermissionError, match="authority"):
            engine.assign(agent, "admin")

    def test_assign_undefined_role(self):
        engine = RoleEngine()
        agent = Agent(name="dev", authority=0.5)
        with pytest.raises(KeyError, match="not defined"):
            engine.assign(agent, "nonexistent")

    def test_assign_at_capacity(self):
        engine = RoleEngine()
        engine.define_role("singleton", max_holders=1, min_authority=0.3)
        a1 = Agent(name="a1", authority=0.5)
        a2 = Agent(name="a2", authority=0.5)
        engine.assign(a1, "singleton")
        with pytest.raises(ValueError, match="capacity"):
            engine.assign(a2, "singleton")

    def test_assign_already_held(self):
        engine = RoleEngine()
        engine.define_role("tester", min_authority=0.3)
        agent = Agent(name="dev", authority=0.5)
        engine.assign(agent, "tester")
        with pytest.raises(ValueError, match="already holds"):
            engine.assign(agent, "tester")

    def test_assign_probation_agent(self):
        engine = RoleEngine()
        engine.define_role("worker", min_authority=0.3)
        agent = Agent(name="dev", authority=0.5, status=AgentStatus.PROBATION)
        with pytest.raises(PermissionError, match="not active"):
            engine.assign(agent, "worker")


class TestRoleRevoke:
    def test_revoke_role(self):
        engine = RoleEngine()
        engine.define_role("tester", min_authority=0.3)
        agent = Agent(name="dev", authority=0.5)
        engine.assign(agent, "tester")
        assert engine.revoke(agent, "tester")
        assert not agent.has_role("tester")

    def test_revoke_not_held(self):
        engine = RoleEngine()
        agent = Agent(name="dev", authority=0.5)
        assert not engine.revoke(agent, "nonexistent")


class TestRoleTransfer:
    def test_transfer_role(self):
        engine = RoleEngine()
        engine.define_role("lead", min_authority=0.4)
        a1 = Agent(name="alice", authority=0.7)
        a2 = Agent(name="bob", authority=0.6)
        engine.assign(a1, "lead")
        engine.transfer(a1, a2, "lead")
        assert not a1.has_role("lead")
        assert a2.has_role("lead")

    def test_transfer_not_held(self):
        engine = RoleEngine()
        a1 = Agent(name="alice", authority=0.7)
        a2 = Agent(name="bob", authority=0.6)
        with pytest.raises(ValueError, match="doesn't hold"):
            engine.transfer(a1, a2, "lead")


class TestExpiry:
    def test_expire_roles(self):
        engine = RoleEngine()
        engine.define_role("temp", min_authority=0.3, default_ttl=0.001)
        agent = Agent(name="dev", authority=0.5)
        engine.assign(agent, "temp", ttl=0.001)
        time.sleep(0.01)
        expired = engine.expire_roles({agent.id: agent})
        assert len(expired) == 1
        assert not agent.has_role("temp")

    def test_no_expiry_when_fresh(self):
        engine = RoleEngine()
        engine.define_role("perm", min_authority=0.3, default_ttl=99999)
        agent = Agent(name="dev", authority=0.5)
        engine.assign(agent, "perm")
        expired = engine.expire_roles({agent.id: agent})
        assert len(expired) == 0


class TestRecommendations:
    def test_recommend_candidates(self):
        engine = RoleEngine()
        engine.define_role("lead", min_authority=0.5)
        agents = [
            Agent(name="high", authority=0.9),
            Agent(name="mid", authority=0.6),
            Agent(name="low", authority=0.3),
        ]
        recs = engine.recommend_candidates("lead", agents, top_n=2)
        assert len(recs) == 2
        assert recs[0]["agent_name"] == "high"

    def test_recommend_excludes_holders(self):
        engine = RoleEngine()
        engine.define_role("lead", min_authority=0.3)
        a1 = Agent(name="holder", authority=0.9)
        a2 = Agent(name="candidate", authority=0.7)
        engine.assign(a1, "lead")
        recs = engine.recommend_candidates("lead", [a1, a2])
        assert len(recs) == 1
        assert recs[0]["agent_name"] == "candidate"


class TestRoleQueries:
    def test_get_holders(self):
        engine = RoleEngine()
        engine.define_role("dev", min_authority=0.3)
        a1 = Agent(name="a1", authority=0.5)
        a2 = Agent(name="a2", authority=0.5)
        engine.assign(a1, "dev")
        engine.assign(a2, "dev")
        holders = engine.get_holders("dev")
        assert len(holders) == 2

    def test_get_stats(self):
        engine = RoleEngine()
        engine.define_role("dev", min_authority=0.3)
        stats = engine.get_stats()
        assert stats["defined_roles"] == 1
        assert stats["active_assignments"] == 0

    def test_get_history(self):
        engine = RoleEngine()
        engine.define_role("dev", min_authority=0.3)
        agent = Agent(name="dev", authority=0.5)
        engine.assign(agent, "dev")
        history = engine.get_history()
        assert len(history) == 1
        assert history[0]["type"] == "assigned"

    def test_assignment_to_dict(self):
        engine = RoleEngine()
        engine.define_role("dev", min_authority=0.3)
        agent = Agent(name="dev", authority=0.5)
        assignment = engine.assign(agent, "dev")
        d = assignment.to_dict()
        assert d["role"] == "dev"
        assert d["agent_id"] == agent.id
