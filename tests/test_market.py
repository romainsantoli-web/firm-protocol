"""Tests for firm.core.market — Internal Market."""

import time
import pytest

from firm.core.market import (
    MarketEngine,
    MarketTask,
    MarketBid,
    Settlement,
    TaskStatus,
    BidStatus,
    MIN_BOUNTY,
    MAX_BOUNTY,
    DEFAULT_FEE_RATE,
    PRICE_EMA_ALPHA,
    MIN_AUTHORITY_TO_POST,
    MIN_AUTHORITY_TO_BID,
)
from firm.core.types import AgentId


@pytest.fixture
def engine():
    return MarketEngine()


@pytest.fixture
def engine_with_fee():
    return MarketEngine(fee_rate=0.10)


@pytest.fixture
def posted_task(engine):
    """An open task ready for bidding."""
    return engine.post_task(
        poster_id=AgentId("poster"),
        title="Build feature X",
        description="Implement the new dashboard",
        category="engineering",
        bounty=100.0,
    )


@pytest.fixture
def assigned_task(engine, posted_task):
    """A task with an accepted bid (ASSIGNED state)."""
    bid = engine.place_bid(
        task_id=posted_task.id,
        bidder_id=AgentId("worker"),
        bidder_authority=0.7,
        amount=80.0,
        pitch="I have experience",
    )
    engine.accept_bid(posted_task.id, bid.id)
    return posted_task


# ── Task Posting ─────────────────────────────────────────────────────────────


class TestPostTask:
    def test_post_task(self, engine):
        task = engine.post_task(
            poster_id=AgentId("alice"),
            title="Test task",
            bounty=50.0,
        )
        assert task.title == "Test task"
        assert task.bounty == 50.0
        assert task.status == TaskStatus.OPEN
        assert task.poster_id == AgentId("alice")

    def test_post_task_with_details(self, engine):
        task = engine.post_task(
            poster_id=AgentId("alice"),
            title="Complex task",
            description="Very detailed",
            category="research",
            bounty=500.0,
            deadline_seconds=3600,
            metadata={"priority": "high"},
        )
        assert task.category == "research"
        assert task.metadata == {"priority": "high"}
        assert task.deadline > time.time()

    def test_bounty_below_minimum(self, engine):
        with pytest.raises(ValueError, match="below minimum"):
            engine.post_task(
                poster_id=AgentId("alice"),
                title="Cheap",
                bounty=0.5,
            )

    def test_bounty_above_maximum(self, engine):
        with pytest.raises(ValueError, match="above maximum"):
            engine.post_task(
                poster_id=AgentId("alice"),
                title="Expensive",
                bounty=20_000.0,
            )

    def test_task_to_dict(self, engine, posted_task):
        d = posted_task.to_dict()
        assert d["title"] == "Build feature X"
        assert d["status"] == "open"
        assert d["bounty"] == 100.0


# ── Bidding ──────────────────────────────────────────────────────────────────


class TestBidding:
    def test_place_bid(self, engine, posted_task):
        bid = engine.place_bid(
            task_id=posted_task.id,
            bidder_id=AgentId("bob"),
            bidder_authority=0.6,
            amount=80.0,
            pitch="I'm qualified",
        )
        assert bid.amount == 80.0
        assert bid.status == BidStatus.PENDING
        assert len(posted_task.bids) == 1

    def test_bid_defaults_to_full_bounty(self, engine, posted_task):
        bid = engine.place_bid(
            task_id=posted_task.id,
            bidder_id=AgentId("bob"),
            bidder_authority=0.5,
        )
        assert bid.amount == posted_task.bounty

    def test_self_bid_rejected(self, engine, posted_task):
        with pytest.raises(ValueError, match="Cannot bid on your own"):
            engine.place_bid(
                task_id=posted_task.id,
                bidder_id=AgentId("poster"),
                bidder_authority=0.5,
            )

    def test_duplicate_bid_rejected(self, engine, posted_task):
        engine.place_bid(
            task_id=posted_task.id,
            bidder_id=AgentId("bob"),
            bidder_authority=0.5,
        )
        with pytest.raises(ValueError, match="already has a pending bid"):
            engine.place_bid(
                task_id=posted_task.id,
                bidder_id=AgentId("bob"),
                bidder_authority=0.5,
            )

    def test_bid_exceeds_bounty(self, engine, posted_task):
        with pytest.raises(ValueError, match="exceeds bounty"):
            engine.place_bid(
                task_id=posted_task.id,
                bidder_id=AgentId("bob"),
                bidder_authority=0.5,
                amount=200.0,
            )

    def test_negative_bid_rejected(self, engine, posted_task):
        with pytest.raises(ValueError, match="must be positive"):
            engine.place_bid(
                task_id=posted_task.id,
                bidder_id=AgentId("bob"),
                bidder_authority=0.5,
                amount=0.0,
            )

    def test_bid_on_nonexistent_task(self, engine):
        with pytest.raises(KeyError, match="not found"):
            engine.place_bid(
                task_id="bogus",
                bidder_id=AgentId("bob"),
                bidder_authority=0.5,
            )

    def test_bid_on_non_open_task(self, engine, assigned_task):
        with pytest.raises(ValueError, match="not open"):
            engine.place_bid(
                task_id=assigned_task.id,
                bidder_id=AgentId("charlie"),
                bidder_authority=0.5,
            )

    def test_bid_score(self):
        bid = MarketBid(
            bidder_id=AgentId("bob"),
            amount=50.0,
            bidder_authority=0.8,
        )
        assert bid.score == pytest.approx(0.016, abs=0.001)

    def test_bid_score_zero_amount(self):
        bid = MarketBid(amount=0.0)
        assert bid.score == 0.0


# ── Accept Bid ───────────────────────────────────────────────────────────────


class TestAcceptBid:
    def test_accept_bid(self, engine, posted_task):
        b1 = engine.place_bid(
            task_id=posted_task.id,
            bidder_id=AgentId("bob"),
            bidder_authority=0.7,
            amount=80.0,
        )
        b2 = engine.place_bid(
            task_id=posted_task.id,
            bidder_id=AgentId("charlie"),
            bidder_authority=0.5,
            amount=90.0,
        )
        task = engine.accept_bid(posted_task.id, b1.id)
        assert task.status == TaskStatus.ASSIGNED
        assert task.assigned_to == AgentId("bob")
        assert b1.status == BidStatus.ACCEPTED
        assert b2.status == BidStatus.REJECTED

    def test_accept_nonexistent_bid(self, engine, posted_task):
        with pytest.raises(KeyError, match="Bid .* not found"):
            engine.accept_bid(posted_task.id, "bogus-bid")

    def test_accept_on_non_open_task(self, engine, assigned_task):
        bid_id = assigned_task.bids[0].id
        with pytest.raises(ValueError, match="not open"):
            engine.accept_bid(assigned_task.id, bid_id)


# ── Withdraw Bid ─────────────────────────────────────────────────────────────


class TestWithdrawBid:
    def test_withdraw_bid(self, engine, posted_task):
        bid = engine.place_bid(
            task_id=posted_task.id,
            bidder_id=AgentId("bob"),
            bidder_authority=0.5,
        )
        withdrawn = engine.withdraw_bid(posted_task.id, bid.id)
        assert withdrawn.status == BidStatus.WITHDRAWN

    def test_withdraw_non_pending(self, engine, assigned_task):
        # The accepted bid is no longer PENDING
        accepted_bid = next(
            b for b in assigned_task.bids if b.status == BidStatus.ACCEPTED
        )
        with pytest.raises(ValueError, match="not pending"):
            engine.withdraw_bid(assigned_task.id, accepted_bid.id)


# ── Settlement ───────────────────────────────────────────────────────────────


class TestSettlement:
    def test_complete_task(self, engine, assigned_task):
        settlement = engine.complete_task(assigned_task.id)
        assert settlement.amount == 80.0  # No fee (default 0%)
        assert settlement.fee == 0.0
        assert assigned_task.status == TaskStatus.COMPLETED

    def test_complete_task_with_fee(self, engine_with_fee):
        task = engine_with_fee.post_task(
            poster_id=AgentId("poster"),
            title="Paid task",
            bounty=100.0,
        )
        bid = engine_with_fee.place_bid(
            task_id=task.id,
            bidder_id=AgentId("worker"),
            bidder_authority=0.7,
            amount=100.0,
        )
        engine_with_fee.accept_bid(task.id, bid.id)
        settlement = engine_with_fee.complete_task(task.id)
        assert settlement.fee == pytest.approx(10.0)
        assert settlement.amount == pytest.approx(90.0)
        assert engine_with_fee.commons_pool == pytest.approx(10.0)

    def test_complete_non_assigned(self, engine, posted_task):
        with pytest.raises(ValueError, match="must be ASSIGNED"):
            engine.complete_task(posted_task.id)

    def test_fail_task(self, engine, assigned_task):
        settlement = engine.fail_task(assigned_task.id, reason="Missed deadline")
        assert settlement.amount == 0.0
        assert assigned_task.status == TaskStatus.FAILED

    def test_fail_task_with_fee(self, engine_with_fee):
        task = engine_with_fee.post_task(
            poster_id=AgentId("poster"),
            title="Failed task",
            bounty=200.0,
        )
        bid = engine_with_fee.place_bid(
            task_id=task.id,
            bidder_id=AgentId("worker"),
            bidder_authority=0.5,
            amount=200.0,
        )
        engine_with_fee.accept_bid(task.id, bid.id)
        settlement = engine_with_fee.fail_task(task.id)
        # Half fee on failure: 200 * 0.10 * 0.5 = 10.0
        assert settlement.fee == pytest.approx(10.0)
        assert settlement.amount == 0.0

    def test_settlement_to_dict(self, engine, assigned_task):
        settlement = engine.complete_task(assigned_task.id)
        d = settlement.to_dict()
        assert d["from_agent"] == AgentId("poster")
        assert d["to_agent"] == AgentId("worker")


# ── Cancel ───────────────────────────────────────────────────────────────────


class TestCancel:
    def test_cancel_task(self, engine, posted_task):
        engine.place_bid(
            task_id=posted_task.id,
            bidder_id=AgentId("bob"),
            bidder_authority=0.5,
        )
        cancelled = engine.cancel_task(posted_task.id, AgentId("poster"))
        assert cancelled.status == TaskStatus.CANCELLED
        # All pending bids rejected
        assert all(b.status == BidStatus.REJECTED for b in cancelled.bids)

    def test_cancel_by_non_poster(self, engine, posted_task):
        with pytest.raises(PermissionError, match="Only the poster"):
            engine.cancel_task(posted_task.id, AgentId("intruder"))

    def test_cancel_assigned_task(self, engine, assigned_task):
        with pytest.raises(ValueError, match="OPEN"):
            engine.cancel_task(assigned_task.id, AgentId("poster"))


# ── Dispute ──────────────────────────────────────────────────────────────────


class TestDispute:
    def test_dispute_completed(self, engine, assigned_task):
        engine.complete_task(assigned_task.id)
        disputed = engine.dispute_task(assigned_task.id)
        assert disputed.status == TaskStatus.DISPUTED

    def test_dispute_failed(self, engine, assigned_task):
        engine.fail_task(assigned_task.id)
        disputed = engine.dispute_task(assigned_task.id)
        assert disputed.status == TaskStatus.DISPUTED

    def test_dispute_open_task(self, engine, posted_task):
        with pytest.raises(ValueError, match="COMPLETED or FAILED"):
            engine.dispute_task(posted_task.id)


# ── Expiry ───────────────────────────────────────────────────────────────────


class TestExpiry:
    def test_expire_past_deadline(self, engine):
        task = engine.post_task(
            poster_id=AgentId("poster"),
            title="Urgent",
            bounty=10.0,
            deadline_seconds=-1,  # Already expired
        )
        engine.place_bid(
            task_id=task.id,
            bidder_id=AgentId("bob"),
            bidder_authority=0.5,
        )
        expired = engine.expire_tasks()
        assert len(expired) == 1
        assert expired[0].status == TaskStatus.EXPIRED
        assert all(b.status == BidStatus.REJECTED for b in expired[0].bids)

    def test_expire_nothing(self, engine, posted_task):
        expired = engine.expire_tasks()
        assert len(expired) == 0


# ── Price Discovery ──────────────────────────────────────────────────────────


class TestPriceDiscovery:
    def test_no_initial_price(self, engine):
        assert engine.get_market_price("engineering") is None

    def test_price_after_settlement(self, engine, assigned_task):
        engine.complete_task(assigned_task.id)
        price = engine.get_market_price("engineering")
        assert price is not None
        # First settlement: EMA = amount (80.0)
        assert price == pytest.approx(80.0)

    def test_ema_update(self, engine):
        # Simulate two completions in same category
        for amount in [100.0, 50.0]:
            task = engine.post_task(
                poster_id=AgentId("poster"),
                title="Task",
                category="dev",
                bounty=amount,
            )
            bid = engine.place_bid(
                task_id=task.id,
                bidder_id=AgentId("worker"),
                bidder_authority=0.5,
                amount=amount,
            )
            engine.accept_bid(task.id, bid.id)
            engine.complete_task(task.id)

        # EMA: 0.2 * 50 + 0.8 * 100 = 10 + 80 = 90
        assert engine.get_market_price("dev") == pytest.approx(90.0)

    def test_get_all_prices(self, engine, assigned_task):
        engine.complete_task(assigned_task.id)
        prices = engine.get_all_prices()
        assert "engineering" in prices


# ── Queries ──────────────────────────────────────────────────────────────────


class TestQueries:
    def test_get_task(self, engine, posted_task):
        assert engine.get_task(posted_task.id) is posted_task

    def test_get_task_nonexistent(self, engine):
        assert engine.get_task("bogus") is None

    def test_get_open_tasks(self, engine):
        engine.post_task(poster_id=AgentId("a"), title="T1", bounty=50.0, category="dev")
        engine.post_task(poster_id=AgentId("a"), title="T2", bounty=100.0, category="dev")
        engine.post_task(poster_id=AgentId("a"), title="T3", bounty=30.0, category="ops")
        open_tasks = engine.get_open_tasks()
        assert len(open_tasks) == 3
        # Sorted by bounty descending
        assert open_tasks[0].bounty >= open_tasks[1].bounty

    def test_get_open_tasks_by_category(self, engine):
        engine.post_task(poster_id=AgentId("a"), title="T1", bounty=10.0, category="dev")
        engine.post_task(poster_id=AgentId("a"), title="T2", bounty=10.0, category="ops")
        dev_tasks = engine.get_open_tasks(category="dev")
        assert len(dev_tasks) == 1

    def test_get_agent_tasks(self, engine):
        engine.post_task(poster_id=AgentId("alice"), title="T1", bounty=10.0)
        engine.post_task(poster_id=AgentId("alice"), title="T2", bounty=10.0)
        engine.post_task(poster_id=AgentId("bob"), title="T3", bounty=10.0)
        assert len(engine.get_agent_tasks(AgentId("alice"), as_poster=True)) == 2

    def test_get_settlements(self, engine, assigned_task):
        engine.complete_task(assigned_task.id)
        all_s = engine.get_settlements()
        assert len(all_s) == 1
        agent_s = engine.get_settlements(agent_id=AgentId("poster"))
        assert len(agent_s) == 1


class TestStats:
    def test_initial_stats(self, engine):
        stats = engine.get_stats()
        assert stats["total_tasks"] == 0
        assert stats["total_volume"] == 0.0
        assert stats["commons_pool"] == 0.0

    def test_stats_after_activity(self, engine, assigned_task):
        engine.complete_task(assigned_task.id)
        stats = engine.get_stats()
        assert stats["total_tasks"] == 1
        assert stats["total_volume"] == 80.0
        assert stats["total_settlements"] == 1

    def test_commons_pool(self, engine):
        assert engine.commons_pool == 0.0
