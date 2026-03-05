import pytest
from firm.core.governance import GovernanceEngine, Proposal, Vote, SimulationResult
from firm.core.types import ProposalStatus, VoteChoice
from firm.core.agent import Agent

def test_governance_engine_initialization():
    engine = GovernanceEngine()
    assert engine.quorum_ratio == 0.6
    assert engine.approval_ratio == 0.5
    assert engine.cooldown_seconds == 3600

def test_create_proposal():
    engine = GovernanceEngine()
    proposer = Agent(id="agent1", authority=0.9)
    proposal = engine.create_proposal(
        proposer=proposer,
        title="Test Proposal",
        description="This is a test proposal",
    )
    assert proposal.title == "Test Proposal"
    assert proposal.status == ProposalStatus.DRAFT

def test_create_proposal_insufficient_authority():
    engine = GovernanceEngine()
    proposer = Agent(id="agent2", authority=0.5)
    with pytest.raises(PermissionError):
        engine.create_proposal(
            proposer=proposer,
            title="Invalid Proposal",
            description="This should fail",
        )

def test_vote_on_proposal():
    engine = GovernanceEngine()
    proposer = Agent(id="agent3", authority=0.9)
    voter = Agent(id="agent4", authority=0.7)
    proposal = engine.create_proposal(
        proposer=proposer,
        title="Voting Test",
        description="Testing voting",
    )
    proposal.status = ProposalStatus.VOTING
    vote = engine.vote(
        proposal=proposal,
        voter=voter,
        choice=VoteChoice.APPROVE,
        reason="Looks good",
    )
    assert vote.choice == VoteChoice.APPROVE
    assert len(proposal.votes) == 1

def test_vote_insufficient_authority():
    engine = GovernanceEngine()
    proposer = Agent(id="agent5", authority=0.9)
    voter = Agent(id="agent6", authority=0.4)
    proposal = engine.create_proposal(
        proposer=proposer,
        title="Invalid Vote Test",
        description="Testing invalid vote",
    )
    proposal.status = ProposalStatus.VOTING
    with pytest.raises(PermissionError):
        engine.vote(
            proposal=proposal,
            voter=voter,
            choice=VoteChoice.REJECT,
            reason="Not enough authority",
        )