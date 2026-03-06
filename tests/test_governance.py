"""Tests for firm.core.governance — Governance Engine"""

import time

import pytest

from firm.core.agent import Agent
from firm.core.governance import (
    GovernanceEngine,
    Proposal,
    SimulationResult,
    Vote,
)
from firm.core.types import ProposalStatus, VoteChoice


class TestSimulationResult:
    def test_create(self):
        sr = SimulationResult(success=True, impact_summary="All good", risk_score=0.1)
        assert sr.success
        assert sr.risk_score == 0.1

    def test_to_dict(self):
        sr = SimulationResult(
            success=False,
            impact_summary="Failed hard",
            risk_score=0.9,
            side_effects=["broke X"],
        )
        d = sr.to_dict()
        assert d["risk_score"] == 0.9
        assert len(d["side_effects"]) == 1


class TestVote:
    def test_approve_weighted(self):
        v = Vote(voter_id="a1", choice=VoteChoice.APPROVE, authority_weight=0.8)
        assert v.weighted_value == 0.8

    def test_reject_weighted(self):
        v = Vote(voter_id="a1", choice=VoteChoice.REJECT, authority_weight=0.6)
        assert v.weighted_value == -0.6

    def test_abstain_zero(self):
        v = Vote(voter_id="a1", choice=VoteChoice.ABSTAIN, authority_weight=0.9)
        assert v.weighted_value == 0.0


class TestProposal:
    def _make_proposal(self) -> Proposal:
        return Proposal(
            proposer_id="a1",
            title="Test Proposal",
            description="A test",
        )

    def test_create_draft(self):
        p = self._make_proposal()
        assert p.status == ProposalStatus.DRAFT

    def test_full_lifecycle(self):
        p = self._make_proposal()

        # Simulation 1
        p.advance_to_simulation_1(SimulationResult(True, "ok", 0.1))
        assert p.status == ProposalStatus.SIMULATION_1

        # Stress test
        p.advance_to_stress_test(SimulationResult(True, "survived", 0.3))
        assert p.status == ProposalStatus.STRESS_TEST

        # Simulation 2
        p.advance_to_simulation_2(SimulationResult(True, "still ok", 0.2))
        assert p.status == ProposalStatus.SIMULATION_2

        # Open voting
        p.open_voting()
        assert p.status == ProposalStatus.VOTING

    def test_invalid_transitions(self):
        p = self._make_proposal()
        with pytest.raises(ValueError, match="Cannot advance"):
            p.advance_to_stress_test(SimulationResult(True, "skip", 0.1))

    def test_cast_vote(self):
        p = self._make_proposal()
        p.advance_to_simulation_1(SimulationResult(True, "ok", 0.1))
        p.advance_to_stress_test(SimulationResult(True, "ok", 0.1))
        p.advance_to_simulation_2(SimulationResult(True, "ok", 0.1))
        p.open_voting()
        p.cast_vote(Vote(voter_id="v1", choice=VoteChoice.APPROVE, authority_weight=0.8))
        assert len(p.votes) == 1

    def test_duplicate_vote_rejected(self):
        p = self._make_proposal()
        p.advance_to_simulation_1(SimulationResult(True, "ok", 0.1))
        p.advance_to_stress_test(SimulationResult(True, "ok", 0.1))
        p.advance_to_simulation_2(SimulationResult(True, "ok", 0.1))
        p.open_voting()
        p.cast_vote(Vote(voter_id="v1", choice=VoteChoice.APPROVE, authority_weight=0.8))
        with pytest.raises(ValueError, match="already voted"):
            p.cast_vote(Vote(voter_id="v1", choice=VoteChoice.REJECT, authority_weight=0.8))

    def test_vote_on_non_voting_fails(self):
        p = self._make_proposal()  # DRAFT
        with pytest.raises(ValueError, match="Cannot vote"):
            p.cast_vote(Vote(voter_id="v1", choice=VoteChoice.APPROVE, authority_weight=0.8))

    def test_tally_approval(self):
        p = self._make_proposal()
        p.advance_to_simulation_1(SimulationResult(True, "ok", 0.1))
        p.advance_to_stress_test(SimulationResult(True, "ok", 0.1))
        p.advance_to_simulation_2(SimulationResult(True, "ok", 0.1))
        p.open_voting()

        p.cast_vote(Vote(voter_id="v1", choice=VoteChoice.APPROVE, authority_weight=0.9))
        p.cast_vote(Vote(voter_id="v2", choice=VoteChoice.APPROVE, authority_weight=0.7))
        p.cast_vote(Vote(voter_id="v3", choice=VoteChoice.REJECT, authority_weight=0.6))

        tally = p.tally_votes(eligible_voters=5)
        assert tally["quorum_met"]  # 3/5 = 0.6 >= 0.6
        assert tally["approved"]  # (0.9+0.7)/(0.9+0.7+0.6) > 0.5

    def test_tally_quorum_not_met(self):
        p = self._make_proposal()
        p.advance_to_simulation_1(SimulationResult(True, "ok", 0.1))
        p.advance_to_stress_test(SimulationResult(True, "ok", 0.1))
        p.advance_to_simulation_2(SimulationResult(True, "ok", 0.1))
        p.open_voting()

        p.cast_vote(Vote(voter_id="v1", choice=VoteChoice.APPROVE, authority_weight=0.9))

        tally = p.tally_votes(eligible_voters=10)
        assert not tally["quorum_met"]  # 1/10 = 0.1 < 0.6
        assert not tally["approved"]

    def test_finalize_approved_enters_cooldown(self):
        p = self._make_proposal()
        p.advance_to_simulation_1(SimulationResult(True, "ok", 0.1))
        p.advance_to_stress_test(SimulationResult(True, "ok", 0.1))
        p.advance_to_simulation_2(SimulationResult(True, "ok", 0.1))
        p.open_voting()

        p.cast_vote(Vote(voter_id="v1", choice=VoteChoice.APPROVE, authority_weight=0.9))
        p.cast_vote(Vote(voter_id="v2", choice=VoteChoice.APPROVE, authority_weight=0.7))

        result = p.finalize(eligible_voters=3, cooldown_seconds=0.01)
        assert result["outcome"] == "approved_pending_cooldown"
        assert p.status == ProposalStatus.COOLDOWN

    def test_finalize_rejected(self):
        p = self._make_proposal()
        p.advance_to_simulation_1(SimulationResult(True, "ok", 0.1))
        p.advance_to_stress_test(SimulationResult(True, "ok", 0.1))
        p.advance_to_simulation_2(SimulationResult(True, "ok", 0.1))
        p.open_voting()

        p.cast_vote(Vote(voter_id="v1", choice=VoteChoice.REJECT, authority_weight=0.9))
        p.cast_vote(Vote(voter_id="v2", choice=VoteChoice.REJECT, authority_weight=0.7))

        result = p.finalize(eligible_voters=3)
        assert result["outcome"] == "rejected"
        assert p.status == ProposalStatus.REJECTED

    def test_constitutional_veto(self):
        p = self._make_proposal()
        p.advance_to_simulation_1(SimulationResult(True, "ok", 0.1))
        p.advance_to_stress_test(SimulationResult(True, "ok", 0.1))
        p.advance_to_simulation_2(SimulationResult(True, "ok", 0.1))
        p.open_voting()

        # Add a vote so finalize has something to work with
        p.cast_vote(Vote(voter_id="v1", choice=VoteChoice.APPROVE, authority_weight=0.9))
        # Veto BEFORE finalize — sets flag but does NOT change status
        p.constitutional_veto = True
        p.veto_reason = "Violates INV-1"
        result = p.finalize(eligible_voters=5)
        assert result["outcome"] == "rejected"
        assert result["reason"] == "constitutional_veto"

    def test_cooldown_completion(self):
        p = self._make_proposal()
        p.advance_to_simulation_1(SimulationResult(True, "ok", 0.1))
        p.advance_to_stress_test(SimulationResult(True, "ok", 0.1))
        p.advance_to_simulation_2(SimulationResult(True, "ok", 0.1))
        p.open_voting()
        p.cast_vote(Vote(voter_id="v1", choice=VoteChoice.APPROVE, authority_weight=0.9))
        p.cast_vote(Vote(voter_id="v2", choice=VoteChoice.APPROVE, authority_weight=0.7))
        p.finalize(eligible_voters=3, cooldown_seconds=0.001)

        time.sleep(0.01)
        assert p.complete_cooldown()
        assert p.status == ProposalStatus.APPROVED

    def test_rollback(self):
        p = self._make_proposal()
        p.advance_to_simulation_1(SimulationResult(True, "ok", 0.1))
        p.advance_to_stress_test(SimulationResult(True, "ok", 0.1))
        p.advance_to_simulation_2(SimulationResult(True, "ok", 0.1))
        p.open_voting()
        p.cast_vote(Vote(voter_id="v1", choice=VoteChoice.APPROVE, authority_weight=0.9))
        p.finalize(eligible_voters=1, cooldown_seconds=0.001)
        time.sleep(0.01)
        p.complete_cooldown()

        p.rollback("Caused unexpected issues")
        assert p.status == ProposalStatus.ROLLED_BACK
        assert p.rolled_back

    def test_to_dict(self):
        p = self._make_proposal()
        d = p.to_dict()
        assert d["title"] == "Test Proposal"
        assert d["status"] == "draft"


class TestGovernanceEngine:
    def test_create_proposal(self):
        engine = GovernanceEngine()
        proposer = Agent(authority=0.85)
        proposal = engine.create_proposal(proposer, "Test", "A test proposal")
        assert proposal.status == ProposalStatus.DRAFT

    def test_create_proposal_low_authority(self):
        engine = GovernanceEngine()
        proposer = Agent(authority=0.5)
        with pytest.raises(PermissionError, match="authority"):
            engine.create_proposal(proposer, "Test", "A test proposal")

    def test_vote_low_authority(self):
        engine = GovernanceEngine()
        proposer = Agent(authority=0.85)
        proposal = engine.create_proposal(proposer, "Test", "A test proposal")

        # Run through simulations
        engine.simulate(proposal, SimulationResult(True, "ok", 0.1))
        engine.simulate(proposal, SimulationResult(True, "ok", 0.1))
        engine.simulate(proposal, SimulationResult(True, "ok", 0.1))
        engine.open_voting(proposal)

        low_voter = Agent(authority=0.3)
        with pytest.raises(PermissionError, match="authority"):
            engine.vote(proposal, low_voter, VoteChoice.APPROVE)

    def test_get_active_proposals(self):
        engine = GovernanceEngine()
        proposer = Agent(authority=0.85)
        engine.create_proposal(proposer, "P1", "First")
        engine.create_proposal(proposer, "P2", "Second")
        active = engine.get_active_proposals()
        assert len(active) == 2

    def test_simulate_phases(self):
        engine = GovernanceEngine()
        proposer = Agent(authority=0.85)
        p = engine.create_proposal(proposer, "Test", "desc")

        engine.simulate(p, SimulationResult(True, "sim1", 0.1))
        assert p.status == ProposalStatus.SIMULATION_1

        engine.simulate(p, SimulationResult(True, "stress", 0.3))
        assert p.status == ProposalStatus.STRESS_TEST

        engine.simulate(p, SimulationResult(True, "sim2", 0.2))
        assert p.status == ProposalStatus.SIMULATION_2
