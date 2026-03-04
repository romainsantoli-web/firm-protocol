"""
firm.core.spawn — Spawn/Merge Engine (Layer 7)

Agent lifecycle management in FIRM:

  - **Spawn**: Create a new agent from a template or by splitting an existing one.
    The spawned agent starts with reduced authority — it must earn its place.
  - **Merge**: Combine two agents into one. Authority is averaged (weighted by
    success rate), credits are summed, roles are unioned.
  - **Split**: Divide an agent into two specialized agents, each inheriting a
    subset of roles and half the authority.

All spawn/merge operations require minimum authority from the initiator
and are recorded in the ledger.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from firm.core.agent import Agent, AgentRole
from firm.core.types import AgentId, AgentStatus

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

SPAWN_AUTHORITY_FRACTION = 0.3  # New agent starts at 30% of parent's authority
SPAWN_CREDIT_FRACTION = 0.2  # New agent gets 20% of parent's credits
MIN_AUTHORITY_TO_SPAWN = 0.6  # Must have ≥ 0.6 authority to spawn
MIN_AUTHORITY_TO_MERGE = 0.5  # Both agents must have ≥ 0.5 to merge
SPLIT_AUTHORITY_RATIO = 0.5  # Each half gets 50% of original authority


@dataclass
class SpawnEvent:
    """Record of an agent spawn operation."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    event_type: str = "spawn"  # spawn, merge, split
    parent_ids: list[AgentId] = field(default_factory=list)
    child_ids: list[AgentId] = field(default_factory=list)
    initiator_id: AgentId = AgentId("")
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "parent_ids": self.parent_ids,
            "child_ids": self.child_ids,
            "initiator_id": self.initiator_id,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class SpawnEngine:
    """
    Manages agent lifecycle: spawn, merge, split.

    All operations respect authority gates and produce
    auditable events.
    """

    def __init__(self) -> None:
        self._events: list[SpawnEvent] = []

    # ── Spawn ────────────────────────────────────────────────────────────

    def spawn(
        self,
        parent: Agent,
        name: str,
        roles: list[AgentRole] | None = None,
        authority_fraction: float = SPAWN_AUTHORITY_FRACTION,
        credit_fraction: float = SPAWN_CREDIT_FRACTION,
    ) -> Agent:
        """
        Spawn a new agent from a parent.

        The child starts with a fraction of the parent's authority and credits.
        The parent's credits are reduced by the amount given to the child.

        Args:
            parent: The agent initiating the spawn
            name: Name for the new agent
            roles: Optional roles to grant immediately
            authority_fraction: What fraction of parent authority the child gets
            credit_fraction: What fraction of parent credits the child gets

        Raises:
            PermissionError: Parent lacks authority to spawn
        """
        if parent.authority < MIN_AUTHORITY_TO_SPAWN:
            raise PermissionError(
                f"Agent '{parent.name}' authority {parent.authority:.2f} "
                f"< required {MIN_AUTHORITY_TO_SPAWN:.2f} to spawn"
            )

        if parent.status != AgentStatus.ACTIVE:
            raise PermissionError(f"Agent '{parent.name}' is not active")

        # Compute child attributes
        child_authority = parent.authority * authority_fraction
        child_credits = parent.credits * credit_fraction

        # Deduct from parent
        parent.credits -= child_credits

        # Create child
        child = Agent(
            name=name,
            authority=child_authority,
            credits=child_credits,
        )

        if roles:
            for role in roles:
                child.grant_role(role)

        event = SpawnEvent(
            event_type="spawn",
            parent_ids=[parent.id],
            child_ids=[child.id],
            initiator_id=parent.id,
            metadata={
                "child_name": name,
                "authority_fraction": authority_fraction,
                "child_authority": round(child_authority, 4),
                "child_credits": round(child_credits, 2),
            },
        )
        self._events.append(event)

        logger.info(
            "Agent '%s' spawned '%s' (authority=%.2f, credits=%.2f)",
            parent.name, name, child_authority, child_credits,
        )
        return child

    # ── Merge ────────────────────────────────────────────────────────────

    def merge(
        self,
        agent_a: Agent,
        agent_b: Agent,
        merged_name: str,
    ) -> Agent:
        """
        Merge two agents into one.

        The merged agent gets:
          - Weighted average authority (weighted by success rate)
          - Sum of credits
          - Union of roles
          - Combined action history

        Both source agents are terminated.

        Args:
            agent_a: First agent to merge
            agent_b: Second agent to merge
            merged_name: Name for the merged agent

        Raises:
            PermissionError: One or both agents lack authority
            ValueError: Agents have same ID
        """
        if agent_a.id == agent_b.id:
            raise ValueError("Cannot merge an agent with itself")

        if agent_a.authority < MIN_AUTHORITY_TO_MERGE:
            raise PermissionError(
                f"Agent '{agent_a.name}' authority {agent_a.authority:.2f} "
                f"< required {MIN_AUTHORITY_TO_MERGE:.2f} to merge"
            )
        if agent_b.authority < MIN_AUTHORITY_TO_MERGE:
            raise PermissionError(
                f"Agent '{agent_b.name}' authority {agent_b.authority:.2f} "
                f"< required {MIN_AUTHORITY_TO_MERGE:.2f} to merge"
            )

        # Weighted average authority
        total_rate = agent_a.success_rate + agent_b.success_rate
        if total_rate > 0:
            w_a = agent_a.success_rate / total_rate
            w_b = agent_b.success_rate / total_rate
        else:
            w_a = w_b = 0.5

        merged_authority = w_a * agent_a.authority + w_b * agent_b.authority
        merged_credits = agent_a.credits + agent_b.credits

        # Create merged agent
        merged = Agent(
            name=merged_name,
            authority=merged_authority,
            credits=merged_credits,
        )

        # Union of roles
        for role in agent_a.roles | agent_b.roles:
            merged.grant_role(role)

        # Combine history
        merged._action_count = agent_a._action_count + agent_b._action_count
        merged._success_count = agent_a._success_count + agent_b._success_count
        merged._failure_count = agent_a._failure_count + agent_b._failure_count

        # Terminate source agents
        agent_a.status = AgentStatus.TERMINATED
        agent_a.metadata["terminated_reason"] = f"Merged into {merged.id}"
        agent_b.status = AgentStatus.TERMINATED
        agent_b.metadata["terminated_reason"] = f"Merged into {merged.id}"

        event = SpawnEvent(
            event_type="merge",
            parent_ids=[agent_a.id, agent_b.id],
            child_ids=[merged.id],
            initiator_id=agent_a.id,
            metadata={
                "merged_name": merged_name,
                "merged_authority": round(merged_authority, 4),
                "merged_credits": round(merged_credits, 2),
                "weight_a": round(w_a, 4),
                "weight_b": round(w_b, 4),
            },
        )
        self._events.append(event)

        logger.info(
            "Agents '%s' + '%s' merged into '%s' (authority=%.2f)",
            agent_a.name, agent_b.name, merged_name, merged_authority,
        )
        return merged

    # ── Split ────────────────────────────────────────────────────────────

    def split(
        self,
        agent: Agent,
        name_a: str,
        name_b: str,
        roles_a: list[AgentRole] | None = None,
        roles_b: list[AgentRole] | None = None,
        authority_ratio: float = SPLIT_AUTHORITY_RATIO,
    ) -> tuple[Agent, Agent]:
        """
        Split an agent into two specialized agents.

        Each child gets a fraction of the parent's authority and credits.
        The parent is terminated.

        Args:
            agent: The agent to split
            name_a: Name for the first child
            name_b: Name for the second child
            roles_a: Roles for first child
            roles_b: Roles for second child
            authority_ratio: Fraction of parent authority for first child
                            (second gets 1 - ratio)

        Raises:
            PermissionError: Agent lacks authority
            ValueError: Invalid ratio
        """
        if not (0.1 <= authority_ratio <= 0.9):
            raise ValueError("Authority ratio must be between 0.1 and 0.9")

        if agent.authority < MIN_AUTHORITY_TO_SPAWN:
            raise PermissionError(
                f"Agent '{agent.name}' authority {agent.authority:.2f} "
                f"< required {MIN_AUTHORITY_TO_SPAWN:.2f} to split"
            )

        if agent.status != AgentStatus.ACTIVE:
            raise PermissionError(f"Agent '{agent.name}' is not active")

        # Create children
        child_a = Agent(
            name=name_a,
            authority=agent.authority * authority_ratio,
            credits=agent.credits * authority_ratio,
        )
        child_b = Agent(
            name=name_b,
            authority=agent.authority * (1 - authority_ratio),
            credits=agent.credits * (1 - authority_ratio),
        )

        if roles_a:
            for role in roles_a:
                child_a.grant_role(role)
        if roles_b:
            for role in roles_b:
                child_b.grant_role(role)

        # Split history proportionally
        child_a._action_count = int(agent._action_count * authority_ratio)
        child_a._success_count = int(agent._success_count * authority_ratio)
        child_a._failure_count = int(agent._failure_count * authority_ratio)
        child_b._action_count = agent._action_count - child_a._action_count
        child_b._success_count = agent._success_count - child_a._success_count
        child_b._failure_count = agent._failure_count - child_a._failure_count

        # Terminate parent
        agent.status = AgentStatus.TERMINATED
        agent.metadata["terminated_reason"] = f"Split into {child_a.id}, {child_b.id}"

        event = SpawnEvent(
            event_type="split",
            parent_ids=[agent.id],
            child_ids=[child_a.id, child_b.id],
            initiator_id=agent.id,
            metadata={
                "name_a": name_a,
                "name_b": name_b,
                "authority_ratio": authority_ratio,
            },
        )
        self._events.append(event)

        logger.info(
            "Agent '%s' split into '%s' (%.0f%%) + '%s' (%.0f%%)",
            agent.name, name_a, authority_ratio * 100,
            name_b, (1 - authority_ratio) * 100,
        )
        return child_a, child_b

    # ── Queries ──────────────────────────────────────────────────────────

    def get_events(self, event_type: str | None = None) -> list[SpawnEvent]:
        if event_type:
            return [e for e in self._events if e.event_type == event_type]
        return list(self._events)

    def get_lineage(self, agent_id: str) -> list[SpawnEvent]:
        """Get all spawn events involving this agent (as parent or child)."""
        return [
            e for e in self._events
            if agent_id in e.parent_ids or agent_id in e.child_ids
        ]

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_events": len(self._events),
            "spawns": sum(1 for e in self._events if e.event_type == "spawn"),
            "merges": sum(1 for e in self._events if e.event_type == "merge"),
            "splits": sum(1 for e in self._events if e.event_type == "split"),
        }
