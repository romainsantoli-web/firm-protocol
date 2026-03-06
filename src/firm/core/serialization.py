"""
firm.core.serialization — Save / Load FIRM State

Serialize a full FIRM organization to JSON and restore it.
This enables:
  - Persistent storage (save to disk, load on restart)
  - Snapshots for rollback or debugging
  - Migration between environments
  - Audit trail with full state history

Design choices:
  - JSON format (human-readable, portable, no binary deps)
  - Deterministic output (sorted keys)
  - Version field for forward compatibility
  - No external dependencies
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from firm.runtime import Firm

logger = logging.getLogger(__name__)

SERIALIZATION_VERSION = "1.1.0"


def save_firm(firm: "Firm", path: str | Path | None = None) -> dict[str, Any]:
    """
    Serialize a FIRM organization to a JSON-compatible dict.

    Args:
        firm: The Firm instance to serialize
        path: Optional file path to write JSON to

    Returns:
        The serialized state as a dict
    """
    state = _extract_state(firm)

    if path is not None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f, indent=2, sort_keys=True, default=str)
        logger.info("FIRM '%s' saved to %s", firm.name, path)

    return state


def load_firm(source: str | Path | dict[str, Any]) -> "Firm":
    """
    Restore a FIRM organization from saved state.

    Args:
        source: File path (str/Path) or a state dict

    Returns:
        A new Firm instance with restored state
    """

    if isinstance(source, dict):
        state = source
    else:
        p = Path(source)
        with open(p) as f:
            state = json.load(f)

    version = state.get("_version", "unknown")
    if version != SERIALIZATION_VERSION:
        logger.warning(
            "State version mismatch: expected %s, got %s",
            SERIALIZATION_VERSION, version,
        )

    return _restore_state(state)


def snapshot(firm: "Firm") -> dict[str, Any]:
    """
    Take an in-memory snapshot (no file I/O).

    Useful for before/after comparisons or rollback.
    """
    return save_firm(firm)


def diff_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """
    Compute a summary diff between two snapshots.

    Returns a dict describing what changed.
    """
    changes: dict[str, Any] = {}

    # Agent count
    b_agents = before.get("agents", {})
    a_agents = after.get("agents", {})
    if len(b_agents) != len(a_agents):
        changes["agents_added"] = len(a_agents) - len(b_agents)
    else:
        # Check authority changes
        auth_changes = []
        for aid, a_data in a_agents.items():
            b_data = b_agents.get(aid)
            if b_data and b_data.get("authority") != a_data.get("authority"):
                auth_changes.append({
                    "agent_id": aid,
                    "before": b_data.get("authority"),
                    "after": a_data.get("authority"),
                })
        if auth_changes:
            changes["authority_changes"] = auth_changes

    # Ledger growth
    b_ledger = before.get("ledger", {}).get("length", 0)
    a_ledger = after.get("ledger", {}).get("length", 0)
    if a_ledger != b_ledger:
        changes["ledger_entries_added"] = a_ledger - b_ledger

    # Memory count
    b_mem = before.get("memory", {}).get("total_entries", 0)
    a_mem = after.get("memory", {}).get("total_entries", 0)
    if a_mem != b_mem:
        changes["memories_added"] = a_mem - b_mem

    # Constitution
    b_inv = len(before.get("constitution", {}).get("invariants", []))
    a_inv = len(after.get("constitution", {}).get("invariants", []))
    if a_inv != b_inv:
        changes["invariants_changed"] = a_inv - b_inv

    changes["_snapshot_time_before"] = before.get("_saved_at", "?")
    changes["_snapshot_time_after"] = after.get("_saved_at", "?")

    return changes


# ── Internal helpers ─────────────────────────────────────────────────────────

def _extract_state(firm: "Firm") -> dict[str, Any]:
    """Extract all restorable state from a Firm."""

    agents = {}
    for agent in firm.get_agents(active_only=False):
        agents[agent.id] = {
            "id": agent.id,
            "name": agent.name,
            "authority": agent.authority,
            "credits": agent.credits,
            "status": agent.status.value,
            "roles": [r.name for r in agent.roles],
            "action_count": agent._action_count,
            "success_count": agent._success_count,
            "failure_count": agent._failure_count,
            "created_at": agent.created_at,
            "metadata": agent.metadata,
        }

    # Memory entries
    memories = []
    for entry in firm.memory._memories.values():
        memories.append({
            "id": entry.id,
            "content": entry.content,
            "tags": entry.tags,
            "contributor_id": entry.contributor_id,
            "contributor_authority": entry.contributor_authority,
            "weight": entry.weight,
            "created_at": entry.created_at,
            "reinforced_by": list(entry.reinforced_by),
            "challenged_by": list(entry.challenged_by),
            "metadata": entry.metadata,
        })

    # Ledger entries
    ledger_entries = firm.ledger.get_entries()

    # Roles
    roles = []
    for rd in firm.roles._definitions.values():
        roles.append({
            "name": rd.role.name,
            "description": rd.role.description,
            "min_authority": rd.min_authority,
            "is_critical": rd.is_critical,
            "max_holders": rd.role.max_holders,
            "permissions": rd.role.permissions,
        })

    # Constitution
    invariants = []
    for inv in firm.constitution.invariants:
        invariants.append({
            "id": inv.id,
            "description": inv.description,
            "violation_keywords": list(inv.violation_keywords),
        })

    return {
        "_version": SERIALIZATION_VERSION,
        "_saved_at": time.time(),
        "name": firm.name,
        "id": firm.id,
        "created_at": firm.created_at,
        "agents": agents,
        "ledger": {
            "entries": ledger_entries,
            "length": firm.ledger.length,
        },
        "memory": {
            "entries": memories,
            "total_entries": len(memories),
        },
        "roles": roles,
        "constitution": {
            "kill_switch_active": firm.constitution.kill_switch_active,
            "invariants": invariants,
        },
        "authority_config": {
            "learning_rate": firm.authority.learning_rate,
            "decay": firm.authority.decay,
        },
        "evolution": firm.evolution.get_stats(),
        "market": firm.market.get_stats(),
        "federation": firm.federation.get_stats(),
        "reputation": firm.reputation.get_stats(),
        "prediction": _extract_prediction_state(firm),
    }


def _extract_prediction_state(firm: "Firm") -> dict[str, Any]:
    """Extract prediction market state for serialization."""
    markets = []
    for m in firm.prediction._markets.values():
        markets.append({
            "id": m.id,
            "creator_id": m.creator_id,
            "question": m.question,
            "description": m.description,
            "category": m.category,
            "status": m.status.value,
            "aggregated_probability": m.aggregated_probability,
            "total_staked": m.total_staked,
            "created_at": m.created_at,
            "deadline": m.deadline,
            "outcome": m.outcome,
            "resolved_at": m.resolved_at,
            "linked_proposal_id": m.linked_proposal_id,
            "positions": [
                {
                    "agent_id": p.agent_id,
                    "side": p.side.value,
                    "stake": p.stake,
                    "probability": p.probability,
                    "authority_weight": p.authority_weight,
                    "timestamp": p.timestamp,
                }
                for p in m.positions
            ],
        })

    calibration = dict(firm.prediction._calibration)

    return {
        "markets": markets,
        "calibration_scores": calibration,
        "stats": firm.prediction.get_stats(),
    }


def _restore_state(state: dict[str, Any]) -> "Firm":
    """Reconstruct a Firm from saved state."""
    from firm.core.agent import Agent, AgentRole
    from firm.core.memory import MemoryEntry
    from firm.core.types import AgentId, AgentStatus
    from firm.runtime import Firm

    auth_config = state.get("authority_config", {})
    firm = Firm(
        name=state["name"],
        firm_id=state.get("id"),
        learning_rate=auth_config.get("learning_rate", 0.05),
        decay=auth_config.get("decay", 0.02),
    )
    firm.created_at = state.get("created_at", firm.created_at)

    # Restore agents
    for aid, adata in state.get("agents", {}).items():
        agent = Agent(
            id=AgentId(adata["id"]),
            name=adata["name"],
            authority=adata["authority"],
            credits=adata["credits"],
            status=AgentStatus(adata["status"]),
            created_at=adata.get("created_at", time.time()),
            metadata=adata.get("metadata", {}),
        )
        agent._action_count = adata.get("action_count", 0)
        agent._success_count = adata.get("success_count", 0)
        agent._failure_count = adata.get("failure_count", 0)
        for rn in adata.get("roles", []):
            agent.grant_role(AgentRole(name=rn))
        firm._agents[agent.id] = agent

    # Restore role definitions
    for rdata in state.get("roles", []):
        firm.define_role(
            name=rdata["name"],
            min_authority=rdata.get("min_authority", 0.4),
            is_critical=rdata.get("is_critical", False),
            max_holders=rdata.get("max_holders", 0),
            permissions=rdata.get("permissions", []),
            description=rdata.get("description", ""),
        )

    # Restore memory entries
    for mdata in state.get("memory", {}).get("entries", []):
        entry = MemoryEntry(
            id=mdata["id"],
            content=mdata["content"],
            tags=mdata["tags"],
            contributor_id=AgentId(mdata["contributor_id"]),
            contributor_authority=mdata["contributor_authority"],
            weight=mdata["weight"],
            created_at=mdata.get("created_at", time.time()),
            reinforced_by=[AgentId(x) for x in mdata.get("reinforced_by", [])],
            challenged_by=[AgentId(x) for x in mdata.get("challenged_by", [])],
            metadata=mdata.get("metadata", {}),
        )
        firm.memory._memories[entry.id] = entry
        for tag in entry.tags:
            if tag not in firm.memory._tag_index:
                firm.memory._tag_index[tag] = set()
            firm.memory._tag_index[tag].add(entry.id)

    # Restore constitution state
    const_state = state.get("constitution", {})
    if const_state.get("kill_switch_active"):
        firm.constitution.activate_kill_switch(reason="restored from saved state")

    # Restore prediction markets
    pred_state = state.get("prediction", {})
    for mdata in pred_state.get("markets", []):
        from firm.core.prediction import MarketStatus, Position, PositionSide, PredictionMarket
        positions = []
        for pdata in mdata.get("positions", []):
            positions.append(Position(
                agent_id=AgentId(pdata["agent_id"]),
                side=PositionSide(pdata["side"]),
                stake=pdata["stake"],
                probability=pdata["probability"],
                authority_weight=pdata["authority_weight"],
                timestamp=pdata["timestamp"],
            ))
        market = PredictionMarket(
            id=mdata["id"],
            creator_id=AgentId(mdata["creator_id"]),
            question=mdata["question"],
            description=mdata.get("description", ""),
            category=mdata.get("category", "general"),
            status=MarketStatus(mdata["status"]),
            aggregated_probability=mdata.get("aggregated_probability", 0.5),
            total_staked=mdata.get("total_staked", 0.0),
            created_at=mdata.get("created_at", time.time()),
            deadline=mdata.get("deadline", 0.0),
            outcome=mdata.get("outcome"),
            resolved_at=mdata.get("resolved_at"),
            linked_proposal_id=mdata.get("linked_proposal_id"),
            positions=positions,
        )
        firm.prediction._markets[market.id] = market

    # Restore calibration scores
    for aid, score in pred_state.get("calibration_scores", {}).items():
        firm.prediction._calibration[AgentId(aid)] = score

    logger.info(
        "FIRM '%s' restored: %d agents, %d memories, %d prediction markets",
        firm.name,
        len(firm._agents),
        len(firm.memory._memories),
        len(firm.prediction._markets),
    )
    return firm
