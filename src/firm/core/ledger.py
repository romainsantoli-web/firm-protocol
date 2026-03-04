"""
firm.core.ledger — Responsibility Ledger (Layer 1)

Every action in a FIRM has economic consequences.
The Responsibility Ledger is an append-only, cryptographically
chained record of all decisions, outcomes, and their costs.

Key principles:
  - Append-only: no entry can be modified or deleted
  - Chained: each entry includes the hash of the previous entry
  - Economic: every action has a credit cost/reward
  - Transparent: any agent can read the full ledger
  - Auditable: the chain can be verified at any time

The ledger is the source of truth for:
  - Who decided what
  - What happened as a result
  - What it cost
  - Whether the chain is intact
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from firm.core.types import AgentId, EntryId, LedgerAction, Severity

logger = logging.getLogger(__name__)

# ── Entry ────────────────────────────────────────────────────────────────────

GENESIS_HASH = "0" * 64  # SHA-256 of nothing — the first entry's previous_hash


@dataclass
class LedgerEntry:
    """
    A single, immutable record in the Responsibility Ledger.

    Once created, an entry cannot be changed. Its hash is computed
    from its contents and the hash of the previous entry, forming
    an unbreakable chain.
    """

    id: EntryId = field(default_factory=lambda: EntryId(str(uuid.uuid4())[:12]))
    agent_id: AgentId = field(default_factory=lambda: AgentId(""))
    action: LedgerAction = LedgerAction.DECISION
    description: str = ""
    credit_delta: float = 0.0  # Positive = earned, negative = cost
    authority_at_time: float = 0.0
    outcome: str = ""  # "success", "failure", "pending"
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    previous_hash: str = GENESIS_HASH
    entry_hash: str = ""

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of this entry's content + previous hash."""
        payload = json.dumps(
            {
                "id": self.id,
                "agent_id": self.agent_id,
                "action": self.action.value,
                "description": self.description,
                "credit_delta": self.credit_delta,
                "authority_at_time": self.authority_at_time,
                "outcome": self.outcome,
                "timestamp": self.timestamp,
                "previous_hash": self.previous_hash,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def seal(self) -> None:
        """Compute and set the entry hash. Can only be called once."""
        if self.entry_hash:
            raise RuntimeError(f"Entry {self.id} is already sealed")
        self.entry_hash = self.compute_hash()

    def verify(self) -> bool:
        """Verify that the entry hash matches its contents."""
        if not self.entry_hash:
            return False
        return self.entry_hash == self.compute_hash()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "action": self.action.value,
            "description": self.description,
            "credit_delta": round(self.credit_delta, 2),
            "authority_at_time": round(self.authority_at_time, 4),
            "outcome": self.outcome,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
            "entry_hash": self.entry_hash,
        }


# ── Ledger ───────────────────────────────────────────────────────────────────


class ResponsibilityLedger:
    """
    Append-only, hash-chained ledger of all actions in a FIRM.

    The ledger enforces:
    - Immutability: entries cannot be modified after sealing
    - Chain integrity: each entry links to the previous
    - Economic tracking: credit balances are maintained
    - Full audit trail: the complete history is always available
    """

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []
        self._credit_balances: dict[str, float] = {}  # agent_id → balance

    @property
    def length(self) -> int:
        return len(self._entries)

    @property
    def last_hash(self) -> str:
        if not self._entries:
            return GENESIS_HASH
        return self._entries[-1].entry_hash

    def append(
        self,
        agent_id: AgentId,
        action: LedgerAction,
        description: str,
        credit_delta: float = 0.0,
        authority_at_time: float = 0.0,
        outcome: str = "pending",
        metadata: dict[str, Any] | None = None,
    ) -> LedgerEntry:
        """
        Create and append a new entry to the ledger.

        The entry is automatically chained to the previous entry
        and sealed (hashed). Returns the sealed entry.
        """
        entry = LedgerEntry(
            agent_id=agent_id,
            action=action,
            description=description,
            credit_delta=credit_delta,
            authority_at_time=authority_at_time,
            outcome=outcome,
            metadata=metadata or {},
            previous_hash=self.last_hash,
        )
        entry.seal()
        self._entries.append(entry)

        # Update credit balance
        balance = self._credit_balances.get(agent_id, 0.0)
        self._credit_balances[agent_id] = balance + credit_delta

        logger.debug(
            "Ledger entry %s: agent=%s action=%s credits=%+.2f",
            entry.id, agent_id, action.value, credit_delta,
        )

        return entry

    def verify_chain(self) -> dict[str, Any]:
        """
        Verify the integrity of the entire ledger chain.

        Returns a report with:
        - valid: bool — overall chain validity
        - checked: int — number of entries checked
        - broken_at: int | None — index of first broken link
        - findings: list — detailed issues found
        """
        findings: list[dict[str, str]] = []

        if not self._entries:
            return {"valid": True, "checked": 0, "broken_at": None, "findings": []}

        # First entry must chain from genesis
        if self._entries[0].previous_hash != GENESIS_HASH:
            findings.append({
                "severity": Severity.CRITICAL.value,
                "index": 0,
                "message": "First entry does not chain from genesis hash",
            })

        for i, entry in enumerate(self._entries):
            # Verify self-hash
            if not entry.verify():
                findings.append({
                    "severity": Severity.CRITICAL.value,
                    "index": i,
                    "message": f"Entry {entry.id} hash mismatch — data tampered",
                })
                return {
                    "valid": False,
                    "checked": i + 1,
                    "broken_at": i,
                    "findings": findings,
                }

            # Verify chain link (skip first entry)
            if i > 0:
                expected_prev = self._entries[i - 1].entry_hash
                if entry.previous_hash != expected_prev:
                    findings.append({
                        "severity": Severity.CRITICAL.value,
                        "index": i,
                        "message": (
                            f"Entry {entry.id} previous_hash mismatch: "
                            f"expected {expected_prev[:16]}..., "
                            f"got {entry.previous_hash[:16]}..."
                        ),
                    })
                    return {
                        "valid": False,
                        "checked": i + 1,
                        "broken_at": i,
                        "findings": findings,
                    }

        return {
            "valid": len(findings) == 0,
            "checked": len(self._entries),
            "broken_at": None,
            "findings": findings,
        }

    def get_balance(self, agent_id: AgentId) -> float:
        """Get the current credit balance for an agent."""
        return self._credit_balances.get(agent_id, 0.0)

    def get_entries(
        self,
        agent_id: AgentId | None = None,
        action: LedgerAction | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query ledger entries with optional filters."""
        entries = self._entries
        if agent_id:
            entries = [e for e in entries if e.agent_id == agent_id]
        if action:
            entries = [e for e in entries if e.action == action]
        return [e.to_dict() for e in entries[-limit:]]

    def get_agent_summary(self, agent_id: AgentId) -> dict[str, Any]:
        """Get a summary of an agent's ledger activity."""
        agent_entries = [e for e in self._entries if e.agent_id == agent_id]
        if not agent_entries:
            return {"agent_id": agent_id, "total_entries": 0}

        actions: dict[str, int] = {}
        total_credits = 0.0
        outcomes: dict[str, int] = {}

        for e in agent_entries:
            actions[e.action.value] = actions.get(e.action.value, 0) + 1
            total_credits += e.credit_delta
            outcomes[e.outcome] = outcomes.get(e.outcome, 0) + 1

        return {
            "agent_id": agent_id,
            "total_entries": len(agent_entries),
            "actions": actions,
            "total_credits": round(total_credits, 2),
            "current_balance": round(self.get_balance(agent_id), 2),
            "outcomes": outcomes,
            "first_entry": agent_entries[0].timestamp,
            "last_entry": agent_entries[-1].timestamp,
        }

    def get_stats(self) -> dict[str, Any]:
        """Get overall ledger statistics."""
        if not self._entries:
            return {"total_entries": 0, "agents": 0, "total_credits_flow": 0.0}

        agents = set(e.agent_id for e in self._entries)
        total_positive = sum(e.credit_delta for e in self._entries if e.credit_delta > 0)
        total_negative = sum(e.credit_delta for e in self._entries if e.credit_delta < 0)

        return {
            "total_entries": len(self._entries),
            "agents": len(agents),
            "total_credits_earned": round(total_positive, 2),
            "total_credits_spent": round(abs(total_negative), 2),
            "net_flow": round(total_positive + total_negative, 2),
            "chain_valid": self.verify_chain()["valid"],
        }
