"""Tests for prediction-related methods on Firm runtime."""

import pytest

from firm.core.prediction import MarketStatus
from firm.runtime import Firm


def _make_firm() -> Firm:
    """Create a minimal Firm instance with two agents."""
    firm = Firm(name="test-firm")
    firm.add_agent("alice", authority=0.7, credits=500.0)
    firm.add_agent("bob", authority=0.5, credits=500.0)
    return firm


def _agent_id(firm: Firm, name: str) -> str:
    """Get agent id by name."""
    for a in firm.get_agents(active_only=False):
        if a.name == name:
            return a.id
    raise KeyError(f"Agent {name} not found")


# ── create_prediction_market ─────────────────────────────────────────────────


class TestCreatePredictionMarket:
    def test_basic_create(self):
        firm = _make_firm()
        aid = _agent_id(firm, "alice")
        market = firm.create_prediction_market(
            creator_id=aid,
            question="Ship by Friday?",
        )
        assert market.question == "Ship by Friday?"
        assert market.status == MarketStatus.OPEN

    def test_create_unknown_agent(self):
        firm = _make_firm()
        with pytest.raises(KeyError, match="not found"):
            firm.create_prediction_market("nobody", "Q?")

    def test_create_inactive_agent(self):
        firm = _make_firm()
        aid = _agent_id(firm, "alice")
        from firm.core.types import AgentStatus
        firm._agents[aid].status = AgentStatus.TERMINATED
        with pytest.raises(ValueError, match="not active"):
            firm.create_prediction_market(aid, "Q?")

    def test_ledger_entry_created(self):
        firm = _make_firm()
        aid = _agent_id(firm, "alice")
        initial_len = len(firm.ledger._entries)
        firm.create_prediction_market(aid, "Q?")
        assert len(firm.ledger._entries) > initial_len


# ── predict ──────────────────────────────────────────────────────────────────


class TestPredict:
    def test_basic_predict(self):
        firm = _make_firm()
        aid_alice = _agent_id(firm, "alice")
        aid_bob = _agent_id(firm, "bob")
        market = firm.create_prediction_market(aid_alice, "Q?")
        pos = firm.predict(aid_bob, market.id, "yes", 50.0, 0.7)
        assert pos.agent_id == aid_bob
        assert pos.stake == 50.0

    def test_credits_deducted(self):
        firm = _make_firm()
        aid_alice = _agent_id(firm, "alice")
        aid_bob = _agent_id(firm, "bob")
        market = firm.create_prediction_market(aid_alice, "Q?")
        initial = firm._agents[aid_bob].credits
        firm.predict(aid_bob, market.id, "yes", 50.0)
        assert firm._agents[aid_bob].credits == initial - 50.0

    def test_insufficient_credits(self):
        firm = _make_firm()
        aid_alice = _agent_id(firm, "alice")
        aid_bob = _agent_id(firm, "bob")
        market = firm.create_prediction_market(aid_alice, "Q?")
        with pytest.raises(ValueError, match="Insufficient credits"):
            firm.predict(aid_bob, market.id, "yes", 9999.0)

    def test_predict_unknown_agent(self):
        firm = _make_firm()
        aid_alice = _agent_id(firm, "alice")
        market = firm.create_prediction_market(aid_alice, "Q?")
        with pytest.raises(KeyError, match="not found"):
            firm.predict("nobody", market.id, "yes", 10.0)


# ── resolve_prediction ───────────────────────────────────────────────────────


class TestResolvePrediction:
    def test_basic_resolve(self):
        firm = _make_firm()
        aid_a = _agent_id(firm, "alice")
        aid_b = _agent_id(firm, "bob")
        market = firm.create_prediction_market(aid_a, "Q?")
        firm.predict(aid_a, market.id, "yes", 50.0, 0.8)
        firm.predict(aid_b, market.id, "no", 30.0, 0.3)
        settlements = firm.resolve_prediction(market.id, outcome=True)
        assert isinstance(settlements, list)
        assert len(settlements) == 2

    def test_winners_receive_credits(self):
        firm = _make_firm()
        aid_a = _agent_id(firm, "alice")
        aid_b = _agent_id(firm, "bob")
        market = firm.create_prediction_market(aid_a, "Q?")
        firm.predict(aid_a, market.id, "yes", 50.0, 0.8)
        firm.predict(aid_b, market.id, "no", 30.0, 0.3)
        alice_before = firm._agents[aid_a].credits
        firm.resolve_prediction(market.id, outcome=True)
        # Alice bet YES and outcome=YES → she should get credits
        assert firm._agents[aid_a].credits > alice_before


# ── view_predictions ─────────────────────────────────────────────────────────


class TestViewPredictions:
    def test_view_specific_market(self):
        firm = _make_firm()
        aid = _agent_id(firm, "alice")
        market = firm.create_prediction_market(aid, "Q?")
        result = firm.view_predictions(market_id=market.id)
        assert "market" in result
        assert result["market"]["question"] == "Q?"

    def test_view_agent_stats(self):
        firm = _make_firm()
        aid = _agent_id(firm, "alice")
        market = firm.create_prediction_market(aid, "Q?")
        firm.predict(aid, market.id, "yes", 10.0)
        result = firm.view_predictions(agent_id=aid)
        assert "agent_stats" in result

    def test_view_by_category(self):
        firm = _make_firm()
        aid = _agent_id(firm, "alice")
        firm.create_prediction_market(aid, "Q?", category="finance")
        result = firm.view_predictions(category="finance")
        assert result["markets_in_category"] == 1

    def test_view_all(self):
        firm = _make_firm()
        aid = _agent_id(firm, "alice")
        firm.create_prediction_market(aid, "Q1?")
        firm.create_prediction_market(aid, "Q2?")
        result = firm.view_predictions()
        assert "stats" in result
        assert "open_markets" in result

    def test_view_nonexistent_market(self):
        firm = _make_firm()
        result = firm.view_predictions(market_id="fake")
        assert "error" in result


# ── analyze_restructuring ────────────────────────────────────────────────────


class TestAnalyzeRestructuring:
    def test_basic_analyze(self):
        firm = _make_firm()
        recs = firm.analyze_restructuring()
        assert isinstance(recs, list)

    def test_analyze_with_categories(self):
        firm = _make_firm()
        cats = ["dev"] * 10 + ["sales"] * 10 + ["ops"] * 10 + ["legal"] * 10
        recs = firm.analyze_restructuring(task_categories=cats)
        assert isinstance(recs, list)
