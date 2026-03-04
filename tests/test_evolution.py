"""Tests for firm.core.evolution — Evolution Engine."""

import time
import pytest

from firm.core.evolution import (
    EvolutionEngine,
    EvolutionProposal,
    EvolutionStatus,
    ParameterCategory,
    ParameterChange,
    PARAMETER_BOUNDS,
    MIN_AUTHORITY_TO_EVOLVE,
    EVOLUTION_APPROVAL_RATIO,
    PARAMETER_CHANGE_COOLDOWN,
)
from firm.core.types import AgentId


@pytest.fixture
def engine():
    return EvolutionEngine()


# ── Parameter Access ─────────────────────────────────────────────────────────


class TestParameterAccess:
    def test_get_parameter(self, engine):
        assert engine.get_parameter("authority", "learning_rate") == 0.05

    def test_get_parameter_unknown_category(self, engine):
        with pytest.raises(KeyError, match="Unknown category"):
            engine.get_parameter("nonexistent", "x")

    def test_get_parameter_unknown_name(self, engine):
        with pytest.raises(KeyError, match="Unknown parameter"):
            engine.get_parameter("authority", "nonexistent")

    def test_get_all_parameters(self, engine):
        params = engine.get_parameters()
        assert "authority" in params
        assert "governance" in params
        assert "economy" in params
        assert "spawn" in params
        assert "memory" in params

    def test_get_parameters_by_category(self, engine):
        params = engine.get_parameters("authority")
        assert "learning_rate" in params
        assert "threshold_propose" in params

    def test_get_parameters_unknown_category(self, engine):
        with pytest.raises(KeyError, match="Unknown category"):
            engine.get_parameters("nonexistent")

    def test_generation_starts_at_zero(self, engine):
        assert engine.generation == 0


# ── Proposal Creation ────────────────────────────────────────────────────────


class TestProposalCreation:
    def test_create_proposal(self, engine):
        proposal = engine.propose(
            proposer_id=AgentId("agent-1"),
            changes=[{
                "category": "authority",
                "parameter_name": "learning_rate",
                "new_value": 0.1,
            }],
            rationale="Faster learning",
        )
        assert proposal.status == EvolutionStatus.PROPOSED
        assert len(proposal.changes) == 1
        assert proposal.changes[0].old_value == 0.05
        assert proposal.changes[0].new_value == 0.1

    def test_proposal_multiple_changes(self, engine):
        proposal = engine.propose(
            proposer_id=AgentId("agent-1"),
            changes=[
                {"category": "authority", "parameter_name": "learning_rate", "new_value": 0.1},
                {"category": "governance", "parameter_name": "quorum_ratio", "new_value": 0.7},
            ],
        )
        assert len(proposal.changes) == 2

    def test_empty_changes_rejected(self, engine):
        with pytest.raises(ValueError, match="at least one change"):
            engine.propose(
                proposer_id=AgentId("agent-1"),
                changes=[],
            )

    def test_unknown_category_rejected(self, engine):
        with pytest.raises(ValueError, match="Unknown category"):
            engine.propose(
                proposer_id=AgentId("agent-1"),
                changes=[{"category": "bogus", "parameter_name": "x", "new_value": 1}],
            )

    def test_unknown_parameter_rejected(self, engine):
        with pytest.raises(ValueError, match="Unknown parameter"):
            engine.propose(
                proposer_id=AgentId("agent-1"),
                changes=[{"category": "authority", "parameter_name": "bogus", "new_value": 1}],
            )

    def test_missing_new_value_rejected(self, engine):
        with pytest.raises(ValueError, match="Missing new_value"):
            engine.propose(
                proposer_id=AgentId("agent-1"),
                changes=[{"category": "authority", "parameter_name": "learning_rate"}],
            )

    def test_out_of_bounds_rejected_too_low(self, engine):
        with pytest.raises(ValueError, match="outside bounds"):
            engine.propose(
                proposer_id=AgentId("agent-1"),
                changes=[{
                    "category": "authority",
                    "parameter_name": "learning_rate",
                    "new_value": 0.0001,  # Below 0.001 minimum
                }],
            )

    def test_out_of_bounds_rejected_too_high(self, engine):
        with pytest.raises(ValueError, match="outside bounds"):
            engine.propose(
                proposer_id=AgentId("agent-1"),
                changes=[{
                    "category": "authority",
                    "parameter_name": "learning_rate",
                    "new_value": 0.9,  # Above 0.5 maximum
                }],
            )

    def test_boundary_values_accepted(self, engine):
        lo, hi = PARAMETER_BOUNDS["authority"]["learning_rate"]
        proposal = engine.propose(
            proposer_id=AgentId("agent-1"),
            changes=[{
                "category": "authority",
                "parameter_name": "learning_rate",
                "new_value": lo,
            }],
        )
        assert proposal.changes[0].new_value == lo

    def test_proposal_to_dict(self, engine):
        proposal = engine.propose(
            proposer_id=AgentId("agent-1"),
            changes=[{
                "category": "authority",
                "parameter_name": "learning_rate",
                "new_value": 0.1,
            }],
        )
        d = proposal.to_dict()
        assert d["status"] == "proposed"
        assert d["changes"][0]["old_value"] == 0.05
        assert d["changes"][0]["new_value"] == 0.1


# ── Voting ───────────────────────────────────────────────────────────────────


class TestVoting:
    def test_vote_approve(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "authority", "parameter_name": "decay", "new_value": 0.03}],
        )
        engine.vote(p.id, AgentId("v1"), 0.8, approve=True)
        assert p.votes_for == 0.8
        assert p.votes_against == 0.0

    def test_vote_reject(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "authority", "parameter_name": "decay", "new_value": 0.03}],
        )
        engine.vote(p.id, AgentId("v1"), 0.7, approve=False)
        assert p.votes_against == 0.7

    def test_double_vote_rejected(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "authority", "parameter_name": "decay", "new_value": 0.03}],
        )
        engine.vote(p.id, AgentId("v1"), 0.8, approve=True)
        with pytest.raises(ValueError, match="already voted"):
            engine.vote(p.id, AgentId("v1"), 0.8, approve=True)

    def test_vote_on_nonexistent(self, engine):
        with pytest.raises(KeyError):
            engine.vote("bogus", AgentId("v1"), 0.8, approve=True)

    def test_vote_on_non_proposed(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "authority", "parameter_name": "decay", "new_value": 0.03}],
        )
        engine.vote(p.id, AgentId("v1"), 0.9, approve=True)
        engine.finalize(p.id, 0.9)  # Approves
        with pytest.raises(ValueError, match="Cannot vote"):
            engine.vote(p.id, AgentId("v2"), 0.8, approve=True)


# ── Finalization ─────────────────────────────────────────────────────────────


class TestFinalization:
    def test_approve_with_supermajority(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "economy", "parameter_name": "success_reward", "new_value": 15.0}],
        )
        engine.vote(p.id, AgentId("v1"), 0.9, approve=True)
        engine.vote(p.id, AgentId("v2"), 0.8, approve=True)
        result = engine.finalize(p.id, 2.0)
        assert result.status == EvolutionStatus.APPROVED

    def test_reject_below_supermajority(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "economy", "parameter_name": "success_reward", "new_value": 15.0}],
        )
        engine.vote(p.id, AgentId("v1"), 0.5, approve=True)
        engine.vote(p.id, AgentId("v2"), 0.8, approve=False)
        result = engine.finalize(p.id, 1.5)
        assert result.status == EvolutionStatus.REJECTED

    def test_reject_quorum_not_met(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "economy", "parameter_name": "success_reward", "new_value": 15.0}],
        )
        engine.vote(p.id, AgentId("v1"), 0.3, approve=True)
        result = engine.finalize(p.id, 10.0)  # Only 0.3/10.0 = 3%
        assert result.status == EvolutionStatus.REJECTED

    def test_finalize_nonexistent(self, engine):
        with pytest.raises(KeyError):
            engine.finalize("bogus", 1.0)

    def test_finalize_non_proposed(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "economy", "parameter_name": "success_reward", "new_value": 15.0}],
        )
        engine.vote(p.id, AgentId("v1"), 0.9, approve=True)
        engine.finalize(p.id, 0.9)
        with pytest.raises(ValueError, match="Cannot finalize"):
            engine.finalize(p.id, 0.9)


# ── Apply ────────────────────────────────────────────────────────────────────


class TestApply:
    def _approve_proposal(self, engine, changes):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=changes,
        )
        engine.vote(p.id, AgentId("v1"), 0.9, approve=True)
        engine.finalize(p.id, 0.9)
        return p

    def test_apply_changes_parameter(self, engine):
        p = self._approve_proposal(engine, [{
            "category": "authority",
            "parameter_name": "learning_rate",
            "new_value": 0.1,
        }])
        applied = engine.apply(p.id)
        assert len(applied) == 1
        assert engine.get_parameter("authority", "learning_rate") == 0.1
        assert engine.generation == 1

    def test_apply_multiple_changes(self, engine):
        p = self._approve_proposal(engine, [
            {"category": "authority", "parameter_name": "learning_rate", "new_value": 0.1},
            {"category": "governance", "parameter_name": "quorum_ratio", "new_value": 0.7},
        ])
        engine.apply(p.id)
        assert engine.get_parameter("authority", "learning_rate") == 0.1
        assert engine.get_parameter("governance", "quorum_ratio") == 0.7

    def test_apply_non_approved(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "authority", "parameter_name": "decay", "new_value": 0.03}],
        )
        with pytest.raises(ValueError, match="Cannot apply"):
            engine.apply(p.id)

    def test_apply_records_history(self, engine):
        p = self._approve_proposal(engine, [{
            "category": "authority",
            "parameter_name": "learning_rate",
            "new_value": 0.15,
        }])
        engine.apply(p.id)
        history = engine.get_history()
        assert len(history) == 1
        assert history[0]["proposal_id"] == p.id

    def test_rate_limiting(self, engine):
        # First change
        p1 = self._approve_proposal(engine, [{
            "category": "authority",
            "parameter_name": "learning_rate",
            "new_value": 0.1,
        }])
        engine.apply(p1.id)

        # Second change to same category — should be rate-limited
        p2 = self._approve_proposal(engine, [{
            "category": "authority",
            "parameter_name": "decay",
            "new_value": 0.03,
        }])
        with pytest.raises(ValueError, match="cooldown"):
            engine.apply(p2.id)


# ── Rollback ─────────────────────────────────────────────────────────────────


class TestRollback:
    def test_rollback_reverts_parameter(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "authority", "parameter_name": "learning_rate", "new_value": 0.2}],
        )
        engine.vote(p.id, AgentId("v1"), 0.9, approve=True)
        engine.finalize(p.id, 0.9)
        engine.apply(p.id)
        assert engine.get_parameter("authority", "learning_rate") == 0.2

        reverted = engine.rollback(p.id)
        assert engine.get_parameter("authority", "learning_rate") == 0.05
        assert len(reverted) == 1
        assert reverted[0].new_value == 0.05  # Rolled back to original

    def test_rollback_non_applied(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "authority", "parameter_name": "learning_rate", "new_value": 0.1}],
        )
        with pytest.raises(ValueError, match="Cannot rollback"):
            engine.rollback(p.id)

    def test_rollback_nonexistent(self, engine):
        with pytest.raises(KeyError):
            engine.rollback("bogus")

    def test_rollback_changes_status(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "authority", "parameter_name": "learning_rate", "new_value": 0.2}],
        )
        engine.vote(p.id, AgentId("v1"), 0.9, approve=True)
        engine.finalize(p.id, 0.9)
        engine.apply(p.id)
        engine.rollback(p.id)
        assert p.status == EvolutionStatus.ROLLED_BACK


# ── Queries ──────────────────────────────────────────────────────────────────


class TestQueries:
    def test_get_proposal(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "authority", "parameter_name": "decay", "new_value": 0.03}],
        )
        assert engine.get_proposal(p.id) == p

    def test_get_proposal_nonexistent(self, engine):
        assert engine.get_proposal("bogus") is None

    def test_get_proposals_all(self, engine):
        engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "authority", "parameter_name": "decay", "new_value": 0.03}],
        )
        engine.propose(
            proposer_id=AgentId("a2"),
            changes=[{"category": "economy", "parameter_name": "success_reward", "new_value": 20.0}],
        )
        assert len(engine.get_proposals()) == 2

    def test_get_proposals_by_status(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "authority", "parameter_name": "decay", "new_value": 0.03}],
        )
        engine.vote(p.id, AgentId("v1"), 0.9, approve=True)
        engine.finalize(p.id, 0.9)
        assert len(engine.get_proposals(status=EvolutionStatus.APPROVED)) == 1
        assert len(engine.get_proposals(status=EvolutionStatus.PROPOSED)) == 0


class TestStats:
    def test_initial_stats(self, engine):
        stats = engine.get_stats()
        assert stats["generation"] == 0
        assert stats["total_proposals"] == 0
        assert stats["applied_count"] == 0
        assert "authority" in stats["parameter_categories"]

    def test_stats_after_evolution(self, engine):
        p = engine.propose(
            proposer_id=AgentId("a1"),
            changes=[{"category": "authority", "parameter_name": "learning_rate", "new_value": 0.1}],
        )
        engine.vote(p.id, AgentId("v1"), 0.9, approve=True)
        engine.finalize(p.id, 0.9)
        engine.apply(p.id)
        stats = engine.get_stats()
        assert stats["generation"] == 1
        assert stats["total_proposals"] == 1
        assert stats["applied_count"] == 1


class TestParameterChange:
    def test_to_dict(self):
        pc = ParameterChange(
            category=ParameterCategory.AUTHORITY,
            parameter_name="learning_rate",
            old_value=0.05,
            new_value=0.1,
        )
        d = pc.to_dict()
        assert d["category"] == "authority"
        assert d["old_value"] == 0.05
        assert d["new_value"] == 0.1
