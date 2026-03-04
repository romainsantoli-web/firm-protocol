"""
firm.core.market — Internal Market

The Market module implements an internal economy for a FIRM.
Beyond simple credit tracking, it provides:

  - **Task Bounties**: Agents post tasks with credit rewards
  - **Bidding**: Agents bid on tasks, committing to deliverables
  - **Contracts**: Binding agreements between poster and bidder
  - **Settlement**: Automatic credit transfer on completion/failure
  - **Price Discovery**: Running averages of task categories

This transforms a flat credit system into a dynamic marketplace
where agents compete for work and resources are allocated by
demonstrated competence (authority-weighted bidding).

Economic properties:
  - Credits flow from task posters to task performers
  - Failed contracts penalize both parties (poster loses bounty, bidder gets nothing)
  - Transaction fees (configurable, default 0%) accrue to the FIRM commons pool
  - Price discovery through exponential moving average per task category
"""

from __future__ import annotations

import enum
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from firm.core.types import AgentId

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

MIN_BOUNTY = 1.0             # Minimum task bounty
MAX_BOUNTY = 10_000.0        # Maximum task bounty
DEFAULT_DEADLINE = 86400.0   # 24 hours default deadline
MIN_AUTHORITY_TO_POST = 0.3  # Minimum authority to post tasks
MIN_AUTHORITY_TO_BID = 0.2   # Minimum authority to bid
DEFAULT_FEE_RATE = 0.0       # 0% transaction fee by default
PRICE_EMA_ALPHA = 0.2        # Exponential moving average weight


class TaskStatus(str, enum.Enum):
    """Lifecycle of a market task."""

    OPEN = "open"                 # Accepting bids
    ASSIGNED = "assigned"         # Contract awarded, in progress
    COMPLETED = "completed"       # Successfully delivered
    FAILED = "failed"             # Deliverable not met
    CANCELLED = "cancelled"       # Poster withdrew
    EXPIRED = "expired"           # Deadline passed without assignment
    DISPUTED = "disputed"         # Outcome contested


class BidStatus(str, enum.Enum):
    """Status of a bid on a task."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


@dataclass
class MarketBid:
    """A bid placed by an agent on a task."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_id: str = ""
    bidder_id: AgentId = field(default_factory=lambda: AgentId(""))
    amount: float = 0.0          # Requested payment (can be <= bounty)
    bidder_authority: float = 0.0
    pitch: str = ""              # Why this bidder is qualified
    status: BidStatus = BidStatus.PENDING
    created_at: float = field(default_factory=time.time)

    @property
    def score(self) -> float:
        """
        Bid score: authority-weighted cost efficiency.

        Higher authority + lower ask = better score.
        score = authority / amount  (higher is better)
        """
        if self.amount <= 0:
            return 0.0
        return self.bidder_authority / self.amount

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "bidder_id": self.bidder_id,
            "amount": round(self.amount, 2),
            "bidder_authority": round(self.bidder_authority, 4),
            "pitch": self.pitch,
            "status": self.status.value,
            "score": round(self.score, 4),
            "created_at": self.created_at,
        }


@dataclass
class MarketTask:
    """
    A task posted on the internal market.

    Task lifecycle:
        OPEN → ASSIGNED (bid accepted) → COMPLETED | FAILED
        OPEN → CANCELLED (poster withdraws)
        OPEN → EXPIRED (deadline passes)
        COMPLETED/FAILED → DISPUTED (outcome contested)
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    poster_id: AgentId = field(default_factory=lambda: AgentId(""))
    title: str = ""
    description: str = ""
    category: str = "general"
    bounty: float = 0.0
    deadline: float = 0.0        # Unix timestamp
    status: TaskStatus = TaskStatus.OPEN
    created_at: float = field(default_factory=time.time)

    # Assignment
    assigned_to: AgentId | None = None
    assigned_at: float | None = None
    accepted_bid_id: str | None = None

    # Settlement
    settled_at: float | None = None
    settlement_amount: float = 0.0

    # Bids
    bids: list[MarketBid] = field(default_factory=list)

    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "poster_id": self.poster_id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "bounty": round(self.bounty, 2),
            "deadline": self.deadline,
            "status": self.status.value,
            "assigned_to": self.assigned_to,
            "bid_count": len(self.bids),
            "settlement_amount": round(self.settlement_amount, 2),
            "created_at": self.created_at,
        }


@dataclass
class Settlement:
    """Record of a credit transfer for a completed/failed contract."""

    task_id: str
    from_agent: AgentId
    to_agent: AgentId
    amount: float
    fee: float
    reason: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "amount": round(self.amount, 2),
            "fee": round(self.fee, 2),
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class MarketEngine:
    """
    Internal marketplace for a FIRM organization.

    Manages the lifecycle of tasks, bids, contracts, and settlements.
    Provides price discovery through exponential moving averages.
    """

    def __init__(self, fee_rate: float = DEFAULT_FEE_RATE) -> None:
        self._tasks: dict[str, MarketTask] = {}
        self._settlements: list[Settlement] = []
        self._commons_pool: float = 0.0  # Accumulated transaction fees
        self._fee_rate: float = fee_rate

        # Price discovery: EMA of settlement amounts per category
        self._price_ema: dict[str, float] = {}

        # Counters
        self._total_volume: float = 0.0

    # ── Task Posting ─────────────────────────────────────────────────────

    def post_task(
        self,
        poster_id: AgentId,
        title: str,
        description: str = "",
        category: str = "general",
        bounty: float = 10.0,
        deadline_seconds: float = DEFAULT_DEADLINE,
        metadata: dict[str, Any] | None = None,
    ) -> MarketTask:
        """
        Post a new task on the market.

        The poster's credits will be escrowed (not immediately deducted)
        until settlement.

        Raises:
            ValueError: If bounty is out of range
        """
        if bounty < MIN_BOUNTY:
            raise ValueError(f"Bounty {bounty} below minimum {MIN_BOUNTY}")
        if bounty > MAX_BOUNTY:
            raise ValueError(f"Bounty {bounty} above maximum {MAX_BOUNTY}")

        task = MarketTask(
            poster_id=poster_id,
            title=title,
            description=description,
            category=category,
            bounty=bounty,
            deadline=time.time() + deadline_seconds,
            metadata=metadata or {},
        )
        self._tasks[task.id] = task

        logger.info(
            "Task '%s' posted by %s — bounty %.2f, category '%s'",
            task.title,
            poster_id,
            bounty,
            category,
        )
        return task

    # ── Bidding ──────────────────────────────────────────────────────────

    def place_bid(
        self,
        task_id: str,
        bidder_id: AgentId,
        bidder_authority: float,
        amount: float | None = None,
        pitch: str = "",
    ) -> MarketBid:
        """
        Place a bid on an open task.

        Args:
            task_id: Task to bid on
            bidder_id: Agent placing the bid
            bidder_authority: Current authority (used for scoring)
            amount: Requested payment (defaults to full bounty)
            pitch: Why this agent is qualified

        Raises:
            KeyError: If task not found
            ValueError: If task not open, agent is poster, or amount invalid
        """
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")

        if task.status != TaskStatus.OPEN:
            raise ValueError(f"Task is not open (status: {task.status.value})")

        if bidder_id == task.poster_id:
            raise ValueError("Cannot bid on your own task")

        # Check for duplicate bid
        if any(b.bidder_id == bidder_id and b.status == BidStatus.PENDING
               for b in task.bids):
            raise ValueError(f"Agent {bidder_id} already has a pending bid")

        bid_amount = amount if amount is not None else task.bounty
        if bid_amount <= 0:
            raise ValueError("Bid amount must be positive")
        if bid_amount > task.bounty:
            raise ValueError(
                f"Bid amount {bid_amount} exceeds bounty {task.bounty}"
            )

        bid = MarketBid(
            task_id=task_id,
            bidder_id=bidder_id,
            amount=bid_amount,
            bidder_authority=bidder_authority,
            pitch=pitch,
        )
        task.bids.append(bid)
        return bid

    def accept_bid(self, task_id: str, bid_id: str) -> MarketTask:
        """
        Accept a bid and assign the task.

        Transitions task from OPEN to ASSIGNED.

        Raises:
            KeyError: If task or bid not found
            ValueError: If task not open or bid not pending
        """
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")

        if task.status != TaskStatus.OPEN:
            raise ValueError(f"Task is not open (status: {task.status.value})")

        bid = next((b for b in task.bids if b.id == bid_id), None)
        if not bid:
            raise KeyError(f"Bid {bid_id} not found on task {task_id}")

        if bid.status != BidStatus.PENDING:
            raise ValueError(f"Bid is not pending (status: {bid.status.value})")

        # Accept this bid, reject all others
        bid.status = BidStatus.ACCEPTED
        for other in task.bids:
            if other.id != bid_id and other.status == BidStatus.PENDING:
                other.status = BidStatus.REJECTED

        task.status = TaskStatus.ASSIGNED
        task.assigned_to = bid.bidder_id
        task.assigned_at = time.time()
        task.accepted_bid_id = bid_id

        logger.info(
            "Task '%s' assigned to %s (bid: %.2f)",
            task.title,
            bid.bidder_id,
            bid.amount,
        )
        return task

    def withdraw_bid(self, task_id: str, bid_id: str) -> MarketBid:
        """Withdraw a pending bid."""
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")

        bid = next((b for b in task.bids if b.id == bid_id), None)
        if not bid:
            raise KeyError(f"Bid {bid_id} not found")

        if bid.status != BidStatus.PENDING:
            raise ValueError(f"Bid is not pending (status: {bid.status.value})")

        bid.status = BidStatus.WITHDRAWN
        return bid

    # ── Settlement ───────────────────────────────────────────────────────

    def complete_task(self, task_id: str) -> Settlement:
        """
        Mark a task as successfully completed.

        Credits flow: poster → bidder (minus fee).
        Fee accrues to the commons pool.

        Returns:
            Settlement record
        """
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")

        if task.status != TaskStatus.ASSIGNED:
            raise ValueError(
                f"Task must be ASSIGNED to complete (status: {task.status.value})"
            )

        if not task.assigned_to or not task.accepted_bid_id:
            raise ValueError("Task has no assignee")

        # Get the accepted bid amount
        bid = next(
            (b for b in task.bids if b.id == task.accepted_bid_id), None
        )
        if not bid:
            raise ValueError("Accepted bid not found")

        amount = bid.amount
        fee = amount * self._fee_rate
        net_amount = amount - fee

        settlement = Settlement(
            task_id=task_id,
            from_agent=task.poster_id,
            to_agent=task.assigned_to,
            amount=net_amount,
            fee=fee,
            reason=f"Task completed: {task.title}",
        )

        task.status = TaskStatus.COMPLETED
        task.settlement_amount = net_amount
        task.settled_at = time.time()
        self._settlements.append(settlement)
        self._commons_pool += fee
        self._total_volume += amount

        # Update price EMA
        self._update_price_ema(task.category, amount)

        logger.info(
            "Task '%s' completed — %.2f credits transferred (fee: %.2f)",
            task.title,
            net_amount,
            fee,
        )
        return settlement

    def fail_task(self, task_id: str, reason: str = "") -> Settlement:
        """
        Mark an assigned task as failed.

        The assigned agent gets nothing. Poster retains bounty minus half fee.
        A reduced fee still applies (cost of market usage).

        Returns:
            Settlement record (amount=0 to worker, fee to commons)
        """
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")

        if task.status != TaskStatus.ASSIGNED:
            raise ValueError(
                f"Task must be ASSIGNED to fail (status: {task.status.value})"
            )

        if not task.assigned_to:
            raise ValueError("Task has no assignee")

        # Half fee on failure
        fee = task.bounty * self._fee_rate * 0.5

        settlement = Settlement(
            task_id=task_id,
            from_agent=task.poster_id,
            to_agent=task.assigned_to,
            amount=0.0,
            fee=fee,
            reason=f"Task failed: {task.title}" + (f" — {reason}" if reason else ""),
        )

        task.status = TaskStatus.FAILED
        task.settlement_amount = 0.0
        task.settled_at = time.time()
        self._settlements.append(settlement)
        self._commons_pool += fee

        return settlement

    def cancel_task(self, task_id: str, canceller_id: AgentId) -> MarketTask:
        """
        Cancel an open task.

        Only the poster can cancel. Cannot cancel assigned tasks.
        """
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")

        if task.poster_id != canceller_id:
            raise PermissionError("Only the poster can cancel a task")

        if task.status != TaskStatus.OPEN:
            raise ValueError(
                f"Can only cancel OPEN tasks (status: {task.status.value})"
            )

        task.status = TaskStatus.CANCELLED

        # Reject all pending bids
        for bid in task.bids:
            if bid.status == BidStatus.PENDING:
                bid.status = BidStatus.REJECTED

        return task

    def dispute_task(self, task_id: str) -> MarketTask:
        """
        Mark a settled task as disputed.

        Can dispute either completed or failed tasks.
        """
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")

        if task.status not in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            raise ValueError(
                f"Can only dispute COMPLETED or FAILED tasks "
                f"(status: {task.status.value})"
            )

        task.status = TaskStatus.DISPUTED
        return task

    def expire_tasks(self) -> list[MarketTask]:
        """
        Expire all open tasks past their deadline.

        Returns list of newly expired tasks.
        """
        now = time.time()
        expired = []

        for task in self._tasks.values():
            if task.status == TaskStatus.OPEN and task.deadline < now:
                task.status = TaskStatus.EXPIRED
                for bid in task.bids:
                    if bid.status == BidStatus.PENDING:
                        bid.status = BidStatus.REJECTED
                expired.append(task)

        return expired

    # ── Price Discovery ──────────────────────────────────────────────────

    def _update_price_ema(self, category: str, amount: float) -> None:
        """Update the exponential moving average price for a category."""
        if category in self._price_ema:
            self._price_ema[category] = (
                PRICE_EMA_ALPHA * amount
                + (1 - PRICE_EMA_ALPHA) * self._price_ema[category]
            )
        else:
            self._price_ema[category] = amount

    def get_market_price(self, category: str) -> float | None:
        """Get the current EMA price for a task category."""
        return self._price_ema.get(category)

    def get_all_prices(self) -> dict[str, float]:
        """Get EMA prices for all categories with data."""
        return {k: round(v, 2) for k, v in self._price_ema.items()}

    # ── Queries ──────────────────────────────────────────────────────────

    def get_task(self, task_id: str) -> MarketTask | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def get_open_tasks(self, category: str | None = None) -> list[MarketTask]:
        """Get all open tasks, optionally filtered by category."""
        tasks = [
            t for t in self._tasks.values() if t.status == TaskStatus.OPEN
        ]
        if category:
            tasks = [t for t in tasks if t.category == category]
        return sorted(tasks, key=lambda t: t.bounty, reverse=True)

    def get_agent_tasks(
        self,
        agent_id: AgentId,
        as_poster: bool = True,
    ) -> list[MarketTask]:
        """Get tasks where agent is poster or assignee."""
        if as_poster:
            return [
                t for t in self._tasks.values() if t.poster_id == agent_id
            ]
        return [
            t for t in self._tasks.values() if t.assigned_to == agent_id
        ]

    def get_settlements(
        self,
        agent_id: AgentId | None = None,
    ) -> list[Settlement]:
        """Get settlement history, optionally filtered by agent."""
        if agent_id:
            return [
                s for s in self._settlements
                if s.from_agent == agent_id or s.to_agent == agent_id
            ]
        return list(self._settlements)

    @property
    def commons_pool(self) -> float:
        """Credits accumulated as transaction fees."""
        return self._commons_pool

    def get_stats(self) -> dict[str, Any]:
        """Get market statistics."""
        by_status: dict[str, int] = {}
        total_bids = 0
        for t in self._tasks.values():
            by_status[t.status.value] = by_status.get(t.status.value, 0) + 1
            total_bids += len(t.bids)

        return {
            "total_tasks": len(self._tasks),
            "tasks_by_status": by_status,
            "total_bids": total_bids,
            "total_settlements": len(self._settlements),
            "total_volume": round(self._total_volume, 2),
            "commons_pool": round(self._commons_pool, 2),
            "fee_rate": self._fee_rate,
            "categories_with_prices": list(self._price_ema.keys()),
        }
