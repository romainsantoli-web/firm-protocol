"""Tests for firm.core.prediction — Prediction Market Engine."""

import time

import pytest

from firm.core.prediction import (
    CALIBRATION_INITIAL,
    CALIBRATION_MAX,
    CALIBRATION_MIN,
    MarketStatus,
    Position,
    PositionSide,
    PredictionEngine,
    PredictionMarket,
    PredictionSettlement,
)
from firm.core.types import AgentId

# ── Market Creation ──────────────────────────────────────────────────────────


class TestCreateMarket:
    def test_create_basic_market(self):
        engine = PredictionEngine()
        market = engine.create_market(
            question="Will feature X ship this sprint?",
            creator_id=AgentId("alice"),
        )
        assert market.question == "Will feature X ship this sprint?"
        assert market.status == MarketStatus.OPEN
        assert market.creator_id == "alice"
        assert market.total_stake == 0.0
        assert market.market_probability == 0.5

    def test_create_market_with_details(self):
        engine = PredictionEngine()
        market = engine.create_market(
            question="Will Q3 revenue exceed $10M?",
            creator_id=AgentId("bob"),
            category="finance",
            deadline_seconds=48.0 * 3600,
            description="Based on current pipeline",
            proposal_id="prop-123",
        )
        assert market.category == "finance"
        assert market.description == "Based on current pipeline"
        assert market.proposal_id == "prop-123"
        assert market.deadline > time.time()

    def test_empty_question_rejected(self):
        engine = PredictionEngine()
        with pytest.raises(ValueError, match="empty"):
            engine.create_market(question="  ", creator_id=AgentId("a"))

    def test_get_open_markets(self):
        engine = PredictionEngine()
        engine.create_market("Q1?", AgentId("a"))
        engine.create_market("Q2?", AgentId("a"))
        assert len(engine.get_open_markets()) == 2

    def test_get_markets_for_proposal(self):
        engine = PredictionEngine()
        engine.create_market("Q1?", AgentId("a"), proposal_id="p1")
        engine.create_market("Q2?", AgentId("a"), proposal_id="p1")
        engine.create_market("Q3?", AgentId("a"), proposal_id="p2")
        assert len(engine.get_markets_for_proposal("p1")) == 2
        assert len(engine.get_markets_for_proposal("p2")) == 1

    def test_get_market(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("a"))
        assert engine.get_market(market.id) is market
        assert engine.get_market("nonexistent") is None


# ── Taking Positions ─────────────────────────────────────────────────────────


class TestTakePosition:
    def test_take_yes_position(self):
        engine = PredictionEngine()
        market = engine.create_market("Ship it?", AgentId("creator"))
        pos = engine.take_position(
            market_id=market.id,
            agent_id=AgentId("alice"),
            side="yes",
            stake=50.0,
            probability=0.7,
            agent_authority=0.8,
        )
        assert pos.agent_id == "alice"
        assert pos.side == PositionSide.YES
        assert pos.stake == 50.0
        assert pos.probability == 0.7

    def test_take_no_position(self):
        engine = PredictionEngine()
        market = engine.create_market("Ship it?", AgentId("creator"))
        pos = engine.take_position(
            market_id=market.id,
            agent_id=AgentId("bob"),
            side="no",
            stake=20.0,
            probability=0.3,
            agent_authority=0.5,
        )
        assert pos.side == PositionSide.NO

    def test_stake_too_low(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("creator"))
        with pytest.raises(ValueError, match="below minimum"):
            engine.take_position(market.id, AgentId("a"), "yes", 0.1, 0.5, 0.5)

    def test_stake_too_high(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("creator"))
        with pytest.raises(ValueError, match="above maximum"):
            engine.take_position(market.id, AgentId("a"), "yes", 5000.0, 0.5, 0.5)

    def test_nonexistent_market(self):
        engine = PredictionEngine()
        with pytest.raises(KeyError, match="not found"):
            engine.take_position("fake-id", AgentId("a"), "yes", 10.0, 0.5, 0.5)

    def test_duplicate_position_rejected(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("c"))
        engine.take_position(market.id, AgentId("a"), "yes", 10.0, 0.5, 0.5)
        with pytest.raises(ValueError, match="already has a position"):
            engine.take_position(market.id, AgentId("a"), "no", 10.0, 0.5, 0.5)

    def test_market_probability_updates(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("c"))
        engine.take_position(market.id, AgentId("a"), "yes", 10.0, 0.9, 0.9)
        updated = engine._markets[market.id]
        assert updated.market_probability != 0.5

    def test_total_staked_accumulates(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("c"))
        engine.take_position(market.id, AgentId("a"), "yes", 10.0, 0.5, 0.5)
        engine.take_position(market.id, AgentId("b"), "no", 20.0, 0.5, 0.5)
        assert engine._markets[market.id].total_stake == 30.0

    def test_closed_market_rejects_position(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("c"))
        engine.close_market(market.id)
        with pytest.raises(ValueError, match="not open"):
            engine.take_position(market.id, AgentId("a"), "yes", 10.0, 0.5, 0.5)

    def test_probability_clamped(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("c"))
        pos = engine.take_position(market.id, AgentId("a"), "yes", 10.0, 1.5, 0.5)
        assert pos.probability <= 0.99


# ── Resolution ───────────────────────────────────────────────────────────────


class TestResolveMarket:
    def _create_market_with_positions(self, engine):
        market = engine.create_market("Will it work?", AgentId("creator"))
        engine.take_position(market.id, AgentId("alice"), "yes", 50.0, 0.8, 0.8)
        engine.take_position(market.id, AgentId("bob"), "no", 30.0, 0.3, 0.6)
        return market

    def test_resolve_yes(self):
        engine = PredictionEngine()
        market = self._create_market_with_positions(engine)
        settlements = engine.resolve(market.id, outcome=True)
        assert isinstance(settlements, list)
        assert len(settlements) == 2

    def test_resolve_no(self):
        engine = PredictionEngine()
        market = self._create_market_with_positions(engine)
        settlements = engine.resolve(market.id, outcome=False)
        bob_s = next(s for s in settlements if s.agent_id == "bob")
        assert bob_s.was_correct is True

    def test_resolve_updates_status_yes(self):
        engine = PredictionEngine()
        market = self._create_market_with_positions(engine)
        engine.resolve(market.id, outcome=True)
        assert engine._markets[market.id].status == MarketStatus.RESOLVED_YES

    def test_resolve_updates_status_no(self):
        engine = PredictionEngine()
        market = self._create_market_with_positions(engine)
        engine.resolve(market.id, outcome=False)
        assert engine._markets[market.id].status == MarketStatus.RESOLVED_NO

    def test_resolve_nonexistent_market(self):
        engine = PredictionEngine()
        with pytest.raises(KeyError, match="not found"):
            engine.resolve("fake", True)

    def test_resolve_already_resolved(self):
        engine = PredictionEngine()
        market = self._create_market_with_positions(engine)
        engine.resolve(market.id, True)
        with pytest.raises(ValueError, match="cannot be resolved"):
            engine.resolve(market.id, False)

    def test_winners_get_positive_payout(self):
        engine = PredictionEngine()
        market = self._create_market_with_positions(engine)
        settlements = engine.resolve(market.id, True)
        alice_s = next(s for s in settlements if s.agent_id == "alice")
        assert alice_s.was_correct is True
        assert alice_s.payout > 0

    def test_losers_lose_stake(self):
        engine = PredictionEngine()
        market = self._create_market_with_positions(engine)
        settlements = engine.resolve(market.id, True)
        bob_s = next(s for s in settlements if s.agent_id == "bob")
        assert bob_s.was_correct is False
        assert bob_s.payout == 0.0
        assert bob_s.profit == -bob_s.stake

    def test_brier_scores_computed(self):
        engine = PredictionEngine()
        market = self._create_market_with_positions(engine)
        settlements = engine.resolve(market.id, True)
        for s in settlements:
            assert s.brier_score >= 0.0
            assert s.brier_score <= 1.0


# ── Calibration ──────────────────────────────────────────────────────────────


class TestCalibration:
    def test_initial_calibration(self):
        engine = PredictionEngine()
        assert engine.get_calibration(AgentId("new")) == CALIBRATION_INITIAL

    def test_calibration_updates_after_resolution(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("c"))
        engine.take_position(market.id, AgentId("alice"), "yes", 10.0, 0.9, 0.8)
        engine.resolve(market.id, True)
        cal = engine.get_calibration(AgentId("alice"))
        assert cal >= CALIBRATION_MIN
        assert cal <= CALIBRATION_MAX

    def test_bad_prediction_lowers_calibration(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("c"))
        engine.take_position(market.id, AgentId("bad"), "yes", 10.0, 0.9, 0.5)
        engine.resolve(market.id, False)
        cal = engine.get_calibration(AgentId("bad"))
        assert cal < CALIBRATION_INITIAL


# ── Close / Cancel ───────────────────────────────────────────────────────────


class TestCloseCancel:
    def test_close_market(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("c"))
        closed = engine.close_market(market.id)
        assert closed.status == MarketStatus.CLOSED

    def test_close_nonexistent(self):
        engine = PredictionEngine()
        with pytest.raises(KeyError):
            engine.close_market("fake")

    def test_close_already_closed(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("c"))
        engine.close_market(market.id)
        with pytest.raises(ValueError, match="not open"):
            engine.close_market(market.id)

    def test_cancel_market_refund(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("c"))
        engine.take_position(market.id, AgentId("a"), "yes", 25.0, 0.6, 0.5)
        cancelled = engine.cancel_market(market.id)
        assert cancelled.status == MarketStatus.CANCELLED
        assert cancelled.positions[0].payout == 25.0

    def test_cancel_nonexistent(self):
        engine = PredictionEngine()
        with pytest.raises(KeyError):
            engine.cancel_market("fake")

    def test_cancel_resolved_rejected(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("c"))
        engine.resolve(market.id, True)
        with pytest.raises(ValueError, match="resolved"):
            engine.cancel_market(market.id)

    def test_close_expired_markets(self):
        engine = PredictionEngine()
        engine.create_market("Q?", AgentId("c"), deadline_seconds=0)
        closed = engine.close_expired_markets()
        assert len(closed) == 1


# ── Queries ──────────────────────────────────────────────────────────────────


class TestQueries:
    def test_get_agent_positions(self):
        engine = PredictionEngine()
        m1 = engine.create_market("Q1?", AgentId("c"))
        m2 = engine.create_market("Q2?", AgentId("c"))
        engine.take_position(m1.id, AgentId("a"), "yes", 10.0, 0.5, 0.5)
        engine.take_position(m2.id, AgentId("a"), "no", 15.0, 0.3, 0.5)
        assert len(engine.get_agent_positions(AgentId("a"))) == 2

    def test_get_agent_prediction_stats_empty(self):
        engine = PredictionEngine()
        stats = engine.get_agent_prediction_stats(AgentId("a"))
        assert stats["total_predictions"] == 0

    def test_get_agent_prediction_stats_with_data(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("c"))
        engine.take_position(market.id, AgentId("a"), "yes", 10.0, 0.5, 0.5)
        engine.resolve(market.id, True)
        stats = engine.get_agent_prediction_stats(AgentId("a"))
        assert stats["total_predictions"] == 1
        assert "accuracy" in stats

    def test_get_leaderboard(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("c"))
        engine.take_position(market.id, AgentId("a"), "yes", 10.0, 0.8, 0.5)
        engine.take_position(market.id, AgentId("b"), "no", 10.0, 0.3, 0.5)
        engine.resolve(market.id, True)
        board = engine.get_leaderboard()
        assert len(board) > 0
        assert "rank_score" in board[0]

    def test_get_stats(self):
        engine = PredictionEngine()
        engine.create_market("Q1?", AgentId("c"))
        engine.create_market("Q2?", AgentId("c"))
        stats = engine.get_stats()
        assert stats["total_markets"] == 2
        assert stats["markets_by_status"]["open"] == 2
        assert stats["total_settlements"] == 0

    def test_get_agent_settlements(self):
        engine = PredictionEngine()
        market = engine.create_market("Q?", AgentId("c"))
        engine.take_position(market.id, AgentId("a"), "yes", 10.0, 0.5, 0.5)
        engine.resolve(market.id, True)
        assert len(engine.get_agent_settlements(AgentId("a"))) == 1


# ── Data class methods ───────────────────────────────────────────────────────


class TestDataClasses:
    def test_position_to_dict(self):
        pos = Position(
            market_id="m1", agent_id=AgentId("a"), side=PositionSide.YES,
            stake=10.0, probability=0.7, agent_authority=0.5,
        )
        d = pos.to_dict()
        assert d["side"] == "yes"
        assert d["stake"] == 10.0

    def test_position_to_dict_with_brier(self):
        pos = Position(
            market_id="m1", agent_id=AgentId("a"), side=PositionSide.YES,
            stake=10.0, probability=0.7, agent_authority=0.5,
        )
        pos.brier_score = 0.09
        pos.payout = 15.0
        d = pos.to_dict()
        assert "brier_score" in d
        assert "payout" in d

    def test_market_to_dict(self):
        m = PredictionMarket(question="Q?", creator_id=AgentId("a"))
        d = m.to_dict()
        assert d["question"] == "Q?"
        assert d["market_probability"] == 0.5

    def test_settlement_to_dict(self):
        s = PredictionSettlement(
            market_id="m1", agent_id=AgentId("a"), position_id="p1",
            side=PositionSide.YES, stake=10.0, payout=15.0,
            profit=5.0, brier_score=0.04, was_correct=True,
        )
        d = s.to_dict()
        assert d["was_correct"] is True
        assert d["side"] == "yes"

    def test_market_properties(self):
        m = PredictionMarket(question="Q?", creator_id=AgentId("a"))
        m.positions.append(Position(side=PositionSide.YES, stake=10.0))
        m.positions.append(Position(side=PositionSide.NO, stake=5.0))
        assert m.total_stake == 15.0
        assert m.yes_stake == 10.0
        assert m.no_stake == 5.0

    def test_market_is_resolved(self):
        m = PredictionMarket()
        assert m.is_resolved is False
        m.status = MarketStatus.RESOLVED_YES
        assert m.is_resolved is True

    def test_position_side_enum(self):
        assert PositionSide.YES.value == "yes"
        assert PositionSide.NO.value == "no"

    def test_market_status_enum(self):
        assert MarketStatus.OPEN.value == "open"
        assert MarketStatus.CLOSED.value == "closed"
        assert MarketStatus.RESOLVED_YES.value == "resolved_yes"
        assert MarketStatus.RESOLVED_NO.value == "resolved_no"
        assert MarketStatus.CANCELLED.value == "cancelled"


# ── Edge Cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_market_with_no_positions_resolve(self):
        engine = PredictionEngine()
        market = engine.create_market("Empty market?", AgentId("c"))
        settlements = engine.resolve(market.id, True)
        assert len(settlements) == 0

    def test_open_markets_filtered_by_category(self):
        engine = PredictionEngine()
        engine.create_market("Q1?", AgentId("a"), category="tech")
        engine.create_market("Q2?", AgentId("a"), category="finance")
        assert len(engine.get_open_markets(category="tech")) == 1
