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
from firm.core.evolution import (
    EvolutionEngine,
    EvolutionProposal,
    ParameterChange,
    MIN_AUTHORITY_TO_EVOLVE,
)
from firm.core.federation import (
    FederationEngine,
    FederationMessage,
    AgentSecondment,
    PeerFirm,
    MessageType,
    MIN_AUTHORITY_TO_FEDERATE,
    MIN_AUTHORITY_TO_SEND,
    MIN_AUTHORITY_TO_SECOND,
)
from firm.core.governance import GovernanceEngine, Proposal, SimulationResult, Vote
from firm.core.human import HumanOverride
from firm.core.ledger import ResponsibilityLedger
from firm.core.market import (
    MarketEngine,
    MarketTask,
    MarketBid,
    Settlement,
    MIN_AUTHORITY_TO_POST,
    MIN_AUTHORITY_TO_BID,
)
from firm.core.memory import MemoryEngine, MemoryEntry
from firm.core.meta import (
    MetaConstitutional,
    Amendment,
    MIN_AUTHORITY_TO_AMEND,
)
from firm.core.reputation import (
    ReputationBridge,
    ReputationAttestation,
    ImportedReputation,
)
from firm.core.events import EventBus, Event
from firm.core.plugins import PluginManager, FirmPlugin
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

        # S2 engines
        self.federation = FederationEngine(self.id, self.name)
        self.reputation = ReputationBridge(self.id)

        # S3 engines
        self.evolution = EvolutionEngine()
        self.market = MarketEngine()
        self.meta = MetaConstitutional(self.constitution)

        # S5 — Event bus & plugin system
        self.events = EventBus()
        self.plugins = PluginManager()

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

        # Emit genesis event
        self.events.emit("firm.created", {
            "name": name, "id": self.id,
        }, source="runtime")

    # ── Serialization shortcuts ──────────────────────────────────────────

    def save(self, path: str | None = None) -> dict[str, Any]:
        """Save FIRM state to JSON. See firm.core.serialization."""
        from firm.core.serialization import save_firm
        return save_firm(self, path)

    @classmethod
    def load(cls, source: str | dict[str, Any]) -> "Firm":
        """Load FIRM state from JSON. See firm.core.serialization."""
        from firm.core.serialization import load_firm
        return load_firm(source)

    def snapshot(self) -> dict[str, Any]:
        """Take an in-memory snapshot for comparison."""
        from firm.core.serialization import snapshot
        return snapshot(self)

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

        self.events.emit("agent.added", {
            "agent_id": agent.id, "name": name, "authority": authority,
        }, source="runtime")

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

        self.events.emit("action.recorded", {
            "agent_id": agent_id, "success": success,
            "authority": agent.authority,
        }, source="runtime")

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

    # ── Federation (Layer 8) ─────────────────────────────────────────────

    def register_peer(
        self,
        agent_id: str,
        peer_firm_id: str,
        peer_name: str,
        metadata: dict[str, Any] | None = None,
    ) -> PeerFirm:
        """Register a peer FIRM (authority-gated)."""
        agent = self._agents.get(AgentId(agent_id))
        if not agent:
            raise KeyError(f"Agent {agent_id} not found")
        if agent.authority < MIN_AUTHORITY_TO_FEDERATE:
            raise PermissionError(
                f"Authority too low to federate: {agent.authority:.2f} "
                f"< {MIN_AUTHORITY_TO_FEDERATE}"
            )

        peer = self.federation.register_peer(
            FirmId(peer_firm_id), peer_name, metadata,
        )

        self.ledger.append(
            agent_id=AgentId(agent_id),
            action=LedgerAction.FEDERATION,
            description=f"Registered peer FIRM '{peer_name}' ({peer_firm_id})",
            authority_at_time=agent.authority,
            outcome="success",
        )
        return peer

    def send_federation_message(
        self,
        agent_id: str,
        to_firm: str,
        message_type: str,
        subject: str,
        body: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> FederationMessage:
        """Send a message to a peer FIRM (authority-gated)."""
        agent = self._agents.get(AgentId(agent_id))
        if not agent:
            raise KeyError(f"Agent {agent_id} not found")
        if agent.authority < MIN_AUTHORITY_TO_SEND:
            raise PermissionError(
                f"Authority too low to send: {agent.authority:.2f} "
                f"< {MIN_AUTHORITY_TO_SEND}"
            )

        msg = self.federation.send_message(
            to_firm=FirmId(to_firm),
            sender_agent=AgentId(agent_id),
            message_type=message_type,
            subject=subject,
            body=body,
            metadata=metadata,
        )

        self.ledger.append(
            agent_id=AgentId(agent_id),
            action=LedgerAction.FEDERATION,
            description=f"Sent [{message_type}] to '{to_firm}': {subject}",
            authority_at_time=agent.authority,
            outcome="success",
        )
        return msg

    def second_agent(
        self,
        authorizer_id: str,
        agent_id: str,
        host_firm: str,
        duration: float | None = None,
        reason: str = "",
    ) -> AgentSecondment:
        """Second (lend) an agent to a peer FIRM (authority-gated)."""
        authorizer = self._agents.get(AgentId(authorizer_id))
        if not authorizer:
            raise KeyError(f"Agent {authorizer_id} not found")
        if authorizer.authority < MIN_AUTHORITY_TO_SECOND:
            raise PermissionError(
                f"Authority too low to second: {authorizer.authority:.2f} "
                f"< {MIN_AUTHORITY_TO_SECOND}"
            )

        agent = self._agents.get(AgentId(agent_id))
        if not agent:
            raise KeyError(f"Agent {agent_id} not found")
        if not agent.is_active:
            raise ValueError(
                f"Agent {agent_id} is not active (status: {agent.status.value})"
            )

        from firm.core.federation import DEFAULT_SECONDMENT_DURATION
        sec = self.federation.second_agent(
            agent_id=AgentId(agent_id),
            agent_name=agent.name,
            agent_authority=agent.authority,
            host_firm=FirmId(host_firm),
            duration=duration or DEFAULT_SECONDMENT_DURATION,
            reason=reason,
        )

        self.ledger.append(
            agent_id=AgentId(authorizer_id),
            action=LedgerAction.AGENT_SECONDMENT,
            description=(
                f"Seconded agent '{agent.name}' to '{host_firm}' "
                f"(effective auth: {sec.effective_authority:.2f})"
            ),
            authority_at_time=authorizer.authority,
            outcome="success",
        )
        return sec

    def recall_secondment(self, secondment_id: str) -> AgentSecondment:
        """Recall a seconded agent."""
        sec = self.federation.recall_secondment(secondment_id)
        self.ledger.append(
            agent_id=AgentId(sec.agent_id),
            action=LedgerAction.AGENT_SECONDMENT,
            description=f"Secondment '{secondment_id}' recalled",
            outcome="success",
        )
        return sec

    # ── Reputation Bridge (Layer 9) ──────────────────────────────────────

    def issue_reputation(
        self,
        agent_id: str,
        endorsement: str = "",
    ) -> ReputationAttestation:
        """Issue a reputation attestation for a local agent."""
        agent = self._agents.get(AgentId(agent_id))
        if not agent:
            raise KeyError(f"Agent {agent_id} not found")

        attestation = self.reputation.issue_attestation(
            agent_id=AgentId(agent_id),
            agent_name=agent.name,
            authority=agent.authority,
            success_rate=agent.success_rate,
            action_count=agent._action_count,
            endorsement=endorsement,
        )

        self.ledger.append(
            agent_id=AgentId(agent_id),
            action=LedgerAction.REPUTATION_ATTESTATION,
            description=f"Reputation attestation issued (auth={agent.authority:.2f})",
            authority_at_time=agent.authority,
            outcome="success",
        )
        return attestation

    def import_reputation(
        self,
        agent_id: str,
        attestation: ReputationAttestation,
        discount: float | None = None,
    ) -> ImportedReputation:
        """
        Import a foreign reputation attestation for a local agent.

        The source FIRM's trust level determines the discount factor.
        """
        agent = self._agents.get(AgentId(agent_id))
        if not agent:
            raise KeyError(f"Agent {agent_id} not found")

        # Look up trust with the source FIRM
        peer = self.federation.get_peer(attestation.source_firm)
        if not peer:
            raise KeyError(
                f"Source FIRM '{attestation.source_firm}' is not a registered peer"
            )

        imp = self.reputation.import_attestation(
            attestation=attestation,
            peer_trust=peer.trust,
            discount=discount,
        )

        self.ledger.append(
            agent_id=AgentId(agent_id),
            action=LedgerAction.REPUTATION_ATTESTATION,
            description=(
                f"Imported reputation from '{attestation.source_firm}': "
                f"{imp.original_authority:.2f} × {imp.discount_factor:.2f} "
                f"= {imp.effective_authority:.4f}"
            ),
            authority_at_time=agent.authority,
            outcome="success",
        )
        return imp

    def get_agent_reputation(
        self,
        agent_id: str,
    ) -> dict[str, Any]:
        """Get combined local + imported reputation for an agent."""
        agent = self._agents.get(AgentId(agent_id))
        if not agent:
            raise KeyError(f"Agent {agent_id} not found")
        return self.reputation.get_agent_reputation_summary(
            agent_id=AgentId(agent_id),
            local_authority=agent.authority,
        )

    # ── Evolution Engine ─────────────────────────────────────────────────

    def propose_evolution(
        self,
        proposer_id: str,
        changes: list[dict[str, Any]],
        rationale: str = "",
    ) -> EvolutionProposal:
        """
        Propose evolving FIRM parameters (authority-gated at 0.85).

        Args:
            proposer_id: Agent proposing the evolution
            changes: List of {category, parameter_name, new_value}
            rationale: Why this evolution is needed
        """
        agent = self._agents.get(AgentId(proposer_id))
        if not agent:
            raise KeyError(f"Agent {proposer_id} not found")
        if agent.authority < MIN_AUTHORITY_TO_EVOLVE:
            raise PermissionError(
                f"Authority too low to propose evolution: {agent.authority:.2f} "
                f"< {MIN_AUTHORITY_TO_EVOLVE}"
            )

        proposal = self.evolution.propose(
            proposer_id=AgentId(proposer_id),
            changes=changes,
            rationale=rationale,
        )

        self.ledger.append(
            agent_id=AgentId(proposer_id),
            action=LedgerAction.EVOLUTION,
            description=f"Evolution proposed: {len(changes)} parameter change(s)",
            authority_at_time=agent.authority,
            outcome="proposed",
        )
        return proposal

    def vote_evolution(
        self,
        proposal_id: str,
        voter_id: str,
        approve: bool,
    ) -> EvolutionProposal:
        """Cast a weighted vote on an evolution proposal."""
        voter = self._agents.get(AgentId(voter_id))
        if not voter:
            raise KeyError(f"Agent {voter_id} not found")

        proposal = self.evolution.vote(
            proposal_id=proposal_id,
            voter_id=AgentId(voter_id),
            voter_authority=voter.authority,
            approve=approve,
        )

        self.ledger.append(
            agent_id=AgentId(voter_id),
            action=LedgerAction.EVOLUTION,
            description=(
                f"Voted {'for' if approve else 'against'} "
                f"evolution proposal '{proposal_id}'"
            ),
            authority_at_time=voter.authority,
            outcome="success",
        )
        return proposal

    def apply_evolution(self, proposal_id: str) -> list[ParameterChange]:
        """
        Finalize and apply an evolution proposal.

        Automatically finalizes voting, then applies if approved.
        """
        # Finalize voting
        eligible = [a for a in self.get_agents() if a.authority >= 0.6]
        total_weight = sum(a.authority for a in eligible)
        proposal = self.evolution.finalize(proposal_id, total_weight)

        if proposal.status.value != "approved":
            self.ledger.append(
                agent_id=AgentId(proposal.proposer_id),
                action=LedgerAction.EVOLUTION,
                description=f"Evolution proposal '{proposal_id}' {proposal.status.value}",
                outcome=proposal.status.value,
            )
            return []

        # Apply
        applied = self.evolution.apply(proposal_id)

        self.ledger.append(
            agent_id=AgentId(proposal.proposer_id),
            action=LedgerAction.EVOLUTION,
            description=(
                f"Evolution applied — generation {self.evolution.generation}: "
                + ", ".join(f"{c.parameter_name}: {c.old_value}→{c.new_value}"
                            for c in applied)
            ),
            outcome="applied",
        )
        return applied

    def rollback_evolution(self, proposal_id: str) -> list[ParameterChange]:
        """Rollback a previously applied evolution."""
        reverted = self.evolution.rollback(proposal_id)

        self.ledger.append(
            agent_id=AgentId("system"),
            action=LedgerAction.EVOLUTION,
            description=f"Evolution '{proposal_id}' rolled back",
            outcome="rolled_back",
        )
        return reverted

    def get_firm_parameters(
        self,
        category: str | None = None,
    ) -> dict[str, Any]:
        """Get current FIRM operating parameters."""
        return self.evolution.get_parameters(category)

    # ── Market ───────────────────────────────────────────────────────────

    def post_task(
        self,
        poster_id: str,
        title: str,
        description: str = "",
        category: str = "general",
        bounty: float = 10.0,
        deadline_seconds: float = 86400.0,
    ) -> MarketTask:
        """
        Post a task on the internal market (authority-gated at 0.3).

        The poster offers credits as a bounty for task completion.
        """
        agent = self._agents.get(AgentId(poster_id))
        if not agent:
            raise KeyError(f"Agent {poster_id} not found")
        if agent.authority < MIN_AUTHORITY_TO_POST:
            raise PermissionError(
                f"Authority too low to post tasks: {agent.authority:.2f} "
                f"< {MIN_AUTHORITY_TO_POST}"
            )
        if agent.credits < bounty:
            raise ValueError(
                f"Insufficient credits: {agent.credits:.2f} < {bounty:.2f}"
            )

        task = self.market.post_task(
            poster_id=AgentId(poster_id),
            title=title,
            description=description,
            category=category,
            bounty=bounty,
            deadline_seconds=deadline_seconds,
        )

        self.ledger.append(
            agent_id=AgentId(poster_id),
            action=LedgerAction.MARKET_TRANSACTION,
            description=f"Posted task '{title}' — bounty {bounty}",
            authority_at_time=agent.authority,
            credit_delta=0.0,  # Credits escrowed, not yet deducted
            outcome="success",
        )
        return task

    def bid_on_task(
        self,
        task_id: str,
        bidder_id: str,
        amount: float | None = None,
        pitch: str = "",
    ) -> MarketBid:
        """Place a bid on an open task (authority-gated at 0.2)."""
        agent = self._agents.get(AgentId(bidder_id))
        if not agent:
            raise KeyError(f"Agent {bidder_id} not found")
        if agent.authority < MIN_AUTHORITY_TO_BID:
            raise PermissionError(
                f"Authority too low to bid: {agent.authority:.2f} "
                f"< {MIN_AUTHORITY_TO_BID}"
            )

        bid = self.market.place_bid(
            task_id=task_id,
            bidder_id=AgentId(bidder_id),
            bidder_authority=agent.authority,
            amount=amount,
            pitch=pitch,
        )

        self.ledger.append(
            agent_id=AgentId(bidder_id),
            action=LedgerAction.MARKET_TRANSACTION,
            description=f"Bid on task '{task_id}' — amount {bid.amount}",
            authority_at_time=agent.authority,
            outcome="success",
        )
        return bid

    def accept_bid(self, task_id: str, bid_id: str) -> MarketTask:
        """Accept a bid and assign the task. Only the poster can accept."""
        task = self.market.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        return self.market.accept_bid(task_id, bid_id)

    def settle_task(
        self,
        task_id: str,
        success: bool,
        reason: str = "",
    ) -> Settlement:
        """
        Settle a task — transfer credits based on outcome.

        On success: poster pays bidder (minus fee).
        On failure: bidder gets nothing.
        """
        task = self.market.get_task(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")

        if success:
            settlement = self.market.complete_task(task_id)
        else:
            settlement = self.market.fail_task(task_id, reason)

        # Apply credit transfers to agents
        poster = self._agents.get(AgentId(settlement.from_agent))
        worker = self._agents.get(AgentId(settlement.to_agent))

        if poster and success:
            poster.credits -= (settlement.amount + settlement.fee)
        elif poster and not success:
            poster.credits -= settlement.fee

        if worker and success:
            worker.credits += settlement.amount

        self.ledger.append(
            agent_id=AgentId(settlement.to_agent) if success else AgentId(settlement.from_agent),
            action=LedgerAction.MARKET_TRANSACTION,
            description=(
                f"Task '{task_id}' {'completed' if success else 'failed'}: "
                f"{settlement.amount:.2f} credits transferred"
            ),
            credit_delta=settlement.amount if success else 0.0,
            outcome="success" if success else "failure",
        )
        return settlement

    def cancel_task(self, task_id: str, canceller_id: str) -> MarketTask:
        """Cancel an open task (poster only)."""
        return self.market.cancel_task(task_id, AgentId(canceller_id))

    # ── Meta-Constitutional ──────────────────────────────────────────────

    def propose_amendment(
        self,
        proposer_id: str,
        amendment_type: str,
        rationale: str = "",
        invariant_id: str = "",
        description: str = "",
        keywords: list[str] | None = None,
    ) -> Amendment:
        """
        Propose a constitutional amendment (authority-gated at 0.9).

        Args:
            proposer_id: Agent proposing the amendment
            amendment_type: "add_invariant", "remove_invariant",
                            "add_keywords", "remove_keywords"
            rationale: Why this change is needed
            invariant_id: Target invariant (for modifications) or new ID
            description: Description for new invariant
            keywords: Keywords to add/remove or for new invariant
        """
        agent = self._agents.get(AgentId(proposer_id))
        if not agent:
            raise KeyError(f"Agent {proposer_id} not found")
        if agent.authority < MIN_AUTHORITY_TO_AMEND:
            raise PermissionError(
                f"Authority too low to propose amendment: {agent.authority:.2f} "
                f"< {MIN_AUTHORITY_TO_AMEND}"
            )

        kw = keywords or []

        if amendment_type == "add_invariant":
            amendment = self.meta.propose_add_invariant(
                proposer_id=AgentId(proposer_id),
                invariant_id=invariant_id,
                description=description,
                keywords=kw,
                rationale=rationale,
            )
        elif amendment_type == "remove_invariant":
            amendment = self.meta.propose_remove_invariant(
                proposer_id=AgentId(proposer_id),
                invariant_id=invariant_id,
                rationale=rationale,
            )
        elif amendment_type == "add_keywords":
            amendment = self.meta.propose_add_keywords(
                proposer_id=AgentId(proposer_id),
                invariant_id=invariant_id,
                keywords=kw,
                rationale=rationale,
            )
        elif amendment_type == "remove_keywords":
            amendment = self.meta.propose_remove_keywords(
                proposer_id=AgentId(proposer_id),
                invariant_id=invariant_id,
                keywords=kw,
                rationale=rationale,
            )
        else:
            raise ValueError(f"Unknown amendment type: {amendment_type}")

        self.ledger.append(
            agent_id=AgentId(proposer_id),
            action=LedgerAction.CONSTITUTIONAL_AMENDMENT,
            description=(
                f"Amendment proposed: {amendment_type} "
                f"(invariant: {invariant_id or 'new'})"
            ),
            authority_at_time=agent.authority,
            outcome="proposed",
        )
        return amendment

    def review_amendment(self, amendment_id: str) -> Amendment:
        """Constitutional Agent reviews an amendment for violations."""
        amendment = self.meta.review(amendment_id)

        self.ledger.append(
            agent_id=AgentId("constitutional"),
            action=LedgerAction.CONSTITUTIONAL_AMENDMENT,
            description=(
                f"Amendment '{amendment_id}' reviewed: "
                f"{'passed' if amendment.review_passed else 'VETOED'}"
            ),
            outcome="vetoed" if not amendment.review_passed else "review_passed",
        )
        return amendment

    def vote_amendment(
        self,
        amendment_id: str,
        voter_id: str,
        approve: bool,
    ) -> Amendment:
        """Cast a weighted vote on a constitutional amendment."""
        voter = self._agents.get(AgentId(voter_id))
        if not voter:
            raise KeyError(f"Agent {voter_id} not found")

        amendment = self.meta.vote(
            amendment_id=amendment_id,
            voter_id=AgentId(voter_id),
            voter_authority=voter.authority,
            approve=approve,
        )

        self.ledger.append(
            agent_id=AgentId(voter_id),
            action=LedgerAction.CONSTITUTIONAL_AMENDMENT,
            description=(
                f"Voted {'for' if approve else 'against'} "
                f"amendment '{amendment_id}'"
            ),
            authority_at_time=voter.authority,
            outcome="success",
        )
        return amendment

    def apply_amendment(self, amendment_id: str) -> Amendment:
        """
        Finalize and apply a constitutional amendment.

        Automatically finalizes voting, then applies if approved.
        """
        eligible = [a for a in self.get_agents() if a.authority >= 0.6]
        total_weight = sum(a.authority for a in eligible)
        amendment = self.meta.finalize(amendment_id, total_weight)

        if amendment.status.value != "approved":
            self.ledger.append(
                agent_id=AgentId(amendment.proposer_id),
                action=LedgerAction.CONSTITUTIONAL_AMENDMENT,
                description=(
                    f"Amendment '{amendment_id}' {amendment.status.value}"
                ),
                outcome=amendment.status.value,
            )
            return amendment

        # Apply the amendment
        applied = self.meta.apply(amendment_id)

        self.ledger.append(
            agent_id=AgentId(applied.proposer_id),
            action=LedgerAction.CONSTITUTIONAL_AMENDMENT,
            description=(
                f"Amendment '{amendment_id}' applied — "
                f"constitution revision {self.meta.revision}"
            ),
            outcome="applied",
        )
        return applied

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
            "federation": self.federation.get_stats(),
            "reputation": self.reputation.get_stats(),
            "evolution": self.evolution.get_stats(),
            "market": self.market.get_stats(),
            "meta_constitutional": self.meta.get_stats(),
            "events": self.events.get_stats(),
            "plugins": self.plugins.get_stats(),
            "uptime_seconds": round(time.time() - self.created_at, 1),
        }
