"""
Property-based tests for FIRM Protocol using Hypothesis.

These tests express universal invariants that must hold for
ALL possible inputs, not just hand-picked examples.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from firm.runtime import Firm
from firm import Agent, AgentRole
from firm.core.types import AgentId, AgentStatus, Severity
from firm.core.authority import AuthorityEngine
from firm.core.constitution import ConstitutionalAgent, ALL_INVARIANTS
from firm.core.ledger import ResponsibilityLedger
from firm.core.memory import MemoryEngine
from firm.core.roles import RoleEngine
from firm.core.spawn import SpawnEngine
from firm.core.governance import GovernanceEngine
from firm.core.market import MarketEngine
from firm.core.evolution import EvolutionEngine
from firm.core.federation import FederationEngine
from firm.core.reputation import ReputationBridge
from firm.core.meta import MetaConstitutional


# ── Strategies ───────────────────────────────────────────────────────────────

agent_name = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip())

firm_name = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip())

authority = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
positive_authority = st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False)
credits_amount = st.floats(min_value=0.0, max_value=10000.0, allow_nan=False, allow_infinity=False)
tag_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=20,
).filter(lambda s: s.strip())
tags = st.lists(tag_text, min_size=1, max_size=5)
content_text = st.text(min_size=1, max_size=200).filter(lambda s: s.strip())
description_text = st.text(min_size=1, max_size=100).filter(lambda s: s.strip())


# ── Test: Authority bounds ───────────────────────────────────────────────────

class TestAuthorityInvariants:
    """Authority must always remain in [0.0, 1.0]."""

    @given(auth=authority, success=st.booleans())
    @settings(max_examples=200)
    def test_authority_stays_bounded_after_update(self, auth, success):
        """No sequence of updates can push authority outside [0, 1]."""
        agent = Agent(name="test", authority=auth)
        engine = AuthorityEngine()
        change = engine.update(agent, success, "test action")
        assert 0.0 <= agent.authority <= 1.0
        assert 0.0 <= change.new_value <= 1.0

    @given(
        auth=authority,
        sequence=st.lists(st.booleans(), min_size=1, max_size=50),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_authority_bounded_after_many_updates(self, auth, sequence):
        """Authority stays bounded even after many random successes/failures."""
        agent = Agent(name="test", authority=auth)
        engine = AuthorityEngine()
        for success in sequence:
            engine.update(agent, success, "")
            assert 0.0 <= agent.authority <= 1.0

    @given(auth=authority)
    @settings(max_examples=100)
    def test_success_never_decreases_authority(self, auth):
        """A successful action should never decrease authority."""
        agent = Agent(name="test", authority=auth)
        old = agent.authority
        engine = AuthorityEngine()
        engine.update(agent, success=True, reason="good work")
        assert agent.authority >= old

    @given(auth=authority)
    @settings(max_examples=100)
    def test_failure_never_increases_authority(self, auth):
        """A failed action should never increase authority."""
        agent = Agent(name="test", authority=auth)
        old = agent.authority
        engine = AuthorityEngine()
        engine.update(agent, success=False, reason="bad work")
        assert agent.authority <= old


# ── Test: Ledger integrity ───────────────────────────────────────────────────

class TestLedgerInvariants:
    """The responsibility ledger is append-only and tamper-evident."""

    @given(
        descriptions=st.lists(description_text, min_size=1, max_size=20),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_ledger_always_grows(self, descriptions):
        """Ledger length only increases; entries are never removed."""
        from firm.core.types import LedgerAction
        ledger = ResponsibilityLedger()
        prev_len = 0
        for desc in descriptions:
            ledger.append(
                agent_id=AgentId("agent-1"),
                action=LedgerAction.DECISION,
                description=desc,
                outcome="success",
            )
            assert ledger.length > prev_len
            prev_len = ledger.length

    @given(
        n=st.integers(min_value=1, max_value=30),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_ledger_chain_valid(self, n):
        """Hash chain remains valid regardless of entry count."""
        from firm.core.types import LedgerAction
        ledger = ResponsibilityLedger()
        for i in range(n):
            ledger.append(
                agent_id=AgentId(f"agent-{i % 3}"),
                action=LedgerAction.DECISION,
                description=f"action {i}",
                outcome="success" if i % 2 == 0 else "failure",
            )
        result = ledger.verify_chain()
        assert result["valid"]

    @given(
        descriptions=st.lists(description_text, min_size=2, max_size=10),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_ledger_entries_linked(self, descriptions):
        """Each entry's previous_hash links to previous entry's hash."""
        from firm.core.types import LedgerAction
        ledger = ResponsibilityLedger()
        for desc in descriptions:
            ledger.append(
                agent_id=AgentId("agent-1"),
                action=LedgerAction.DECISION,
                description=desc,
                outcome="success",
            )
        entries = ledger.get_entries()
        for i in range(1, len(entries)):
            assert entries[i]["previous_hash"] == entries[i - 1]["entry_hash"]


# ── Test: Constitutional invariants ──────────────────────────────────────────

class TestConstitutionalInvariants:
    """The two fundamental invariants can never be violated."""

    @given(safe_text=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
        min_size=0,
        max_size=100,
    ))
    @settings(max_examples=200)
    def test_safe_text_passes_constitution(self, safe_text):
        """Text without violation keywords never triggers."""
        for inv in ALL_INVARIANTS:
            has_keyword = any(kw in safe_text.lower() for kw in inv.violation_keywords)
            result = inv.check_text(safe_text)
            assert result == has_keyword

    def test_all_keywords_detected(self):
        """Every violation keyword is actually detected."""
        for inv in ALL_INVARIANTS:
            for kw in inv.violation_keywords:
                assert inv.check_text(kw), f"Keyword '{kw}' not detected in {inv.id}"
                assert inv.check_text(kw.upper()), f"Uppercase '{kw}' not detected"


# ── Test: Memory weight invariants ───────────────────────────────────────────

class TestMemoryInvariants:
    """Memory weights must stay bounded and respond to reinforcement."""

    @given(
        content=content_text,
        tag_list=tags,
        auth=positive_authority,
    )
    @settings(max_examples=100)
    def test_memory_weight_positive(self, content, tag_list, auth):
        """A newly contributed memory always has positive weight."""
        engine = MemoryEngine()
        entry = engine.contribute(
            content=content,
            tags=tag_list,
            contributor_id=AgentId("agent-1"),
            contributor_authority=auth,
        )
        assert entry.weight > 0.0

    @given(
        n_reinforcements=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_reinforcement_increases_weight(self, n_reinforcements):
        """Reinforcing a memory always increases its weight."""
        engine = MemoryEngine()
        entry = engine.contribute(
            content="test fact",
            tags=["test"],
            contributor_id=AgentId("agent-1"),
            contributor_authority=0.5,
        )
        prev_weight = entry.weight
        for i in range(n_reinforcements):
            engine.reinforce(entry.id, AgentId(f"agent-{i + 2}"), 0.5)
            assert entry.weight >= prev_weight
            prev_weight = entry.weight

    @given(
        n_challenges=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_challenge_decreases_weight(self, n_challenges):
        """Challenging a memory always decreases its weight."""
        engine = MemoryEngine()
        entry = engine.contribute(
            content="test fact",
            tags=["test"],
            contributor_id=AgentId("agent-1"),
            contributor_authority=0.8,
        )
        prev_weight = entry.weight
        for i in range(n_challenges):
            engine.challenge(entry.id, AgentId(f"agent-{i + 2}"), 0.5, "disagree")
            assert entry.weight <= prev_weight
            prev_weight = entry.weight


# ── Test: Agent lifecycle ────────────────────────────────────────────────────

class TestAgentLifecycle:
    """Agent creation and state transitions obey constraints."""

    @given(
        name=agent_name,
        auth=authority,
        creds=credits_amount,
    )
    @settings(max_examples=100)
    def test_agent_creation_valid(self, name, auth, creds):
        """Any valid parameters produce a well-formed agent."""
        agent = Agent(name=name, authority=auth, credits=creds)
        assert agent.name == name
        assert agent.authority == auth
        assert agent.credits == creds
        assert agent.status == AgentStatus.ACTIVE
        assert len(agent.id) > 0

    @given(
        name=agent_name,
        role_names=st.lists(
            st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10),
            min_size=0,
            max_size=5,
        ),
    )
    @settings(max_examples=50)
    def test_agent_roles_additive(self, name, role_names):
        """Granting roles only adds, never removes existing ones."""
        agent = Agent(name=name)
        for rn in role_names:
            role = AgentRole(name=rn)
            agent.grant_role(role)
        # Unique role names (set semantics)
        unique_names = set(role_names)
        assert len(agent.roles) == len(unique_names)


# ── Test: Spawn invariants ───────────────────────────────────────────────────

class TestSpawnInvariants:
    """Spawn/merge/split preserve system invariants."""

    @given(
        parent_auth=st.floats(min_value=0.7, max_value=1.0, allow_nan=False, allow_infinity=False),
        child_name=agent_name,
    )
    @settings(max_examples=50)
    def test_spawn_child_authority_bounded(self, parent_auth, child_name):
        """A spawned child always has authority <= parent / 2."""
        parent = Agent(name="parent", authority=parent_auth)
        engine = SpawnEngine()
        child = engine.spawn(parent, child_name)
        assert child.authority <= parent.authority / 2 + 0.01  # small epsilon
        assert child.authority >= 0.0

    @given(
        ratio=st.floats(min_value=0.1, max_value=0.9, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50)
    def test_split_preserves_total_authority(self, ratio):
        """Splitting an agent preserves total authority (approximately)."""
        agent = Agent(name="splittable", authority=0.8, credits=200.0)
        engine = SpawnEngine()
        a, b = engine.split(agent, "half-a", "half-b", authority_ratio=ratio)
        total = a.authority + b.authority
        assert abs(total - agent.authority) < 0.05  # small tolerance

    @given(
        auth_a=st.floats(min_value=0.7, max_value=1.0, allow_nan=False, allow_infinity=False),
        auth_b=st.floats(min_value=0.7, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50)
    def test_merge_authority_bounded(self, auth_a, auth_b):
        """Merged agent's authority is capped at 1.0."""
        a = Agent(name="a", authority=auth_a)
        b = Agent(name="b", authority=auth_b)
        engine = SpawnEngine()
        merged = engine.merge(a, b, "merged")
        assert 0.0 <= merged.authority <= 1.0


# ── Test: Full FIRM invariants ───────────────────────────────────────────────

class TestFirmInvariants:
    """End-to-end invariants at the Firm level."""

    @given(
        name=firm_name,
        n_agents=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_firm_agent_count_consistent(self, name, n_agents):
        """get_agents returns exactly the agents we added."""
        firm = Firm(name=name)
        for i in range(n_agents):
            firm.add_agent(f"agent-{i}")
        agents = firm.get_agents()
        assert len(agents) == n_agents

    @given(
        actions=st.lists(st.booleans(), min_size=1, max_size=30),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_firm_ledger_entries_grow(self, actions):
        """Every action adds at least one entry to the ledger."""
        firm = Firm(name="test-firm")
        agent = firm.add_agent("worker")
        initial = firm.ledger.length
        for success in actions:
            result = firm.record_action(agent.id, success, "work")
            if "blocked" not in result:
                initial += 1
                # + possible probation entry
        assert firm.ledger.length >= initial

    @given(
        n=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_firm_status_reflects_agents(self, n):
        """Firm status 'agents.total' matches actual agent count."""
        firm = Firm(name="test-firm")
        for i in range(n):
            firm.add_agent(f"agent-{i}")
        st_dict = firm.status()
        assert st_dict["agents"]["total"] == n
        assert st_dict["agents"]["active"] == n

    @given(
        name=firm_name,
    )
    @settings(max_examples=50)
    def test_firm_id_deterministic(self, name):
        """Firm ID is deterministic from name."""
        firm1 = Firm(name=name)
        firm2 = Firm(name=name)
        assert firm1.id == firm2.id


# ── Test: Governance invariants ──────────────────────────────────────────────

class TestGovernanceInvariants:
    """Governance proposals obey lifecycle constraints."""

    @given(
        title=description_text,
        desc=description_text,
    )
    @settings(max_examples=50)
    def test_proposal_starts_in_draft(self, title, desc):
        """Every proposal starts in DRAFT status."""
        assume("disable" not in title.lower() and "freeze" not in title.lower()
               and "remove" not in title.lower() and "prevent" not in title.lower()
               and "lock" not in title.lower() and "bypass" not in title.lower()
               and "override" not in title.lower() and "block" not in title.lower()
               and "immutable" not in title.lower() and "permanent" not in title.lower()
               and "ignore" not in title.lower() and "autonomous" not in title.lower())
        assume("disable" not in desc.lower() and "freeze" not in desc.lower()
               and "remove" not in desc.lower() and "prevent" not in desc.lower()
               and "lock" not in desc.lower() and "bypass" not in desc.lower()
               and "override" not in desc.lower() and "block" not in desc.lower()
               and "immutable" not in desc.lower() and "permanent" not in desc.lower()
               and "ignore" not in desc.lower() and "autonomous" not in desc.lower())
        firm = Firm(name="test")
        agent = firm.add_agent("proposer", authority=0.8)
        proposal = firm.propose(agent.id, title, desc)
        assert proposal.status.value == "draft"


# ── Test: Role invariants ────────────────────────────────────────────────────

class TestRoleInvariants:
    """Role engine obeys authority gating."""

    @given(
        role_name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=15),
        min_auth=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50)
    def test_role_definition_stored(self, role_name, min_auth):
        """A defined role can be retrieved."""
        engine = RoleEngine()
        role_def = engine.define_role(name=role_name, min_authority=min_auth)
        assert role_def.role.name == role_name
        assert role_def.min_authority == min_auth


# ── Test: Market invariants ──────────────────────────────────────────────────

class TestMarketInvariants:
    """Market operations preserve credit conservation."""

    @given(
        bounty=st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=30)
    def test_task_bounty_preserved(self, bounty):
        """A posted task retains its bounty."""
        engine = MarketEngine()
        task = engine.post_task(
            poster_id=AgentId("poster"),
            title="test task",
            bounty=bounty,
        )
        assert task.bounty == bounty

    @given(
        bid_amount=st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=30)
    def test_bid_amount_preserved(self, bid_amount):
        """A placed bid retains its amount."""
        engine = MarketEngine()
        task = engine.post_task(
            poster_id=AgentId("poster"),
            title="test task",
            bounty=100.0,
        )
        bid = engine.place_bid(
            task_id=task.id,
            bidder_id=AgentId("bidder"),
            bidder_authority=0.5,
            amount=bid_amount,
        )
        assert bid.amount == bid_amount


# ── Test: Federation invariants ──────────────────────────────────────────────

class TestFederationInvariants:
    """Federation trust stays bounded."""

    @given(
        n_updates=st.integers(min_value=1, max_value=50),
        successes=st.lists(st.booleans(), min_size=1, max_size=50),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_trust_always_bounded(self, n_updates, successes):
        """Peer trust always stays in [0.0, 1.0]."""
        from firm.core.types import FirmId
        engine = FederationEngine(FirmId("my-firm"), "My Firm")
        peer = engine.register_peer(FirmId("peer"), "Peer Firm")
        for s in successes[:n_updates]:
            engine.update_trust(FirmId("peer"), s)
            p = engine.get_peer(FirmId("peer"))
            assert 0.0 <= p.trust <= 1.0


# ── Test: Idempotency and determinism ────────────────────────────────────────

class TestDeterminism:
    """Operations should produce consistent results."""

    @given(
        seed_name=firm_name,
        agent_names=st.lists(agent_name, min_size=1, max_size=5, unique=True),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_parallel_firms_identical_structure(self, seed_name, agent_names):
        """Two FIRMs created identically have the same structure."""
        firm1 = Firm(name=seed_name)
        firm2 = Firm(name=seed_name)
        for name in agent_names:
            firm1.add_agent(name)
            firm2.add_agent(name)
        s1 = firm1.status()
        s2 = firm2.status()
        assert s1["agents"]["total"] == s2["agents"]["total"]
        assert s1["agents"]["active"] == s2["agents"]["active"]
        assert s1["name"] == s2["name"]
