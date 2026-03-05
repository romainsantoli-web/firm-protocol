#!/usr/bin/env python3
"""
docs/tutorial.py — Tutoriel complet du FIRM Protocol

Ce tutoriel guide pas à pas à travers les 12 couches du FIRM Protocol.
Chaque section est indépendante et peut être exécutée séparément.

Run:
    python docs/tutorial.py

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from firm.runtime import Firm
from firm import (
    FirmPlugin,
    save_firm,
    load_firm,
    snapshot,
    diff_snapshots,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def titre(text: str) -> None:
    print(f"\n{'━' * 70}")
    print(f"  {text}")
    print(f"{'━' * 70}\n")


def sous_titre(text: str) -> None:
    print(f"\n  ── {text} ──\n")


def afficher_autorite(firm: Firm) -> None:
    for a in firm.get_agents():
        bar = "█" * int(a.authority * 30)
        print(f"    {a.name:<15} {a.authority:.4f}  {bar}  ({a.credits:.0f} crédits)")


# ═════════════════════════════════════════════════════════════════════════════
# 1. CRÉATION & AGENTS (Couche 1 — Authority Engine)
# ═════════════════════════════════════════════════════════════════════════════

def tutorial_01_creation():
    """
    Le FIRM Protocol est un runtime pour organisations autonomes.
    Chaque agent possède une autorité (0.0 → 1.0) qui évolue
    en fonction de ses actions : succès = +autorité, échec = -autorité.
    """
    titre("1. CRÉATION DE L'ORGANISATION & AGENTS")

    # Créer une organisation
    firm = Firm(name="TechStartup")
    print(f"  Organisation créée : {firm.name} (id: {firm.id})")

    # Ajouter des agents avec des autorités différentes
    alice = firm.add_agent("Alice", authority=0.9, credits=1000)   # Fondatrice
    bob   = firm.add_agent("Bob",   authority=0.7, credits=500)    # CTO
    carol = firm.add_agent("Carol", authority=0.6, credits=300)    # Développeuse

    print(f"\n  Agents créés :")
    afficher_autorite(firm)

    # L'autorité change en fonction des résultats
    sous_titre("Actions et conséquences")

    firm.record_action(bob.id, success=True, description="Livré le MVP en temps")
    firm.record_action(bob.id, success=True, description="Formé l'équipe junior")
    firm.record_action(carol.id, success=True, description="Corrigé un bug critique")
    firm.record_action(carol.id, success=False, description="Cassé la pipeline CI")

    print("  Après les actions :")
    afficher_autorite(firm)
    print("\n  → Bob monte (2 succès), Carol stagne (1 succès + 1 échec)")

    return firm


# ═════════════════════════════════════════════════════════════════════════════
# 2. RESPONSABILITÉ (Couche 2 — Responsibility Ledger)
# ═════════════════════════════════════════════════════════════════════════════

def tutorial_02_ledger(firm: Firm):
    """
    Chaque action est enregistrée dans un ledger chaîné (hash-chain).
    Aucune entrée ne peut être supprimée ou modifiée.
    """
    titre("2. LEDGER DE RESPONSABILITÉ")

    stats = firm.ledger.get_stats()
    print(f"  Entrées totales : {stats['total_entries']}")
    print(f"  Chaîne valide :   {'✓' if stats['chain_valid'] else '✗'}")

    entries = firm.ledger.get_entries()
    print(f"\n  Dernières 5 entrées :")
    for e in entries[-5:]:
        print(f"    [{e['action']:<20}] {e['agent_id'][:8]}… — {e['description'][:50]}")

    print("\n  → Le ledger est tamper-evident : toute modification casse la chaîne")


# ═════════════════════════════════════════════════════════════════════════════
# 3. RÔLES FLUIDES (Couche 3 — Role Fluidity)
# ═════════════════════════════════════════════════════════════════════════════

def tutorial_03_roles(firm: Firm):
    """
    Les rôles ne sont pas fixes — ils requièrent un niveau minimum d'autorité.
    Si l'autorité d'un agent descend sous le seuil, il perd automatiquement
    l'éligibilité au rôle.
    """
    titre("3. RÔLES FLUIDES")

    # Définir des rôles avec seuils d'autorité
    firm.define_role("CTO", min_authority=0.6, description="Direction technique")
    firm.define_role("Lead", min_authority=0.5, description="Chef d'équipe")
    firm.define_role("Dev", min_authority=0.3, description="Développeur")

    agents = firm.get_agents()
    bob = [a for a in agents if a.name == "Bob"][0]
    carol = [a for a in agents if a.name == "Carol"][0]

    # Assigner des rôles (gated par l'autorité)
    firm.assign_role(bob.id, "CTO")
    firm.assign_role(carol.id, "Dev")

    print(f"  Bob ({bob.authority:.2f})   → CTO (seuil: 0.6) ✓")
    print(f"  Carol ({carol.authority:.2f}) → Dev (seuil: 0.3) ✓")

    print("\n  → Si l'autorité de Bob descend sous 0.6, il ne qualifie plus pour CTO")


# ═════════════════════════════════════════════════════════════════════════════
# 4. MÉMOIRE COLLECTIVE (Couche 4 — Collective Memory)
# ═════════════════════════════════════════════════════════════════════════════

def tutorial_04_memory(firm: Firm):
    """
    Les agents contribuent du savoir à la mémoire partagée.
    Les mémoires ont un poids influencé par l'autorité du contributeur.
    D'autres agents peuvent renforcer ou contester une mémoire.
    """
    titre("4. MÉMOIRE COLLECTIVE")

    agents = firm.get_agents()
    alice = [a for a in agents if a.name == "Alice"][0]
    bob = [a for a in agents if a.name == "Bob"][0]
    carol = [a for a in agents if a.name == "Carol"][0]

    # Contribuer des connaissances
    m1 = firm.contribute_memory(
        alice.id,
        "Notre marché cible est le SaaS B2B enterprise",
        tags=["stratégie", "marché"],
    )
    m2 = firm.contribute_memory(
        bob.id,
        "L'architecture microservices est la bonne approche pour notre scale",
        tags=["architecture", "technique"],
    )
    m3 = firm.contribute_memory(
        carol.id,
        "Les tests d'intégration doivent couvrir 80% minimum",
        tags=["qualité", "technique"],
    )

    print(f"  3 mémoires contribuées (stratégie, architecture, qualité)")

    # Renforcer une mémoire (consensus)
    firm.reinforce_memory(bob.id, m1.id)
    print(f"\n  Bob renforce la mémoire stratégie d'Alice → poids augmenté")

    # Contester une mémoire
    firm.challenge_memory(carol.id, m2.id, reason="Les monolithes sont plus simples au début")
    print(f"  Carol conteste la mémoire architecture de Bob → poids diminué")

    # Rappeler par tag
    results = firm.recall_memory(tags=["technique"])
    print(f"\n  Rappel par tag 'technique' : {len(results)} résultat(s)")
    for r in results:
        print(f"    [{r.weight:.2f}] {r.content[:60]}…")


# ═════════════════════════════════════════════════════════════════════════════
# 5. GOUVERNANCE (Couche 5 — Constitutional Governance)
# ═════════════════════════════════════════════════════════════════════════════

def tutorial_05_governance(firm: Firm):
    """
    Les propositions passent par un cycle à 5 phases :
    DRAFT → SIMULATION_1 → STRESS_TEST → SIMULATION_2 → VOTING → FINALIZED

    Les votes sont pondérés par l'autorité de chaque votant.
    """
    titre("5. GOUVERNANCE CONSTITUTIONNELLE")

    agents = firm.get_agents()
    alice = [a for a in agents if a.name == "Alice"][0]
    bob = [a for a in agents if a.name == "Bob"][0]
    carol = [a for a in agents if a.name == "Carol"][0]

    # Créer une proposition
    proposal = firm.propose(
        alice.id,
        title="Recruter un designer UX",
        description="Nous avons besoin d'un spécialiste UX pour le produit",
    )
    print(f"  Proposition créée : {proposal.id[:12]}…")
    print(f"  Statut : {proposal.status.value}")

    # Simuler (3 phases obligatoires)
    firm.simulate_proposal(proposal.id, success=True, impact_summary="Impact budgétaire modéré")
    print(f"  → Phase 1 (simulation) : ✓")

    firm.simulate_proposal(proposal.id, success=True, impact_summary="Stress test OK")
    print(f"  → Phase 2 (stress test) : ✓")

    firm.simulate_proposal(proposal.id, success=True, impact_summary="Validation finale")
    print(f"  → Phase 3 (simulation 2) : ✓")

    # Ouvrir le vote
    p = firm.governance.get_proposal(proposal.id)
    firm.governance.open_voting(p)
    print(f"  → Voting ouvert")

    # Voter (pondéré par autorité)
    firm.vote(proposal.id, alice.id, "approve", reason="Essentiel pour le produit")
    firm.vote(proposal.id, bob.id, "approve", reason="D'accord")
    firm.vote(proposal.id, carol.id, "reject", reason="Budget limité")

    print(f"\n  Votes : Alice (approve, auth={alice.authority:.2f}), "
          f"Bob (approve, auth={bob.authority:.2f}), Carol (reject, auth={carol.authority:.2f})")

    # Finaliser
    result = firm.finalize_proposal(proposal.id)
    print(f"\n  Résultat : {result.get('status', 'unknown')}")
    print(f"  → Le vote est pondéré : l'autorité plus haute d'Alice pèse davantage")


# ═════════════════════════════════════════════════════════════════════════════
# 6. SELF-EVOLUTION (Couche 6 — Parameter Evolution)
# ═════════════════════════════════════════════════════════════════════════════

def tutorial_06_evolution(firm: Firm):
    """
    L'organisation peut modifier ses propres paramètres de fonctionnement.
    Seuls les agents à haute autorité (>= 0.85) peuvent proposer des évolutions.
    """
    titre("6. AUTO-ÉVOLUTION DES PARAMÈTRES")

    agents = firm.get_agents()
    alice = [a for a in agents if a.name == "Alice"][0]
    bob = [a for a in agents if a.name == "Bob"][0]

    # Voir les paramètres actuels
    params = firm.get_firm_parameters("authority")
    print(f"  Paramètres actuels (authority) :")
    for k, v in params.items():
        print(f"    {k}: {v}")

    # Alice (haute autorité) propose un changement
    evo = firm.propose_evolution(
        alice.id,
        changes=[{
            "category": "authority",
            "parameter_name": "learning_rate",
            "new_value": 0.08,
        }],
        rationale="Accélérer l'apprentissage pour la phase de croissance",
    )
    print(f"\n  Évolution proposée : learning_rate → 0.08 (id: {evo.id[:12]}…)")

    # Vote de l'évolution
    firm.vote_evolution(evo.id, alice.id, approve=True)
    firm.vote_evolution(evo.id, bob.id, approve=True)

    # Appliquer
    changes = firm.apply_evolution(evo.id)
    if changes:
        for c in changes:
            print(f"  Appliqué : {c.parameter_name} : {c.old_value} → {c.new_value}")
    else:
        print(f"  L'évolution a été rejetée (quorum insuffisant)")

    print(f"\n  → L'organisation peut modifier son propre comportement par consensus")


# ═════════════════════════════════════════════════════════════════════════════
# 7. SPAWN & MERGE (Couche 7)
# ═════════════════════════════════════════════════════════════════════════════

def tutorial_07_spawn(firm: Firm):
    """
    Les agents peuvent se reproduire (spawn), fusionner (merge) ou se diviser (split).
    L'autorité du parent détermine celle de l'enfant.
    """
    titre("7. SPAWN, MERGE & SPLIT")

    agents = firm.get_agents()
    alice = [a for a in agents if a.name == "Alice"][0]
    bob = [a for a in agents if a.name == "Bob"][0]

    # Spawn — Alice crée un agent junior
    junior = firm.spawn_agent(alice.id, "Junior-Dev")
    print(f"  Alice spawne '{junior.name}' → autorité: {junior.authority:.4f}")
    print(f"  (hérite d'une fraction de l'autorité du parent)")

    # Split — un agent se divise en deux spécialistes
    carol = [a for a in firm.get_agents() if a.name == "Carol"][0]
    frontend, backend = firm.split_agent(carol.id, "Carol-Frontend", "Carol-Backend", authority_ratio=0.6)
    print(f"\n  Carol se split :")
    print(f"    → {frontend.name} (autorité: {frontend.authority:.4f})")
    print(f"    → {backend.name} (autorité: {backend.authority:.4f})")

    print(f"\n  Agents actifs : {len(firm.get_agents())}")
    afficher_autorite(firm)


# ═════════════════════════════════════════════════════════════════════════════
# 8. MARCHÉ INTERNE (Couche 8 — Internal Market)
# ═════════════════════════════════════════════════════════════════════════════

def tutorial_08_market(firm: Firm):
    """
    Les agents postent des tâches avec des bounties.
    D'autres agents enchérissent pour les réaliser.
    Les crédits sont transférés selon le résultat.
    """
    titre("8. MARCHÉ INTERNE")

    agents = firm.get_agents()
    alice = [a for a in agents if a.name == "Alice"][0]
    active = [a for a in agents if a.name not in ("Alice", "Carol") and a.is_active]
    worker = active[0] if active else agents[1]

    # Poster une tâche
    task = firm.post_task(
        alice.id,
        title="Implémenter le dashboard",
        description="Dashboard métriques avec graphes temps réel",
        bounty=50.0,
    )
    print(f"  Tâche postée : '{task.title}' — bounty: {task.bounty} crédits")

    # Un agent enchérit
    bid = firm.bid_on_task(task.id, worker.id, amount=45.0, pitch="Je connais D3.js")
    print(f"  {worker.name} enchérit : {bid.amount} crédits")

    # Accepter l'enchère
    firm.accept_bid(task.id, bid.id)
    print(f"  Enchère acceptée → tâche assignée à {worker.name}")

    # Règlement après complétion
    settlement = firm.settle_task(task.id, success=True)
    print(f"\n  Tâche complétée !")
    print(f"    Transfert : {settlement.amount:.1f} crédits ({settlement.from_agent[:8]}… → {settlement.to_agent[:8]}…)")
    print(f"    Fee :       {settlement.fee:.1f} crédits")


# ═════════════════════════════════════════════════════════════════════════════
# 9. AUDIT (Couche 10 — Audit Engine)
# ═════════════════════════════════════════════════════════════════════════════

def tutorial_09_audit(firm: Firm):
    """
    L'audit vérifie l'intégrité du ledger, la santé de l'autorité,
    et identifie les anomalies dans l'organisation.
    """
    titre("9. AUDIT ORGANISATIONNEL")

    report = firm.run_audit()
    print(f"  Rapport généré : {report.generated_at}")
    print(f"  Chaîne ledger valide : {'✓' if report.chain_valid else '✗'}")
    print(f"  Findings : {len(report.findings)}")

    for f in report.findings[:5]:
        print(f"    [{f.severity.value:<8}] {f.category}: {f.title}")

    if not report.findings:
        print(f"    Aucun problème détecté ✓")


# ═════════════════════════════════════════════════════════════════════════════
# 10. EVENT BUS & PLUGINS (Couche transversale)
# ═════════════════════════════════════════════════════════════════════════════

def tutorial_10_events_plugins():
    """
    Le bus d'événements permet la communication entre couches.
    Les plugins étendent le comportement de l'organisation.
    """
    titre("10. ÉVÉNEMENTS & PLUGINS")

    firm = Firm(name="PluginDemo")
    events_log = []

    # S'abonner aux événements
    def on_agent(event):
        events_log.append(f"Agent: {event.data['name']}")

    def on_action(event):
        events_log.append(f"Action: {event.data['agent_id'][:8]}… success={event.data['success']}")

    firm.events.subscribe("agent.added", on_agent)
    firm.events.subscribe("action.recorded", on_action)

    # Les actions émettent automatiquement des événements
    a = firm.add_agent("TestAgent", authority=0.7)
    firm.record_action(a.id, success=True, description="Test")

    print(f"  Événements capturés :")
    for e in events_log:
        print(f"    → {e}")

    # Plugin personnalisé
    sous_titre("Plugin personnalisé")

    class ActionCounter(FirmPlugin):
        name = "action-counter"
        version = "1.0.0"
        description = "Compte les actions réussies/échouées"

        def __init__(self):
            super().__init__()
            self.successes = 0
            self.failures = 0

        def on_activate(self, firm):
            firm.events.subscribe("action.recorded", self._count)

        def on_deactivate(self, firm):
            firm.events.unsubscribe("action.recorded", self._count)

        def _count(self, event):
            if event.data.get("success"):
                self.successes += 1
            else:
                self.failures += 1

    counter = ActionCounter()
    firm.plugins.register(counter)
    firm.plugins.activate("action-counter", firm)

    # Les actions sont maintenant comptabilisées
    firm.record_action(a.id, success=True, description="Feature livrée")
    firm.record_action(a.id, success=True, description="Bug corrigé")
    firm.record_action(a.id, success=False, description="Test échoué")

    print(f"  Plugin '{counter.name}' : {counter.successes} succès, {counter.failures} échecs")

    firm.plugins.deactivate("action-counter", firm)
    print(f"  Plugin désactivé — les événements ne sont plus comptés")


# ═════════════════════════════════════════════════════════════════════════════
# 11. SÉRIALISATION (Save/Load/Snapshot)
# ═════════════════════════════════════════════════════════════════════════════

def tutorial_11_serialization():
    """
    Sauvegarder et restaurer l'état complet de l'organisation.
    Comparer des snapshots pour détecter les changements.
    """
    titre("11. SÉRIALISATION & SNAPSHOTS")

    firm = Firm(name="SaveDemo")
    firm.add_agent("Alice", authority=0.8)
    firm.add_agent("Bob", authority=0.6)

    # Snapshot avant
    before = snapshot(firm)

    # Faire des changements
    agents = firm.get_agents()
    firm.record_action(agents[0].id, success=True, description="Shipped!")
    firm.add_agent("Charlie", authority=0.5)

    # Snapshot après
    after = snapshot(firm)

    # Comparer
    changes = diff_snapshots(before, after)
    print(f"  Changements détectés :")
    for section, details in changes.items():
        if details:
            print(f"    {section}: {details}")

    # Sauvegarder sur disque
    import tempfile, json
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        state = save_firm(firm, f.name)
        path = f.name

    print(f"\n  État sauvegardé → {path}")

    # Restaurer
    restored = load_firm(path)
    print(f"  État restauré : '{restored.name}' ({len(restored.get_agents())} agents)")

    # Nettoyage
    os.unlink(path)


# ═════════════════════════════════════════════════════════════════════════════
# 12. HUMAN OVERRIDE (Couche 12 — Kill Switch)
# ═════════════════════════════════════════════════════════════════════════════

def tutorial_12_kill_switch():
    """
    L'humain (fondateur, board, DAO) peut toujours arrêter l'organisation.
    C'est l'invariant non-négociable #1 du protocole.
    """
    titre("12. KILL SWITCH — L'HUMAIN GARDE LE CONTRÔLE")

    firm = Firm(name="KillSwitchDemo")
    a = firm.add_agent("Agent", authority=0.8)

    # Tout fonctionne normalement
    result = firm.record_action(a.id, success=True, description="Normal operation")
    print(f"  Action normale : blocked={result.get('blocked', False)}")

    # Activer le kill switch
    firm.human.activate_kill_switch(reason="Comportement anormal détecté")
    print(f"\n  ⚠️  KILL SWITCH ACTIVÉ")

    # Les actions sont désormais bloquées
    result = firm.record_action(a.id, success=True, description="This should be blocked")
    print(f"  Action tentée : blocked={result.get('blocked', True)}")
    print(f"  Raison : {result.get('message', 'Operations halted')}")

    # Désactiver le kill switch
    firm.human.deactivate_kill_switch(reason="Situation résolue")
    result = firm.record_action(a.id, success=True, description="Resuming operations")
    print(f"\n  Kill switch désactivé — opérations reprises")
    print(f"  Action : blocked={result.get('blocked', False)}")


# ═════════════════════════════════════════════════════════════════════════════
# EXÉCUTION
# ═════════════════════════════════════════════════════════════════════════════

def main():
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║        TUTORIEL FIRM PROTOCOL — Organisation Autonome Évolutive     ║")
    print("║        12 couches · Autorité méritée · Mémoire débat · Kill switch  ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    # Couches 1-4 utilisent la même organisation
    firm = tutorial_01_creation()
    tutorial_02_ledger(firm)
    tutorial_03_roles(firm)
    tutorial_04_memory(firm)

    # Couches 5-9 continuent avec la même org
    tutorial_05_governance(firm)
    tutorial_06_evolution(firm)
    tutorial_07_spawn(firm)
    tutorial_08_market(firm)
    tutorial_09_audit(firm)

    # Couches transversales (demos indépendantes)
    tutorial_10_events_plugins()
    tutorial_11_serialization()
    tutorial_12_kill_switch()

    titre("TUTORIEL TERMINÉ")
    print("  Le FIRM Protocol définit la physique des organisations autonomes.")
    print("  L'autorité est méritée. La mémoire est un débat.")
    print("  La structure est fluide. Les erreurs ont des conséquences économiques.")
    print("  L'évolution n'est pas optionnelle.")
    print()
    print("  Deux invariants non-négociables :")
    print("    1. L'humain peut toujours tout arrêter")
    print("    2. Le système ne peut pas effacer sa capacité à évoluer")
    print()


if __name__ == "__main__":
    main()
