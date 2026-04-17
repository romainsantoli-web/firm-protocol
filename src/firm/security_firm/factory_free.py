"""Factory for the Free-tier Security Firm.

Same as ``create_security_firm()`` but uses free Copilot Pro models
with 6000-token chunked execution.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

from typing import Any

from firm.security_firm.agents_free import FREE_SECURITY_AGENTS
from firm.security_firm.pipeline_free import ChunkedSecurityPipeline
from firm.security_firm.tools.repo_scanner import make_repo_tools


def create_free_security_firm(
    repo_path: str,
    firm_name: str = "SecurityFirm-Free",
    db_path: str = ":memory:",
    use_mcp: bool = True,
    max_workers: int = 3,
    chunk_budget: int = 6_000,
    max_chunks: int = 15,
) -> dict[str, Any]:
    """Create a Security Firm using free-tier models + chunked execution.

    Models:
      - security-director: gpt-5.4 (premium, unchunked)
      - code-scanner:      gpt-4.1 (free, 6000-token chunks)
      - static-analyzer:   gpt-4o  (free, 6000-token chunks)
      - report-synthesizer: gpt-5-mini (free, 6000-token chunks)

    Returns the same dict shape as ``create_security_firm()``.
    """
    pipeline = ChunkedSecurityPipeline(
        repo_path=repo_path,
        firm_name=firm_name,
        db_path=db_path,
        use_mcp=use_mcp,
        max_workers=max_workers,
        chunk_budget=chunk_budget,
        max_chunks=max_chunks,
    )

    return {
        "pipeline": pipeline,
        "firm": pipeline.firm,
        "agents": FREE_SECURITY_AGENTS,
        "tools": make_repo_tools(),
        "db": pipeline.db,
    }
