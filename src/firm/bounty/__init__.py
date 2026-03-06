"""FIRM BountyHunter Module — Multi-agent bug bounty hunting platform.

Orchestrates specialised AI agents through FIRM Protocol to discover,
triage, deduplicate and report security vulnerabilities on bug-bounty
programmes (HackerOne, Bugcrowd, Intigriti …).

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

__version__ = "0.1.0"

from firm.bounty.campaign import Campaign, CampaignPhase, CampaignStats
from firm.bounty.dedup import DeduplicationEngine
from firm.bounty.factory import BOUNTY_AGENTS, create_bounty_firm
from firm.bounty.reward import RewardEngine
from firm.bounty.scope import (
    Asset,
    AssetType,
    ScopeEnforcer,
    TargetScope,
)
from firm.bounty.triage import TriagePipeline
from firm.bounty.vulnerability import (
    CVSSVector,
    VulnDatabase,
    Vulnerability,
    VulnSeverity,
    VulnStatus,
)

__all__ = [
    # Scope
    "AssetType",
    "Asset",
    "TargetScope",
    "ScopeEnforcer",
    # Vulnerability
    "CVSSVector",
    "VulnSeverity",
    "VulnStatus",
    "Vulnerability",
    "VulnDatabase",
    # Pipeline
    "DeduplicationEngine",
    "TriagePipeline",
    # Campaign
    "Campaign",
    "CampaignPhase",
    "CampaignStats",
    # Reward
    "RewardEngine",
    # Factory
    "create_bounty_firm",
    "BOUNTY_AGENTS",
]
