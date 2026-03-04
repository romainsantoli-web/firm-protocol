"""
firm.core.agent — Agent primitive

An Agent in FIRM is not just a wrapper around an LLM.
It has identity, authority, memory, and accountability.
Authority is earned through successful actions, not assigned by hierarchy.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from firm.core.types import AgentId, AgentStatus


@dataclass
class AgentRole:
    """
    A named capability/responsibility that an agent can hold.

    Roles are not permanent — they can be granted, revoked,
    or transferred through governance proposals.
    """

    name: str
    description: str = ""
    permissions: list[str] = field(default_factory=list)
    max_holders: int = 0  # 0 = unlimited

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, AgentRole):
            return self.name == other.name
        return NotImplemented


@dataclass
class Agent:
    """
    A participant in a FIRM organization.

    Each agent has:
    - An authority score [0.0, 1.0] — earned, never assigned
    - A set of roles — granted through governance
    - A credit balance — economic consequences of actions
    - A status — active, suspended, probation, terminated

    The Constitutional Agent is special: it has no authority score,
    cannot be deleted, and bootstraps governance when needed.
    """

    id: AgentId = field(default_factory=lambda: AgentId(str(uuid.uuid4())[:8]))
    name: str = ""
    authority: float = 0.5  # Start neutral — must be earned
    roles: set[AgentRole] = field(default_factory=set)
    credits: float = 100.0  # Starting credit balance
    status: AgentStatus = AgentStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── History tracking ─────────────────────────────────────────────────

    _action_count: int = field(default=0, repr=False)
    _success_count: int = field(default=0, repr=False)
    _failure_count: int = field(default=0, repr=False)

    @property
    def success_rate(self) -> float:
        """Ratio of successful actions to total actions."""
        if self._action_count == 0:
            return 0.0
        return self._success_count / self._action_count

    @property
    def is_active(self) -> bool:
        return self.status == AgentStatus.ACTIVE

    def record_success(self) -> None:
        """Record a successful action."""
        self._action_count += 1
        self._success_count += 1

    def record_failure(self) -> None:
        """Record a failed action."""
        self._action_count += 1
        self._failure_count += 1

    def has_role(self, role_name: str) -> bool:
        """Check if agent holds a specific role."""
        return any(r.name == role_name for r in self.roles)

    def grant_role(self, role: AgentRole) -> bool:
        """Grant a role to this agent. Returns False if already held."""
        if role in self.roles:
            return False
        self.roles.add(role)
        return True

    def revoke_role(self, role_name: str) -> bool:
        """Revoke a role by name. Returns False if not held."""
        role = next((r for r in self.roles if r.name == role_name), None)
        if role is None:
            return False
        self.roles.discard(role)
        return True

    def suspend(self, reason: str = "") -> None:
        """Suspend this agent."""
        self.status = AgentStatus.SUSPENDED
        self.metadata["suspension_reason"] = reason
        self.metadata["suspended_at"] = time.time()

    def reactivate(self) -> None:
        """Reactivate a suspended agent (on probation)."""
        if self.status == AgentStatus.SUSPENDED:
            self.status = AgentStatus.PROBATION
            self.metadata["probation_started_at"] = time.time()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "authority": round(self.authority, 4),
            "roles": [r.name for r in self.roles],
            "credits": round(self.credits, 2),
            "status": self.status.value,
            "success_rate": round(self.success_rate, 4),
            "action_count": self._action_count,
            "created_at": self.created_at,
        }
