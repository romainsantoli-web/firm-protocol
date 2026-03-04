"""
test_e2e — End-to-end integration test exercising all 12 FIRM Protocol layers.

This test simulates the full lifecycle of a FIRM organization:

  1. Bootstrap (L0-L2) — Create firm, add agents, record actions, verify authority
  2. Governance (L6) — Proposal lifecycle: create → simulate → vote → finalize
  3. Roles (L3) — Define and assign roles
  4. Memory (L4) — Contribute, recall, reinforce, challenge
  5. Spawn (L7) — Spawn child agent from parent
  6. Federation (L8) — Register peer, send message, second agent
  7. Reputation (L9) — Issue and verify attestation
  8. Audit (L10) — Full audit report
  9. Human Override (L11) — Kill switch
  10. Evolution (S3) — Propose, vote, apply parameter change
  11. Market (S3) — Post task, bid, accept, settle
  12. Meta-Constitutional (S3) — Amend the constitution itself
"""

import pytest

from firm.runtime import Firm


class TestFullLifecycle:
    """End-to-end: bootstrap → governance → roles → memory → spawn →
    federation → reputation → audit → human → evolution → market → meta."""

    def setup_method(self) -> None:
        """Create a fresh FIRM with 3 agents for each test."""
        self.firm = Firm(name="e2e-test-firm")

        # CEO: high authority, can do everything
        self.ceo = self.firm.add_agent("CEO", authority=0.95, credits=1000.0)
        # Engineer: medium authority
        self.eng = self.firm.add_agent("Engineer", authority=0.65, credits=200.0)
        # Intern: low authority
        self.intern = self.firm.add_agent("Intern", authority=0.35, credits=50.0)

    # ── Phase 1: Bootstrap (L0-L2) ───────────────────────────────────────

    def test_phase1_bootstrap(self) -> None:
        """L0 Authority + L1 Ledger + L2 Constitution — basic operations."""
        # Record successful actions for engineer
        old_eng_auth = self.eng.authority
        r = self.firm.record_action(self.eng.id, success=True, description="Shipped feature A")
        assert r["authority"]["new_value"] > old_eng_auth

        # Record failure for intern — authority should drop
        old_intern_auth = self.intern.authority
        r2 = self.firm.record_action(self.intern.id, success=False, description="Broke CI")
        assert r2["authority"]["new_value"] < old_intern_auth

        # Ledger should have genesis + 2 agent joins + 2 actions = 5 entries
        entries = self.firm.ledger.get_entries()
        assert len(entries) >= 5

        # Chain integrity
        chain = self.firm.ledger.verify_chain()
        assert chain["valid"] is True

        # Constitution active
        assert self.firm.constitution.kill_switch_active is False
        assert len(self.firm.constitution.invariants) >= 2  # INV-1, INV-2

    # ── Phase 2: Governance (L6) ─────────────────────────────────────────

    def test_phase2_governance(self) -> None:
        """Full proposal lifecycle: create → simulate → vote → finalize."""
        # CEO proposes (authority 0.95 > 0.8 threshold)
        proposal = self.firm.propose(
            self.ceo.id,
            title="Introduce QA process",
            description="Add mandatory code review before deploy",
        )
        assert proposal.status.value == "draft"

        # Run simulation phases
        self.firm.simulate_proposal(proposal.id, success=True, impact_summary="Low risk")
        self.firm.simulate_proposal(proposal.id, success=True, impact_summary="Stress OK")
        self.firm.simulate_proposal(proposal.id, success=True, impact_summary="Final OK")

        # Advance to voting
        self.firm.governance.open_voting(proposal)

        # CEO and Engineer vote
        self.firm.vote(proposal.id, self.ceo.id, "approve", reason="Good for quality")
        self.firm.vote(proposal.id, self.eng.id, "approve", reason="Agreed")

        # Finalize
        result = self.firm.finalize_proposal(proposal.id)
        # Should be approved (possibly pending cooldown)
        assert result["approved"] is True or result["outcome"] in ("approved", "approved_pending_cooldown")

    # ── Phase 3: Roles (L3) ─────────────────────────────────────────────

    def test_phase3_roles(self) -> None:
        """Define roles and assign them based on authority."""
        # Define roles
        qa_role = self.firm.define_role("QA Lead", min_authority=0.5, description="Quality")
        dev_role = self.firm.define_role("Developer", min_authority=0.3, description="Dev")

        # Engineer can be QA Lead (0.65 > 0.5)
        assignment = self.firm.assign_role(self.eng.id, "QA Lead")
        assert assignment.agent_id == self.eng.id
        assert assignment.role.name == "QA Lead"

        # Intern can be Developer (0.35 > 0.3)
        dev_assign = self.firm.assign_role(self.intern.id, "Developer")
        assert dev_assign.role.name == "Developer"

        # Intern cannot be QA Lead (0.35 < 0.5) — should raise
        with pytest.raises((PermissionError, ValueError)):
            self.firm.assign_role(self.intern.id, "QA Lead")

    # ── Phase 4: Memory (L4) ────────────────────────────────────────────

    def test_phase4_memory(self) -> None:
        """Contribute, recall, reinforce, and challenge memories."""
        # CEO contributes a memory
        mem = self.firm.contribute_memory(
            agent_id=self.ceo.id,
            content="Always run tests before deploying to production",
            tags=["process", "testing"],
        )
        assert mem.content == "Always run tests before deploying to production"

        # Recall by tag
        results = self.firm.recall_memory(tags=["testing"])
        assert len(results) >= 1
        assert any("tests" in r.content for r in results)

        # Engineer reinforces — save weight before (object is mutated in place)
        old_weight = mem.weight
        reinforced = self.firm.reinforce_memory(self.eng.id, mem.id)
        assert reinforced.weight >= old_weight
        assert self.eng.id in reinforced.reinforced_by

        # Intern challenges
        challenged = self.firm.challenge_memory(
            self.intern.id, mem.id, reason="Too strict for prototypes"
        )
        assert len(challenged.challenged_by) >= 1

    # ── Phase 5: Spawn (L7) ─────────────────────────────────────────────

    def test_phase5_spawn(self) -> None:
        """Spawn a child agent from a high-authority parent."""
        child = self.firm.spawn_agent(
            parent_id=self.ceo.id,
            name="QA-Bot",
        )
        assert child.name == "QA-Bot"
        assert child.authority < self.ceo.authority  # Child gets fraction
        assert child.authority > 0
        assert child.is_active

        # Child should be in the agent registry
        found = self.firm.get_agent(child.id)
        assert found is not None
        assert found.name == "QA-Bot"

    # ── Phase 6: Federation (L8) ────────────────────────────────────────

    def test_phase6_federation(self) -> None:
        """Register a peer, build trust, send a message, second an agent."""
        # CEO registers a peer FIRM (requires high authority)
        peer = self.firm.register_peer(
            agent_id=self.ceo.id,
            peer_firm_id="partner-firm",
            peer_name="Partner Corp",
        )
        assert peer.name == "Partner Corp"

        # Build trust through successful interactions (default trust is 0.3)
        # Need ~10 updates to get above 0.5 threshold for secondment
        for _ in range(10):
            self.firm.federation.update_trust("partner-firm", success=True, weight=1.0)

        # CEO sends a federation message
        msg = self.firm.send_federation_message(
            agent_id=self.ceo.id,
            to_firm="partner-firm",
            message_type="proposal",
            subject="Joint venture on AI safety",
            body="Let's collaborate on safety standards.",
        )
        assert msg.subject == "Joint venture on AI safety"

        # CEO seconds the Engineer to partner firm
        sec = self.firm.second_agent(
            authorizer_id=self.ceo.id,
            agent_id=self.eng.id,
            host_firm="partner-firm",
            reason="Cross-training",
        )
        assert sec.agent_id == self.eng.id
        assert sec.host_firm == "partner-firm"

    # ── Phase 7: Reputation (L9) ────────────────────────────────────────

    def test_phase7_reputation(self) -> None:
        """Issue and verify reputation attestations."""
        # Build up some action history first
        self.firm.record_action(self.eng.id, success=True, description="Task 1")
        self.firm.record_action(self.eng.id, success=True, description="Task 2")

        # Issue attestation for engineer
        attestation = self.firm.issue_reputation(
            agent_id=self.eng.id,
            endorsement="Reliable engineer with strong delivery track record",
        )
        assert attestation.agent_id == self.eng.id
        assert attestation.source_firm == self.firm.id
        assert "Reliable" in attestation.endorsement

        # Get aggregate reputation
        rep = self.firm.get_agent_reputation(self.eng.id)
        assert rep["agent_id"] == self.eng.id
        assert rep["combined_authority"] > 0

    # ── Phase 8: Audit (L10) ────────────────────────────────────────────

    def test_phase8_audit(self) -> None:
        """Run a full audit and verify the report."""
        # Do some activity first
        self.firm.record_action(self.ceo.id, success=True, description="Led review")
        self.firm.record_action(self.eng.id, success=True, description="Shipped fix")

        report = self.firm.run_audit()
        assert report.generated_at > 0
        assert isinstance(report.findings, list)
        # Report should reflect the firm state
        assert report.firm_name == "e2e-test-firm"

    # ── Phase 9: Human Override (L11) ────────────────────────────────────

    def test_phase9_human_override(self) -> None:
        """Kill switch stops all operations, then can be released."""
        # Activate kill switch
        event = self.firm.human.activate_kill_switch(reason="Emergency maintenance")
        assert self.firm.constitution.kill_switch_active is True

        # Actions should be blocked while kill switch is active
        r_blocked = self.firm.record_action(self.eng.id, success=True, description="Should fail")
        assert r_blocked["blocked"] is True
        assert r_blocked["reason"] == "kill_switch_active"

        # Deactivate kill switch
        self.firm.human.deactivate_kill_switch(reason="Maintenance complete")
        assert self.firm.constitution.kill_switch_active is False

        # Actions should work again
        r = self.firm.record_action(self.eng.id, success=True, description="Works again")
        assert r["success"] is True

    # ── Phase 10: Evolution (S3) ─────────────────────────────────────────

    def test_phase10_evolution(self) -> None:
        """Propose, vote, and apply a parameter evolution."""
        # Add a third high-authority agent to meet quorum
        senior = self.firm.add_agent("Senior", authority=0.9, credits=500.0)

        # CEO proposes changing learning rate (authority >= 0.85)
        proposal = self.firm.propose_evolution(
            proposer_id=self.ceo.id,
            changes=[{
                "category": "authority",
                "parameter_name": "learning_rate",
                "new_value": 0.08,
            }],
            rationale="Slightly faster learning after stabilization phase",
        )
        assert proposal.status.value == "proposed"

        # All high-authority agents vote approve
        self.firm.vote_evolution(proposal.id, self.ceo.id, True)
        self.firm.vote_evolution(proposal.id, senior.id, True)

        # Apply (auto-finalizes)
        changes = self.firm.apply_evolution(proposal.id)
        assert len(changes) >= 1
        assert changes[0].parameter_name == "learning_rate"
        assert changes[0].new_value == 0.08

        # Verify parameter changed
        params = self.firm.get_firm_parameters("authority")
        assert params["learning_rate"] == 0.08

        # Verify generation incremented
        assert self.firm.evolution.generation >= 1

    # ── Phase 11: Market (S3) ────────────────────────────────────────────

    def test_phase11_market(self) -> None:
        """Post task, bid, accept, and settle on the internal market."""
        # CEO posts a task
        task = self.firm.post_task(
            poster_id=self.ceo.id,
            title="Write unit tests for auth module",
            description="Full coverage of authentication flow",
            bounty=50.0,
        )
        assert task.title == "Write unit tests for auth module"
        assert task.bounty == 50.0

        # Engineer bids
        bid = self.firm.bid_on_task(task.id, self.eng.id, amount=45.0)
        assert bid.bidder_id == self.eng.id

        # CEO accepts the bid
        assigned = self.firm.accept_bid(task.id, bid.id)
        assert assigned.assigned_to == self.eng.id

        # Settle as success — credits transfer
        ceo_credits_before = self.ceo.credits
        eng_credits_before = self.eng.credits

        settlement = self.firm.settle_task(task.id, success=True)
        assert settlement.amount > 0

        # Verify credit flow
        assert self.eng.credits > eng_credits_before  # Worker gained
        assert self.ceo.credits < ceo_credits_before  # Poster paid

    # ── Phase 12: Meta-Constitutional (S3) ───────────────────────────────

    def test_phase12_meta_constitutional(self) -> None:
        """Amend the constitution by adding a new invariant."""
        senior = self.firm.add_agent("Senior2", authority=0.95, credits=500.0)

        # CEO proposes adding a new invariant
        amendment = self.firm.propose_amendment(
            proposer_id=self.ceo.id,
            amendment_type="add_invariant",
            invariant_id="INV-3",
            description="The organization must maintain diversity in agent roles",
            keywords=["diversity", "roles", "representation"],
            rationale="Prevent monoculture in agent specialization",
        )
        assert amendment.status.value == "proposed"

        # Review (constitutional agent checks for violations)
        reviewed = self.firm.review_amendment(amendment.id)
        assert reviewed.review_passed is True

        # Vote — need supermajority (80%)
        self.firm.vote_amendment(amendment.id, self.ceo.id, approve=True)
        self.firm.vote_amendment(amendment.id, senior.id, approve=True)

        # Apply
        applied = self.firm.apply_amendment(amendment.id)
        assert applied.status.value == "applied"

        # Verify new invariant exists in the constitution
        found = any(inv.id == "INV-3" for inv in self.firm.constitution.invariants)
        assert found, "INV-3 should exist in constitution after amendment"


class TestFullScenario:
    """A complete narrative scenario exercising all layers in sequence."""

    def test_startup_to_maturity(self) -> None:
        """A FIRM goes from bootstrap to stable operation across all layers."""
        # === Act 1: Bootstrap ===
        firm = Firm(name="Startup Alpha")
        alice = firm.add_agent("Alice", authority=0.9, credits=500.0)
        bob = firm.add_agent("Bob", authority=0.6, credits=200.0)
        carol = firm.add_agent("Carol", authority=0.5, credits=150.0)

        # Early actions — Alice leads, Bob supports, Carol learning
        for _ in range(3):
            firm.record_action(alice.id, success=True, description="Strategic decision")
        for _ in range(2):
            firm.record_action(bob.id, success=True, description="Shipped code")
        firm.record_action(carol.id, success=True, description="Completed training")
        firm.record_action(carol.id, success=False, description="Bug in production")

        # Verify authority divergence
        assert alice.authority > bob.authority > carol.authority

        # === Act 2: Define Structure ===
        firm.define_role("CTO", min_authority=0.8, description="Technical leadership")
        firm.define_role("Engineer", min_authority=0.4, description="Software development")
        firm.define_role("Junior", min_authority=0.2, description="Learning & growth")

        firm.assign_role(alice.id, "CTO")
        firm.assign_role(bob.id, "Engineer")
        firm.assign_role(carol.id, "Junior")

        # === Act 3: Build Knowledge ===
        mem1 = firm.contribute_memory(
            alice.id, "Microservices are better for our scale",
            tags=["architecture", "decision"],
        )
        mem2 = firm.contribute_memory(
            bob.id, "We should use PostgreSQL for persistence",
            tags=["architecture", "database"],
        )
        firm.reinforce_memory(bob.id, mem1.id)     # Bob agrees with Alice
        firm.reinforce_memory(alice.id, mem2.id)    # Alice agrees with Bob

        arch_memories = firm.recall_memory(tags=["architecture"])
        assert len(arch_memories) >= 2

        # === Act 4: Governance ===
        proposal = firm.propose(
            alice.id,
            title="Adopt CI/CD pipeline",
            description="Mandatory automated tests and deployment",
        )
        firm.simulate_proposal(proposal.id, success=True)
        firm.simulate_proposal(proposal.id, success=True)
        firm.simulate_proposal(proposal.id, success=True)
        firm.governance.open_voting(proposal)
        firm.vote(proposal.id, alice.id, "approve")
        firm.vote(proposal.id, bob.id, "approve")
        result = firm.finalize_proposal(proposal.id)

        # === Act 5: Spawn & Scale ===
        bot = firm.spawn_agent(alice.id, "CI-Bot")
        assert bot.is_active

        # === Act 6: Internal Economy ===
        task = firm.post_task(
            alice.id, "Write integration tests",
            description="Full E2E test suite",
            bounty=30.0,
        )
        bid = firm.bid_on_task(task.id, bob.id, amount=25.0)
        firm.accept_bid(task.id, bid.id)
        firm.settle_task(task.id, success=True)

        # === Act 7: Federation ===
        peer = firm.register_peer(alice.id, "partner-beta", "Partner Beta")
        # Build trust for secondment (need ~10 updates to cross 0.5 threshold)
        for _ in range(10):
            firm.federation.update_trust("partner-beta", success=True, weight=1.0)
        firm.send_federation_message(
            alice.id, "partner-beta", "proposal",
            "API Integration", "Let's integrate our APIs",
        )

        # === Act 8: Reputation ===
        att = firm.issue_reputation(bob.id, "Consistently delivers quality code")
        assert att.agent_id == bob.id

        # === Act 9: Audit ===
        report = firm.run_audit()
        assert report.firm_name == "Startup Alpha"

        # === Act 10: Evolution ===
        senior = firm.add_agent("Senior", authority=0.92, credits=300.0)
        evo = firm.propose_evolution(
            alice.id,
            changes=[{"category": "economy", "parameter_name": "success_reward", "new_value": 15.0}],
            rationale="Increase incentives as we scale",
        )
        firm.vote_evolution(evo.id, alice.id, True)
        firm.vote_evolution(evo.id, senior.id, True)
        firm.apply_evolution(evo.id)
        assert firm.get_firm_parameters("economy")["success_reward"] == 15.0

        # === Act 11: Meta-Constitutional ===
        amendment = firm.propose_amendment(
            proposer_id=alice.id,
            amendment_type="add_invariant",
            invariant_id="INV-3",
            description="The organization must publish an annual transparency report",
            keywords=["transparency", "report", "annual"],
            rationale="Accountability to stakeholders",
        )
        firm.review_amendment(amendment.id)
        firm.vote_amendment(amendment.id, alice.id, approve=True)
        firm.vote_amendment(amendment.id, senior.id, approve=True)
        applied = firm.apply_amendment(amendment.id)
        assert applied.status.value == "applied"

        # === Final: Verify comprehensive state ===
        status = firm.status()
        assert status["agents"]["total"] >= 5   # alice, bob, carol, bot, senior
        assert status["agents"]["active"] >= 5

        chain = firm.ledger.verify_chain()
        assert chain["valid"] is True

        entries = firm.ledger.get_entries()
        # Should have many entries from all the operations
        assert len(entries) >= 20

        # Check that constitutional amendment took effect
        found_inv3 = any(inv.id == "INV-3" for inv in firm.constitution.invariants)
        assert found_inv3

        # Generation should have advanced
        assert firm.evolution.generation >= 1
