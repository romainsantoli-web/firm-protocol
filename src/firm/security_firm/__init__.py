"""FIRM Security Firm — Multi-agent repository security scanner.

Orchestrates 4 specialised LLM agents through FIRM Protocol to scan
Git repositories for vulnerabilities, misconfigurations, and secrets.

Agents:
  - security-director  (claude-opus-4.6)   — orchestrates + triages
  - code-scanner       (gpt-5.4)           — code review
  - static-analyzer    (gpt-5.3-codex)     — semgrep + deps + secrets
  - report-synthesizer (gemini-3.1-pro)    — final report

All agents run via copilot-pro (zero API cost), with 1M tokens each.

Usage::

    from firm.security_firm import create_security_firm

    ctx = create_security_firm("/path/to/repo")
    report = ctx["pipeline"].run()
    print(report)

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

__version__ = "0.1.0"

from firm.security_firm.agents import SECURITY_AGENTS, AgentSpec, get_role_def
from firm.security_firm.factory import create_security_firm
from firm.security_firm.findings import (
    Finding,
    FindingsDB,
    FindingStatus,
    Severity,
)
from firm.security_firm.pipeline import SecurityPipeline
from firm.security_firm.report import ReportGenerator
from firm.security_firm.tools.repo_scanner import make_repo_tools

__all__ = [
    # Factory
    "create_security_firm",
    # Pipeline
    "SecurityPipeline",
    # Agents
    "SECURITY_AGENTS",
    "AgentSpec",
    "get_role_def",
    # Findings
    "Finding",
    "FindingsDB",
    "FindingStatus",
    "Severity",
    # Report
    "ReportGenerator",
    # Tools
    "make_repo_tools",
]
