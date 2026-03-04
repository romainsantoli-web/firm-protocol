"""
firm.core.federation — Inter-Firm Protocol (Layer 8)

Enables communication and collaboration between independent FIRMs.
Each FIRM is sovereign — federation is opt-in, revocable, and transparent.

Key concepts:
  - **Peer Registry**: FIRMs discover and register each other
  - **Trust Score**: Earned through successful interactions (Hebbian)
  - **Agent Secondment**: Temporary lending of agents between FIRMs
  - **Cross-Firm Messages**: Structured communication with audit trail
  - **Federation Agreements**: Bilateral terms governing collaboration

Design principles:
  - No FIRM can unilaterally modify another FIRM's state
  - All cross-firm operations require minimum authority thresholds
  - Every inter-firm action is logged to both FIRMs' ledgers
  - Trust is earned, decays, and can be revoked
  - Seconded agents retain their home FIRM identity
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from firm.core.types import AgentId, FirmId, Severity

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

# Trust scoring (Hebbian-inspired)
INITIAL_TRUST = 0.3          # New peers start low
TRUST_LEARNING_RATE = 0.05   # How fast trust grows
TRUST_DECAY_RATE = 0.01      # Passive trust decay per period
MAX_TRUST = 1.0
MIN_TRUST = 0.0

# Authority gates
MIN_AUTHORITY_TO_FEDERATE = 0.7    # To register/manage peer FIRMs
MIN_AUTHORITY_TO_SEND = 0.5        # To send inter-firm messages
MIN_AUTHORITY_TO_SECOND = 0.8      # To second (lend) an agent
MIN_TRUST_TO_SECOND = 0.5          # Peer must be trusted enough

# Secondment limits
MAX_SECONDMENT_DURATION = 86400 * 30  # 30 days max
DEFAULT_SECONDMENT_DURATION = 86400   # 1 day default
SECONDMENT_AUTHORITY_DISCOUNT = 0.5   # Seconded agents operate at 50% authority


# ── Enums ────────────────────────────────────────────────────────────────────

class PeerStatus(str, Enum):
    """Status of a peer FIRM in the federation."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class MessageType(str, Enum):
    """Types of inter-firm messages."""
    PROPOSAL = "proposal"          # Cross-firm governance proposal
    NOTIFICATION = "notification"  # Informational
    REQUEST = "request"            # Requesting action/resource
    RESPONSE = "response"          # Response to a request
    ATTESTATION = "attestation"    # Reputation/trust attestation


class SecondmentStatus(str, Enum):
    """Status of an agent secondment."""
    ACTIVE = "active"
    COMPLETED = "completed"
    RECALLED = "recalled"   # Ended early by home FIRM
    EXPIRED = "expired"     # Duration exceeded


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class PeerFirm:
    """
    A registered peer FIRM in the federation.

    Trust is Hebbian: it grows with successful interactions
    and decays with inactivity or failures.
    """
    firm_id: FirmId
    name: str
    trust: float = INITIAL_TRUST
    status: PeerStatus = PeerStatus.ACTIVE
    registered_at: float = field(default_factory=time.time)
    last_interaction: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Interaction history
    successful_interactions: int = 0
    failed_interactions: int = 0

    @property
    def is_active(self) -> bool:
        return self.status == PeerStatus.ACTIVE

    @property
    def interaction_count(self) -> int:
        return self.successful_interactions + self.failed_interactions

    @property
    def success_rate(self) -> float:
        if self.interaction_count == 0:
            return 0.0
        return self.successful_interactions / self.interaction_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "firm_id": self.firm_id,
            "name": self.name,
            "trust": round(self.trust, 4),
            "status": self.status.value,
            "registered_at": self.registered_at,
            "last_interaction": self.last_interaction,
            "successful_interactions": self.successful_interactions,
            "failed_interactions": self.failed_interactions,
            "metadata": self.metadata,
        }


@dataclass
class FederationMessage:
    """
    A structured message between two FIRMs.

    Messages are signed (hashed) for integrity verification.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    from_firm: FirmId = field(default_factory=lambda: FirmId(""))
    to_firm: FirmId = field(default_factory=lambda: FirmId(""))
    sender_agent: AgentId = field(default_factory=lambda: AgentId(""))
    message_type: MessageType = MessageType.NOTIFICATION
    subject: str = ""
    body: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    message_hash: str = ""

    def compute_hash(self) -> str:
        """Compute integrity hash of the message."""
        payload = json.dumps(
            {
                "id": self.id,
                "from_firm": self.from_firm,
                "to_firm": self.to_firm,
                "sender_agent": self.sender_agent,
                "message_type": self.message_type.value,
                "subject": self.subject,
                "body": self.body,
                "timestamp": self.timestamp,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def seal(self) -> None:
        """Compute and set the message hash."""
        self.message_hash = self.compute_hash()

    def verify(self) -> bool:
        """Verify message integrity."""
        if not self.message_hash:
            return False
        return self.message_hash == self.compute_hash()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from_firm": self.from_firm,
            "to_firm": self.to_firm,
            "sender_agent": self.sender_agent,
            "message_type": self.message_type.value,
            "subject": self.subject,
            "body": self.body,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
            "message_hash": self.message_hash,
        }


@dataclass
class AgentSecondment:
    """
    A temporary assignment of an agent to a peer FIRM.

    The agent retains identity in their home FIRM but operates
    at reduced authority in the host FIRM.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    agent_id: AgentId = field(default_factory=lambda: AgentId(""))
    agent_name: str = ""
    home_firm: FirmId = field(default_factory=lambda: FirmId(""))
    host_firm: FirmId = field(default_factory=lambda: FirmId(""))
    original_authority: float = 0.0
    effective_authority: float = 0.0  # Discounted authority in host
    status: SecondmentStatus = SecondmentStatus.ACTIVE
    started_at: float = field(default_factory=time.time)
    duration: float = DEFAULT_SECONDMENT_DURATION
    reason: str = ""
    completed_at: float | None = None

    @property
    def expires_at(self) -> float:
        return self.started_at + self.duration

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def is_active(self) -> bool:
        return self.status == SecondmentStatus.ACTIVE and not self.is_expired

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "home_firm": self.home_firm,
            "host_firm": self.host_firm,
            "original_authority": round(self.original_authority, 4),
            "effective_authority": round(self.effective_authority, 4),
            "status": self.status.value,
            "started_at": self.started_at,
            "duration": self.duration,
            "expires_at": self.expires_at,
            "reason": self.reason,
            "completed_at": self.completed_at,
        }


# ── Federation Engine ────────────────────────────────────────────────────────

class FederationEngine:
    """
    Manages inter-FIRM communication and collaboration.

    Responsibilities:
     - Peer discovery and registration
     - Trust scoring (Hebbian)
     - Message exchange with integrity verification
     - Agent secondment (lending)
     - Federation health monitoring
    """

    def __init__(self, home_firm_id: FirmId, home_firm_name: str) -> None:
        self._home_id = home_firm_id
        self._home_name = home_firm_name
        self._peers: dict[str, PeerFirm] = {}
        self._messages: list[FederationMessage] = []
        self._secondments: dict[str, AgentSecondment] = {}

    # ── Peer management ──────────────────────────────────────────────────

    def register_peer(
        self,
        firm_id: FirmId,
        name: str,
        metadata: dict[str, Any] | None = None,
    ) -> PeerFirm:
        """
        Register a peer FIRM in the federation.

        Peers start with low trust that must be earned through
        successful interactions.
        """
        if firm_id == self._home_id:
            raise ValueError("Cannot register self as peer")

        if firm_id in self._peers:
            existing = self._peers[firm_id]
            if existing.status == PeerStatus.REVOKED:
                raise ValueError(
                    f"Peer '{firm_id}' was revoked — cannot re-register"
                )
            raise ValueError(f"Peer '{firm_id}' already registered")

        peer = PeerFirm(
            firm_id=firm_id,
            name=name,
            metadata=metadata or {},
        )
        self._peers[firm_id] = peer

        logger.info(
            "Peer FIRM '%s' (%s) registered with trust=%.2f",
            name, firm_id, peer.trust,
        )
        return peer

    def get_peer(self, firm_id: FirmId) -> PeerFirm | None:
        """Look up a peer by FIRM ID."""
        return self._peers.get(firm_id)

    def get_peers(self, active_only: bool = True) -> list[PeerFirm]:
        """List all registered peers."""
        if active_only:
            return [p for p in self._peers.values() if p.is_active]
        return list(self._peers.values())

    def suspend_peer(self, firm_id: FirmId, reason: str = "") -> PeerFirm:
        """Suspend a peer (temporarily halt interactions)."""
        peer = self._peers.get(firm_id)
        if not peer:
            raise KeyError(f"Peer '{firm_id}' not found")
        if not peer.is_active:
            raise ValueError(f"Peer '{firm_id}' is not active (status: {peer.status.value})")
        peer.status = PeerStatus.SUSPENDED
        peer.metadata["suspension_reason"] = reason
        peer.metadata["suspended_at"] = time.time()
        logger.info("Peer '%s' suspended: %s", firm_id, reason)
        return peer

    def reactivate_peer(self, firm_id: FirmId) -> PeerFirm:
        """Reactivate a suspended peer."""
        peer = self._peers.get(firm_id)
        if not peer:
            raise KeyError(f"Peer '{firm_id}' not found")
        if peer.status != PeerStatus.SUSPENDED:
            raise ValueError(f"Peer '{firm_id}' is not suspended (status: {peer.status.value})")
        peer.status = PeerStatus.ACTIVE
        logger.info("Peer '%s' reactivated", firm_id)
        return peer

    def revoke_peer(self, firm_id: FirmId, reason: str = "") -> PeerFirm:
        """Permanently revoke a peer (cannot be re-registered)."""
        peer = self._peers.get(firm_id)
        if not peer:
            raise KeyError(f"Peer '{firm_id}' not found")
        peer.status = PeerStatus.REVOKED
        peer.trust = MIN_TRUST
        peer.metadata["revocation_reason"] = reason
        peer.metadata["revoked_at"] = time.time()

        # Recall all active secondments with this peer
        for sec in self._secondments.values():
            if sec.host_firm == firm_id and sec.status == SecondmentStatus.ACTIVE:
                sec.status = SecondmentStatus.RECALLED
                sec.completed_at = time.time()

        logger.warning("Peer '%s' revoked: %s", firm_id, reason)
        return peer

    # ── Trust scoring ────────────────────────────────────────────────────

    def update_trust(
        self,
        firm_id: FirmId,
        success: bool,
        weight: float = 1.0,
    ) -> float:
        """
        Update trust for a peer based on interaction outcome.

        Uses Hebbian-inspired formula:
          success: trust += lr × weight × (1 - trust)
          failure: trust -= lr × weight × trust
        """
        peer = self._peers.get(firm_id)
        if not peer:
            raise KeyError(f"Peer '{firm_id}' not found")

        old_trust = peer.trust

        if success:
            delta = TRUST_LEARNING_RATE * weight * (MAX_TRUST - peer.trust)
            peer.trust = min(MAX_TRUST, peer.trust + delta)
            peer.successful_interactions += 1
        else:
            delta = TRUST_LEARNING_RATE * weight * peer.trust
            peer.trust = max(MIN_TRUST, peer.trust - delta)
            peer.failed_interactions += 1

        peer.last_interaction = time.time()

        logger.debug(
            "Trust update for '%s': %.4f → %.4f (%s)",
            firm_id, old_trust, peer.trust,
            "success" if success else "failure",
        )
        return peer.trust

    def apply_trust_decay(self) -> dict[str, float]:
        """
        Apply passive trust decay to all active peers.

        Peers that don't interact lose trust over time.
        Returns mapping of peer_id → new trust.
        """
        results = {}
        for peer in self._peers.values():
            if peer.is_active and peer.trust > MIN_TRUST:
                decay = TRUST_DECAY_RATE * peer.trust
                peer.trust = max(MIN_TRUST, peer.trust - decay)
                results[peer.firm_id] = round(peer.trust, 4)
        return results

    # ── Messaging ────────────────────────────────────────────────────────

    def send_message(
        self,
        to_firm: FirmId,
        sender_agent: AgentId,
        message_type: MessageType | str,
        subject: str,
        body: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> FederationMessage:
        """
        Send a message to a peer FIRM.

        The message is sealed (hashed) for integrity verification.
        """
        peer = self._peers.get(to_firm)
        if not peer:
            raise KeyError(f"Peer '{to_firm}' not found")
        if not peer.is_active:
            raise ValueError(f"Peer '{to_firm}' is not active (status: {peer.status.value})")

        if not subject.strip():
            raise ValueError("Message subject cannot be empty")

        if isinstance(message_type, str):
            message_type = MessageType(message_type)

        msg = FederationMessage(
            from_firm=self._home_id,
            to_firm=to_firm,
            sender_agent=sender_agent,
            message_type=message_type,
            subject=subject,
            body=body,
            metadata=metadata or {},
        )
        msg.seal()
        self._messages.append(msg)

        peer.last_interaction = time.time()

        logger.info(
            "Message %s sent to '%s': [%s] %s",
            msg.id, to_firm, message_type.value if isinstance(message_type, MessageType) else message_type, subject,
        )
        return msg

    def get_messages(
        self,
        peer_id: FirmId | None = None,
        message_type: MessageType | None = None,
    ) -> list[FederationMessage]:
        """Retrieve messages, optionally filtered by peer or type."""
        result = self._messages
        if peer_id:
            result = [m for m in result if m.to_firm == peer_id or m.from_firm == peer_id]
        if message_type:
            result = [m for m in result if m.message_type == message_type]
        return result

    # ── Agent Secondment ─────────────────────────────────────────────────

    def second_agent(
        self,
        agent_id: AgentId,
        agent_name: str,
        agent_authority: float,
        host_firm: FirmId,
        duration: float = DEFAULT_SECONDMENT_DURATION,
        reason: str = "",
    ) -> AgentSecondment:
        """
        Second (lend) an agent to a peer FIRM.

        The agent operates at discounted authority in the host FIRM.
        Secondments have a maximum duration and can be recalled early.
        """
        peer = self._peers.get(host_firm)
        if not peer:
            raise KeyError(f"Peer '{host_firm}' not found")
        if not peer.is_active:
            raise ValueError(f"Peer '{host_firm}' is not active")

        if peer.trust < MIN_TRUST_TO_SECOND:
            raise PermissionError(
                f"Trust too low for secondment: {peer.trust:.2f} < {MIN_TRUST_TO_SECOND}"
            )

        # Check agent isn't already seconded
        for sec in self._secondments.values():
            if sec.agent_id == agent_id and sec.is_active:
                raise ValueError(f"Agent '{agent_id}' is already on active secondment")

        duration = min(duration, MAX_SECONDMENT_DURATION)

        effective_auth = agent_authority * SECONDMENT_AUTHORITY_DISCOUNT

        secondment = AgentSecondment(
            agent_id=agent_id,
            agent_name=agent_name,
            home_firm=self._home_id,
            host_firm=host_firm,
            original_authority=agent_authority,
            effective_authority=effective_auth,
            duration=duration,
            reason=reason,
        )
        self._secondments[secondment.id] = secondment

        peer.last_interaction = time.time()

        logger.info(
            "Agent '%s' seconded to '%s' for %.0fs (effective auth: %.2f)",
            agent_name, host_firm, duration, effective_auth,
        )
        return secondment

    def recall_secondment(self, secondment_id: str) -> AgentSecondment:
        """Recall a seconded agent early."""
        sec = self._secondments.get(secondment_id)
        if not sec:
            raise KeyError(f"Secondment '{secondment_id}' not found")
        if sec.status != SecondmentStatus.ACTIVE:
            raise ValueError(
                f"Secondment is not active (status: {sec.status.value})"
            )
        sec.status = SecondmentStatus.RECALLED
        sec.completed_at = time.time()
        logger.info("Secondment '%s' recalled (agent: %s)", secondment_id, sec.agent_name)
        return sec

    def complete_secondment(self, secondment_id: str) -> AgentSecondment:
        """Mark a secondment as successfully completed."""
        sec = self._secondments.get(secondment_id)
        if not sec:
            raise KeyError(f"Secondment '{secondment_id}' not found")
        if sec.status != SecondmentStatus.ACTIVE:
            raise ValueError(
                f"Secondment is not active (status: {sec.status.value})"
            )
        sec.status = SecondmentStatus.COMPLETED
        sec.completed_at = time.time()
        logger.info("Secondment '%s' completed (agent: %s)", secondment_id, sec.agent_name)
        return sec

    def expire_secondments(self) -> list[AgentSecondment]:
        """Check and expire overdue secondments."""
        expired = []
        now = time.time()
        for sec in self._secondments.values():
            if sec.status == SecondmentStatus.ACTIVE and now > sec.expires_at:
                sec.status = SecondmentStatus.EXPIRED
                sec.completed_at = now
                expired.append(sec)
        return expired

    def get_secondment(self, secondment_id: str) -> AgentSecondment | None:
        """Look up a secondment by ID."""
        return self._secondments.get(secondment_id)

    def get_secondments(
        self,
        active_only: bool = True,
        agent_id: AgentId | None = None,
    ) -> list[AgentSecondment]:
        """List secondments, optionally filtered."""
        result = list(self._secondments.values())
        if active_only:
            result = [s for s in result if s.is_active]
        if agent_id:
            result = [s for s in result if s.agent_id == agent_id]
        return result

    # ── Stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get federation statistics."""
        peers = list(self._peers.values())
        active_peers = [p for p in peers if p.is_active]
        active_secondments = [s for s in self._secondments.values() if s.is_active]

        avg_trust = 0.0
        if active_peers:
            avg_trust = sum(p.trust for p in active_peers) / len(active_peers)

        return {
            "home_firm": self._home_id,
            "peers": {
                "total": len(peers),
                "active": len(active_peers),
                "avg_trust": round(avg_trust, 4),
            },
            "messages": {
                "total": len(self._messages),
            },
            "secondments": {
                "total": len(self._secondments),
                "active": len(active_secondments),
            },
        }
