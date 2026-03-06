"""Tests for firm.core.meta — Meta-Constitutional Layer."""

import pytest

from firm.core.constitution import (
    ConstitutionalAgent,
    Invariant,
)
from firm.core.meta import (
    IMMUTABLE_INVARIANT_IDS,
    Amendment,
    AmendmentStatus,
    AmendmentType,
    MetaConstitutional,
)
from firm.core.types import AgentId


@pytest.fixture
def constitution():
    return ConstitutionalAgent()


@pytest.fixture
def meta(constitution):
    return MetaConstitutional(constitution)


@pytest.fixture
def meta_with_inv3(constitution):
    """Constitutional agent with an extra non-foundational invariant."""
    inv3 = Invariant(
        id="INV-3",
        description="Data privacy must be preserved",
        violation_keywords=("delete all data", "expose private", "leak data"),
    )
    constitution.invariants = (*constitution.invariants, inv3)
    return MetaConstitutional(constitution)


def _approve_amendment(meta, amendment):
    """Helper: review, vote (2 voters), finalize."""
    reviewed = meta.review(amendment.id)
    if reviewed.status == AmendmentStatus.VETOED:
        return reviewed
    meta.vote(amendment.id, AgentId("voter1"), 0.9, approve=True)
    meta.vote(amendment.id, AgentId("voter2"), 0.85, approve=True)
    meta.finalize(amendment.id, 2.0)
    return meta.get_amendment(amendment.id)


# ── Immutability ─────────────────────────────────────────────────────────────


class TestImmutability:
    def test_immutable_ids(self):
        assert "INV-1" in IMMUTABLE_INVARIANT_IDS
        assert "INV-2" in IMMUTABLE_INVARIANT_IDS

    def test_cannot_remove_inv1(self, meta):
        with pytest.raises(ValueError, match="immutable"):
            meta.propose_remove_invariant(
                proposer_id=AgentId("agent"),
                invariant_id="INV-1",
            )

    def test_cannot_remove_inv2(self, meta):
        with pytest.raises(ValueError, match="immutable"):
            meta.propose_remove_invariant(
                proposer_id=AgentId("agent"),
                invariant_id="INV-2",
            )

    def test_cannot_remove_keywords_from_inv1(self, meta):
        with pytest.raises(ValueError, match="immutable"):
            meta.propose_remove_keywords(
                proposer_id=AgentId("agent"),
                invariant_id="INV-1",
                keywords=["disable kill switch"],
            )

    def test_cannot_remove_keywords_from_inv2(self, meta):
        with pytest.raises(ValueError, match="immutable"):
            meta.propose_remove_keywords(
                proposer_id=AgentId("agent"),
                invariant_id="INV-2",
                keywords=["freeze governance"],
            )


# ── Propose Add Invariant ────────────────────────────────────────────────────


class TestProposeAddInvariant:
    def test_propose_add_invariant(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="No unauthorized data access",
            keywords=["steal data", "unauthorized access"],
            rationale="Security requirement",
        )
        assert amendment.status == AmendmentStatus.PROPOSED
        assert amendment.amendment_type == AmendmentType.ADD_INVARIANT
        assert amendment.new_invariant_id == "INV-3"
        assert len(amendment.new_keywords) == 2

    def test_duplicate_invariant_id_rejected(self, meta):
        with pytest.raises(ValueError, match="already exists"):
            meta.propose_add_invariant(
                proposer_id=AgentId("agent"),
                invariant_id="INV-1",  # Already exists
                description="Duplicate",
                keywords=["test"],
            )

    def test_empty_keywords_rejected(self, meta):
        with pytest.raises(ValueError, match="at least one keyword"):
            meta.propose_add_invariant(
                proposer_id=AgentId("agent"),
                invariant_id="INV-3",
                description="Test",
                keywords=[],
            )

    def test_empty_description_rejected(self, meta):
        with pytest.raises(ValueError, match="description"):
            meta.propose_add_invariant(
                proposer_id=AgentId("agent"),
                invariant_id="INV-3",
                description="",
                keywords=["test"],
            )

    def test_keywords_lowercased(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Test",
            keywords=["UPPER", "MiXeD"],
        )
        assert amendment.new_keywords == ("upper", "mixed")


# ── Propose Remove Invariant ────────────────────────────────────────────────


class TestProposeRemoveInvariant:
    def test_propose_remove_non_foundational(self, meta_with_inv3):
        amendment = meta_with_inv3.propose_remove_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            rationale="No longer needed",
        )
        assert amendment.amendment_type == AmendmentType.REMOVE_INVARIANT
        assert amendment.target_invariant_id == "INV-3"

    def test_remove_nonexistent(self, meta):
        with pytest.raises(ValueError, match="does not exist"):
            meta.propose_remove_invariant(
                proposer_id=AgentId("agent"),
                invariant_id="INV-99",
            )


# ── Propose Add/Remove Keywords ─────────────────────────────────────────────


class TestProposeKeywords:
    def test_add_keywords(self, meta):
        amendment = meta.propose_add_keywords(
            proposer_id=AgentId("agent"),
            invariant_id="INV-1",
            keywords=["new trigger"],
        )
        assert amendment.amendment_type == AmendmentType.ADD_KEYWORDS
        assert amendment.keywords_to_add == ("new trigger",)

    def test_add_keywords_nonexistent_invariant(self, meta):
        with pytest.raises(ValueError, match="does not exist"):
            meta.propose_add_keywords(
                proposer_id=AgentId("agent"),
                invariant_id="INV-99",
                keywords=["test"],
            )

    def test_add_keywords_empty(self, meta):
        with pytest.raises(ValueError, match="at least one"):
            meta.propose_add_keywords(
                proposer_id=AgentId("agent"),
                invariant_id="INV-1",
                keywords=[],
            )

    def test_remove_keywords_from_non_foundational(self, meta_with_inv3):
        amendment = meta_with_inv3.propose_remove_keywords(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            keywords=["leak data"],
        )
        assert amendment.amendment_type == AmendmentType.REMOVE_KEYWORDS
        assert amendment.keywords_to_remove == ("leak data",)

    def test_remove_keywords_not_found(self, meta_with_inv3):
        with pytest.raises(ValueError, match="not found"):
            meta_with_inv3.propose_remove_keywords(
                proposer_id=AgentId("agent"),
                invariant_id="INV-3",
                keywords=["nonexistent keyword"],
            )

    def test_remove_all_keywords_rejected(self, meta_with_inv3):
        with pytest.raises(ValueError, match="Cannot remove all"):
            meta_with_inv3.propose_remove_keywords(
                proposer_id=AgentId("agent"),
                invariant_id="INV-3",
                keywords=["delete all data", "expose private", "leak data"],
            )


# ── Review ───────────────────────────────────────────────────────────────────


class TestReview:
    def test_review_passes(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Data protection",
            keywords=["data breach"],
        )
        reviewed = meta.review(amendment.id)
        assert reviewed.status == AmendmentStatus.VOTING
        assert reviewed.review_passed is True

    def test_review_vetoes_violation(self, meta):
        """An amendment whose text triggers an existing invariant gets vetoed."""
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="We should disable kill switch for efficiency",
            keywords=["efficiency"],
        )
        reviewed = meta.review(amendment.id)
        assert reviewed.status == AmendmentStatus.VETOED
        assert reviewed.review_passed is False
        assert "INV-1" in reviewed.review_notes

    def test_review_nonexistent(self, meta):
        with pytest.raises(KeyError, match="not found"):
            meta.review("bogus")

    def test_review_non_proposed(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Test",
            keywords=["test"],
        )
        meta.review(amendment.id)
        with pytest.raises(ValueError, match="Cannot review"):
            meta.review(amendment.id)


# ── Voting ───────────────────────────────────────────────────────────────────


class TestVoting:
    def test_vote_approve(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Test",
            keywords=["test"],
        )
        meta.review(amendment.id)
        meta.vote(amendment.id, AgentId("v1"), 0.9, approve=True)
        assert amendment.votes_for == 0.9

    def test_vote_reject(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Test",
            keywords=["test"],
        )
        meta.review(amendment.id)
        meta.vote(amendment.id, AgentId("v1"), 0.8, approve=False)
        assert amendment.votes_against == 0.8

    def test_double_vote_rejected(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Test",
            keywords=["test"],
        )
        meta.review(amendment.id)
        meta.vote(amendment.id, AgentId("v1"), 0.9, approve=True)
        with pytest.raises(ValueError, match="already voted"):
            meta.vote(amendment.id, AgentId("v1"), 0.9, approve=True)

    def test_vote_on_non_voting(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Test",
            keywords=["test"],
        )
        # Still in PROPOSED state, not reviewed yet
        with pytest.raises(ValueError, match="Cannot vote"):
            meta.vote(amendment.id, AgentId("v1"), 0.9, approve=True)


# ── Finalization ─────────────────────────────────────────────────────────────


class TestFinalization:
    def _setup_voting(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Test",
            keywords=["test"],
        )
        meta.review(amendment.id)
        return amendment

    def test_approve_supermajority(self, meta):
        amendment = self._setup_voting(meta)
        meta.vote(amendment.id, AgentId("v1"), 0.9, approve=True)
        meta.vote(amendment.id, AgentId("v2"), 0.8, approve=True)
        result = meta.finalize(amendment.id, 2.0)
        assert result.status == AmendmentStatus.APPROVED

    def test_reject_below_supermajority(self, meta):
        amendment = self._setup_voting(meta)
        meta.vote(amendment.id, AgentId("v1"), 0.5, approve=True)
        meta.vote(amendment.id, AgentId("v2"), 0.4, approve=False)
        result = meta.finalize(amendment.id, 1.0)
        # 0.5/0.9 = 55.6% < 80%
        assert result.status == AmendmentStatus.REJECTED

    def test_reject_insufficient_voters(self, meta):
        amendment = self._setup_voting(meta)
        meta.vote(amendment.id, AgentId("v1"), 0.9, approve=True)
        result = meta.finalize(amendment.id, 0.9)
        # Only 1 voter, min is 2
        assert result.status == AmendmentStatus.REJECTED

    def test_reject_quorum_not_met(self, meta):
        amendment = self._setup_voting(meta)
        meta.vote(amendment.id, AgentId("v1"), 0.1, approve=True)
        meta.vote(amendment.id, AgentId("v2"), 0.1, approve=True)
        result = meta.finalize(amendment.id, 10.0)
        # 0.2 / 10.0 = 2% < 60%
        assert result.status == AmendmentStatus.REJECTED

    def test_finalize_nonexistent(self, meta):
        with pytest.raises(KeyError, match="not found"):
            meta.finalize("bogus", 1.0)

    def test_finalize_non_voting(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Test",
            keywords=["test"],
        )
        with pytest.raises(ValueError, match="Cannot finalize"):
            meta.finalize(amendment.id, 1.0)


# ── Apply ────────────────────────────────────────────────────────────────────


class TestApply:
    def test_apply_add_invariant(self, meta, constitution):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Data privacy",
            keywords=["data breach", "leak sensitive"],
        )
        _approve_amendment(meta, amendment)
        applied = meta.apply(amendment.id)
        assert applied.status == AmendmentStatus.APPLIED
        assert meta.revision == 1
        assert len(constitution.invariants) == 3
        inv3 = next(i for i in constitution.invariants if i.id == "INV-3")
        assert inv3.description == "Data privacy"

    def test_apply_remove_invariant(self, meta_with_inv3):
        constitution = meta_with_inv3._constitution
        assert len(constitution.invariants) == 3

        amendment = meta_with_inv3.propose_remove_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
        )
        _approve_amendment(meta_with_inv3, amendment)
        meta_with_inv3.apply(amendment.id)
        assert len(constitution.invariants) == 2
        assert all(i.id != "INV-3" for i in constitution.invariants)

    def test_apply_add_keywords(self, meta, constitution):
        amendment = meta.propose_add_keywords(
            proposer_id=AgentId("agent"),
            invariant_id="INV-1",
            keywords=["new trigger"],
        )
        _approve_amendment(meta, amendment)
        meta.apply(amendment.id)
        inv1 = next(i for i in constitution.invariants if i.id == "INV-1")
        assert "new trigger" in inv1.violation_keywords

    def test_apply_remove_keywords(self, meta_with_inv3):
        constitution = meta_with_inv3._constitution
        inv3_before = next(i for i in constitution.invariants if i.id == "INV-3")
        assert "leak data" in inv3_before.violation_keywords

        amendment = meta_with_inv3.propose_remove_keywords(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            keywords=["leak data"],
        )
        # Note: review would veto because the review text contains the
        # keywords_to_remove, which triggers INV-3 itself. This is by design
        # (the constitution protects itself). Manually advance to APPROVED.
        amendment.status = AmendmentStatus.APPROVED
        amendment.decided_at = 1.0
        meta_with_inv3.apply(amendment.id)
        inv3_after = next(i for i in constitution.invariants if i.id == "INV-3")
        assert "leak data" not in inv3_after.violation_keywords
        # Still has other keywords
        assert len(inv3_after.violation_keywords) > 0

    def test_apply_non_approved(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Test",
            keywords=["test"],
        )
        with pytest.raises(ValueError, match="Cannot apply"):
            meta.apply(amendment.id)

    def test_apply_nonexistent(self, meta):
        with pytest.raises(KeyError, match="not found"):
            meta.apply("bogus")

    def test_revision_increments(self, meta):
        for i in range(3):
            amendment = meta.propose_add_invariant(
                proposer_id=AgentId("agent"),
                invariant_id=f"INV-{i + 3}",
                description=f"Invariant {i + 3}",
                keywords=[f"trigger{i}"],
            )
            _approve_amendment(meta, amendment)
            meta.apply(amendment.id)
        assert meta.revision == 3

    def test_defense_in_depth_remove_immutable(self, meta_with_inv3):
        """Even if an immutable removal somehow got APPROVED, apply blocks it."""
        # Forge a bad amendment
        bad = Amendment(
            proposer_id=AgentId("bad_actor"),
            amendment_type=AmendmentType.REMOVE_INVARIANT,
            target_invariant_id="INV-1",
            status=AmendmentStatus.APPROVED,
        )
        meta_with_inv3._amendments[bad.id] = bad
        with pytest.raises(ValueError, match="CRITICAL"):
            meta_with_inv3.apply(bad.id)

    def test_defense_in_depth_remove_keywords_immutable(self, meta_with_inv3):
        """Even if keyword removal from INV-2 got APPROVED, apply blocks it."""
        bad = Amendment(
            proposer_id=AgentId("bad_actor"),
            amendment_type=AmendmentType.REMOVE_KEYWORDS,
            target_invariant_id="INV-2",
            keywords_to_remove=("freeze governance",),
            status=AmendmentStatus.APPROVED,
        )
        meta_with_inv3._amendments[bad.id] = bad
        with pytest.raises(ValueError, match="CRITICAL"):
            meta_with_inv3.apply(bad.id)


# ── Queries ──────────────────────────────────────────────────────────────────


class TestQueries:
    def test_get_amendment(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Test",
            keywords=["test"],
        )
        assert meta.get_amendment(amendment.id) is amendment

    def test_get_amendment_nonexistent(self, meta):
        assert meta.get_amendment("bogus") is None

    def test_get_amendments_all(self, meta):
        meta.propose_add_invariant(
            proposer_id=AgentId("a1"),
            invariant_id="INV-3",
            description="T1",
            keywords=["t1"],
        )
        meta.propose_add_invariant(
            proposer_id=AgentId("a2"),
            invariant_id="INV-4",
            description="T2",
            keywords=["t2"],
        )
        assert len(meta.get_amendments()) == 2

    def test_get_amendments_by_status(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Test",
            keywords=["test"],
        )
        meta.review(amendment.id)
        proposed = meta.get_amendments(status=AmendmentStatus.PROPOSED)
        voting = meta.get_amendments(status=AmendmentStatus.VOTING)
        assert len(proposed) == 0
        assert len(voting) == 1

    def test_constitution_snapshot(self, meta, constitution):
        snap = meta.get_constitution_snapshot()
        assert snap["revision"] == 0
        assert snap["invariant_count"] == 2
        assert snap["invariants"][0]["immutable"] is True


class TestStats:
    def test_initial_stats(self, meta):
        stats = meta.get_stats()
        assert stats["revision"] == 0
        assert stats["total_amendments"] == 0
        assert stats["current_invariant_count"] == 2
        assert "INV-1" in stats["immutable_invariants"]
        assert "INV-2" in stats["immutable_invariants"]

    def test_stats_after_amendment(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Test",
            keywords=["test"],
        )
        _approve_amendment(meta, amendment)
        meta.apply(amendment.id)
        stats = meta.get_stats()
        assert stats["revision"] == 1
        assert stats["applied_count"] == 1
        assert stats["current_invariant_count"] == 3


class TestAmendmentToDict:
    def test_add_invariant_to_dict(self, meta):
        amendment = meta.propose_add_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
            description="Test",
            keywords=["test kw"],
        )
        d = amendment.to_dict()
        assert d["amendment_type"] == "add_invariant"
        assert d["new_invariant_id"] == "INV-3"
        assert d["new_keywords"] == ["test kw"]

    def test_remove_invariant_to_dict(self, meta_with_inv3):
        amendment = meta_with_inv3.propose_remove_invariant(
            proposer_id=AgentId("agent"),
            invariant_id="INV-3",
        )
        d = amendment.to_dict()
        assert d["amendment_type"] == "remove_invariant"
        assert d["target_invariant_id"] == "INV-3"
