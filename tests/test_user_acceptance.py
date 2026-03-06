"""
tests/test_user_acceptance.py — Test d'acceptation utilisateur (UAT)

Scénarios end-to-end simulant un vrai parcours utilisateur :
  1. Lifecycle complet d'une startup (bootstrap → maturité)
  2. Parcours de gouvernance (proposition → vote → finalisation)
  3. Marché interne (post → bid → settle)
  4. Gestion de crise (échecs en cascade → probation → kill switch → recovery)
  5. Extension par plugins et événements
  6. Persistance (save → load → vérification)

Chaque test vérifie le comportement du point de vue utilisateur,
pas les détails d'implémentation.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from firm import (
    FirmPlugin,
    diff_snapshots,
    load_firm,
    save_firm,
    snapshot,
)
from firm.runtime import Firm

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def startup():
    """Create a fresh startup with 3 founding agents."""
    firm = Firm(name="TestStartup")
    alice = firm.add_agent("Alice", authority=0.9, credits=1000)
    bob = firm.add_agent("Bob", authority=0.7, credits=500)
    carol = firm.add_agent("Carol", authority=0.6, credits=300)
    return firm, alice, bob, carol


@pytest.fixture
def tmp_json():
    """Provide a temporary JSON file path, cleaned up after use."""
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


# ═════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 1 — Lifecycle complet d'une startup
# ═════════════════════════════════════════════════════════════════════════════

class TestStartupLifecycle:
    """Simulate a startup from bootstrap to maturity."""

    def test_bootstrap_agents_created(self, startup):
        """Vérifier que les agents sont créés avec les bonnes autorités."""
        firm, alice, bob, carol = startup
        assert len(firm.get_agents()) == 3
        assert alice.authority == 0.9
        assert bob.authority == 0.7
        assert carol.authority == 0.6

    def test_authority_increases_on_success(self, startup):
        """L'autorité monte quand un agent réussit."""
        firm, _, bob, _ = startup
        initial = bob.authority
        firm.record_action(bob.id, success=True, description="Shipped feature")
        assert bob.authority > initial

    def test_authority_decreases_on_failure(self, startup):
        """L'autorité descend quand un agent échoue."""
        firm, _, _, carol = startup
        initial = carol.authority
        firm.record_action(carol.id, success=False, description="Broke production")
        assert carol.authority < initial

    def test_credits_adjust_with_actions(self, startup):
        """Les crédits augmentent sur succès, diminuent sur échec."""
        firm, _, bob, carol = startup
        bob_initial = bob.credits
        carol_initial = carol.credits

        firm.record_action(bob.id, success=True, description="Good work")
        firm.record_action(carol.id, success=False, description="Bad work")

        assert bob.credits > bob_initial
        assert carol.credits < carol_initial

    def test_ledger_records_all_actions(self, startup):
        """Chaque action est enregistrée dans le ledger."""
        firm, alice, bob, _ = startup
        initial_count = firm.ledger.get_stats()["total_entries"]

        firm.record_action(alice.id, success=True, description="Action 1")
        firm.record_action(bob.id, success=True, description="Action 2")

        stats = firm.ledger.get_stats()
        assert stats["total_entries"] == initial_count + 2
        assert stats["chain_valid"] is True

    def test_full_lifecycle_authority_diverges(self, startup):
        """After multiple actions, authorities diverge based on performance."""
        firm, alice, bob, carol = startup

        # Alice: consistently excellent
        for _ in range(5):
            firm.record_action(alice.id, success=True, description="Strategic win")

        # Bob: mostly good, one mistake
        for _ in range(4):
            firm.record_action(bob.id, success=True, description="Good code")
        firm.record_action(bob.id, success=False, description="Bug")

        # Carol: struggling
        firm.record_action(carol.id, success=True, description="Small fix")
        for _ in range(3):
            firm.record_action(carol.id, success=False, description="Failure")

        # Authority should reflect performance
        assert alice.authority > bob.authority > carol.authority


# ═════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 2 — Gouvernance complète
# ═════════════════════════════════════════════════════════════════════════════

class TestGovernanceWorkflow:
    """End-to-end governance: propose → simulate → vote → finalize."""

    def test_proposal_full_lifecycle(self, startup):
        """Une proposition traverse toutes les phases jusqu'à approbation."""
        firm, alice, bob, carol = startup

        # Créer la proposition
        proposal = firm.propose(
            alice.id,
            title="Hire a Designer",
            description="We need UX support",
        )
        assert proposal.status.value == "draft"

        # 3 phases de simulation
        firm.simulate_proposal(proposal.id, success=True)
        assert firm.governance.get_proposal(proposal.id).status.value == "simulation_1"

        firm.simulate_proposal(proposal.id, success=True)
        assert firm.governance.get_proposal(proposal.id).status.value == "stress_test"

        firm.simulate_proposal(proposal.id, success=True)
        assert firm.governance.get_proposal(proposal.id).status.value == "simulation_2"

        # Open voting
        p = firm.governance.get_proposal(proposal.id)
        firm.governance.open_voting(p)
        assert p.status.value == "voting"

        # Vote (pondéré par autorité)
        firm.vote(proposal.id, alice.id, "approve")
        firm.vote(proposal.id, bob.id, "approve")
        firm.vote(proposal.id, carol.id, "reject")

        # Finalize
        result = firm.finalize_proposal(proposal.id)
        # Alice (0.9) + Bob (0.7) = 1.6 pour, Carol (0.6) = 0.6 contre → approuvé
        assert result["outcome"] in ("approved_pending_cooldown", "approved")

    def test_proposal_rejected_by_majority(self, startup):
        """Une proposition peut être rejetée si la majorité vote contre."""
        firm, alice, bob, carol = startup

        proposal = firm.propose(alice.id, "Risky Move", "A very risky proposal")
        for _ in range(3):
            firm.simulate_proposal(proposal.id, success=True)
        p = firm.governance.get_proposal(proposal.id)
        firm.governance.open_voting(p)

        # Tout le monde rejette
        firm.vote(proposal.id, alice.id, "reject")
        firm.vote(proposal.id, bob.id, "reject")
        firm.vote(proposal.id, carol.id, "reject")

        result = firm.finalize_proposal(proposal.id)
        assert result["outcome"] == "rejected"

    def test_cannot_vote_twice(self, startup):
        """Un agent ne peut pas voter deux fois sur la même proposition."""
        firm, alice, bob, _ = startup

        proposal = firm.propose(alice.id, "Rule Change", "Changing a rule")
        for _ in range(3):
            firm.simulate_proposal(proposal.id, success=True)
        p = firm.governance.get_proposal(proposal.id)
        firm.governance.open_voting(p)

        firm.vote(proposal.id, bob.id, "approve")
        with pytest.raises(ValueError, match="already voted"):
            firm.vote(proposal.id, bob.id, "reject")


# ═════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 3 — Marché interne
# ═════════════════════════════════════════════════════════════════════════════

class TestMarketWorkflow:
    """End-to-end market: post → bid → accept → settle."""

    def test_task_posted_and_settled(self, startup):
        """Un cycle complet du marché : poster → enchérir → régler."""
        firm, alice, bob, _ = startup

        # Poster une tâche
        task = firm.post_task(
            alice.id,
            title="Build API",
            description="REST API for the product",
            bounty=50.0,
        )
        assert task.bounty == 50.0

        # Enchérir
        bid = firm.bid_on_task(task.id, bob.id, amount=45.0, pitch="I know Flask")
        assert bid.amount == 45.0

        # Accepter
        firm.accept_bid(task.id, bid.id)

        # Régler (succès)
        bob_credits_before = bob.credits
        settlement = firm.settle_task(task.id, success=True)

        assert settlement.amount == 45.0
        assert bob.credits > bob_credits_before  # Worker gets paid

    def test_failed_task_no_payment(self, startup):
        """Si la tâche échoue, le worker ne reçoit rien."""
        firm, alice, bob, _ = startup

        task = firm.post_task(alice.id, "Hard Task", bounty=30.0)
        bid = firm.bid_on_task(task.id, bob.id, amount=25.0)
        firm.accept_bid(task.id, bid.id)

        bob_before = bob.credits
        firm.settle_task(task.id, success=False, reason="Not completed")
        # Bob shouldn't gain credits on failure
        assert bob.credits == bob_before

    def test_insufficient_credits_rejected(self, startup):
        """Poster une tâche avec bounty > crédits est refusé."""
        firm, _, _, carol = startup  # Carol has 300 credits
        with pytest.raises(ValueError, match="Insufficient credits"):
            firm.post_task(carol.id, "Expensive Task", bounty=9999.0)


# ═════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 4 — Gestion de crise
# ═════════════════════════════════════════════════════════════════════════════

class TestCrisisManagement:
    """Simulate cascading failures, probation, and kill switch."""

    def test_repeated_failures_lower_authority(self, startup):
        """Des échecs répétés font chuter l'autorité significativement."""
        firm, _, _, carol = startup
        initial = carol.authority

        for i in range(10):
            firm.record_action(carol.id, success=False, description=f"Failure #{i+1}")

        assert carol.authority < initial * 0.8  # Noticeable drop

    def test_kill_switch_blocks_all_operations(self, startup):
        """Le kill switch bloque toutes les actions."""
        firm, alice, _, _ = startup

        # Activer le kill switch
        firm.human.activate_kill_switch(reason="Emergency")

        # Les actions sont bloquées
        result = firm.record_action(alice.id, success=True, description="Should block")
        assert result["blocked"] is True
        assert "kill_switch" in result.get("reason", "")

    def test_kill_switch_deactivation_resumes(self, startup):
        """Désactiver le kill switch permet de reprendre les opérations."""
        firm, alice, _, _ = startup
        authority_before = alice.authority

        firm.human.activate_kill_switch(reason="Pause")
        firm.human.deactivate_kill_switch(reason="Resolved")

        result = firm.record_action(alice.id, success=True, description="Resumed")
        assert result.get("blocked") is not True
        assert alice.authority > authority_before

    def test_audit_detects_no_issues_healthy_org(self, startup):
        """Un audit sur une org saine ne trouve aucun problème critique."""
        firm, alice, bob, carol = startup

        # Record some healthy activity
        for agent in [alice, bob, carol]:
            firm.record_action(agent.id, success=True, description="Normal work")

        report = firm.run_audit()
        assert report.chain_valid is True
        # No CRITICAL findings expected in a healthy org
        critical = [f for f in report.findings if f.severity.value == "critical"]
        assert len(critical) == 0


# ═════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 5 — Rôles, mémoire et évolution
# ═════════════════════════════════════════════════════════════════════════════

class TestRolesMemoryEvolution:
    """Parcours utilisateur : structurer l'org puis la faire évoluer."""

    def test_roles_assignment_and_recall(self, startup):
        """Définir des rôles, les assigner, puis vérifier."""
        firm, alice, bob, carol = startup

        firm.define_role("CEO", min_authority=0.8, description="Boss")
        firm.define_role("Dev", min_authority=0.3, description="Developer")

        a1 = firm.assign_role(alice.id, "CEO")
        a2 = firm.assign_role(carol.id, "Dev")

        assert a1.role.name == "CEO"
        assert a2.role.name == "Dev"

    def test_memory_contribute_and_recall(self, startup):
        """Contribuer de la connaissance et la retrouver."""
        firm, alice, bob, carol = startup

        firm.contribute_memory(alice.id, "We use Python 3.11", tags=["tech"])
        firm.contribute_memory(bob.id, "Deploy on AWS", tags=["infra", "tech"])
        firm.contribute_memory(carol.id, "Sprint every 2 weeks", tags=["process"])

        # Recall by tag
        tech = firm.recall_memory(tags=["tech"])
        assert len(tech) >= 2

        process = firm.recall_memory(tags=["process"])
        assert len(process) >= 1

    def test_memory_reinforcement_increases_weight(self, startup):
        """Renforcer une mémoire augmente son poids."""
        firm, alice, bob, _ = startup

        entry = firm.contribute_memory(alice.id, "Important fact", tags=["core"])
        initial_weight = entry.weight

        firm.reinforce_memory(bob.id, entry.id)
        refreshed = firm.memory.get_memory(entry.id)
        assert refreshed.weight > initial_weight

    def test_memory_challenge_decreases_weight(self, startup):
        """Contester une mémoire diminue son poids."""
        firm, alice, _, carol = startup

        entry = firm.contribute_memory(alice.id, "Debatable opinion", tags=["opinion"])
        initial_weight = entry.weight

        firm.challenge_memory(carol.id, entry.id, reason="I disagree")
        refreshed = firm.memory.get_memory(entry.id)
        assert refreshed.weight < initial_weight

    def test_evolution_propose_vote_apply(self, startup):
        """Proposer, voter et appliquer une évolution de paramètre."""
        firm, alice, bob, _ = startup

        # Get current learning rate
        params_before = firm.get_firm_parameters("authority")
        params_before.get("learning_rate", 0.05)

        # Propose evolution (Alice has authority >= 0.85)
        evo = firm.propose_evolution(
            alice.id,
            changes=[{
                "category": "authority",
                "parameter_name": "learning_rate",
                "new_value": 0.1,
            }],
            rationale="Speed up learning",
        )

        # Vote
        firm.vote_evolution(evo.id, alice.id, approve=True)
        firm.vote_evolution(evo.id, bob.id, approve=True)

        # Apply returns the changes
        changes = firm.apply_evolution(evo.id)
        assert len(changes) >= 1
        assert changes[0].new_value == 0.1


# ═════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 6 — Spawn, merge, split
# ═════════════════════════════════════════════════════════════════════════════

class TestSpawnMergeSplit:
    """Test agent lifecycle: spawn children, split, merge."""

    def test_spawn_creates_child(self, startup):
        """Un agent spawne un enfant qui hérite d'une fraction d'autorité."""
        firm, alice, _, _ = startup
        child = firm.spawn_agent(alice.id, "Alice-Junior")

        assert child.name == "Alice-Junior"
        assert child.authority < alice.authority
        assert child.authority > 0

    def test_split_creates_two_agents(self, startup):
        """Split termine le parent et crée deux agents."""
        firm, _, bob, _ = startup
        count_before = len(firm.get_agents())

        a, b = firm.split_agent(bob.id, "Bob-Frontend", "Bob-Backend", authority_ratio=0.6)

        assert a.name == "Bob-Frontend"
        assert b.name == "Bob-Backend"
        assert abs(a.authority + b.authority - bob.authority) < 0.01
        # Bob terminated, 2 new created → net +1
        assert len(firm.get_agents()) == count_before + 1

    def test_merge_combines_agents(self, startup):
        """Merge deux agents → un seul agent avec autorité combinée moyenne."""
        firm, alice, bob, _ = startup

        merged = firm.merge_agents(alice.id, bob.id, "AliceBob")
        assert merged.name == "AliceBob"
        assert merged.is_active
        # Alice and Bob should be terminated
        assert not firm.get_agent(alice.id).is_active
        assert not firm.get_agent(bob.id).is_active


# ═════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 7 — Events & Plugins
# ═════════════════════════════════════════════════════════════════════════════

class TestEventsAndPlugins:
    """Test event bus and plugin system from user perspective."""

    def test_events_fire_on_agent_add(self):
        """L'ajout d'un agent émet un événement."""
        firm = Firm(name="EventTest")
        captured = []
        firm.events.subscribe("agent.added", lambda e: captured.append(e))

        firm.add_agent("Listener")
        assert len(captured) == 1
        assert captured[0].data["name"] == "Listener"

    def test_events_fire_on_action(self):
        """L'enregistrement d'une action émet un événement."""
        firm = Firm(name="EventTest")
        a = firm.add_agent("Worker", authority=0.7)

        captured = []
        firm.events.subscribe("action.recorded", lambda e: captured.append(e))

        firm.record_action(a.id, success=True, description="Worked")
        assert len(captured) == 1
        assert captured[0].data["success"] is True

    def test_plugin_lifecycle(self):
        """Un plugin s'active, reçoit des événements, se désactive."""
        firm = Firm(name="PluginTest")

        class Counter(FirmPlugin):
            name = "counter"
            version = "1.0.0"
            description = "Counts actions"

            def __init__(self):
                super().__init__()
                self.count = 0

            def on_activate(self, firm):
                firm.events.subscribe("action.recorded", self._inc)

            def on_deactivate(self, firm):
                firm.events.unsubscribe("action.recorded", self._inc)

            def _inc(self, event):
                self.count += 1

        plugin = Counter()
        firm.plugins.register(plugin)
        firm.plugins.activate("counter", firm)

        a = firm.add_agent("Worker", authority=0.7)
        firm.record_action(a.id, success=True, description="Work 1")
        firm.record_action(a.id, success=True, description="Work 2")
        assert plugin.count == 2

        firm.plugins.deactivate("counter", firm)
        firm.record_action(a.id, success=True, description="Work 3")
        # Should NOT increment — deactivated
        assert plugin.count == 2

    def test_wildcard_subscription(self):
        """Les wildcards capturent tous les événements d'un namespace."""
        firm = Firm(name="WildcardTest")
        all_events = []
        firm.events.subscribe("*", lambda e: all_events.append(e.type))

        a = firm.add_agent("A", authority=0.7)
        firm.record_action(a.id, success=True, description="Test")

        assert "agent.added" in all_events
        assert "action.recorded" in all_events


# ═════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 8 — Sérialisation (save/load/snapshot)
# ═════════════════════════════════════════════════════════════════════════════

class TestSerialization:
    """Test persistence from user perspective."""

    def test_save_and_load_roundtrip(self, startup, tmp_json):
        """Sauvegarder et restaurer préserve l'état complet."""
        firm, alice, bob, carol = startup

        # Add some state
        firm.record_action(alice.id, success=True, description="Saved work")
        firm.contribute_memory(alice.id, "Important info", tags=["core"])

        # Save
        save_firm(firm, tmp_json)

        # Load
        restored = load_firm(tmp_json)
        assert restored.name == firm.name
        assert len(restored.get_agents()) == len(firm.get_agents())

    def test_snapshot_detects_changes(self, startup):
        """Les snapshots détectent les changements entre deux instants."""
        firm, alice, _, _ = startup

        before = snapshot(firm)
        firm.add_agent("NewAgent", authority=0.5)
        after = snapshot(firm)

        changes = diff_snapshots(before, after)
        assert changes.get("agents_added", 0) >= 1

    def test_save_via_firm_method(self, startup, tmp_json):
        """Firm.save() fonctionne comme raccourci."""
        firm, _, _, _ = startup
        state = firm.save(tmp_json)
        assert isinstance(state, dict)
        assert state["name"] == "TestStartup"

        # Verify file exists and is valid JSON
        with open(tmp_json) as f:
            loaded = json.load(f)
        assert loaded["name"] == "TestStartup"


# ═════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 9 — Parcours intégré (end-to-end narratif)
# ═════════════════════════════════════════════════════════════════════════════

class TestEndToEndNarrative:
    """
    Scénario complet simulant 1 semaine d'activité d'une startup.
    Bootstrap → travail → gouvernance → évolution → audit.
    """

    def test_one_week_scenario(self):
        """Simulate une semaine complète d'activité."""
        # Jour 1 : Bootstrap
        firm = Firm(name="WeekOne")
        ceo = firm.add_agent("CEO", authority=0.9, credits=1000)
        cto = firm.add_agent("CTO", authority=0.7, credits=500)
        dev = firm.add_agent("Dev", authority=0.6, credits=300)

        # Jour 2 : Travail — tout le monde est productif
        for _ in range(3):
            firm.record_action(ceo.id, success=True, description="Leadership")
            firm.record_action(cto.id, success=True, description="Architecture")
            firm.record_action(dev.id, success=True, description="Coding")

        # Vérifier que tous progressent
        assert ceo.authority > 0.9
        assert cto.authority > 0.7
        assert dev.authority > 0.6

        # Jour 3 : Définir les rôles
        firm.define_role("CEO", min_authority=0.8, description="Strategic")
        firm.define_role("CTO", min_authority=0.6, description="Technical")
        firm.assign_role(ceo.id, "CEO")
        firm.assign_role(cto.id, "CTO")

        # Jour 4 : Mémoire collective
        firm.contribute_memory(ceo.id, "Focus on B2B", tags=["strategy"])
        firm.contribute_memory(cto.id, "Use microservices", tags=["tech"])
        assert len(firm.recall_memory(tags=["strategy"])) >= 1

        # Jour 5 : Gouvernance
        proposal = firm.propose(ceo.id, "Hire Designer", "Need UX help")
        for _ in range(3):
            firm.simulate_proposal(proposal.id, success=True)
        p = firm.governance.get_proposal(proposal.id)
        firm.governance.open_voting(p)
        firm.vote(proposal.id, ceo.id, "approve")
        firm.vote(proposal.id, cto.id, "approve")
        firm.vote(proposal.id, dev.id, "approve")
        result = firm.finalize_proposal(proposal.id)
        assert result["outcome"] in ("approved_pending_cooldown", "approved")

        # Jour 6 : Marché interne
        task = firm.post_task(ceo.id, "Build Dashboard", bounty=50.0)
        bid = firm.bid_on_task(task.id, dev.id, amount=45.0)
        firm.accept_bid(task.id, bid.id)
        settlement = firm.settle_task(task.id, success=True)
        assert settlement.amount == 45.0

        # Jour 7 : Audit
        report = firm.run_audit()
        assert report.chain_valid is True
        assert firm.ledger.get_stats()["total_entries"] > 20

        # Status final
        status = firm.status()
        assert status["agents"]["active"] == 3
        assert status["name"] == "WeekOne"


# ═════════════════════════════════════════════════════════════════════════════
# SCÉNARIO 10 — Résilience et cas limites
# ═════════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge cases that a real user might encounter."""

    def test_agent_not_found_raises(self):
        """Action sur un agent inexistant → KeyError."""
        firm = Firm(name="EdgeCase")
        with pytest.raises(KeyError, match="not found"):
            firm.record_action("nonexistent", success=True, description="X")

    def test_inactive_agent_cannot_act(self, startup):
        """Un agent inactif ne peut pas agir."""
        firm, alice, bob, _ = startup
        # Merge terminates both agents
        firm.merge_agents(alice.id, bob.id, "Merged")
        with pytest.raises(ValueError, match="not active"):
            firm.record_action(alice.id, success=True, description="X")

    def test_low_authority_cannot_propose_evolution(self, startup):
        """Autorité trop basse → pas de proposition d'évolution."""
        firm, _, _, carol = startup
        with pytest.raises(PermissionError, match="too low"):
            firm.propose_evolution(
                carol.id,
                changes=[{"category": "authority", "parameter_name": "x", "new_value": 1}],
            )

    def test_empty_org_status(self):
        """Status d'une org sans agents (juste créée) fonctionne."""
        firm = Firm(name="Empty")
        status = firm.status()
        assert status["agents"]["total"] == 0
        assert status["name"] == "Empty"

    def test_multiple_rapid_actions(self, startup):
        """50 actions rapides ne cassent pas le ledger."""
        firm, alice, _, _ = startup
        for i in range(50):
            firm.record_action(alice.id, success=True, description=f"Action {i}")

        stats = firm.ledger.get_stats()
        assert stats["chain_valid"] is True
        assert stats["total_entries"] >= 53  # 3 join + 50 actions

    def test_recall_empty_memory(self, startup):
        """Rappel sur un tag sans résultat → liste vide."""
        firm, _, _, _ = startup
        results = firm.recall_memory(tags=["nonexistent-tag"])
        assert results == []
