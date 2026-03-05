"""Tests for firm.core.spawn.AutoRestructurer — Self-restructuring engine."""

import math

import pytest

from firm.core.agent import Agent, AgentRole
from firm.core.spawn import (
    AUTO_MERGE_SIMILARITY,
    AUTO_PRUNE_AUTHORITY,
    TASK_ENTROPY_SPAWN_THRESHOLD,
    AutoRestructurer,
    RestructureRecommendation,
)
from firm.core.types import AgentId, AgentStatus


def _make_agent(
    name: str,
    authority: float = 0.5,
    roles: set | None = None,
    status: AgentStatus = AgentStatus.ACTIVE,
) -> Agent:
    return Agent(
        id=AgentId(name),
        name=name,
        authority=authority,
        roles=roles or set(),
        status=status,
    )


# ── RestructureRecommendation ────────────────────────────────────────────────


class TestRestructureRecommendation:
    def test_to_dict(self):
        rec = RestructureRecommendation(
            action="prune",
            reason="Low authority",
            target_agents=[AgentId("a1")],
            confidence=0.87654,
        )
        d = rec.to_dict()
        assert d["action"] == "prune"
        assert d["confidence"] == 0.8765
        assert d["target_agents"] == ["a1"]

    def test_defaults(self):
        rec = RestructureRecommendation(action="merge", reason="overlap")
        assert rec.target_agents == []
        assert rec.proposed_name == ""
        assert rec.metadata == {}


# ── Auto-Prune ───────────────────────────────────────────────────────────────


class TestCheckPrune:
    def test_prune_low_authority_agent(self):
        r = AutoRestructurer()
        agents = [
            _make_agent("good", authority=0.5),
            _make_agent("weak", authority=0.05),
        ]
        recs = r._check_prune(agents)
        assert len(recs) == 1
        assert recs[0].action == "prune"
        assert "weak" in recs[0].reason

    def test_no_prune_above_threshold(self):
        r = AutoRestructurer()
        agents = [_make_agent("ok", authority=0.5)]
        assert r._check_prune(agents) == []

    def test_skip_inactive_agents(self):
        r = AutoRestructurer()
        agents = [
            _make_agent("inactive", authority=0.01, status=AgentStatus.TERMINATED),
        ]
        assert r._check_prune(agents) == []

    def test_prune_confidence_scales(self):
        r = AutoRestructurer()
        rec_low = r._check_prune([_make_agent("a", authority=0.01)])[0]
        rec_border = r._check_prune([_make_agent("b", authority=0.09)])[0]
        assert rec_low.confidence > rec_border.confidence

    def test_custom_threshold(self):
        r = AutoRestructurer(prune_threshold=0.5)
        assert len(r._check_prune([_make_agent("mid", authority=0.3)])) == 1


# ── Auto-Merge ───────────────────────────────────────────────────────────────


class TestCheckMerge:
    def test_merge_identical_roles(self):
        r = AutoRestructurer()
        roles = {AgentRole("dev"), AgentRole("review")}
        agents = [
            _make_agent("a", roles=roles.copy()),
            _make_agent("b", roles=roles.copy()),
        ]
        recs = r._check_merge(agents)
        assert len(recs) == 1
        assert recs[0].action == "merge"
        assert recs[0].confidence == pytest.approx(1.0)

    def test_no_merge_different_roles(self):
        r = AutoRestructurer()
        agents = [
            _make_agent("a", roles={AgentRole("dev")}),
            _make_agent("b", roles={AgentRole("sales")}),
        ]
        assert len(r._check_merge(agents)) == 0

    def test_skip_agents_without_roles(self):
        r = AutoRestructurer()
        agents = [
            _make_agent("a", roles=set()),
            _make_agent("b", roles={AgentRole("dev")}),
        ]
        assert len(r._check_merge(agents)) == 0

    def test_merge_partial_overlap(self):
        """3 shared roles out of 4 total → cos = 3/√(3·4) ≈ 0.866 > 0.85"""
        r = AutoRestructurer()
        roles_a = {AgentRole("a"), AgentRole("b"), AgentRole("c")}
        roles_b = {AgentRole("a"), AgentRole("b"), AgentRole("c"), AgentRole("d")}
        agents = [_make_agent("x", roles=roles_a), _make_agent("y", roles=roles_b)]
        assert len(r._check_merge(agents)) == 1

    def test_proposed_name(self):
        r = AutoRestructurer()
        roles = {AgentRole("dev")}
        agents = [
            _make_agent("Alice", roles=roles.copy()),
            _make_agent("Bob", roles=roles.copy()),
        ]
        recs = r._check_merge(agents)
        assert recs[0].proposed_name == "Alice+Bob"

    def test_skip_inactive_for_merge(self):
        r = AutoRestructurer()
        roles = {AgentRole("dev")}
        agents = [
            _make_agent("a", roles=roles.copy()),
            _make_agent("b", roles=roles.copy(), status=AgentStatus.TERMINATED),
        ]
        assert len(r._check_merge(agents)) == 0


# ── Cosine Similarity ────────────────────────────────────────────────────────


class TestRoleCosineSimilarity:
    def test_identical_roles(self):
        a = _make_agent("a", roles={AgentRole("x"), AgentRole("y")})
        b = _make_agent("b", roles={AgentRole("x"), AgentRole("y")})
        assert AutoRestructurer._role_cosine_similarity(a, b) == pytest.approx(1.0)

    def test_disjoint_roles(self):
        a = _make_agent("a", roles={AgentRole("x")})
        b = _make_agent("b", roles={AgentRole("y")})
        assert AutoRestructurer._role_cosine_similarity(a, b) == pytest.approx(0.0)

    def test_empty_roles(self):
        a = _make_agent("a", roles=set())
        b = _make_agent("b", roles={AgentRole("x")})
        assert AutoRestructurer._role_cosine_similarity(a, b) == 0.0

    def test_both_empty(self):
        a = _make_agent("a", roles=set())
        b = _make_agent("b", roles=set())
        assert AutoRestructurer._role_cosine_similarity(a, b) == 0.0

    def test_known_value(self):
        """One shared of 3 total → cos = 1/sqrt(2*2) = 0.5"""
        a = _make_agent("a", roles={AgentRole("x"), AgentRole("y")})
        b = _make_agent("b", roles={AgentRole("x"), AgentRole("z")})
        assert AutoRestructurer._role_cosine_similarity(a, b) == pytest.approx(0.5)


# ── Shannon Entropy ──────────────────────────────────────────────────────────


class TestShannonEntropy:
    def test_single_category(self):
        assert AutoRestructurer._shannon_entropy(["a", "a", "a"]) == 0.0

    def test_two_uniform(self):
        assert AutoRestructurer._shannon_entropy(["a", "b"]) == pytest.approx(1.0)

    def test_four_uniform(self):
        assert AutoRestructurer._shannon_entropy(["a", "b", "c", "d"]) == pytest.approx(2.0)

    def test_empty(self):
        assert AutoRestructurer._shannon_entropy([]) == 0.0

    def test_skewed(self):
        cats = ["a"] * 100 + ["b"]
        assert AutoRestructurer._shannon_entropy(cats) < 0.1


# ── Auto-Spawn ───────────────────────────────────────────────────────────────


class TestCheckSpawn:
    def test_spawn_high_entropy_uncovered(self):
        r = AutoRestructurer(spawn_entropy=1.0)
        agents = [_make_agent("a", roles={AgentRole("dev")})]
        cats = ["sales"] * 5 + ["dev"] * 3 + ["design"] * 3 + ["ops"] * 3
        recs = r._check_spawn(agents, cats)
        assert len(recs) == 1
        assert recs[0].action == "spawn"
        assert "sales" in recs[0].proposed_name

    def test_no_spawn_low_entropy(self):
        r = AutoRestructurer()
        agents = [_make_agent("a")]
        cats = ["dev", "dev", "dev"]
        assert len(r._check_spawn(agents, cats)) == 0

    def test_no_spawn_empty_categories(self):
        r = AutoRestructurer()
        assert len(r._check_spawn([_make_agent("a")], [])) == 0

    def test_no_spawn_if_covered(self):
        r = AutoRestructurer(spawn_entropy=1.0)
        agents = [
            _make_agent("a", roles={AgentRole("sales")}),
            _make_agent("b", roles={AgentRole("dev")}),
        ]
        cats = ["sales"] * 5 + ["dev"] * 5
        assert len(r._check_spawn(agents, cats)) == 0

    def test_spawn_metadata_includes_entropy(self):
        r = AutoRestructurer(spawn_entropy=0.5)
        agents = [_make_agent("a")]
        cats = ["x"] * 5 + ["y"] * 5 + ["z"] * 5
        recs = r._check_spawn(agents, cats)
        if recs:
            assert "entropy" in recs[0].metadata


# ── Full analyze() ───────────────────────────────────────────────────────────


class TestAnalyze:
    def test_analyze_combines_all_checks(self):
        r = AutoRestructurer(spawn_entropy=1.0)
        agents = [
            _make_agent("weak", authority=0.01, roles={AgentRole("dev")}),
            _make_agent("strong", authority=0.9, roles={AgentRole("dev")}),
        ]
        cats = ["sales"] * 5 + ["design"] * 5 + ["ops"] * 5
        recs = r.analyze(agents, cats)
        actions = {rec.action for rec in recs}
        assert "prune" in actions
        assert "merge" in actions
        assert "spawn" in actions

    def test_analyze_no_categories(self):
        r = AutoRestructurer()
        recs = r.analyze([_make_agent("ok")])
        assert all(rec.action != "spawn" for rec in recs)

    def test_get_recommendations_accumulates(self):
        r = AutoRestructurer()
        agents = [_make_agent("weak", authority=0.01)]
        r.analyze(agents)
        r.analyze(agents)
        assert len(r.get_recommendations()) == 2

    def test_get_stats(self):
        r = AutoRestructurer()
        r.analyze([_make_agent("weak", authority=0.01)])
        stats = r.get_stats()
        assert stats["total_recommendations"] == 1
        assert stats["by_action"]["prune"] == 1
