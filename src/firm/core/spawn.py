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
import math
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


# ── Auto-Restructuring ──────────────────────────────────────────────────────

# Thresholds for automatic restructuring decisions
AUTO_PRUNE_AUTHORITY = 0.1  # Auto-prune below this
AUTO_MERGE_SIMILARITY = 0.85  # Cosine similarity threshold for merge
TASK_ENTROPY_SPAWN_THRESHOLD = 2.0  # Shannon entropy threshold to spawn


@dataclass
class RestructureRecommendation:
    """A recommendation from the auto-restructurer."""

    action: str  # "prune", "merge", "spawn"
    reason: str
    target_agents: list[AgentId] = field(default_factory=list)
    confidence: float = 0.0  # [0, 1]
    proposed_name: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "target_agents": self.target_agents,
            "confidence": round(self.confidence, 4),
            "proposed_name": self.proposed_name,
            "metadata": self.metadata,
        }


class AutoRestructurer:
    """
    Automatically recommends organizational restructuring based on signals.

    Three mechanisms:
      - **Auto-prune**: Agents with authority < 0.1 for extended periods
      - **Auto-merge**: Agents with cosine similarity > 0.85 on roles/tags
      - **Auto-spawn**: When task entropy exceeds threshold (diverse needs)

    All recommendations go through governance — never applied automatically.
    """

    def __init__(
        self,
        prune_threshold: float = AUTO_PRUNE_AUTHORITY,
        merge_similarity: float = AUTO_MERGE_SIMILARITY,
        spawn_entropy: float = TASK_ENTROPY_SPAWN_THRESHOLD,
    ) -> None:
        self.prune_threshold = prune_threshold
        self.merge_similarity = merge_similarity
        self.spawn_entropy = spawn_entropy
        self._recommendations: list[RestructureRecommendation] = []

    def analyze(
        self,
        agents: list[Agent],
        task_categories: list[str] | None = None,
    ) -> list[RestructureRecommendation]:
        """
        Analyze the organization and produce restructuring recommendations.

        Args:
            agents: All active agents
            task_categories: Recent task categories for entropy calculation

        Returns:
            List of recommendations (each should become a governance proposal)
        """
        recs: list[RestructureRecommendation] = []

        # 1. Auto-prune: agents stuck below threshold
        recs.extend(self._check_prune(agents))

        # 2. Auto-merge: overlapping agents
        recs.extend(self._check_merge(agents))

        # 3. Auto-spawn: task diversity exceeds agent specialization
        if task_categories:
            recs.extend(self._check_spawn(agents, task_categories))

        self._recommendations.extend(recs)
        return recs

    def _check_prune(self, agents: list[Agent]) -> list[RestructureRecommendation]:
        """Identify agents that should be pruned (authority too low)."""
        recs = []
        for agent in agents:
            if not agent.is_active:
                continue
            if agent.authority < self.prune_threshold:
                recs.append(RestructureRecommendation(
                    action="prune",
                    reason=(
                        f"Agent '{agent.name}' authority ({agent.authority:.4f}) "
                        f"below threshold ({self.prune_threshold})"
                    ),
                    target_agents=[agent.id],
                    confidence=1.0 - (agent.authority / self.prune_threshold),
                ))
        return recs

    def _check_merge(self, agents: list[Agent]) -> list[RestructureRecommendation]:
        """Identify pairs of agents that should be merged (overlapping roles)."""
        recs = []
        active = [a for a in agents if a.is_active and a.roles]

        for i, a in enumerate(active):
            for b in active[i + 1:]:
                sim = self._role_cosine_similarity(a, b)
                if sim >= self.merge_similarity:
                    recs.append(RestructureRecommendation(
                        action="merge",
                        reason=(
                            f"Agents '{a.name}' and '{b.name}' have "
                            f"{sim:.2%} role overlap (threshold: {self.merge_similarity:.0%})"
                        ),
                        target_agents=[a.id, b.id],
                        confidence=sim,
                        proposed_name=f"{a.name}+{b.name}",
                    ))
        return recs

    def _check_spawn(
        self,
        agents: list[Agent],
        task_categories: list[str],
    ) -> list[RestructureRecommendation]:
        """Check if task entropy warrants spawning a new specialist."""
        if not task_categories:
            return []

        entropy = self._shannon_entropy(task_categories)
        agent_count = len([a for a in agents if a.is_active])

        # More diverse tasks than agents can cover → recommend spawn
        if entropy > self.spawn_entropy and agent_count > 0:
            # Find the most common underserved category
            counts: dict[str, int] = {}
            for cat in task_categories:
                counts[cat] = counts.get(cat, 0) + 1
            top_cat = max(counts, key=lambda k: counts[k])

            # Check if any agent has role matching this category
            covered = any(
                a.has_role(top_cat) for a in agents if a.is_active
            )

            if not covered:
                return [RestructureRecommendation(
                    action="spawn",
                    reason=(
                        f"Task entropy ({entropy:.2f}) exceeds threshold "
                        f"({self.spawn_entropy}). Top uncovered category: '{top_cat}' "
                        f"({counts[top_cat]} tasks)"
                    ),
                    confidence=min(1.0, entropy / (self.spawn_entropy * 2)),
                    proposed_name=f"{top_cat}-specialist",
                    metadata={"category": top_cat, "entropy": round(entropy, 4)},
                )]
        return []

    @staticmethod
    def _role_cosine_similarity(a: Agent, b: Agent) -> float:
        """Cosine similarity between two agents' role sets."""
        roles_a = {r.name for r in a.roles}
        roles_b = {r.name for r in b.roles}

        if not roles_a or not roles_b:
            return 0.0

        all_roles = roles_a | roles_b
        vec_a = [1.0 if r in roles_a else 0.0 for r in sorted(all_roles)]
        vec_b = [1.0 if r in roles_b else 0.0 for r in sorted(all_roles)]

        dot = sum(x * y for x, y in zip(vec_a, vec_b))
        mag_a = math.sqrt(sum(x * x for x in vec_a))
        mag_b = math.sqrt(sum(x * x for x in vec_b))

        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    @staticmethod
    def _shannon_entropy(categories: list[str]) -> float:
        """Compute Shannon entropy of task category distribution."""
        if not categories:
            return 0.0

        counts: dict[str, int] = {}
        for cat in categories:
            counts[cat] = counts.get(cat, 0) + 1

        total = len(categories)
        entropy = 0.0
        for count in counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        return entropy

    def get_recommendations(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get all recommendations."""
        return [r.to_dict() for r in self._recommendations[-limit:]]

    def get_stats(self) -> dict[str, Any]:
        by_action: dict[str, int] = {}
        for r in self._recommendations:
            by_action[r.action] = by_action.get(r.action, 0) + 1
        return {
            "total_recommendations": len(self._recommendations),
            "by_action": by_action,
        }
