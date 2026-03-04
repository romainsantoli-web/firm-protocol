"""Tests for Collective Memory Engine (Layer 4)."""
import time
import pytest
from firm.core.memory import (
    MemoryEngine,
    MemoryEntry,
    MemoryConflict,
    REINFORCEMENT_BOOST,
    CHALLENGE_PENALTY,
    MIN_MEMORY_WEIGHT,
)
from firm.core.types import AgentId


class TestMemoryContribute:
    def test_contribute(self):
        engine = MemoryEngine()
        entry = engine.contribute("Python is great", ["python", "lang"], AgentId("a1"), 0.8)
        assert entry.content == "Python is great"
        assert entry.tags == ["python", "lang"]
        assert entry.weight == 0.8

    def test_contribute_empty_content(self):
        engine = MemoryEngine()
        with pytest.raises(ValueError, match="empty"):
            engine.contribute("  ", ["tag"], AgentId("a1"), 0.5)

    def test_contribute_no_tags(self):
        engine = MemoryEngine()
        with pytest.raises(ValueError, match="tag"):
            engine.contribute("content", [], AgentId("a1"), 0.5)

    def test_contribute_caps_weight_at_1(self):
        engine = MemoryEngine()
        entry = engine.contribute("test", ["tag"], AgentId("a1"), 1.5)
        assert entry.weight <= 1.0

    def test_contribute_normalizes_tags(self):
        engine = MemoryEngine()
        entry = engine.contribute("test", ["  Python ", "LANG"], AgentId("a1"), 0.5)
        assert entry.tags == ["python", "lang"]


class TestMemoryRecall:
    def test_recall_by_tags(self):
        engine = MemoryEngine()
        engine.contribute("Python rocks", ["python", "language"], AgentId("a1"), 0.9)
        engine.contribute("Java is ok", ["java", "language"], AgentId("a2"), 0.4)
        results = engine.recall(["python"])
        assert len(results) >= 1
        assert results[0].content == "Python rocks"

    def test_recall_empty_tags(self):
        engine = MemoryEngine()
        engine.contribute("test", ["tag"], AgentId("a1"), 0.5)
        assert engine.recall([]) == []

    def test_recall_top_k(self):
        engine = MemoryEngine()
        for i in range(10):
            engine.contribute(f"entry-{i}", ["shared"], AgentId("a1"), 0.5)
        results = engine.recall(["shared"], top_k=3)
        assert len(results) == 3

    def test_recall_min_weight(self):
        engine = MemoryEngine()
        entry = engine.contribute("weak", ["tag"], AgentId("a1"), 0.005)
        # Weight is 0.005, below default min_weight
        results = engine.recall(["tag"], min_weight=0.01)
        assert len(results) == 0

    def test_recall_excludes_contested(self):
        engine = MemoryEngine()
        entry = engine.contribute("fact", ["sci"], AgentId("a1"), 0.5)
        engine.challenge(entry.id, AgentId("a2"), 0.8)
        # With contested excluded
        results = engine.recall(["sci"], include_contested=False)
        assert len(results) == 0
        # With contested included
        results = engine.recall(["sci"], include_contested=True)
        assert len(results) == 1


class TestMemoryReinforce:
    def test_reinforce_boosts_weight(self):
        engine = MemoryEngine()
        entry = engine.contribute("fact", ["sci"], AgentId("a1"), 0.5)
        old_weight = entry.weight
        engine.reinforce(entry.id, AgentId("a2"), 0.8)
        assert entry.weight > old_weight
        expected_boost = REINFORCEMENT_BOOST * 0.8
        assert abs(entry.weight - (old_weight + expected_boost)) < 0.001

    def test_reinforce_idempotent(self):
        engine = MemoryEngine()
        entry = engine.contribute("fact", ["sci"], AgentId("a1"), 0.5)
        engine.reinforce(entry.id, AgentId("a2"), 0.8)
        w1 = entry.weight
        engine.reinforce(entry.id, AgentId("a2"), 0.8)  # Same agent
        assert entry.weight == w1

    def test_reinforce_switches_from_challenge(self):
        engine = MemoryEngine()
        entry = engine.contribute("fact", ["sci"], AgentId("a1"), 0.5)
        engine.challenge(entry.id, AgentId("a2"), 0.8)
        assert AgentId("a2") in entry.challenged_by
        engine.reinforce(entry.id, AgentId("a2"), 0.8)
        assert AgentId("a2") not in entry.challenged_by
        assert AgentId("a2") in entry.reinforced_by

    def test_reinforce_not_found(self):
        engine = MemoryEngine()
        with pytest.raises(KeyError):
            engine.reinforce("nonexistent", AgentId("a1"), 0.5)

    def test_reinforce_caps_at_max(self):
        engine = MemoryEngine()
        entry = engine.contribute("fact", ["sci"], AgentId("a1"), 0.99)
        engine.reinforce(entry.id, AgentId("a2"), 1.0)
        assert entry.weight <= 1.0


class TestMemoryChallenge:
    def test_challenge_reduces_weight(self):
        engine = MemoryEngine()
        entry = engine.contribute("claim", ["sci"], AgentId("a1"), 0.7)
        old_weight = entry.weight
        engine.challenge(entry.id, AgentId("a2"), 0.8, reason="no evidence")
        assert entry.weight < old_weight

    def test_challenge_idempotent(self):
        engine = MemoryEngine()
        entry = engine.contribute("claim", ["sci"], AgentId("a1"), 0.7)
        engine.challenge(entry.id, AgentId("a2"), 0.8)
        w1 = entry.weight
        engine.challenge(entry.id, AgentId("a2"), 0.8)
        assert entry.weight == w1

    def test_challenge_switches_from_reinforce(self):
        engine = MemoryEngine()
        entry = engine.contribute("claim", ["sci"], AgentId("a1"), 0.7)
        engine.reinforce(entry.id, AgentId("a2"), 0.8)
        assert AgentId("a2") in entry.reinforced_by
        engine.challenge(entry.id, AgentId("a2"), 0.8)
        assert AgentId("a2") not in entry.reinforced_by
        assert AgentId("a2") in entry.challenged_by

    def test_challenge_not_found(self):
        engine = MemoryEngine()
        with pytest.raises(KeyError):
            engine.challenge("nonexistent", AgentId("a1"), 0.5)

    def test_challenge_records_reason(self):
        engine = MemoryEngine()
        entry = engine.contribute("claim", ["sci"], AgentId("a1"), 0.7)
        engine.challenge(entry.id, AgentId("a2"), 0.8, reason="outdated info")
        assert len(entry.metadata["challenge_reasons"]) == 1
        assert entry.metadata["challenge_reasons"][0]["reason"] == "outdated info"

    def test_challenge_floor(self):
        engine = MemoryEngine()
        entry = engine.contribute("claim", ["sci"], AgentId("a1"), 0.05)
        engine.challenge(entry.id, AgentId("a2"), 1.0)
        assert entry.weight >= MIN_MEMORY_WEIGHT


class TestMemoryDecay:
    def test_decay_reduces_weight(self):
        engine = MemoryEngine(decay_rate=100.0)  # aggressive decay
        entry = engine.contribute("old fact", ["tag"], AgentId("a1"), 0.5)
        # Force last_accessed into the past for reliable decay
        entry.last_accessed -= 1.0
        gc_ids = engine.apply_decay()
        # With aggressive decay and 1s age, should be garbage collected
        assert entry.id in gc_ids

    def test_decay_no_gc_for_fresh(self):
        engine = MemoryEngine(decay_rate=0.0001)  # very mild
        engine.contribute("fresh", ["tag"], AgentId("a1"), 0.9)
        gc_ids = engine.apply_decay()
        assert len(gc_ids) == 0


class TestMemoryConflicts:
    def test_conflict_detected(self):
        engine = MemoryEngine()
        engine.contribute("earth is round", ["earth", "shape", "science"], AgentId("a1"), 0.8)
        engine.contribute("earth is flat", ["earth", "shape", "science"], AgentId("a2"), 0.3)
        conflicts = engine.get_conflicts()
        assert len(conflicts) >= 1

    def test_resolve_a_wins(self):
        engine = MemoryEngine()
        m1 = engine.contribute("fact A", ["topic", "debate"], AgentId("a1"), 0.8)
        m2 = engine.contribute("fact B", ["topic", "debate"], AgentId("a2"), 0.3)
        conflicts = engine.get_conflicts()
        assert len(conflicts) == 1
        engine.resolve_conflict(0, "a_wins")
        assert engine.get_memory(m2.id) is None  # b removed

    def test_resolve_b_wins(self):
        engine = MemoryEngine()
        m1 = engine.contribute("fact A", ["topic", "debate"], AgentId("a1"), 0.8)
        m2 = engine.contribute("fact B", ["topic", "debate"], AgentId("a2"), 0.3)
        engine.resolve_conflict(0, "b_wins")
        assert engine.get_memory(m1.id) is None  # a removed

    def test_resolve_both_kept(self):
        engine = MemoryEngine()
        m1 = engine.contribute("fact A", ["topic", "debate"], AgentId("a1"), 0.8)
        m2 = engine.contribute("fact B", ["topic", "debate"], AgentId("a2"), 0.3)
        engine.resolve_conflict(0, "both_kept")
        assert engine.get_memory(m1.id) is not None
        assert engine.get_memory(m2.id) is not None

    def test_resolve_invalid_index(self):
        engine = MemoryEngine()
        with pytest.raises(IndexError):
            engine.resolve_conflict(99, "a_wins")


class TestMemoryEntry:
    def test_net_support(self):
        entry = MemoryEntry(content="test", tags=["t"])
        entry.reinforced_by = [AgentId("a1"), AgentId("a2")]
        entry.challenged_by = [AgentId("a3")]
        assert entry.net_support == 1

    def test_is_contested(self):
        entry = MemoryEntry(content="test", tags=["t"])
        assert not entry.is_contested
        entry.challenged_by = [AgentId("a1")]
        assert entry.is_contested  # 1 challenge >= 0 reinforcements

    def test_to_dict(self):
        entry = MemoryEntry(content="test", tags=["t"])
        d = entry.to_dict()
        assert "content" in d
        assert "weight" in d
        assert "is_contested" in d


class TestMemoryQueries:
    def test_get_all(self):
        engine = MemoryEngine()
        engine.contribute("a", ["t1"], AgentId("a1"), 0.5)
        engine.contribute("b", ["t2"], AgentId("a2"), 0.8)
        all_mems = engine.get_all()
        assert len(all_mems) == 2
        assert all_mems[0].weight >= all_mems[1].weight  # sorted by weight

    def test_get_agent_contributions(self):
        engine = MemoryEngine()
        engine.contribute("a", ["t1"], AgentId("a1"), 0.5)
        engine.contribute("b", ["t2"], AgentId("a2"), 0.8)
        engine.contribute("c", ["t3"], AgentId("a1"), 0.5)
        contribs = engine.get_agent_contributions("a1")
        assert len(contribs) == 2

    def test_get_stats(self):
        engine = MemoryEngine()
        engine.contribute("a", ["t1"], AgentId("a1"), 0.5)
        stats = engine.get_stats()
        assert stats["total_memories"] == 1
        assert stats["total_tags"] == 1
        assert stats["contested_memories"] == 0
