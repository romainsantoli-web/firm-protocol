"""Tests for Spawn/Merge Engine (Layer 7)."""
import pytest
from firm.core.agent import Agent, AgentRole
from firm.core.spawn import (
    SpawnEngine,
    SpawnEvent,
    SPAWN_AUTHORITY_FRACTION,
    SPAWN_CREDIT_FRACTION,
    MIN_AUTHORITY_TO_SPAWN,
    MIN_AUTHORITY_TO_MERGE,
)
from firm.core.types import AgentStatus


class TestSpawn:
    def test_spawn_basic(self):
        engine = SpawnEngine()
        parent = Agent(name="parent", authority=0.8, credits=100.0)
        child = engine.spawn(parent, "child")
        assert child.name == "child"
        assert abs(child.authority - 0.8 * SPAWN_AUTHORITY_FRACTION) < 0.001
        assert abs(child.credits - 100.0 * SPAWN_CREDIT_FRACTION) < 0.01
        assert parent.credits < 100.0  # Deducted

    def test_spawn_insufficient_authority(self):
        engine = SpawnEngine()
        parent = Agent(name="weak", authority=0.3, credits=100.0)
        with pytest.raises(PermissionError, match="authority"):
            engine.spawn(parent, "child")

    def test_spawn_not_active(self):
        engine = SpawnEngine()
        parent = Agent(name="suspended", authority=0.8, credits=100.0,
                       status=AgentStatus.SUSPENDED)
        with pytest.raises(PermissionError, match="not active"):
            engine.spawn(parent, "child")

    def test_spawn_with_roles(self):
        engine = SpawnEngine()
        parent = Agent(name="parent", authority=0.8, credits=100.0)
        roles = [AgentRole(name="worker")]
        child = engine.spawn(parent, "child", roles=roles)
        assert child.has_role("worker")

    def test_spawn_custom_fractions(self):
        engine = SpawnEngine()
        parent = Agent(name="parent", authority=0.8, credits=200.0)
        child = engine.spawn(parent, "child", authority_fraction=0.5, credit_fraction=0.1)
        assert abs(child.authority - 0.4) < 0.001
        assert abs(child.credits - 20.0) < 0.01

    def test_spawn_records_event(self):
        engine = SpawnEngine()
        parent = Agent(name="parent", authority=0.8, credits=100.0)
        child = engine.spawn(parent, "child")
        events = engine.get_events(event_type="spawn")
        assert len(events) == 1
        assert parent.id in events[0].parent_ids
        assert child.id in events[0].child_ids


class TestMerge:
    def test_merge_basic(self):
        engine = SpawnEngine()
        a = Agent(name="alice", authority=0.7, credits=50.0)
        b = Agent(name="bob", authority=0.6, credits=30.0)
        merged = engine.merge(a, b, "alice-bob")
        assert merged.name == "alice-bob"
        assert abs(merged.credits - 80.0) < 0.01
        assert a.status == AgentStatus.TERMINATED
        assert b.status == AgentStatus.TERMINATED

    def test_merge_authority_weighted_average(self):
        engine = SpawnEngine()
        a = Agent(name="alice", authority=0.8, credits=50.0)
        b = Agent(name="bob", authority=0.6, credits=50.0)
        # Record successes to create success_rate difference
        a._action_count = 10
        a._success_count = 9  # 90%
        b._action_count = 10
        b._success_count = 1  # 10%
        merged = engine.merge(a, b, "merged")
        # Alice has higher success rate, so merged authority should be closer to hers
        assert merged.authority > 0.7

    def test_merge_same_agent(self):
        engine = SpawnEngine()
        a = Agent(name="alice", authority=0.7)
        with pytest.raises(ValueError, match="itself"):
            engine.merge(a, a, "self-merge")

    def test_merge_insufficient_authority_a(self):
        engine = SpawnEngine()
        a = Agent(name="weak", authority=0.3)
        b = Agent(name="strong", authority=0.7)
        with pytest.raises(PermissionError, match="authority"):
            engine.merge(a, b, "merged")

    def test_merge_insufficient_authority_b(self):
        engine = SpawnEngine()
        a = Agent(name="strong", authority=0.7)
        b = Agent(name="weak", authority=0.3)
        with pytest.raises(PermissionError, match="authority"):
            engine.merge(a, b, "merged")

    def test_merge_unions_roles(self):
        engine = SpawnEngine()
        a = Agent(name="alice", authority=0.7)
        b = Agent(name="bob", authority=0.6)
        a.grant_role(AgentRole(name="dev"))
        b.grant_role(AgentRole(name="qa"))
        merged = engine.merge(a, b, "merged")
        assert merged.has_role("dev")
        assert merged.has_role("qa")

    def test_merge_combines_history(self):
        engine = SpawnEngine()
        a = Agent(name="alice", authority=0.7)
        b = Agent(name="bob", authority=0.6)
        a._action_count = 5
        a._success_count = 4
        b._action_count = 3
        b._success_count = 2
        merged = engine.merge(a, b, "merged")
        assert merged._action_count == 8
        assert merged._success_count == 6

    def test_merge_records_event(self):
        engine = SpawnEngine()
        a = Agent(name="alice", authority=0.7)
        b = Agent(name="bob", authority=0.6)
        engine.merge(a, b, "merged")
        events = engine.get_events(event_type="merge")
        assert len(events) == 1


class TestSplit:
    def test_split_basic(self):
        engine = SpawnEngine()
        agent = Agent(name="original", authority=0.8, credits=100.0)
        a, b = engine.split(agent, "half-a", "half-b")
        assert a.name == "half-a"
        assert b.name == "half-b"
        assert abs(a.authority - 0.4) < 0.001
        assert abs(b.authority - 0.4) < 0.001
        assert abs(a.credits + b.credits - 100.0) < 0.01
        assert agent.status == AgentStatus.TERMINATED

    def test_split_custom_ratio(self):
        engine = SpawnEngine()
        agent = Agent(name="original", authority=0.8, credits=100.0)
        a, b = engine.split(agent, "big", "small", authority_ratio=0.7)
        assert abs(a.authority - 0.56) < 0.001  # 0.8 * 0.7
        assert abs(b.authority - 0.24) < 0.001  # 0.8 * 0.3

    def test_split_invalid_ratio_low(self):
        engine = SpawnEngine()
        agent = Agent(name="original", authority=0.8)
        with pytest.raises(ValueError, match="ratio"):
            engine.split(agent, "a", "b", authority_ratio=0.05)

    def test_split_invalid_ratio_high(self):
        engine = SpawnEngine()
        agent = Agent(name="original", authority=0.8)
        with pytest.raises(ValueError, match="ratio"):
            engine.split(agent, "a", "b", authority_ratio=0.95)

    def test_split_insufficient_authority(self):
        engine = SpawnEngine()
        agent = Agent(name="weak", authority=0.3)
        with pytest.raises(PermissionError, match="authority"):
            engine.split(agent, "a", "b")

    def test_split_not_active(self):
        engine = SpawnEngine()
        agent = Agent(name="suspended", authority=0.8, status=AgentStatus.SUSPENDED)
        with pytest.raises(PermissionError, match="not active"):
            engine.split(agent, "a", "b")

    def test_split_with_roles(self):
        engine = SpawnEngine()
        agent = Agent(name="original", authority=0.8)
        roles_a = [AgentRole(name="dev")]
        roles_b = [AgentRole(name="qa")]
        a, b = engine.split(agent, "dev-side", "qa-side", roles_a=roles_a, roles_b=roles_b)
        assert a.has_role("dev")
        assert b.has_role("qa")

    def test_split_records_event(self):
        engine = SpawnEngine()
        agent = Agent(name="original", authority=0.8)
        a, b = engine.split(agent, "a", "b")
        events = engine.get_events(event_type="split")
        assert len(events) == 1
        assert agent.id in events[0].parent_ids
        assert a.id in events[0].child_ids
        assert b.id in events[0].child_ids


class TestSpawnQueries:
    def test_get_events_all(self):
        engine = SpawnEngine()
        p = Agent(name="p", authority=0.8, credits=100.0)
        engine.spawn(p, "c1")
        engine.spawn(p, "c2")
        assert len(engine.get_events()) == 2

    def test_get_lineage(self):
        engine = SpawnEngine()
        p = Agent(name="p", authority=0.8, credits=200.0)
        c = engine.spawn(p, "child")
        lineage = engine.get_lineage(p.id)
        assert len(lineage) == 1
        lineage_c = engine.get_lineage(c.id)
        assert len(lineage_c) == 1

    def test_get_stats(self):
        engine = SpawnEngine()
        p = Agent(name="p", authority=0.8, credits=200.0)
        engine.spawn(p, "c1")
        stats = engine.get_stats()
        assert stats["total_events"] == 1
        assert stats["spawns"] == 1
        assert stats["merges"] == 0

    def test_event_to_dict(self):
        event = SpawnEvent(event_type="spawn", parent_ids=["p1"], child_ids=["c1"])
        d = event.to_dict()
        assert d["event_type"] == "spawn"
        assert d["parent_ids"] == ["p1"]
