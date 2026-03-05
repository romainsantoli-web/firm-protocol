"""
firm.core.memory — Collective Memory Engine (Layer 4)

Memory in FIRM is not a database — it's a living debate.

When agents contribute knowledge, it doesn't go into a static store.
It gets weighted by the contributor's authority, decays over time,
and can be challenged by other agents with competing knowledge.

High-authority agents' memories have more influence on recall.
Old memories fade unless reinforced. Conflicting memories coexist
until resolved through governance or authority-weighted consensus.

This is "memory as a debate":
  - Every memory has a weight (contributor authority × recency)
  - Recall returns the highest-weighted memories for a query
  - Agents can reinforce or challenge existing memories
  - Memories decay passively but can be refreshed
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any

from firm.core.types import AgentId

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_MEMORY_DECAY = 0.001  # Per-second passive decay
MAX_MEMORY_WEIGHT = 1.0
MIN_MEMORY_WEIGHT = 0.01  # Below this, memory is garbage-collected
REINFORCEMENT_BOOST = 0.1
CHALLENGE_PENALTY = 0.15
SIMILARITY_THRESHOLD = 0.3  # For tag-based similarity


@dataclass
class StructuredClaim:
    """A structured prediction claim linked to a memory.

    When agents make predictions, the claim is recorded in memory
    alongside evidence and counter-claims. After the prediction
    market resolves, the resolution field is updated.
    """

    claim: str = ""
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.5  # Agent's stated confidence [0, 1]
    prediction_id: str = ""  # Link to prediction market position
    market_id: str = ""  # Link to prediction market
    counter_claims: list[str] = field(default_factory=list)
    resolution: str = ""  # "correct", "incorrect", "pending"
    resolved_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "evidence": self.evidence,
            "confidence": round(self.confidence, 4),
            "prediction_id": self.prediction_id,
            "market_id": self.market_id,
            "counter_claims": self.counter_claims,
            "resolution": self.resolution or "pending",
        }


@dataclass
class MemoryEntry:
    """
    A single unit of collective knowledge.

    Each memory has:
      - Content: the actual knowledge (text)
      - Tags: semantic labels for retrieval
      - Weight: authority of contributor × recency
      - Contributor: who added it
      - Reinforcements/challenges: who agreed/disagreed
    """

    id: str = field(default_factory=lambda: hashlib.sha256(
        str(time.time()).encode() + str(id(object())).encode()
    ).hexdigest()[:12])
    content: str = ""
    tags: list[str] = field(default_factory=list)
    contributor_id: AgentId = AgentId("")
    contributor_authority: float = 0.5  # Authority at time of contribution
    weight: float = 0.5
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    reinforced_by: list[AgentId] = field(default_factory=list)
    challenged_by: list[AgentId] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    structured_claim: StructuredClaim | None = None  # Optional prediction claim

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    @property
    def net_support(self) -> int:
        """Reinforcements minus challenges."""
        return len(self.reinforced_by) - len(self.challenged_by)

    @property
    def is_contested(self) -> bool:
        """Memory is contested if challenges ≥ reinforcements."""
        return len(self.challenged_by) >= len(self.reinforced_by) and len(self.challenged_by) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "tags": self.tags,
            "contributor_id": self.contributor_id,
            "weight": round(self.weight, 4),
            "created_at": self.created_at,
            "net_support": self.net_support,
            "is_contested": self.is_contested,
            "age_seconds": round(self.age_seconds, 1),
        }


@dataclass
class MemoryConflict:
    """Represents a disagreement between memories on the same topic."""

    memory_a_id: str
    memory_b_id: str
    common_tags: list[str]
    detected_at: float = field(default_factory=time.time)
    resolved: bool = False
    resolution: str = ""  # "a_wins", "b_wins", "merged", "both_kept"

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_a_id": self.memory_a_id,
            "memory_b_id": self.memory_b_id,
            "common_tags": self.common_tags,
            "resolved": self.resolved,
            "resolution": self.resolution,
        }


class MemoryEngine:
    """
    Collective memory with authority-weighted recall.

    This is NOT a vector database. It uses tag-based retrieval
    with authority-weighted ranking. Memories are contributed by
    agents and decay over time unless reinforced.
    """

    def __init__(self, decay_rate: float = DEFAULT_MEMORY_DECAY) -> None:
        self._memories: dict[str, MemoryEntry] = {}
        self._conflicts: list[MemoryConflict] = []
        self._decay_rate = decay_rate
        self._tag_index: dict[str, set[str]] = {}  # tag -> set of memory IDs

    # ── Contribute ───────────────────────────────────────────────────────

    def contribute(
        self,
        content: str,
        tags: list[str],
        contributor_id: AgentId,
        contributor_authority: float,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry:
        """
        Add a new memory to the collective.

        The memory's initial weight is the contributor's authority.
        Higher-authority agents produce higher-weighted memories.
        """
        if not content.strip():
            raise ValueError("Memory content cannot be empty")
        if not tags:
            raise ValueError("Memory must have at least one tag")

        entry = MemoryEntry(
            content=content.strip(),
            tags=[t.lower().strip() for t in tags],
            contributor_id=contributor_id,
            contributor_authority=contributor_authority,
            weight=min(contributor_authority, MAX_MEMORY_WEIGHT),
            metadata=metadata or {},
        )

        self._memories[entry.id] = entry

        # Update tag index
        for tag in entry.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(entry.id)

        # Check for conflicts with existing memories
        self._detect_conflicts(entry)

        logger.info(
            "Memory contributed by %s: '%s...' (weight=%.2f, tags=%s)",
            contributor_id, content[:40], entry.weight, entry.tags,
        )
        return entry

    # ── Recall ───────────────────────────────────────────────────────────

    def recall(
        self,
        tags: list[str],
        top_k: int = 5,
        min_weight: float = MIN_MEMORY_WEIGHT,
        include_contested: bool = True,
    ) -> list[MemoryEntry]:
        """
        Retrieve the highest-weighted memories matching the given tags.

        Results are ranked by: weight × tag_overlap_ratio.
        Contested memories are included by default but flagged.
        """
        query_tags = {t.lower().strip() for t in tags}
        if not query_tags:
            return []

        # Find candidate memory IDs via tag index
        candidate_ids: set[str] = set()
        for tag in query_tags:
            candidate_ids.update(self._tag_index.get(tag, set()))

        # Score and rank
        scored: list[tuple[float, MemoryEntry]] = []
        for mid in candidate_ids:
            entry = self._memories.get(mid)
            if entry is None or entry.weight < min_weight:
                continue
            if not include_contested and entry.is_contested:
                continue

            # Tag overlap ratio
            entry_tags = set(entry.tags)
            overlap = len(query_tags & entry_tags) / len(query_tags | entry_tags)
            score = entry.weight * overlap

            if score > 0:
                entry.last_accessed = time.time()
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]

    # ── Reinforce / Challenge ────────────────────────────────────────────

    def reinforce(
        self,
        memory_id: str,
        agent_id: AgentId,
        agent_authority: float,
    ) -> MemoryEntry:
        """
        Reinforce a memory — signal agreement.

        Boosts the memory's weight proportional to the reinforcer's authority.
        """
        entry = self._memories.get(memory_id)
        if not entry:
            raise KeyError(f"Memory {memory_id} not found")

        if agent_id in entry.reinforced_by:
            return entry  # Already reinforced by this agent

        if agent_id in entry.challenged_by:
            # Switch from challenge to reinforce
            entry.challenged_by.remove(agent_id)

        entry.reinforced_by.append(agent_id)
        boost = REINFORCEMENT_BOOST * agent_authority
        entry.weight = min(MAX_MEMORY_WEIGHT, entry.weight + boost)

        logger.debug("Memory %s reinforced by %s (+%.4f)", memory_id, agent_id, boost)
        return entry

    def challenge(
        self,
        memory_id: str,
        agent_id: AgentId,
        agent_authority: float,
        reason: str = "",
    ) -> MemoryEntry:
        """
        Challenge a memory — signal disagreement.

        Reduces the memory's weight proportional to the challenger's authority.
        """
        entry = self._memories.get(memory_id)
        if not entry:
            raise KeyError(f"Memory {memory_id} not found")

        if agent_id in entry.challenged_by:
            return entry  # Already challenged

        if agent_id in entry.reinforced_by:
            entry.reinforced_by.remove(agent_id)

        entry.challenged_by.append(agent_id)
        penalty = CHALLENGE_PENALTY * agent_authority
        entry.weight = max(MIN_MEMORY_WEIGHT, entry.weight - penalty)

        if reason:
            entry.metadata.setdefault("challenge_reasons", []).append({
                "agent_id": agent_id,
                "reason": reason,
            })

        logger.debug("Memory %s challenged by %s (−%.4f)", memory_id, agent_id, penalty)
        return entry

    # ── Decay ────────────────────────────────────────────────────────────

    def apply_decay(self) -> list[str]:
        """
        Apply passive decay to all memories.

        Uses exponential decay: weight *= e^(−decay_rate × age).
        Memories below MIN_MEMORY_WEIGHT are garbage-collected.

        Returns list of garbage-collected memory IDs.
        """
        gc_ids = []
        now = time.time()

        for mid, entry in list(self._memories.items()):
            age = now - entry.last_accessed
            decay_factor = math.exp(-self._decay_rate * age)
            entry.weight = max(0.0, entry.weight * decay_factor)

            if entry.weight < MIN_MEMORY_WEIGHT:
                gc_ids.append(mid)

        # Garbage collect
        for mid in gc_ids:
            self._remove_memory(mid)

        if gc_ids:
            logger.info("Garbage collected %d decayed memories", len(gc_ids))

        return gc_ids

    # ── Conflict Detection ───────────────────────────────────────────────

    def _detect_conflicts(self, new_entry: MemoryEntry) -> None:
        """Check if a new memory conflicts with existing ones."""
        new_tags = set(new_entry.tags)

        for mid, existing in self._memories.items():
            if mid == new_entry.id:
                continue

            existing_tags = set(existing.tags)
            common = new_tags & existing_tags

            if not common:
                continue

            overlap = len(common) / len(new_tags | existing_tags)
            if overlap >= SIMILARITY_THRESHOLD:
                conflict = MemoryConflict(
                    memory_a_id=existing.id,
                    memory_b_id=new_entry.id,
                    common_tags=sorted(common),
                )
                self._conflicts.append(conflict)
                logger.debug(
                    "Conflict detected: %s vs %s (overlap=%.2f, tags=%s)",
                    existing.id, new_entry.id, overlap, common,
                )

    def resolve_conflict(
        self,
        conflict_index: int,
        resolution: str,
    ) -> MemoryConflict:
        """
        Resolve a memory conflict.

        resolution: "a_wins", "b_wins", "merged", "both_kept"
        """
        if conflict_index >= len(self._conflicts):
            raise IndexError(f"Conflict index {conflict_index} out of range")

        conflict = self._conflicts[conflict_index]

        if resolution == "a_wins":
            self._remove_memory(conflict.memory_b_id)
        elif resolution == "b_wins":
            self._remove_memory(conflict.memory_a_id)
        # "merged" and "both_kept" keep both

        conflict.resolved = True
        conflict.resolution = resolution
        return conflict

    # ── Queries ──────────────────────────────────────────────────────────

    def get_memory(self, memory_id: str) -> MemoryEntry | None:
        return self._memories.get(memory_id)

    def get_all(self, include_contested: bool = True) -> list[MemoryEntry]:
        memories = list(self._memories.values())
        if not include_contested:
            memories = [m for m in memories if not m.is_contested]
        return sorted(memories, key=lambda m: m.weight, reverse=True)

    def get_conflicts(self, unresolved_only: bool = True) -> list[MemoryConflict]:
        if unresolved_only:
            return [c for c in self._conflicts if not c.resolved]
        return list(self._conflicts)

    def get_agent_contributions(self, agent_id: str) -> list[MemoryEntry]:
        return [m for m in self._memories.values() if m.contributor_id == agent_id]

    def get_stats(self) -> dict[str, Any]:
        memories = list(self._memories.values())
        return {
            "total_memories": len(memories),
            "total_tags": len(self._tag_index),
            "contested_memories": sum(1 for m in memories if m.is_contested),
            "unresolved_conflicts": sum(1 for c in self._conflicts if not c.resolved),
            "avg_weight": (
                round(sum(m.weight for m in memories) / len(memories), 4)
                if memories else 0.0
            ),
        }

    # ── Internal ─────────────────────────────────────────────────────────

    def _remove_memory(self, memory_id: str) -> None:
        entry = self._memories.pop(memory_id, None)
        if entry:
            for tag in entry.tags:
                if tag in self._tag_index:
                    self._tag_index[tag].discard(memory_id)
                    if not self._tag_index[tag]:
                        del self._tag_index[tag]
