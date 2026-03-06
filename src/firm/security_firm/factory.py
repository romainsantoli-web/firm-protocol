"""Factory for the Security Firm.

Provides a simple ``create_security_firm()`` entry point that wires
all components and returns a ready-to-use context dict.
"""

from __future__ import annotations

from typing import Any

from firm.security_firm.agents import SECURITY_AGENTS
from firm.security_firm.pipeline import SecurityPipeline
from firm.security_firm.tools.repo_scanner import make_repo_tools


def create_security_firm(
    repo_path: str,
    firm_name: str = "SecurityFirm",
    db_path: str = ":memory:",
    use_mcp: bool = True,
    max_workers: int = 3,
) -> dict[str, Any]:
    """Create a fully wired Security Firm.

    Returns a dict with all components — the caller uses these to run
    the scan pipeline.

    Keys:
        pipeline   — the ``SecurityPipeline`` instance (call ``.run()``)
        agents     — agent spec definitions
        tools      — list of repo-scanner tool dicts
        db         — the ``FindingsDB`` instance

    Usage::

        from firm.security_firm import create_security_firm

        ctx = create_security_firm("/path/to/repo")
        report = ctx["pipeline"].run()
        print(report)

        # Or access findings directly
        findings = ctx["db"].all()
        stats = ctx["db"].stats()
    """
    pipeline = SecurityPipeline(
        repo_path=repo_path,
        firm_name=firm_name,
        db_path=db_path,
        use_mcp=use_mcp,
        max_workers=max_workers,
    )

    return {
        "pipeline": pipeline,
        "firm": pipeline.firm,
        "agents": SECURITY_AGENTS,
        "tools": make_repo_tools(),
        "db": pipeline.db,
    }
