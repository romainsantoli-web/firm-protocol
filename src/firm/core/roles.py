"""
firm.core.roles — Role Fluidity Engine (Layer 3)

Roles in FIRM are not job titles — they're capabilities earned through
demonstrated competence. The Role Fluidity Engine manages:

  - Authority-gated role assignment (minimum authority required)
  - Role capacity limits (max holders per role)
  - Automatic role expiry and rotation
  - Role transfer between agents
  - Role recommendations based on agent performance

In FIRM, a role is a living contract between an agent and the organization.
Hold it well, and your authority rises. Hold it poorly, and it gets
reassigned to someone better.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from firm.core.agent import Agent, AgentRole
from firm.core.types import AgentId, AgentStatus

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_ROLE_TTL = 86400 * 30  # 30 days default
MIN_AUTHORITY_FOR_CRITICAL_ROLE = 0.7
MIN_AUTHORITY_FOR_STANDARD_ROLE = 0.4


@dataclass
class RoleAssignment:
    """Tracks a specific agent-role binding with metadata."""

    agent_id: AgentId
    role: AgentRole
    assigned_at: float = field(default_factory=time.time)
    expires_at: float | None = None  # None = no expiry
    assigned_by: AgentId | None = None  # Who approved/assigned
    performance_score: float = 0.0  # Running score in this role

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    @property
    def tenure_seconds(self) -> float:
        return time.time() - self.assigned_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role.name,
            "assigned_at": self.assigned_at,
            "expires_at": self.expires_at,
            "assigned_by": self.assigned_by,
            "performance_score": round(self.performance_score, 4),
            "is_expired": self.is_expired,
            "tenure_seconds": round(self.tenure_seconds, 1),
        }


@dataclass
class RoleDefinition:
    """
    Blueprint for a role in the organization.

    Defines the authority threshold, capacity limit, and TTL.
    The role itself (AgentRole) is the identity; RoleDefinition
    is the governance metadata around it.
    """

    role: AgentRole
    min_authority: float = MIN_AUTHORITY_FOR_STANDARD_ROLE
    is_critical: bool = False  # Critical roles have higher authority requirements
    max_holders: int = 0  # 0 = unlimited
    default_ttl: float = DEFAULT_ROLE_TTL  # Seconds until auto-expiry
    description: str = ""

    def __post_init__(self) -> None:
        if self.is_critical and self.min_authority < MIN_AUTHORITY_FOR_CRITICAL_ROLE:
            self.min_authority = MIN_AUTHORITY_FOR_CRITICAL_ROLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.role.name,
            "min_authority": self.min_authority,
            "is_critical": self.is_critical,
            "max_holders": self.max_holders,
            "default_ttl": self.default_ttl,
            "description": self.description,
        }


class RoleEngine:
    """
    Manages role lifecycle within a FIRM.

    Roles are fluid — they're assigned based on authority, expire
    after a TTL, and can be transferred. The engine enforces
    capacity limits and authority gates.
    """

    def __init__(self) -> None:
        self._definitions: dict[str, RoleDefinition] = {}
        self._assignments: list[RoleAssignment] = []
        self._history: list[dict[str, Any]] = []

    # ── Role Definition ──────────────────────────────────────────────────

    def define_role(
        self,
        name: str,
        min_authority: float = MIN_AUTHORITY_FOR_STANDARD_ROLE,
        is_critical: bool = False,
        max_holders: int = 0,
        default_ttl: float = DEFAULT_ROLE_TTL,
        description: str = "",
        permissions: list[str] | None = None,
    ) -> RoleDefinition:
        """Define a new role in the organization."""
        role = AgentRole(
            name=name,
            description=description,
            permissions=permissions or [],
            max_holders=max_holders,
        )
        definition = RoleDefinition(
            role=role,
            min_authority=min_authority,
            is_critical=is_critical,
            max_holders=max_holders,
            default_ttl=default_ttl,
            description=description,
        )
        self._definitions[name] = definition
        logger.info("Role '%s' defined (min_authority=%.2f, critical=%s)",
                     name, definition.min_authority, is_critical)
        return definition

    def get_definition(self, name: str) -> RoleDefinition | None:
        return self._definitions.get(name)

    def list_definitions(self) -> list[RoleDefinition]:
        return list(self._definitions.values())

    # ── Assignment ───────────────────────────────────────────────────────

    def assign(
        self,
        agent: Agent,
        role_name: str,
        assigned_by: AgentId | None = None,
        ttl: float | None = None,
    ) -> RoleAssignment:
        """
        Assign a role to an agent.

        Raises:
            KeyError: Role not defined
            PermissionError: Agent doesn't meet authority requirement
            ValueError: Role at capacity
        """
        definition = self._definitions.get(role_name)
        if not definition:
            raise KeyError(f"Role '{role_name}' not defined")

        # Authority gate
        if agent.authority < definition.min_authority:
            raise PermissionError(
                f"Agent '{agent.name}' authority {agent.authority:.2f} "
                f"< required {definition.min_authority:.2f} for role '{role_name}'"
            )

        # Status check
        if agent.status != AgentStatus.ACTIVE:
            raise PermissionError(
                f"Agent '{agent.name}' is {agent.status.value}, not active"
            )

        # Capacity check
        if definition.max_holders > 0:
            current = self._count_active_holders(role_name)
            if current >= definition.max_holders:
                raise ValueError(
                    f"Role '{role_name}' at capacity ({current}/{definition.max_holders})"
                )

        # Already assigned?
        if agent.has_role(role_name):
            raise ValueError(f"Agent '{agent.name}' already holds role '{role_name}'")

        # Compute expiry
        effective_ttl = ttl if ttl is not None else definition.default_ttl
        expires_at = time.time() + effective_ttl if effective_ttl > 0 else None

        # Assign
        agent.grant_role(definition.role)
        assignment = RoleAssignment(
            agent_id=agent.id,
            role=definition.role,
            expires_at=expires_at,
            assigned_by=assigned_by,
        )
        self._assignments.append(assignment)

        self._record_event("assigned", agent.id, role_name, assigned_by)
        logger.info("Role '%s' assigned to agent '%s' (expires=%s)",
                     role_name, agent.name, expires_at)
        return assignment

    def revoke(
        self,
        agent: Agent,
        role_name: str,
        reason: str = "",
    ) -> bool:
        """Revoke a role from an agent."""
        if not agent.has_role(role_name):
            return False

        agent.revoke_role(role_name)
        # Remove from active assignments
        self._assignments = [
            a for a in self._assignments
            if not (a.agent_id == agent.id and a.role.name == role_name)
        ]
        self._record_event("revoked", agent.id, role_name, reason=reason)
        logger.info("Role '%s' revoked from agent '%s': %s", role_name, agent.name, reason)
        return True

    def transfer(
        self,
        from_agent: Agent,
        to_agent: Agent,
        role_name: str,
        reason: str = "",
    ) -> RoleAssignment:
        """
        Transfer a role from one agent to another.

        The receiving agent must meet the authority requirement.
        """
        if not from_agent.has_role(role_name):
            raise ValueError(f"Agent '{from_agent.name}' doesn't hold role '{role_name}'")

        # Revoke from source
        self.revoke(from_agent, role_name, reason=f"Transferred to {to_agent.name}: {reason}")

        # Assign to target (will validate authority + capacity)
        return self.assign(to_agent, role_name, assigned_by=from_agent.id)

    # ── Expiry & rotation ────────────────────────────────────────────────

    def expire_roles(self, agents: dict[str, Agent]) -> list[dict[str, Any]]:
        """
        Check all assignments for expiry and revoke expired ones.

        Returns list of expired role events.
        """
        expired = []
        still_active = []

        for assignment in self._assignments:
            if assignment.is_expired:
                agent = agents.get(assignment.agent_id)
                if agent and agent.has_role(assignment.role.name):
                    agent.revoke_role(assignment.role.name)
                    self._record_event("expired", assignment.agent_id, assignment.role.name)
                    expired.append({
                        "agent_id": assignment.agent_id,
                        "role": assignment.role.name,
                        "expired_at": time.time(),
                    })
                    logger.info("Role '%s' expired for agent %s",
                                assignment.role.name, assignment.agent_id)
            else:
                still_active.append(assignment)

        self._assignments = still_active
        return expired

    def recommend_candidates(
        self,
        role_name: str,
        agents: list[Agent],
        top_n: int = 3,
    ) -> list[dict[str, Any]]:
        """
        Recommend the best candidates for a role based on authority
        and success rate.
        """
        definition = self._definitions.get(role_name)
        if not definition:
            return []

        eligible = [
            a for a in agents
            if a.is_active
            and a.authority >= definition.min_authority
            and not a.has_role(role_name)
        ]

        # Score: 60% authority + 40% success_rate
        scored = sorted(
            eligible,
            key=lambda a: (0.6 * a.authority + 0.4 * a.success_rate),
            reverse=True,
        )

        return [
            {
                "agent_id": a.id,
                "agent_name": a.name,
                "authority": round(a.authority, 4),
                "success_rate": round(a.success_rate, 4),
                "score": round(0.6 * a.authority + 0.4 * a.success_rate, 4),
            }
            for a in scored[:top_n]
        ]

    # ── Queries ──────────────────────────────────────────────────────────

    def get_assignments(self, agent_id: str | None = None) -> list[RoleAssignment]:
        """Get active role assignments, optionally filtered by agent."""
        if agent_id:
            return [a for a in self._assignments if a.agent_id == agent_id]
        return list(self._assignments)

    def get_holders(self, role_name: str) -> list[AgentId]:
        """Get all agent IDs currently holding a role."""
        return [
            a.agent_id for a in self._assignments
            if a.role.name == role_name and not a.is_expired
        ]

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        return {
            "defined_roles": len(self._definitions),
            "active_assignments": len(self._assignments),
            "history_events": len(self._history),
        }

    # ── Internal ─────────────────────────────────────────────────────────

    def _count_active_holders(self, role_name: str) -> int:
        return sum(
            1 for a in self._assignments
            if a.role.name == role_name and not a.is_expired
        )

    def _record_event(
        self,
        event_type: str,
        agent_id: AgentId,
        role_name: str,
        assigned_by: AgentId | None = None,
        reason: str = "",
    ) -> None:
        self._history.append({
            "type": event_type,
            "agent_id": agent_id,
            "role": role_name,
            "assigned_by": assigned_by,
            "reason": reason,
            "timestamp": time.time(),
        })
