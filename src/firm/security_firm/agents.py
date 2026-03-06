"""Agent specifications for the Security Firm.

Defines 4 specialised agents that scan repositories in parallel:
  - security-director  (claude-opus-4.6)   — orchestrates + deep analysis
  - code-scanner       (gpt-5.4)           — line-by-line code review
  - static-analyzer    (gpt-5.3-codex)     — semgrep + deps + configs
  - report-synthesizer (gemini-3.1-pro)    — consolidation + final report

All agents use the ``copilot-pro`` provider (zero API cost).

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

from dataclasses import dataclass

from firm.llm.agent import AgentConfig

# ---------------------------------------------------------------------------
# Agent spec
# ---------------------------------------------------------------------------

@dataclass
class AgentSpec:
    """Declarative agent definition."""

    name: str
    model: str
    provider: str
    initial_authority: float
    description: str
    config: AgentConfig
    mcp_categories: list[str]


# ---------------------------------------------------------------------------
# Role definitions (system prompts)
# ---------------------------------------------------------------------------

_ROLE_DEFS: dict[str, str] = {
    "security-director": (
        "You are the Security Director of a multi-agent security firm.\n"
        "Your responsibilities:\n"
        "1. Map the target repository structure and plan the scan.\n"
        "2. Partition the repo into zones (source, tests, configs, deps).\n"
        "3. Dispatch scan tasks to specialist agents via the FIRM market.\n"
        "4. Analyse complex findings that require deep reasoning.\n"
        "5. Triage and deduplicate all findings — eliminate false positives.\n"
        "6. Make the final severity call on borderline issues.\n"
        "7. Ensure every CRITICAL/HIGH finding has reproduction steps.\n\n"
        "You do NOT scan code yourself — you orchestrate, review, and decide."
    ),
    "code-scanner": (
        "You are the Code Scanner. Review every source file for vulnerabilities:\n"
        "- SQL injection, command injection, SSTI, SSRF\n"
        "- Authentication bypass, broken access control (IDOR, BOLA)\n"
        "- Unsafe deserialization (pickle, yaml.load, eval, exec)\n"
        "- Path traversal (../ in file operations)\n"
        "- Race conditions (TOCTOU, shared mutable state)\n"
        "- Cryptographic misuse (weak hashing, hardcoded keys)\n"
        "- XSS (reflected, stored, DOM-based)\n"
        "- Information disclosure (stack traces, verbose errors)\n\n"
        "For each finding, record: file, line range, code snippet, CWE, severity,\n"
        "impact, and remediation. Use contribute_memory to share findings."
    ),
    "static-analyzer": (
        "You are the Static Analyzer. Focus on automated tooling and configs:\n"
        "- Run semgrep with OWASP and security rulesets\n"
        "- Audit dependencies: requirements.txt, package.json, go.mod, Cargo.toml\n"
        "  → cross-reference known CVEs\n"
        "- Scan for hardcoded secrets (API keys, tokens, passwords, .env files)\n"
        "- Review git history for secrets committed then deleted\n"
        "- Analyse Dockerfile, docker-compose, CI workflows (.github/workflows)\n"
        "- Check file permissions, .gitignore hygiene\n\n"
        "For each finding, record: file, line range, CWE, severity, and remediation.\n"
        "Use contribute_memory to share findings with the team."
    ),
    "report-synthesizer": (
        "You are the Report Synthesizer. Your 1M token context lets you read\n"
        "the ENTIRE repository at once. Your job:\n"
        "1. Read all source files to understand the codebase architecture.\n"
        "2. Recall all findings from team memory.\n"
        "3. Deduplicate: merge findings that describe the same root cause.\n"
        "4. For each unique finding, ensure it has:\n"
        "   - Clear title, CWE ID, CVSS vector + score\n"
        "   - Affected file(s) + line range + code snippet\n"
        "   - Reproduction steps, impact, remediation\n"
        "5. Generate the final Markdown report grouped by severity.\n"
        "6. Include executive summary with risk score and statistics.\n\n"
        "Your output IS the deliverable. Make it professional and actionable."
    ),
}


# ---------------------------------------------------------------------------
# The 4 agents
# ---------------------------------------------------------------------------

SECURITY_AGENTS: list[AgentSpec] = [
    AgentSpec(
        name="security-director",
        model="claude-opus-4.6",
        provider="copilot-pro",
        initial_authority=0.95,
        description="Orchestrator — plans scan, dispatches tasks, triages findings.",
        config=AgentConfig(
            max_iterations=30,
            max_tokens_budget=1_000_000,
            max_cost_usd=10.0,
            temperature=0.2,
            max_response_tokens=8192,
            system_prompt_extra=_ROLE_DEFS["security-director"],
        ),
        mcp_categories=["security", "compliance", "audit"],
    ),
    AgentSpec(
        name="code-scanner",
        model="gpt-5.4",
        provider="copilot-pro",
        initial_authority=0.80,
        description="Code reviewer — scans every source file for vulnerabilities.",
        config=AgentConfig(
            max_iterations=50,
            max_tokens_budget=1_000_000,
            max_cost_usd=10.0,
            temperature=0.1,
            max_response_tokens=4096,
            system_prompt_extra=_ROLE_DEFS["code-scanner"],
        ),
        mcp_categories=["security", "spec"],
    ),
    AgentSpec(
        name="static-analyzer",
        model="gpt-5.3-codex",
        provider="copilot-pro",
        initial_authority=0.75,
        description="Static analysis — semgrep, deps, configs, secrets, git history.",
        config=AgentConfig(
            max_iterations=40,
            max_tokens_budget=1_000_000,
            max_cost_usd=10.0,
            temperature=0.1,
            max_response_tokens=4096,
            system_prompt_extra=_ROLE_DEFS["static-analyzer"],
        ),
        mcp_categories=["security", "observability", "config"],
    ),
    AgentSpec(
        name="report-synthesizer",
        model="gemini-3.1-pro",
        provider="copilot-pro",
        initial_authority=0.70,
        description="Report writer — reads full repo, deduplicates, generates report.",
        config=AgentConfig(
            max_iterations=20,
            max_tokens_budget=1_000_000,
            max_cost_usd=10.0,
            temperature=0.3,
            max_response_tokens=16384,
            system_prompt_extra=_ROLE_DEFS["report-synthesizer"],
        ),
        mcp_categories=["delivery", "security"],
    ),
]


def get_role_def(agent_name: str) -> str:
    """Return the system prompt for *agent_name*."""
    return _ROLE_DEFS.get(agent_name, "")
