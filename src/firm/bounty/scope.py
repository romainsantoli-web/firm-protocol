"""Scope enforcement for bounty hunting.

Ensures every reconnaissance and scanning operation stays within the
programme's authorised scope.  Blocks internal / private IP ranges to
prevent SSRF-style mistakes.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

import yaml

# ---------------------------------------------------------------------------
# Asset types
# ---------------------------------------------------------------------------

class AssetType(str, Enum):
    """H1-compatible asset types."""
    DOMAIN = "domain"
    WILDCARD = "wildcard"
    IP_ADDRESS = "ip_address"
    CIDR = "cidr"
    URL = "url"
    MOBILE = "mobile"
    SOURCE_CODE = "source_code"
    HARDWARE = "hardware"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Asset model
# ---------------------------------------------------------------------------

@dataclass
class Asset:
    """Single in-scope or out-of-scope target."""

    identifier: str
    asset_type: AssetType
    eligible_for_bounty: bool = True
    max_severity: str = "critical"
    notes: str = ""

    # ---- helpers ----

    def matches_domain(self, domain: str) -> bool:
        """Check if *domain* matches this asset (wildcard-aware)."""
        domain = domain.lower().strip(".")
        ident = self.identifier.lower().strip(".")

        if self.asset_type == AssetType.WILDCARD:
            # *.example.com  → matches a.example.com, b.c.example.com
            base = ident.lstrip("*.")
            return domain == base or domain.endswith("." + base)
        if self.asset_type in (AssetType.DOMAIN, AssetType.URL):
            return domain == ident or domain.endswith("." + ident)
        return False

    def matches_ip(self, ip: str) -> bool:
        """Check if *ip* falls inside a CIDR or matches an IP asset."""
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if self.asset_type == AssetType.IP_ADDRESS:
            return addr == ipaddress.ip_address(self.identifier)
        if self.asset_type == AssetType.CIDR:
            return addr in ipaddress.ip_network(self.identifier, strict=False)
        return False


# ---------------------------------------------------------------------------
# Target scope
# ---------------------------------------------------------------------------

@dataclass
class TargetScope:
    """Describes the full scope of a bug-bounty programme."""

    programme_name: str = ""
    programme_handle: str = ""
    in_scope: list[Asset] = field(default_factory=list)
    out_of_scope: list[Asset] = field(default_factory=list)

    # ---- builders ----

    @classmethod
    def from_yaml(cls, path: str | Path) -> "TargetScope":
        """Load from a YAML scope file."""
        data = yaml.safe_load(Path(path).read_text())
        return cls(
            programme_name=data.get("programme_name", ""),
            programme_handle=data.get("programme_handle", ""),
            in_scope=[
                Asset(
                    identifier=a["identifier"],
                    asset_type=AssetType(a.get("type", "domain")),
                    eligible_for_bounty=a.get("eligible", True),
                    max_severity=a.get("max_severity", "critical"),
                    notes=a.get("notes", ""),
                )
                for a in data.get("in_scope", [])
            ],
            out_of_scope=[
                Asset(
                    identifier=a["identifier"],
                    asset_type=AssetType(a.get("type", "domain")),
                    notes=a.get("notes", ""),
                )
                for a in data.get("out_of_scope", [])
            ],
        )

    @classmethod
    def from_hackerone_dict(cls, data: dict) -> "TargetScope":
        """Build from the H1 API ``structured_scopes`` response."""
        scope = cls(
            programme_name=data.get("name", ""),
            programme_handle=data.get("handle", ""),
        )
        for s in data.get("structured_scopes", []):
            asset = Asset(
                identifier=s.get("asset_identifier", ""),
                asset_type=AssetType(s.get("asset_type", "other").lower()),
                eligible_for_bounty=s.get("eligible_for_bounty", False),
                max_severity=s.get("max_severity_guidelines", "critical"),
                notes=s.get("instruction", ""),
            )
            if s.get("eligible_for_submission", True):
                scope.in_scope.append(asset)
            else:
                scope.out_of_scope.append(asset)
        return scope


# ---------------------------------------------------------------------------
# Scope enforcer (middleware)
# ---------------------------------------------------------------------------

# Private / internal ranges — NEVER attack these.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class ScopeEnforcer:
    """Gate-keeper that every tool invocation passes through."""

    def __init__(self, scope: TargetScope):
        self.scope = scope

    # ---- public API ----

    def allow_url(self, url: str) -> bool:
        """Return True only when *url* is in scope."""
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not host:
            return False
        if self._is_blocked_ip(host):
            return False
        if self._is_out_of_scope(host):
            return False
        return self._is_in_scope(host)

    def allow_host(self, host: str) -> bool:
        """Return True only when *host* (domain or IP) is in scope."""
        host = host.lower().strip()
        if self._is_blocked_ip(host):
            return False
        if self._is_out_of_scope(host):
            return False
        return self._is_in_scope(host)

    def allow_command(self, cmd: str) -> bool:
        """Validate that a CLI command only targets in-scope hosts.

        Extracts domain-like and IP-like tokens from the command string
        and checks each one.
        """
        tokens = self._extract_targets(cmd)
        if not tokens:
            return False  # no recognisable target → deny
        return all(self.allow_host(t) for t in tokens)

    # ---- internals ----

    @staticmethod
    def _is_blocked_ip(host: str) -> bool:
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            return False  # not an IP → skip this check
        return any(addr in net for net in _BLOCKED_NETWORKS)

    def _is_out_of_scope(self, host: str) -> bool:
        for asset in self.scope.out_of_scope:
            if asset.matches_domain(host) or asset.matches_ip(host):
                return True
        return False

    def _is_in_scope(self, host: str) -> bool:
        for asset in self.scope.in_scope:
            if asset.matches_domain(host) or asset.matches_ip(host):
                return True
        return False

    @staticmethod
    def _extract_targets(cmd: str) -> list[str]:
        """Best-effort extraction of domain/IP targets from a CLI string."""
        # IP addresses
        ips = re.findall(
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b", cmd
        )
        # domain-like tokens (at least one dot, no leading dash)
        domains = re.findall(
            r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b",
            cmd,
        )
        return list(set(ips + domains))
