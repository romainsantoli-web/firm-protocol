"""
firm.runtime — FIRM Organization Runtime

A FIRM is a self-evolving autonomous organization.
This module ties together all the core primitives:
  - Agents with earned authority
  - Responsibility Ledger (append-only, hash-chained)
  - Constitutional Agent (invariant guardian)
  - Governance Engine (2-cycle proposals)

The runtime provides the high-level API for creating and
operating a FIRM organization.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from firm.core.agent import Agent, AgentRole
from firm.core.audit import AuditEngine, AuditReport
from firm.core.authority import AuthorityEngine, THRESHOLD_PROBATION
from firm.core.constitution import ConstitutionalAgent
from firm.core.governance import GovernanceEngine, Proposal, SimulationResult, Vote
from firm.core.human import HumanOverride
from firm.core.ledger import ResponsibilityLedger
from firm.core.memory import MemoryEngine, MemoryEntry
from firm.core.roles import RoleEngine, RoleAssignment, RoleDefinition
from firm.core.spawn import SpawnEngine
from firm.core.types import (
    AgentId,
    AgentStatus,
    FirmId,
    LedgerAction,
    Severity,
    VoteChoice,
)

logger = logging.getLogger(__name__)


class Firm:
    """
    A self-evolving autonomous organization.

    Usage:
        firm = Firm(name="my-firm")
        ceo = firm.add_agent("ceo", authority=0.9)
        dev = firm.add_agent("dev", authority=0.5)

        # Record actions — authority adjusts automatically
        firm.record_action(dev.id, success=True, description="Shipped feature X")
        firm.record_action(dev.id, success=True, description="Fixed bug Y")

        # Governance
        proposal = firm.propose(ceo.id, "Add QA role", "We need quality assurance")
        firm.vote(proposal.id, dev.id, "approve")
    """

    def __init__(
        self,
        name: str,
        firm_id: FirmId | None = None,
        learning_rate: float = 0.05,
        decay: float = 0.02,
    ) -> None:
        self.name = name
        self.id = firm_id or FirmId(name.lower().replace(" ", "-"))
        self.created_at = time.time()

        # Core engines
        self.authority = AuthorityEngine(learning_rate=learning_rate, decay=decay)
        self.ledger = ResponsibilityLedger()
        self.constitution = ConstitutionalAgent(kill_switch_active=False)
        self.governance = GovernanceEngine()

        # S1 engines
        self.roles = RoleEngine()
        self.memory = MemoryEngine()
        self.spawn_engine = SpawnEngine()
        self.audit = AuditEngine()
        self.human = HumanOverride(self.constitution, self.ledger)

        # Agent registry
        self._agents: dict[str, Agent] = {}

        # Record genesis
        self.ledger.append(
            agent_id=AgentId("system"),
            action=LedgerAction.DECISION,
            description=f"FIRM '{name}' created",
            outcome="success",
        )

        logger.info("FIRM '%s' created (id=%s)", name, self.id)

    # ── Agent management ─────────────────────────────────────────────────

    def add_agent(
        self,
        name: str,
        authority: float = 0.5,
        credits: float = 100.0,
        roles: list[str] | None = None,
    ) -> Agent:
        """Add a new agent to the FIRM."""
        agent = Agent(name=name, authority=authority, credits=credits)

        if roles:
            for role_name in roles:
                agent.grant_role(AgentRole(name=role_name))

        self._agents[agent.id] = agent

        self.ledger.append(
            agent_id=agent.id,
            action=LedgerAction.DECISION,
            description=f"Agent '{name}' joined the FIRM",
            authority_at_time=authority,
            outcome="success",
        )

        return agent

    def get_agent(self, agent_id: str) -> Agent | None:
        return self._agents.get(AgentId(agent_id))

    def get_agents(self, active_only: bool = True) -> list[Agent]:
        if active_only:
            return [a for a in self._agents.values() if a.is_active]
        return list(self._agents.values())

    # ── Actions ──────────────────────────────────────────────────────────

    def record_action(
        self,
        agent_id: str,
        success: bool,
        description: str = "",
        credit_delta: float | None = None,
    ) -> dict[str, Any]:
        """
        Record an agent's action and update authority.

        Success increases authority, failure decreases it.
        Credits are adjusted based on outcome.
        """
        agent = self._agents.get(AgentId(agent_id))
        if not agent:
            raise KeyError(f"Agent {agent_id} not found")

        if not agent.is_active:
            raise ValueError(f"Agent {agent_id} is not active (status: {agent.status.value})")

        # Check kill switch
        if self.constitution.kill_switch_active:
            return {
                "blocked": True,
                "reason": "kill_switch_active",
                "message": "All operations halted by Constitutional Agent",
            }

        # Check for invariant violations
        violations = self.constitution.check_action(description)
        if violations:
            return {
                "blocked": True,
                "reason": "invariant_violation",
                "violations": [v.to_dict() for v in violations],
            }

        # Update authority
        auth_change = self.authority.update(agent, success, description)

        # Compute credit delta
        if credit_delta is None:
            credit_delta = 10.0 if success else -5.0
        agent.credits += credit_delta

        # Record in ledger
        action = LedgerAction.TASK_COMPLETED if success else LedgerAction.TASK_FAILED
        self.ledger.append(
            agent_id=AgentId(agent_id),
            action=action,
            description=description,
            credit_delta=credit_delta,
            authority_at_time=agent.authority,
            outcome="success" if success else "failure",
        )

        # Check if agent needs probation
        if self.authority.needs_probation(agent):
            agent.status = AgentStatus.PROBATION
            self.ledger.append(
                agent_id=AgentId(agent_id),
                action=LedgerAction.AUTHORITY_CHANGE,
                description=f"Agent placed on probation (authority={agent.authority:.4f})",
                authority_at_time=agent.authority,
                outcome="probation",
            )

        # Check if governance needs bootstrap
        self._check_governance_health()

        return {
            "agent_id": agent_id,
            "success": success,
            "authority": auth_change.to_dict(),
            "credits": round(agent.credits, 2),
            "status": agent.status.value,
        }

    # ── Governance shortcuts ─────────────────────────────────────────────

    def propose(
        self,
        proposer_id: str,
        title: str,
        description: str,
        proposal_type: str = "general",
    ) -> Proposal:
        """Create a governance proposal."""
        agent = self._agents.get(AgentId(proposer_id))
        if not agent:
            raise KeyError(f"Agent {proposer_id} not found")

        # Constitutional check
        violations = self.constitution.check_proposal(f"{title}: {description}")
        if violations:
            raise PermissionError(
                f"Proposal violates invariant(s): "
                + ", ".join(v.invariant_id for v in violations)
            )

        proposal = self.governance.create_proposal(
            proposer=agent,
            title=title,
            description=description,
            proposal_type=proposal_type,
        )

        self.ledger.append(
            agent_id=AgentId(proposer_id),
            action=LedgerAction.GOVERNANCE_VOTE,
            description=f"Created proposal: {title}",
            authority_at_time=agent.authority,
            credit_delta=-5.0,  # Proposals cost credits
            outcome="pending",
        )

        return proposal

    def simulate_proposal(
        self,
        proposal_id: str,
        success: bool = True,
        impact_summary: str = "",
        risk_score: float = 0.1,
    ) -> None:
        """Run a simulation phase on a proposal."""
        proposal = self.governance.get_proposal(proposal_id)
        if not proposal:
            raise KeyError(f"Proposal {proposal_id} not found")

        result = SimulationResult(
            success=success,
            impact_summary=impact_summary or f"Simulation for '{proposal.title}'",
            risk_score=risk_score,
        )
        self.governance.simulate(proposal, result)

    def vote(
        self,
        proposal_id: str,
        voter_id: str,
        choice: str,
        reason: str = "",
    ) -> Vote:
        """Cast a vote on a proposal."""
        proposal = self.governance.get_proposal(proposal_id)
        if not proposal:
            raise KeyError(f"Proposal {proposal_id} not found")

        voter = self._agents.get(AgentId(voter_id))
        if not voter:
            raise KeyError(f"Agent {voter_id} not found")

        vote_choice = VoteChoice(choice)
        v = self.governance.vote(proposal, voter, vote_choice, reason)

        self.ledger.append(
            agent_id=AgentId(voter_id),
            action=LedgerAction.GOVERNANCE_VOTE,
            description=f"Voted {choice} on '{proposal.title}'",
            authority_at_time=voter.authority,
            outcome="success",
        )

        return v

    def finalize_proposal(self, proposal_id: str) -> dict[str, Any]:
        """Finalize voting on a proposal."""
        proposal = self.governance.get_proposal(proposal_id)
        if not proposal:
            raise KeyError(f"Proposal {proposal_id} not found")

        eligible = len([a for a in self.get_agents() if self.authority.can_vote(a)])
        return self.governance.finalize(proposal, eligible)

    # ── Role Fluidity (Layer 3) ────────────────────────────────────────

    def define_role(
        self,
        name: str,
        min_authority: float = 0.4,
        is_critical: bool = False,
        max_holders: int = 0,
        permissions: list[str] | None = None,
        description: str = "",
    ) -> RoleDefinition:
        """Define a new role in the organization."""
        return self.roles.define_role(
            name=name,
            min_authority=min_authority,
            is_critical=is_critical,
            max_holders=max_holders,
            permissions=permissions,
            description=description,
        )

    def assign_role(
        self,
        agent_id: str,
        role_name: str,
        assigned_by: str | None = None,
    ) -> RoleAssignment:
        """Assign a defined role to an agent (authority-gated)."""
        agent = self._agents.get(AgentId(agent_id))
        if not agent:
            raise KeyError(f"Agent {agent_id} not found")
        assignment = self.roles.assign(
            agent, role_name,
            assigned_by=AgentId(assigned_by) if assigned_by else None,
        )
        self.ledger.append(
            agent_id=AgentId(agent_id),
            action=LedgerAction.RESTRUCTURE,
            description=f"Role '{role_name}' assigned",
            authority_at_time=agent.authority,
            outcome="success",
        )
        return assignment

    def revoke_role(self, agent_id: str, role_name: str, reason: str = "") -> bool:
        """Revoke a role from an agent."""
        agent = self._agents.get(AgentId(agent_id))
        if not agent:
            raise KeyError(f"Agent {agent_id} not found")
        result = self.roles.revoke(agent, role_name, reason)
        if result:
            self.ledger.append(
                agent_id=AgentId(agent_id),
                action=LedgerAction.RESTRUCTURE,
                description=f"Role '{role_name}' revoked: {reason}",
                authority_at_time=agent.authority,
                outcome="success",
            )
        return result

    # ── Collective Memory (Layer 4) ──────────────────────────────────────

    def contribute_memory(
        self,
        agent_id: str,
        content: str,
        tags: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> MemoryEntry:
        """Add knowledge to the collective memory."""
        agent = self._agents.get(AgentId(agent_id))
        if not agent:
            raise KeyError(f"Agent {agent_id} not found")
        return self.memory.contribute(
            content=content,
            tags=tags,
            contributor_id=agent.id,
            contributor_authority=agent.authority,
            metadata=metadata,
        )

    def recall_memory(
        self,
        tags: list[str],
        top_k: int = 5,
    ) -> list[MemoryEntry]:
        """Retrieve highest-weighted memories matching tags."""
        return self.memory.recall(tags=tags, top_k=top_k)

    def reinforce_memory(self, agent_id: str, memory_id: str) -> MemoryEntry:
        """Reinforce (agree with) a memory entry."""
        agent = self._agents.get(AgentId(agent_id))
        if not agent:
            raise KeyError(f"Agent {agent_id} not found")
        return self.memory.reinforce(memory_id, agent.id, agent.authority)

    def challenge_memory(
        self, agent_id: str, memory_id: str, reason: str = ""
    ) -> MemoryEntry:
        """Challenge (disagree with) a memory entry."""
        agent = self._agents.get(AgentId(agent_id))
        if not agent:
            raise KeyError(f"Agent {agent_id} not found")
        return self.memory.challenge(memory_id, agent.id, agent.authority, reason)

    # ── Spawn/Merge (Layer 7) ────────────────────────────────────────────

    def spawn_agent(
        self,
        parent_id: str,
        name: str,
        roles: list[str] | None = None,
    ) -> Agent:
        """Spawn a child agent from a parent (authority-gated)."""
        parent = self._agents.get(AgentId(parent_id))
        if not parent:
            raise KeyError(f"Agent {parent_id} not found")

        child = self.spawn_engine.spawn(parent, name)
        self._agents[child.id] = child

        if roles:
            for role_name in roles:
                child.grant_role(AgentRole(name=role_name))

        self.ledger.append(
            agent_id=parent.id,
            action=LedgerAction.RESTRUCTURE,
            description=f"Spawned agent '{name}' (id={child.id})",
            authority_at_time=parent.authority,
            outcome="success",
        )
        return child

    def merge_agents(
        self,
        agent_a_id: str,
        agent_b_id: str,
        merged_name: str,
    ) -> Agent:
        """Merge two agents into one (both terminated, new one created)."""
        agent_a = self._agents.get(AgentId(agent_a_id))
        agent_b = self._agents.get(AgentId(agent_b_id))
        if not agent_a:
            raise KeyError(f"Agent {agent_a_id} not found")
        if not agent_b:
            raise KeyError(f"Agent {agent_b_id} not found")

        merged = self.spawn_engine.merge(agent_a, agent_b, merged_name)
        self._agents[merged.id] = merged

        self.ledger.append(
            agent_id=merged.id,
            action=LedgerAction.RESTRUCTURE,
            description=f"Merged from '{agent_a.name}' + '{agent_b.name}'",
            authority_at_time=merged.authority,
            outcome="success",
        )
        return merged

    def split_agent(
        self,
        agent_id: str,
        name_a: str,
        name_b: str,
        authority_ratio: float = 0.5,
    ) -> tuple[Agent, Agent]:
        """Split an agent into two (parent terminated)."""
        agent = self._agents.get(AgentId(agent_id))
        if not agent:
            raise KeyError(f"Agent {agent_id} not found")

        child_a, child_b = self.spawn_engine.split(
            agent, name_a, name_b, authority_ratio=authority_ratio,
        )
        self._agents[child_a.id] = child_a
        self._agents[child_b.id] = child_b

        self.ledger.append(
            agent_id=agent.id,
            action=LedgerAction.RESTRUCTURE,
            description=f"Split into '{name_a}' + '{name_b}'",
            authority_at_time=agent.authority,
            outcome="success",
        )
        return child_a, child_b

    # ── Audit (Layer 10) ─────────────────────────────────────────────────

    def run_audit(self) -> AuditReport:
        """Run a full organization audit."""
        return self.audit.full_audit(
            firm_name=self.name,
            ledger=self.ledger,
            agents=self.get_agents(active_only=False),
            authority_engine=self.authority,
        )

    # ── Health / Status ──────────────────────────────────────────────────

    def _check_governance_health(self) -> None:
        """Auto-check if governance needs bootstrapping."""
        # Include probation agents — they're struggling but still exist
        all_agents = [a for a in self._agents.values()
                      if a.status in (AgentStatus.ACTIVE, AgentStatus.PROBATION)]
        health = self.constitution.assess_governance_health(all_agents)
        if not health.get("functional", True):
            action = health.get("action_required", "")
            if action == "bootstrap" and all_agents:
                logger.warning("Governance deadlock detected — bootstrapping")
                self.constitution.bootstrap_governance(all_agents)

    def status(self) -> dict[str, Any]:
        """Get full FIRM status."""
        agents = self.get_agents(active_only=False)
        active = [a for a in agents if a.is_active]

        return {
            "name": self.name,
            "id": self.id,
            "agents": {
                "total": len(agents),
                "active": len(active),
                "agents": [a.to_dict() for a in agents],
            },
            "authority": self.authority.assess_health(active),
            "ledger": self.ledger.get_stats(),
            "governance": {
                "active_proposals": len(self.governance.get_active_proposals()),
                "total_proposals": len(self.governance.get_all_proposals()),
            },
            "constitution": self.constitution.get_status(),
            "roles": self.roles.get_stats(),
            "memory": self.memory.get_stats(),
            "spawn": self.spawn_engine.get_stats(),
            "audit": self.audit.get_stats(),
            "human_overrides": self.human.get_stats(),
            "uptime_seconds": round(time.time() - self.created_at, 1),
        }
