#!/usr/bin/env python3
"""
examples/startup_lifecycle.py — Narrated demo of a FIRM evolving from bootstrap to maturity.

A fictional AI startup ("NeuralForge") uses the FIRM Protocol to run its organization.
Watch authority flow, governance emerge, knowledge accumulate, and the economy self-regulate.

Run:
    python examples/startup_lifecycle.py

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

import sys
import os

# Ensure firm package is importable when running from the repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from firm.runtime import Firm


def banner(text: str) -> None:
    """Print a section banner."""
    print(f"\n{'═' * 60}")
    print(f"  {text}")
    print(f"{'═' * 60}\n")


def status_line(label: str, value: object) -> None:
    """Print a labeled status line."""
    print(f"  {label:<30} {value}")


def main() -> None:
    banner("ACT 1 · BOOTSTRAP — The Genesis of NeuralForge")

    firm = Firm(name="NeuralForge")
    print(f"  FIRM '{firm.name}' created (id={firm.id})\n")

    # Founding team
    ada = firm.add_agent("Ada", authority=0.9, credits=1000.0)
    kai = firm.add_agent("Kai", authority=0.7, credits=500.0)
    zara = firm.add_agent("Zara", authority=0.5, credits=300.0)
    print(f"  Founding team: Ada (CEO, 0.9), Kai (CTO, 0.7), Zara (Eng, 0.5)")

    # Early work
    for _ in range(5):
        firm.record_action(ada.id, success=True, description="Strategic decision")
    for _ in range(4):
        firm.record_action(kai.id, success=True, description="Shipped core system")
    firm.record_action(kai.id, success=False, description="Outage during demo")
    for _ in range(3):
        firm.record_action(zara.id, success=True, description="Built features")
    firm.record_action(zara.id, success=False, description="Bug in production")

    print(f"\n  Authority after Phase 1:")
    for a in firm.get_agents():
        bar = "█" * int(a.authority * 40)
        print(f"    {a.name:<10} {a.authority:.4f} {bar}")

    # ── Act 2 ──────────────────────────────────────────────
    banner("ACT 2 · STRUCTURE — Defining Roles & Knowledge")

    firm.define_role("CEO", min_authority=0.85, description="Strategic leadership")
    firm.define_role("CTO", min_authority=0.6, description="Technical leadership")
    firm.define_role("Engineer", min_authority=0.4, description="Build & ship")

    firm.assign_role(ada.id, "CEO")
    firm.assign_role(kai.id, "CTO")
    firm.assign_role(zara.id, "Engineer")
    print("  Roles assigned: Ada→CEO, Kai→CTO, Zara→Engineer")

    # Collective memory
    m1 = firm.contribute_memory(
        ada.id,
        "We target enterprise customers with custom AI models",
        tags=["strategy", "market"],
    )
    m2 = firm.contribute_memory(
        kai.id,
        "Use Rust for performance-critical paths, Python for ML pipelines",
        tags=["architecture", "tech-stack"],
    )
    m3 = firm.contribute_memory(
        zara.id,
        "Feature flags reduce deployment risk significantly",
        tags=["process", "deployment"],
    )
    firm.reinforce_memory(kai.id, m1.id)   # Kai agrees with strategy
    firm.reinforce_memory(ada.id, m2.id)   # Ada trusts Kai's tech stack
    firm.reinforce_memory(kai.id, m3.id)   # Kai agrees with Zara

    memories = firm.recall_memory(tags=["architecture", "strategy", "process"])
    print(f"  Collective memories: {len(memories)} entries")
    for m in memories:
        print(f"    [{m.weight:.2f}] {m.content[:60]}...")

    # ── Act 3 ──────────────────────────────────────────────
    banner("ACT 3 · GOVERNANCE — First Proposal")

    proposal = firm.propose(
        ada.id,
        title="Adopt mandatory code review",
        description="All code changes require at least one peer review",
    )
    print(f"  Proposal: '{proposal.title}' (id={proposal.id[:8]})")

    # Fast-track simulations
    firm.simulate_proposal(proposal.id, success=True, impact_summary="Low risk")
    firm.simulate_proposal(proposal.id, success=True, impact_summary="Stress OK")
    firm.simulate_proposal(proposal.id, success=True, impact_summary="Final pass")
    firm.governance.open_voting(proposal)

    firm.vote(proposal.id, ada.id, "approve", reason="Quality first")
    firm.vote(proposal.id, kai.id, "approve", reason="Prevents bugs")
    result = firm.finalize_proposal(proposal.id)
    print(f"  Result: {result['outcome']}")

    # ── Act 4 ──────────────────────────────────────────────
    banner("ACT 4 · SCALE — Spawn & Market Economy")

    # Spawn a CI bot
    ci_bot = firm.spawn_agent(ada.id, "CI-Bot")
    print(f"  Spawned: {ci_bot.name} (authority {ci_bot.authority:.4f})")

    # Internal market
    task = firm.post_task(
        ada.id,
        "Build monitoring dashboard",
        description="Real-time metrics for all services",
        bounty=50.0,
    )
    print(f"\n  Task posted: '{task.title}' — bounty {task.bounty} credits")

    bid = firm.bid_on_task(task.id, kai.id, amount=40.0)
    print(f"  Bid from Kai: {bid.amount} credits")

    firm.accept_bid(task.id, bid.id)
    settlement = firm.settle_task(task.id, success=True)
    print(f"  Task completed! {settlement.amount:.1f} credits transferred to Kai")
    print(f"  Fee to commons: {settlement.fee:.1f} credits")

    # ── Act 5 ──────────────────────────────────────────────
    banner("ACT 5 · FEDERATION — Reaching Beyond")

    peer = firm.register_peer(ada.id, "acme-ai", "Acme AI Labs")
    print(f"  Registered peer: {peer.name}")

    # Build trust before secondment (default trust 0.3, need > 0.5)
    for _ in range(10):
        firm.federation.update_trust("acme-ai", success=True, weight=1.0)

    msg = firm.send_federation_message(
        ada.id, "acme-ai", "proposal",
        "Data sharing agreement",
        "Propose sharing anonymized training datasets",
    )
    print(f"  Message sent: '{msg.subject}'")

    sec = firm.second_agent(
        ada.id, zara.id, "acme-ai",
        reason="Cross-training on their ML pipeline",
    )
    print(f"  Seconded {zara.name} to Acme AI (effective auth: {sec.effective_authority:.4f})")

    # Reputation
    att = firm.issue_reputation(kai.id, "Core contributor, exceptional reliability")
    print(f"\n  Reputation issued for Kai: {att.endorsement[:50]}...")

    # ── Act 6 ──────────────────────────────────────────────
    banner("ACT 6 · EVOLUTION — The Organism Adapts")

    # Need enough high-authority agents for quorum
    senior = firm.add_agent("Senior", authority=0.92, credits=400.0)

    evo = firm.propose_evolution(
        ada.id,
        changes=[{
            "category": "authority",
            "parameter_name": "learning_rate",
            "new_value": 0.08,
        }],
        rationale="Organization is stable enough for faster learning",
    )
    print(f"  Evolution proposed: learning_rate → 0.08 (gen {firm.evolution.generation})")

    firm.vote_evolution(evo.id, ada.id, True)
    firm.vote_evolution(evo.id, senior.id, True)
    changes = firm.apply_evolution(evo.id)

    print(f"  Applied! Generation: {firm.evolution.generation}")
    for c in changes:
        print(f"    {c.category.value}.{c.parameter_name}: {c.old_value} → {c.new_value}")

    # ── Act 7 ──────────────────────────────────────────────
    banner("ACT 7 · META — The Constitution Evolves")

    amendment = firm.propose_amendment(
        proposer_id=ada.id,
        amendment_type="add_invariant",
        invariant_id="INV-3",
        description="All models must be auditable and explainable before deployment",
        keywords=["audit", "explainability", "model", "deployment"],
        rationale="AI safety requires transparency in our systems",
    )
    print(f"  Amendment proposed: {amendment.amendment_type.value}")

    reviewed = firm.review_amendment(amendment.id)
    print(f"  Constitutional review: {'PASSED' if reviewed.review_passed else 'VETOED'}")

    firm.vote_amendment(amendment.id, ada.id, approve=True)
    firm.vote_amendment(amendment.id, senior.id, approve=True)
    applied = firm.apply_amendment(amendment.id)
    print(f"  Amendment {applied.status.value}! Constitution revision: {firm.meta.revision}")

    # ── Final ──────────────────────────────────────────────
    banner("EPILOGUE — The State of NeuralForge")

    report = firm.run_audit()
    print(f"  Audit: {report.firm_name} — {len(report.findings)} findings")
    if report.findings:
        for f in report.findings[:3]:
            print(f"    [{f.severity}] {f.title[:60]}")

    status = firm.status()
    print()
    status_line("Total agents:", status["agents"]["total"])
    status_line("Active agents:", status["agents"]["active"])
    status_line("Ledger entries:", status["ledger"]["total_entries"])
    status_line("Chain valid:", status["ledger"]["chain_valid"])
    status_line("Evolution generation:", status["evolution"]["generation"])
    status_line("Constitution revision:", status["meta_constitutional"]["revision"])

    chain = firm.ledger.verify_chain()
    assert chain["valid"], "Ledger integrity compromised!"

    print()
    print("  Authority rankings:")
    agents = sorted(firm.get_agents(), key=lambda a: a.authority, reverse=True)
    for i, a in enumerate(agents, 1):
        bar = "█" * int(a.authority * 30)
        print(f"    {i}. {a.name:<12} {a.authority:.4f} {bar}")

    print(f"\n  ✓ NeuralForge: {len(agents)} agents, "
          f"gen {firm.evolution.generation}, "
          f"rev {firm.meta.revision}, "
          f"all chains valid.")


if __name__ == "__main__":
    main()
