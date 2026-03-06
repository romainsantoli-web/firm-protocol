"""BountyFirm factory — creates a FIRM with 8 specialised agents.

Each agent has a designated LLM provider, initial authority, and role
definition.  The factory wires up scope enforcement, vuln database,
dedup engine, triage pipeline, and reward engine.

Agent model names can be overridden at runtime via environment variables.
The variable name is derived from the agent name:
  ``FIRM_<AGENT_NAME_UPPER>_MODEL`` where hyphens are replaced by
  underscores.  For example, to override the ``hunt-director`` model::

      FIRM_HUNT_DIRECTOR_MODEL=gpt-4o python -m firm ...

A global fallback ``FIRM_DEFAULT_MODEL`` applies to any agent whose
specific variable is not set.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from firm.bounty.dedup import DeduplicationEngine
from firm.bounty.reward import RewardEngine
from firm.bounty.scope import ScopeEnforcer, TargetScope
from firm.bounty.tools.scanner import RateLimiter, make_bounty_tools
from firm.bounty.triage import TriagePipeline
from firm.bounty.vulnerability import VulnDatabase

# ---------------------------------------------------------------------------
# Agent specs
# ---------------------------------------------------------------------------

@dataclass
class AgentSpec:
    name: str
    model: str
    initial_authority: float
    description: str


def _resolve_model(agent_name: str, default_model: str) -> str:
    """Return the model to use for *agent_name*.

    Resolution order (first match wins):

    1. ``FIRM_<AGENT_NAME_UPPER>_MODEL`` env var  (hyphens → underscores).
       Example: ``FIRM_HUNT_DIRECTOR_MODEL`` for the ``hunt-director`` agent.
    2. ``FIRM_DEFAULT_MODEL`` env var — applies to **all** agents.
    3. The hard-coded *default_model* built into the factory.
    """
    specific_var = "FIRM_" + agent_name.upper().replace("-", "_") + "_MODEL"
    specific = os.environ.get(specific_var, "").strip()
    if specific:
        return specific
    global_default = os.environ.get("FIRM_DEFAULT_MODEL", "").strip()
    if global_default:
        return global_default
    return default_model


BOUNTY_AGENTS: list[AgentSpec] = [
    AgentSpec(
        name="hunt-director",
        model=_resolve_model("hunt-director", "claude-sonnet-4-20250514"),
        initial_authority=0.90,
        description="Campaign coordinator — plans phases, assigns targets, synthesises results.",
    ),
    AgentSpec(
        name="recon-agent",
        model=_resolve_model("recon-agent", "gpt-4.1"),
        initial_authority=0.70,
        description="Reconnaissance specialist — subdomains, ports, tech stack, URL crawling.",
    ),
    AgentSpec(
        name="web-hunter",
        model=_resolve_model("web-hunter", "claude-sonnet-4-20250514"),
        initial_authority=0.65,
        description="Web vulnerability hunter — SQLi, XSS, SSRF, IDOR on web apps.",
    ),
    AgentSpec(
        name="api-hunter",
        model=_resolve_model("api-hunter", "gpt-4o"),
        initial_authority=0.65,
        description="API vulnerability hunter — auth bypass, BOLA, rate limiting, GraphQL.",
    ),
    AgentSpec(
        name="code-auditor",
        model=_resolve_model("code-auditor", "o4-mini"),
        initial_authority=0.60,
        description="Static code auditor — semgrep, pattern-based detection, dependency audit.",
    ),
    AgentSpec(
        name="mobile-hunter",
        model=_resolve_model("mobile-hunter", "claude-sonnet-4-20250514"),
        initial_authority=0.55,
        description="Mobile app security — APK/IPA analysis, certificate pinning, local storage.",
    ),
    AgentSpec(
        name="web3-hunter",
        model=_resolve_model("web3-hunter", "gpt-4.1"),
        initial_authority=0.55,
        description="Smart contract / blockchain security — reentrancy, flash loans, oracle manipulation.",
    ),
    AgentSpec(
        name="report-writer",
        model=_resolve_model("report-writer", "gpt-4o"),
        initial_authority=0.40,
        description="Report writer — crafts clear, detailed H1 reports with reproduction steps.",
    ),
]


# ---------------------------------------------------------------------------
# Role definitions (injected as system prompts)
# ---------------------------------------------------------------------------

_ROLE_DEFS: dict[str, str] = {
    "hunt-director": (
        "You are the Hunt Director of a bug-bounty FIRM. Your job is to:\n"
        "1. Analyse the target scope and plan a phased campaign.\n"
        "2. Assign reconnaissance tasks to recon-agent.\n"
        "3. Dispatch scan tasks to hunters based on attack surface.\n"
        "4. Synthesise all findings and decide which to escalate.\n"
        "5. Never test out-of-scope targets."
    ),
    "recon-agent": (
        "You are the Recon Agent. Map the attack surface:\n"
        "- Enumerate subdomains (subfinder)\n"
        "- Port scan (nmap)\n"
        "- Detect technologies (httpx)\n"
        "- Crawl URLs (katana)\n"
        "Report findings to hunt-director."
    ),
    "web-hunter": (
        "You are the Web Hunter. Your specialty is web application vulns:\n"
        "- Run nuclei templates for known CVEs\n"
        "- Test for SQLi (sqlmap), XSS (dalfox), SSRF, IDOR\n"
        "- Check authentication and session management\n"
        "- Always verify findings before reporting."
    ),
    "api-hunter": (
        "You are the API Hunter. Focus on API endpoints:\n"
        "- Test authentication bypass (JWT, OAuth misconfig)\n"
        "- BOLA / IDOR on API resources\n"
        "- Rate limiting and business logic flaws\n"
        "- GraphQL introspection and injection"
    ),
    "code-auditor": (
        "You are the Code Auditor. Analyse source code:\n"
        "- Run semgrep with security rules\n"
        "- Check for hardcoded secrets\n"
        "- Review dependency vulnerabilities\n"
        "- Identify unsafe deserialization, path traversal"
    ),
    "mobile-hunter": (
        "You are the Mobile Hunter. Focus on mobile apps:\n"
        "- Decompile APK/IPA\n"
        "- Check certificate pinning\n"
        "- Review local storage and IPC\n"
        "- Test API calls from mobile perspective"
    ),
    "web3-hunter": (
        "You are the Web3 Hunter. Focus on blockchain targets:\n"
        "- Review smart contracts for reentrancy, overflow\n"
        "- Check oracle manipulation vectors\n"
        "- Test flash loan attack paths\n"
        "- Verify access control on privileged functions"
    ),
    "report-writer": (
        "You are the Report Writer. Create HackerOne reports:\n"
        "- Clear title describing the vulnerability\n"
        "- Step-by-step reproduction\n"
        "- Impact assessment with CVSS score\n"
        "- Include evidence (HTTP requests/responses)"
    ),
}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_bounty_firm(
    scope: TargetScope,
    db_path: str = ":memory:",
    rate_limit: float = 10.0,
    rate_burst: int = 20,
) -> dict[str, Any]:
    """Create the full BountyFirm context.

    Returns a dict with all wired components — the caller (or a future
    ``BountyFirm`` class) uses these to run a campaign.

    Keys:
        agents, scope, enforcer, db, dedup, triage, reward,
        tools, role_defs, limiter
    """
    enforcer = ScopeEnforcer(scope)
    limiter = RateLimiter(rate=rate_limit, burst=rate_burst)
    db = VulnDatabase(db_path)
    dedup = DeduplicationEngine(db)
    triage = TriagePipeline()
    reward = RewardEngine()

    tools = make_bounty_tools(enforcer, limiter)

    return {
        "agents": BOUNTY_AGENTS,
        "scope": scope,
        "enforcer": enforcer,
        "db": db,
        "dedup": dedup,
        "triage": triage,
        "reward": reward,
        "tools": tools,
        "role_defs": _ROLE_DEFS,
        "limiter": limiter,
    }
