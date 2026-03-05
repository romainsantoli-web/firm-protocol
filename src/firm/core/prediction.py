"""
firm.core.prediction — Prediction Market Engine

Decision economics for FIRM: agents wager authority-backed credits
on the outcomes of decisions, creating skin-in-the-game signals
that are strictly more informative than authority-weighted voting.

Key concepts:
  - **Market**: A yes/no question with a deadline and resolution
  - **Position**: An agent's wager (amount + direction)
  - **Belief Aggregation**: √authority-weighted probability pooling
    P_agg = Σ(√w_i · p_i) / Σ(√w_i)   — anti-oligarchy
  - **Brier Score**: Calibration metric  B = (p - o)²
    where p = agent's prediction, o = outcome (0 or 1)
  - **Contrarian Payout**: profit = stake × (1/market_prob - 1)
    — rewards minority correct predictions
  - **Settlement**: Async payout after outcome is known
  - **Calibration EMA**: Rolling accuracy score per agent
    cal_n = α·(1-B) + (1-α)·cal_{n-1},  clamped ∈ [0.1, 2.0]

Economic properties:
  - Position size is bounded by agent credits
  - Losing positions lose their full stake
  - Winning contrarian positions are more profitable than consensus
  - Calibration scores feed back into authority via the Hebbian formula
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from firm.core.types import AgentId

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

MIN_STAKE = 1.0
MAX_STAKE = 1000.0
DEFAULT_MARKET_DEADLINE = 86400.0  # 24 hours
CALIBRATION_EMA_ALPHA = 0.1
CALIBRATION_MIN = 0.1
CALIBRATION_MAX = 2.0
CALIBRATION_INITIAL = 1.0


# ── Types ────────────────────────────────────────────────────────────────────

MarketId = str


class MarketStatus(str, Enum):
    """Lifecycle of a prediction market."""
    OPEN = "open"           # Accepting positions
    CLOSED = "closed"       # Deadline passed, awaiting resolution
    RESOLVED_YES = "resolved_yes"  # Outcome = YES (1)
    RESOLVED_NO = "resolved_no"    # Outcome = NO (0)
    CANCELLED = "cancelled"        # Market voided, stakes refunded


class PositionSide(str, Enum):
    """Direction of a bet."""
    YES = "yes"
    NO = "no"


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class Position:
    """An agent's wager on a prediction market."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    market_id: MarketId = ""
    agent_id: AgentId = field(default_factory=lambda: AgentId(""))
    side: PositionSide = PositionSide.YES
    stake: float = 0.0
    probability: float = 0.5  # Agent's belief at time of wager
    agent_authority: float = 0.0  # Authority at time of position
    created_at: float = field(default_factory=time.time)

    # Settlement
    payout: float = 0.0
    brier_score: float | None = None  # Computed after resolution

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "market_id": self.market_id,
            "agent_id": self.agent_id,
            "side": self.side.value,
            "stake": round(self.stake, 2),
            "probability": round(self.probability, 4),
            "agent_authority": round(self.agent_authority, 4),
            "created_at": self.created_at,
        }
        if self.brier_score is not None:
            d["brier_score"] = round(self.brier_score, 4)
            d["payout"] = round(self.payout, 2)
        return d


@dataclass
class PredictionMarket:
    """
    A yes/no prediction market.

    Lifecycle: OPEN → CLOSED → RESOLVED_YES | RESOLVED_NO | CANCELLED
    """

    id: MarketId = field(default_factory=lambda: str(uuid.uuid4())[:8])
    question: str = ""
    description: str = ""
    creator_id: AgentId = field(default_factory=lambda: AgentId(""))
    category: str = "general"
    status: MarketStatus = MarketStatus.OPEN
    created_at: float = field(default_factory=time.time)
    deadline: float = 0.0

    # Positions
    positions: list[Position] = field(default_factory=list)

    # Resolution
    resolved_at: float | None = None
    resolution_reason: str = ""

    # Linked governance proposal (for futarchy)
    proposal_id: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_stake(self) -> float:
        return sum(p.stake for p in self.positions)

    @property
    def yes_stake(self) -> float:
        return sum(p.stake for p in self.positions if p.side == PositionSide.YES)

    @property
    def no_stake(self) -> float:
        return sum(p.stake for p in self.positions if p.side == PositionSide.NO)

    @property
    def market_probability(self) -> float:
        """
        √authority-weighted belief aggregation.

        P_agg = Σ(√w_i · p_i) / Σ(√w_i)
        where w_i = agent authority, p_i = agent belief probability.

        Falls back to 0.5 if no positions exist.
        """
        if not self.positions:
            return 0.5

        numerator = 0.0
        denominator = 0.0
        for pos in self.positions:
            sqrt_w = math.sqrt(max(pos.agent_authority, 0.01))
            numerator += sqrt_w * pos.probability
            denominator += sqrt_w

        if denominator == 0:
            return 0.5
        return max(0.01, min(0.99, numerator / denominator))

    @property
    def is_resolved(self) -> bool:
        return self.status in (MarketStatus.RESOLVED_YES, MarketStatus.RESOLVED_NO)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "description": self.description[:300],
            "creator_id": self.creator_id,
            "category": self.category,
            "status": self.status.value,
            "market_probability": round(self.market_probability, 4),
            "total_stake": round(self.total_stake, 2),
            "yes_stake": round(self.yes_stake, 2),
            "no_stake": round(self.no_stake, 2),
            "position_count": len(self.positions),
            "deadline": self.deadline,
            "proposal_id": self.proposal_id,
            "created_at": self.created_at,
        }


# ── Settlement record ────────────────────────────────────────────────────────


@dataclass
class PredictionSettlement:
    """Record of a prediction market settlement."""

    market_id: MarketId
    agent_id: AgentId
    position_id: str
    side: PositionSide
    stake: float
    payout: float
    profit: float  # payout - stake (negative for losers)
    brier_score: float
    was_correct: bool
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "agent_id": self.agent_id,
            "position_id": self.position_id,
            "side": self.side.value,
            "stake": round(self.stake, 2),
            "payout": round(self.payout, 2),
            "profit": round(self.profit, 2),
            "brier_score": round(self.brier_score, 4),
            "was_correct": self.was_correct,
        }


# ── Prediction Engine ────────────────────────────────────────────────────────


class PredictionEngine:
    """
    Manages prediction markets within a FIRM.

    Provides:
      - Market creation and lifecycle
      - Position taking (authority-gated)
      - √authority-weighted belief aggregation
      - Brier-scored settlement with contrarian payout
      - Per-agent calibration EMA tracking
    """

    def __init__(self) -> None:
        self._markets: dict[MarketId, PredictionMarket] = {}
        self._settlements: list[PredictionSettlement] = []
        self._calibration: dict[AgentId, float] = {}  # agent_id → EMA score

    # ── Market lifecycle ─────────────────────────────────────────────────

    def create_market(
        self,
        question: str,
        creator_id: AgentId,
        description: str = "",
        category: str = "general",
        deadline_seconds: float = DEFAULT_MARKET_DEADLINE,
        proposal_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PredictionMarket:
        """
        Create a prediction market.

        Args:
            question: The yes/no question to predict
            creator_id: Agent creating the market
            description: Detailed description / context
            category: Market category (e.g. "strategy", "technical")
            deadline_seconds: Seconds until market closes
            proposal_id: Optional linked governance proposal (for futarchy)
            metadata: Arbitrary metadata

        Returns:
            The created PredictionMarket
        """
        if not question.strip():
            raise ValueError("Question cannot be empty")

        market = PredictionMarket(
            question=question.strip(),
            description=description.strip(),
            creator_id=creator_id,
            category=category,
            deadline=time.time() + deadline_seconds,
            proposal_id=proposal_id,
            metadata=metadata or {},
        )
        self._markets[market.id] = market

        logger.info(
            "Prediction market '%s' created by %s: %s",
            market.id, creator_id, question[:60],
        )
        return market

    def take_position(
        self,
        market_id: MarketId,
        agent_id: AgentId,
        side: str,
        stake: float,
        probability: float,
        agent_authority: float,
    ) -> Position:
        """
        Take a position (bet) on a market.

        Args:
            market_id: Market to bet on
            agent_id: Agent placing the bet
            side: "yes" or "no"
            stake: Amount of credits to wager
            probability: Agent's belief probability [0.01, 0.99]
            agent_authority: Agent's current authority

        Returns:
            The created Position

        Raises:
            KeyError: Market not found
            ValueError: Market not open, invalid parameters
        """
        market = self._markets.get(market_id)
        if not market:
            raise KeyError(f"Market {market_id} not found")
        if market.status != MarketStatus.OPEN:
            raise ValueError(f"Market is not open (status: {market.status.value})")

        # Validate inputs
        if stake < MIN_STAKE:
            raise ValueError(f"Stake {stake} below minimum {MIN_STAKE}")
        if stake > MAX_STAKE:
            raise ValueError(f"Stake {stake} above maximum {MAX_STAKE}")
        probability = max(0.01, min(0.99, probability))

        pos_side = PositionSide(side)

        # Check for duplicate position (one per agent per market)
        existing = [p for p in market.positions if p.agent_id == agent_id]
        if existing:
            raise ValueError(f"Agent {agent_id} already has a position on this market")

        position = Position(
            market_id=market_id,
            agent_id=agent_id,
            side=pos_side,
            stake=stake,
            probability=probability,
            agent_authority=agent_authority,
        )
        market.positions.append(position)

        logger.debug(
            "Position: %s bets %s on %s (stake=%.2f, p=%.2f)",
            agent_id, side, market_id, stake, probability,
        )
        return position

    def close_market(self, market_id: MarketId) -> PredictionMarket:
        """Close a market for new positions (usually at deadline)."""
        market = self._markets.get(market_id)
        if not market:
            raise KeyError(f"Market {market_id} not found")
        if market.status != MarketStatus.OPEN:
            raise ValueError(f"Market not open (status: {market.status.value})")

        market.status = MarketStatus.CLOSED
        return market

    def close_expired_markets(self) -> list[PredictionMarket]:
        """Close all markets past their deadline."""
        now = time.time()
        closed = []
        for market in self._markets.values():
            if market.status == MarketStatus.OPEN and market.deadline < now:
                market.status = MarketStatus.CLOSED
                closed.append(market)
        return closed

    # ── Resolution & Settlement ──────────────────────────────────────────

    def resolve(
        self,
        market_id: MarketId,
        outcome: bool,
        reason: str = "",
    ) -> list[PredictionSettlement]:
        """
        Resolve a market and settle all positions.

        Args:
            market_id: Market to resolve
            outcome: True = YES, False = NO
            reason: Explanation of resolution

        Returns:
            List of settlement records

        Resolution process:
          1. Set market status to RESOLVED_YES or RESOLVED_NO
          2. For each position:
             a. Compute Brier score: B = (p - o)²
             b. Determine if correct (side matches outcome)
             c. If correct: contrarian payout = stake × (1/market_prob - 1)
                If wrong: payout = 0 (lose stake)
             d. Update agent calibration EMA
        """
        market = self._markets.get(market_id)
        if not market:
            raise KeyError(f"Market {market_id} not found")
        if market.status not in (MarketStatus.OPEN, MarketStatus.CLOSED):
            raise ValueError(
                f"Market cannot be resolved (status: {market.status.value})"
            )

        # Set outcome
        market.status = MarketStatus.RESOLVED_YES if outcome else MarketStatus.RESOLVED_NO
        market.resolved_at = time.time()
        market.resolution_reason = reason
        outcome_val = 1.0 if outcome else 0.0

        # Get market probability BEFORE settlement
        market_prob = market.market_probability

        settlements: list[PredictionSettlement] = []

        for pos in market.positions:
            # Brier score: (prediction - outcome)²
            brier = (pos.probability - outcome_val) ** 2
            pos.brier_score = brier

            # Is the agent correct?
            correct = (pos.side == PositionSide.YES and outcome) or \
                      (pos.side == PositionSide.NO and not outcome)

            if correct:
                # Contrarian payout: bigger reward for minority correct
                # If agent bet YES and market_prob was low → big payout
                # If agent bet YES and market_prob was high → small payout
                if pos.side == PositionSide.YES:
                    effective_prob = market_prob
                else:
                    effective_prob = 1.0 - market_prob

                # Clamp to avoid division by zero / extreme payouts
                effective_prob = max(0.05, min(0.95, effective_prob))
                profit = pos.stake * (1.0 / effective_prob - 1.0)
                payout = pos.stake + profit
            else:
                payout = 0.0
                profit = -pos.stake

            pos.payout = payout

            settlement = PredictionSettlement(
                market_id=market_id,
                agent_id=pos.agent_id,
                position_id=pos.id,
                side=pos.side,
                stake=pos.stake,
                payout=payout,
                profit=profit,
                brier_score=brier,
                was_correct=correct,
            )
            settlements.append(settlement)
            self._settlements.append(settlement)

            # Update calibration EMA
            self._update_calibration(pos.agent_id, brier)

        logger.info(
            "Market '%s' resolved (%s) — %d positions settled, "
            "total payout %.2f",
            market_id,
            "YES" if outcome else "NO",
            len(settlements),
            sum(s.payout for s in settlements),
        )
        return settlements

    def cancel_market(
        self,
        market_id: MarketId,
        reason: str = "",
    ) -> PredictionMarket:
        """
        Cancel a market — all stakes refunded.

        Can only cancel OPEN or CLOSED (unresolved) markets.
        """
        market = self._markets.get(market_id)
        if not market:
            raise KeyError(f"Market {market_id} not found")
        if market.is_resolved:
            raise ValueError("Cannot cancel a resolved market")

        market.status = MarketStatus.CANCELLED
        market.resolution_reason = reason

        # Set payouts to refund
        for pos in market.positions:
            pos.payout = pos.stake  # Full refund

        return market

    # ── Calibration tracking ─────────────────────────────────────────────

    def _update_calibration(self, agent_id: AgentId, brier_score: float) -> None:
        """
        Update agent's calibration EMA.

        cal_n = α·(1 - B) + (1 - α)·cal_{n-1}
        Clamped to [CALIBRATION_MIN, CALIBRATION_MAX].

        Lower Brier = better calibration = higher score.
        """
        current = self._calibration.get(agent_id, CALIBRATION_INITIAL)
        accuracy = 1.0 - brier_score  # 1.0 = perfect, 0.0 = worst
        new_cal = CALIBRATION_EMA_ALPHA * accuracy + (1 - CALIBRATION_EMA_ALPHA) * current
        self._calibration[agent_id] = max(CALIBRATION_MIN, min(CALIBRATION_MAX, new_cal))

    def get_calibration(self, agent_id: AgentId) -> float:
        """Get an agent's calibration score (EMA). Default = 1.0."""
        return self._calibration.get(agent_id, CALIBRATION_INITIAL)

    # ── Queries ──────────────────────────────────────────────────────────

    def get_market(self, market_id: MarketId) -> PredictionMarket | None:
        return self._markets.get(market_id)

    def get_open_markets(self, category: str | None = None) -> list[PredictionMarket]:
        """Get all open markets, optionally filtered by category."""
        markets = [m for m in self._markets.values() if m.status == MarketStatus.OPEN]
        if category:
            markets = [m for m in markets if m.category == category]
        return sorted(markets, key=lambda m: m.total_stake, reverse=True)

    def get_agent_positions(self, agent_id: AgentId) -> list[Position]:
        """Get all positions for an agent across all markets."""
        positions: list[Position] = []
        for market in self._markets.values():
            for pos in market.positions:
                if pos.agent_id == agent_id:
                    positions.append(pos)
        return positions

    def get_agent_settlements(self, agent_id: AgentId) -> list[PredictionSettlement]:
        """Get all settlements for an agent."""
        return [s for s in self._settlements if s.agent_id == agent_id]

    def get_agent_prediction_stats(self, agent_id: AgentId) -> dict[str, Any]:
        """Get prediction accuracy stats for an agent."""
        settlements = self.get_agent_settlements(agent_id)
        if not settlements:
            return {
                "agent_id": agent_id,
                "total_predictions": 0,
                "calibration": self.get_calibration(agent_id),
            }

        correct = sum(1 for s in settlements if s.was_correct)
        total_staked = sum(s.stake for s in settlements)
        total_payout = sum(s.payout for s in settlements)
        avg_brier = sum(s.brier_score for s in settlements) / len(settlements)

        return {
            "agent_id": agent_id,
            "total_predictions": len(settlements),
            "correct_predictions": correct,
            "accuracy": round(correct / len(settlements), 4),
            "avg_brier_score": round(avg_brier, 4),
            "total_staked": round(total_staked, 2),
            "total_payout": round(total_payout, 2),
            "net_profit": round(total_payout - total_staked, 2),
            "calibration": round(self.get_calibration(agent_id), 4),
        }

    def get_leaderboard(self, top_k: int = 10) -> list[dict[str, Any]]:
        """Get prediction leaderboard sorted by calibration × accuracy."""
        agent_ids = set()
        for market in self._markets.values():
            for pos in market.positions:
                agent_ids.add(pos.agent_id)

        stats = []
        for aid in agent_ids:
            s = self.get_agent_prediction_stats(aid)
            if s["total_predictions"] > 0:
                # Rank by calibration × accuracy
                rank_score = s["calibration"] * s["accuracy"]
                s["rank_score"] = round(rank_score, 4)
                stats.append(s)

        stats.sort(key=lambda x: x["rank_score"], reverse=True)
        return stats[:top_k]

    def get_markets_for_proposal(self, proposal_id: str) -> list[PredictionMarket]:
        """Get all prediction markets linked to a governance proposal (futarchy)."""
        return [
            m for m in self._markets.values()
            if m.proposal_id == proposal_id
        ]

    def get_stats(self) -> dict[str, Any]:
        """Get prediction engine statistics."""
        by_status: dict[str, int] = {}
        total_stake = 0.0
        for m in self._markets.values():
            by_status[m.status.value] = by_status.get(m.status.value, 0) + 1
            total_stake += m.total_stake

        return {
            "total_markets": len(self._markets),
            "markets_by_status": by_status,
            "total_positions": sum(
                len(m.positions) for m in self._markets.values()
            ),
            "total_stake": round(total_stake, 2),
            "total_settlements": len(self._settlements),
            "calibrated_agents": len(self._calibration),
        }
