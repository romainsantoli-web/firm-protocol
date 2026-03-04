"""
firm.core.reputation — Reputation Bridge (Layer 9)

Manages portable agent reputation across FIRMs.
Reputation is never transferred raw — it is attested, discounted,
and independently verified by each receiving FIRM.

Key concepts:
  - **Attestation**: A signed statement from a FIRM about an agent's record
  - **Import Discount**: Foreign reputation is never worth full local value
  - **Decay**: Imported reputation decays faster than local reputation
  - **Verification**: Each FIRM independently validates incoming attestations

Design principles:
  - No FIRM can inflate its agents' reputation externally
  - Attestations are cryptographically hashed for integrity
  - Reputation import requires minimum trust with the source FIRM
  - The receiving FIRM controls the discount factor
  - All reputation changes are auditable
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

# Discount — foreign reputation is never worth full local value
DEFAULT_IMPORT_DISCOUNT = 0.5      # 50% of attested authority
MIN_IMPORT_DISCOUNT = 0.1          # At least 10%
MAX_IMPORT_DISCOUNT = 0.7          # At most 70%

# Trust gate — must trust source FIRM this much to import reputation
MIN_TRUST_TO_IMPORT = 0.4

# Decay — imported reputation decays faster
FOREIGN_REPUTATION_DECAY = 0.05    # 5% per decay cycle (vs 0.2% local)

# Limits
MAX_ATTESTATION_AGE = 86400 * 90   # 90 days — attestations expire
MAX_IMPORTED_AUTHORITY_BOOST = 0.3  # Max authority gain from imports


# ── Enums ────────────────────────────────────────────────────────────────────

class AttestationStatus(str, Enum):
    """Status of a reputation attestation."""
    VALID = "valid"
    EXPIRED = "expired"
    REVOKED = "revoked"
    REJECTED = "rejected"


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ReputationAttestation:
    """
    A signed statement from a source FIRM about an agent's performance.

    Contains the agent's authority, success rate, and action count
    at the time of attestation. Hashed for integrity.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    agent_id: AgentId = field(default_factory=lambda: AgentId(""))
    agent_name: str = ""
    source_firm: FirmId = field(default_factory=lambda: FirmId(""))
    authority: float = 0.0          # Agent's authority in the source FIRM
    success_rate: float = 0.0       # Agent's success rate in the source FIRM
    action_count: int = 0           # Number of recorded actions
    endorsement: str = ""           # Free-text endorsement/context
    created_at: float = field(default_factory=time.time)
    status: AttestationStatus = AttestationStatus.VALID
    attestation_hash: str = ""

    @property
    def age(self) -> float:
        """Age of the attestation in seconds."""
        return time.time() - self.created_at

    @property
    def is_expired(self) -> bool:
        return self.age > MAX_ATTESTATION_AGE

    @property
    def is_valid(self) -> bool:
        return self.status == AttestationStatus.VALID and not self.is_expired

    def compute_hash(self) -> str:
        """Compute integrity hash of the attestation."""
        payload = json.dumps(
            {
                "id": self.id,
                "agent_id": self.agent_id,
                "source_firm": self.source_firm,
                "authority": self.authority,
                "success_rate": self.success_rate,
                "action_count": self.action_count,
                "created_at": self.created_at,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def seal(self) -> None:
        """Compute and set the attestation hash."""
        self.attestation_hash = self.compute_hash()

    def verify(self) -> bool:
        """Verify attestation integrity."""
        if not self.attestation_hash:
            return False
        return self.attestation_hash == self.compute_hash()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "source_firm": self.source_firm,
            "authority": round(self.authority, 4),
            "success_rate": round(self.success_rate, 4),
            "action_count": self.action_count,
            "endorsement": self.endorsement,
            "created_at": self.created_at,
            "status": self.status.value,
            "attestation_hash": self.attestation_hash,
        }


@dataclass
class ImportedReputation:
    """
    A processed reputation import — the discounted authority
    actually granted to an agent from a foreign attestation.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    agent_id: AgentId = field(default_factory=lambda: AgentId(""))
    source_firm: FirmId = field(default_factory=lambda: FirmId(""))
    attestation_id: str = ""
    original_authority: float = 0.0     # From the attestation
    discount_factor: float = DEFAULT_IMPORT_DISCOUNT
    effective_authority: float = 0.0    # What's actually applied
    imported_at: float = field(default_factory=time.time)
    current_weight: float = 1.0        # Decays over time

    @property
    def weighted_authority(self) -> float:
        """Current effective authority after decay."""
        return self.effective_authority * self.current_weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "source_firm": self.source_firm,
            "attestation_id": self.attestation_id,
            "original_authority": round(self.original_authority, 4),
            "discount_factor": round(self.discount_factor, 4),
            "effective_authority": round(self.effective_authority, 4),
            "current_weight": round(self.current_weight, 4),
            "weighted_authority": round(self.weighted_authority, 4),
            "imported_at": self.imported_at,
        }


# ── Reputation Bridge ────────────────────────────────────────────────────────

class ReputationBridge:
    """
    Manages cross-FIRM agent reputation.

    Responsibilities:
     - Issue attestations for local agents (outbound)
     - Validate and import foreign attestations (inbound)
     - Apply discount factors based on trust level
     - Decay imported reputation over time
     - Track reputation provenance for auditability
    """

    def __init__(self, home_firm_id: FirmId) -> None:
        self._home_id = home_firm_id
        # Attestations this FIRM has issued (outbound)
        self._issued: list[ReputationAttestation] = []
        # Attestations received from other FIRMs (inbound)
        self._received: list[ReputationAttestation] = []
        # Processed imports — actual authority adjustments
        self._imports: dict[str, ImportedReputation] = {}  # keyed by import id
        # Per-agent import tracking
        self._agent_imports: dict[str, list[str]] = {}  # agent_id → [import_ids]

    # ── Issue attestations (outbound) ────────────────────────────────────

    def issue_attestation(
        self,
        agent_id: AgentId,
        agent_name: str,
        authority: float,
        success_rate: float,
        action_count: int,
        endorsement: str = "",
    ) -> ReputationAttestation:
        """
        Issue a reputation attestation for a local agent.

        This creates a sealed (hashed) statement about the agent's
        current standing that can be shared with peer FIRMs.
        """
        if authority < 0.0 or authority > 1.0:
            raise ValueError(f"Authority must be in [0, 1], got {authority}")
        if success_rate < 0.0 or success_rate > 1.0:
            raise ValueError(f"Success rate must be in [0, 1], got {success_rate}")
        if action_count < 0:
            raise ValueError(f"Action count must be non-negative, got {action_count}")

        attestation = ReputationAttestation(
            agent_id=agent_id,
            agent_name=agent_name,
            source_firm=self._home_id,
            authority=authority,
            success_rate=success_rate,
            action_count=action_count,
            endorsement=endorsement,
        )
        attestation.seal()
        self._issued.append(attestation)

        logger.info(
            "Issued attestation %s for agent '%s' (auth=%.2f, sr=%.2f)",
            attestation.id, agent_name, authority, success_rate,
        )
        return attestation

    def revoke_attestation(self, attestation_id: str) -> ReputationAttestation:
        """Revoke a previously issued attestation."""
        att = next((a for a in self._issued if a.id == attestation_id), None)
        if not att:
            raise KeyError(f"Attestation '{attestation_id}' not found")
        if att.status == AttestationStatus.REVOKED:
            raise ValueError(f"Attestation '{attestation_id}' already revoked")
        att.status = AttestationStatus.REVOKED
        logger.info("Attestation '%s' revoked", attestation_id)
        return att

    def get_issued(
        self,
        agent_id: AgentId | None = None,
        valid_only: bool = False,
    ) -> list[ReputationAttestation]:
        """List issued attestations."""
        result = self._issued
        if agent_id:
            result = [a for a in result if a.agent_id == agent_id]
        if valid_only:
            result = [a for a in result if a.is_valid]
        return result

    # ── Import attestations (inbound) ────────────────────────────────────

    def import_attestation(
        self,
        attestation: ReputationAttestation,
        peer_trust: float,
        discount: float | None = None,
    ) -> ImportedReputation:
        """
        Import a foreign attestation and compute discounted authority.

        Args:
            attestation: The foreign attestation to import
            peer_trust: Current trust level with the source FIRM
            discount: Override discount factor (default: trust-scaled)

        Returns:
            ImportedReputation with the effective authority to apply.

        Raises:
            PermissionError: Trust too low
            ValueError: Invalid or tampered attestation
        """
        # Validate integrity
        if not attestation.verify():
            raise ValueError("Attestation integrity check failed — possible tampering")

        # Check validity
        if attestation.status != AttestationStatus.VALID:
            raise ValueError(
                f"Attestation status is '{attestation.status.value}', expected 'valid'"
            )
        if attestation.is_expired:
            raise ValueError("Attestation has expired")

        # Trust gate
        if peer_trust < MIN_TRUST_TO_IMPORT:
            raise PermissionError(
                f"Trust too low to import: {peer_trust:.2f} < {MIN_TRUST_TO_IMPORT}"
            )

        # Check for duplicate import
        for imp in self._imports.values():
            if imp.attestation_id == attestation.id:
                raise ValueError(
                    f"Attestation '{attestation.id}' already imported"
                )

        # Compute discount factor — scaled by trust
        if discount is None:
            # Higher trust → lower discount (more generous)
            # trust 0.4 → discount 0.3, trust 1.0 → discount 0.7
            discount = MIN_IMPORT_DISCOUNT + (
                (MAX_IMPORT_DISCOUNT - MIN_IMPORT_DISCOUNT) * peer_trust
            )
        discount = max(MIN_IMPORT_DISCOUNT, min(MAX_IMPORT_DISCOUNT, discount))

        effective = attestation.authority * discount

        # Cap the boost
        agent_id = attestation.agent_id
        current_total = self._get_agent_imported_authority(agent_id)
        if current_total + effective > MAX_IMPORTED_AUTHORITY_BOOST:
            effective = max(0.0, MAX_IMPORTED_AUTHORITY_BOOST - current_total)

        imp = ImportedReputation(
            agent_id=agent_id,
            source_firm=attestation.source_firm,
            attestation_id=attestation.id,
            original_authority=attestation.authority,
            discount_factor=discount,
            effective_authority=effective,
        )
        self._imports[imp.id] = imp
        self._received.append(attestation)

        # Track per-agent
        if agent_id not in self._agent_imports:
            self._agent_imports[agent_id] = []
        self._agent_imports[agent_id].append(imp.id)

        logger.info(
            "Imported reputation for '%s' from '%s': %.4f × %.2f = %.4f effective",
            agent_id, attestation.source_firm,
            attestation.authority, discount, effective,
        )
        return imp

    def _get_agent_imported_authority(self, agent_id: AgentId) -> float:
        """Sum of all active imported authority for an agent."""
        import_ids = self._agent_imports.get(agent_id, [])
        total = 0.0
        for iid in import_ids:
            imp = self._imports.get(iid)
            if imp:
                total += imp.weighted_authority
        return total

    def get_agent_reputation_summary(
        self,
        agent_id: AgentId,
        local_authority: float,
    ) -> dict[str, Any]:
        """
        Get combined reputation for an agent (local + imported).

        Returns a summary showing local authority, imported authority,
        and the combined effective authority.
        """
        imported = self._get_agent_imported_authority(agent_id)
        import_ids = self._agent_imports.get(agent_id, [])
        sources = []
        for iid in import_ids:
            imp = self._imports.get(iid)
            if imp and imp.weighted_authority > 0:
                sources.append(imp.to_dict())

        combined = min(1.0, local_authority + imported)

        return {
            "agent_id": agent_id,
            "local_authority": round(local_authority, 4),
            "imported_authority": round(imported, 4),
            "combined_authority": round(combined, 4),
            "import_count": len(import_ids),
            "sources": sources,
        }

    # ── Decay ────────────────────────────────────────────────────────────

    def apply_decay(self) -> dict[str, float]:
        """
        Decay all imported reputation entries.

        Imported reputation decays faster than local authority,
        ensuring agents can't coast on foreign achievements.

        Returns mapping of import_id → new weighted authority.
        """
        results = {}
        for imp in self._imports.values():
            if imp.current_weight > 0.0:
                imp.current_weight = max(
                    0.0,
                    imp.current_weight - FOREIGN_REPUTATION_DECAY,
                )
                results[imp.id] = round(imp.weighted_authority, 4)
        return results

    # ── Queries ──────────────────────────────────────────────────────────

    def get_imports(
        self,
        agent_id: AgentId | None = None,
        source_firm: FirmId | None = None,
    ) -> list[ImportedReputation]:
        """List imported reputations, optionally filtered."""
        result = list(self._imports.values())
        if agent_id:
            result = [r for r in result if r.agent_id == agent_id]
        if source_firm:
            result = [r for r in result if r.source_firm == source_firm]
        return result

    def get_received_attestations(
        self,
        valid_only: bool = False,
    ) -> list[ReputationAttestation]:
        """List received attestations."""
        result = self._received
        if valid_only:
            result = [a for a in result if a.is_valid]
        return result

    # ── Stats ────────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get reputation bridge statistics."""
        active_imports = [
            imp for imp in self._imports.values()
            if imp.weighted_authority > 0
        ]
        total_imported = sum(imp.weighted_authority for imp in active_imports)

        return {
            "home_firm": self._home_id,
            "issued_attestations": len(self._issued),
            "received_attestations": len(self._received),
            "active_imports": len(active_imports),
            "total_imports": len(self._imports),
            "total_imported_authority": round(total_imported, 4),
            "agents_with_imports": len(self._agent_imports),
        }
