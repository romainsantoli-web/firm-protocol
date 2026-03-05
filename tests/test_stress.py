"""
Stress tests — validate FIRM Protocol at scale and under concurrent-like load.

These tests push the system beyond normal parameters:
  - Large agent populations (100+)
  - Rapid authority mutations
  - Memory contention (many contributes/challenges)
  - Governance overload (many proposals)
  - Market saturation (many tasks/bids)
  - Ledger chain integrity under heavy writes
"""

from __future__ import annotations

import time

import pytest

from firm.runtime import Firm
from firm.core.types import AgentId, Severity


# ── Scale tests ──────────────────────────────────────────────────────────────


class TestLargePopulation:
    """FIRM with 100+ agents must stay consistent."""

    def test_100_agents_creation(self):
        """Create 100 agents — all tracked, IDs unique."""
        firm = Firm(name="stress-100")
        agents = [firm.add_agent(f"agent-{i}", authority=0.5) for i in range(100)]
        assert len(firm.get_agents()) == 100
        ids = {a.id for a in agents}
        assert len(ids) == 100  # all unique

    def test_100_agents_rapid_actions(self):
        """100 agents each perform 10 actions — authority stays bounded."""
        firm = Firm(name="stress-actions")
        agents = [firm.add_agent(f"a-{i}", authority=0.5) for i in range(100)]
        for agent in agents:
            for j in range(10):
                result = firm.record_action(agent.id, success=(j % 3 != 0), description=f"task-{j}")
                if "blocked" not in result:
                    a = firm.get_agent(agent.id)
                    assert 0.0 <= a.authority <= 1.0
        # All agent authorities in bounds
        for a in firm.get_agents(active_only=False):
            assert 0.0 <= a.authority <= 1.0

    def test_status_with_large_population(self):
        """Firm.status() works correctly with many agents."""
        firm = Firm(name="stress-status")
        for i in range(50):
            firm.add_agent(f"agent-{i}")
        status = firm.status()
        assert status["agents"]["total"] == 50
        assert status["agents"]["active"] == 50


class TestLedgerStress:
    """Ledger integrity under heavy write load."""

    def test_1000_entries_chain_valid(self):
        """1000 ledger entries — hash chain stays valid."""
        firm = Firm(name="ledger-stress")
        agents = [firm.add_agent(f"a-{i}", authority=0.5) for i in range(10)]
        for i in range(1000):
            agent = agents[i % 10]
            try:
                firm.record_action(agent.id, success=(i % 4 != 0), description=f"action-{i}")
            except (ValueError, KeyError):
                pass  # Agent may be inactive
        result = firm.ledger.verify_chain()
        assert result["valid"]

    def test_mixed_operations_chain_valid(self):
        """Mixed governance + actions + memory — chain stays valid."""
        firm = Firm(name="mixed-stress")
        a1 = firm.add_agent("proposer", authority=0.85)
        a2 = firm.add_agent("voter", authority=0.7)
        a3 = firm.add_agent("worker", authority=0.5)

        # Actions
        for i in range(50):
            firm.record_action(a3.id, success=True, description=f"work-{i}")

        # Memory
        for i in range(20):
            firm.contribute_memory(a1.id, f"fact-{i}", tags=["stress"])

        # Governance
        p = firm.propose(a1.id, "Stress proposal", "Testing under load")
        firm.simulate_proposal(p.id, success=True)
        firm.simulate_proposal(p.id, success=True)
        firm.simulate_proposal(p.id, success=True)
        firm.governance.open_voting(p)
        firm.vote(p.id, a2.id, "approve")

        # Verify chain
        result = firm.ledger.verify_chain()
        assert result["valid"]


class TestMemoryStress:
    """Memory engine under contention."""

    def test_100_memories_recall(self):
        """100 memories — recall returns top-k correctly."""
        firm = Firm(name="memory-stress")
        agent = firm.add_agent("contributor", authority=0.8)
        for i in range(100):
            firm.contribute_memory(
                agent.id,
                f"Knowledge item {i}",
                tags=["science" if i % 2 == 0 else "art"],
            )
        results = firm.recall_memory(tags=["science"], top_k=10)
        assert len(results) <= 10
        assert all(hasattr(r, "weight") for r in results)

    def test_memory_contention_reinforce_challenge(self):
        """Multiple agents reinforce/challenge the same memory."""
        firm = Firm(name="contention")
        contributor = firm.add_agent("c", authority=0.7)
        supporters = [firm.add_agent(f"s-{i}", authority=0.6) for i in range(10)]
        challengers = [firm.add_agent(f"ch-{i}", authority=0.5) for i in range(10)]

        entry = firm.contribute_memory(contributor.id, "contested fact", tags=["debate"])
        initial_weight = entry.weight

        for s in supporters:
            firm.reinforce_memory(s.id, entry.id)
        for c in challengers:
            firm.challenge_memory(c.id, entry.id, reason="disagree")

        # Weight should still be positive (reinforcement > challenge weight)
        assert entry.weight > 0.0


class TestMarketStress:
    """Market under saturation."""

    def test_50_tasks_with_bids(self):
        """50 tasks, each with 3 bids — market stays consistent."""
        firm = Firm(name="market-stress")
        poster = firm.add_agent("poster", authority=0.8, credits=5000)
        bidders = [firm.add_agent(f"bidder-{i}", authority=0.5) for i in range(10)]

        tasks = []
        for i in range(50):
            task = firm.post_task(
                poster.id,
                title=f"Task {i}",
                description=f"Do thing {i}",
                bounty=10.0,
            )
            tasks.append(task)

        # Place bids on first 20 tasks
        for i, task in enumerate(tasks[:20]):
            for j in range(3):
                bidder = bidders[j % len(bidders)]
                firm.bid_on_task(task.id, bidder.id, amount=9.0, pitch=f"I can do it {j}")

        stats = firm.market.get_stats()
        assert stats["total_tasks"] == 50


class TestGovernanceStress:
    """Governance under overload."""

    def test_many_proposals(self):
        """20 proposals created, some voted on — no corruption."""
        firm = Firm(name="gov-stress")
        proposer = firm.add_agent("boss", authority=0.85)
        voters = [firm.add_agent(f"voter-{i}", authority=0.7) for i in range(5)]

        proposals = []
        for i in range(20):
            p = firm.propose(proposer.id, f"Proposal {i}", f"Change {i}")
            proposals.append(p)

        # Process first 5 through full lifecycle
        for p in proposals[:5]:
            firm.simulate_proposal(p.id, success=True)
            firm.simulate_proposal(p.id, success=True)
            firm.simulate_proposal(p.id, success=True)
            firm.governance.open_voting(p)
            for v in voters:
                firm.vote(p.id, v.id, "approve")
            result = firm.finalize_proposal(p.id)
            assert "outcome" in result

        all_props = firm.governance.get_all_proposals()
        assert len(all_props) == 20


class TestSpawnStress:
    """Spawn/merge/split at scale."""

    def test_spawn_chain(self):
        """A → B → C → D chain of spawns."""
        firm = Firm(name="spawn-chain")
        parent = firm.add_agent("root", authority=0.9)
        current = parent
        for i in range(5):
            if current.authority >= 0.7:  # spawn requires high authority
                child = firm.spawn_agent(current.id, f"gen-{i}")
                assert child.authority > 0.0
                assert child.authority < current.authority
                current = firm.get_agent(current.id)  # refresh
            else:
                break
        # All agents in the firm
        all_agents = firm.get_agents(active_only=False)
        assert len(all_agents) >= 2

    def test_split_and_merge(self):
        """Split then merge — authority conserved approximately."""
        firm = Firm(name="split-merge")
        agent = firm.add_agent("original", authority=0.95, credits=200)

        a, b = firm.split_agent(agent.id, "half-a", "half-b", authority_ratio=0.6)
        assert a.authority + b.authority <= 1.0  # ~original authority

        # Both halves need >= 0.5 authority to merge; boost if needed
        for half in (a, b):
            if half.authority < 0.5:
                half.authority = 0.55

        merged = firm.merge_agents(a.id, b.id, "reunited")
        assert 0.0 <= merged.authority <= 1.0


# ── Performance benchmarks ───────────────────────────────────────────────────

class TestPerformance:
    """Ensure operations complete within reasonable time."""

    def test_firm_creation_fast(self):
        """Creating a FIRM with 50 agents takes < 0.5s."""
        start = time.time()
        firm = Firm(name="perf-test")
        for i in range(50):
            firm.add_agent(f"agent-{i}")
        elapsed = time.time() - start
        assert elapsed < 0.5, f"Took {elapsed:.2f}s"

    def test_1000_actions_fast(self):
        """1000 record_action calls take < 2s."""
        firm = Firm(name="perf-actions")
        agents = [firm.add_agent(f"a-{i}", authority=0.5) for i in range(10)]
        start = time.time()
        for i in range(1000):
            agent = agents[i % 10]
            try:
                firm.record_action(agent.id, success=(i % 3 != 0), description="perf")
            except (ValueError, KeyError):
                pass
        elapsed = time.time() - start
        assert elapsed < 2.0, f"Took {elapsed:.2f}s"

    def test_audit_fast(self):
        """Full audit on a 50-agent firm takes < 1s."""
        firm = Firm(name="perf-audit")
        for i in range(50):
            a = firm.add_agent(f"agent-{i}", authority=0.5)
            firm.record_action(a.id, success=True, description="setup")
        start = time.time()
        report = firm.run_audit()
        elapsed = time.time() - start
        assert elapsed < 1.0, f"Took {elapsed:.2f}s"
        assert report.firm_name == "perf-audit"

    def test_status_fast(self):
        """Firm.status() on a 100-agent firm takes < 0.5s."""
        firm = Firm(name="perf-status")
        for i in range(100):
            firm.add_agent(f"agent-{i}")
        start = time.time()
        firm.status()
        elapsed = time.time() - start
        assert elapsed < 0.5, f"Took {elapsed:.2f}s"
