import time

import pytest

from firm.core.agent import Agent
from firm.core.governance import GovernanceEngine, SimulationResult
from firm.core.types import ProposalStatus, VoteChoice


def _sim_result(success: bool = True, risk: float = 0.2) -> SimulationResult:
    return SimulationResult(
        success=success,
        impact_summary="simulation run",
        risk_score=risk,
        side_effects=[],
        duration_ms=10.0,
    )


def _advance_to_voting(engine: GovernanceEngine, proposal) -> None:
    engine.simulate(proposal, _sim_result())
    engine.simulate(proposal, _sim_result())
    engine.simulate(proposal, _sim_result())
    engine.open_voting(proposal)


def test_governance_engine_initialization_and_proposal_defaults():
    engine = GovernanceEngine(quorum_ratio=0.75, approval_ratio=0.66, cooldown_seconds=15)
    proposer = Agent(name="alice", authority=0.95)

    proposal = engine.create_proposal(
        proposer=proposer,
        title="Adopt improved policy",
        description="Proposal to improve process.",
    )

    assert proposal.status == ProposalStatus.DRAFT
    assert proposal.quorum_ratio == 0.75
    assert proposal.approval_ratio == 0.66
    assert engine.get_proposal(str(proposal.id)) is proposal


def test_proposal_submission_requires_min_authority():
    engine = GovernanceEngine()
    weak_proposer = Agent(name="low-auth", authority=0.5)

    with pytest.raises(PermissionError):
        engine.create_proposal(
            proposer=weak_proposer,
            title="Should fail",
            description="Insufficient proposer authority",
        )


def test_voting_with_different_strategies_weighted_approval_passes():
    engine = GovernanceEngine(quorum_ratio=0.6, approval_ratio=0.5, cooldown_seconds=5)
    proposer = Agent(name="proposer", authority=0.9)
    proposal = engine.create_proposal(proposer, "Resource shift", "Reallocate budget")
    _advance_to_voting(engine, proposal)

    strong_yes = Agent(name="strong-yes", authority=0.95)
    weak_no = Agent(name="weak-no", authority=0.65)
    abstain = Agent(name="abstain", authority=0.8)

    engine.vote(proposal, strong_yes, VoteChoice.APPROVE, reason="net positive")
    engine.vote(proposal, weak_no, VoteChoice.REJECT, reason="cost concerns")
    engine.vote(proposal, abstain, VoteChoice.ABSTAIN, reason="neutral")

    tally = proposal.tally_votes(eligible_voters=3)

    assert tally["quorum_met"] is True
    assert tally["approved"] is True
    assert tally["approve_weight"] == pytest.approx(0.95)
    assert tally["reject_weight"] == pytest.approx(0.65)
    assert tally["approval_percentage"] == pytest.approx(round(0.95 / (0.95 + 0.65), 3))


def test_quorum_validation_rejects_when_participation_too_low():
    engine = GovernanceEngine(quorum_ratio=0.75, approval_ratio=0.5, cooldown_seconds=1)
    proposer = Agent(name="p", authority=0.9)
    proposal = engine.create_proposal(proposer, "Change role caps", "Adjust role limits")
    _advance_to_voting(engine, proposal)

    voter = Agent(name="single-voter", authority=0.9)
    engine.vote(proposal, voter, VoteChoice.APPROVE)

    result = engine.finalize(proposal, eligible_voters=4)

    assert result["quorum_met"] is False
    assert result["outcome"] == "rejected"
    assert proposal.status == ProposalStatus.REJECTED


def test_edge_cases_duplicate_votes_and_expired_cooldown_completion():
    engine = GovernanceEngine(quorum_ratio=0.5, approval_ratio=0.5, cooldown_seconds=0.01)
    proposer = Agent(name="owner", authority=0.95)
    proposal = engine.create_proposal(proposer, "Meta update", "Tune governance parameters")
    _advance_to_voting(engine, proposal)

    voter = Agent(name="voter", authority=0.9)
    engine.vote(proposal, voter, VoteChoice.APPROVE)

    with pytest.raises(ValueError, match="already voted"):
        engine.vote(proposal, voter, VoteChoice.REJECT)

    outcome = engine.finalize(proposal, eligible_voters=1)
    assert outcome["outcome"] == "approved_pending_cooldown"
    assert proposal.status == ProposalStatus.COOLDOWN

    time.sleep(0.02)
    assert proposal.complete_cooldown() is True
    assert proposal.status == ProposalStatus.APPROVED
