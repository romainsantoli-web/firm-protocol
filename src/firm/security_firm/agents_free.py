"""Free-tier agent specifications for the Security Firm.

Uses mostly free Copilot Pro models to minimize cost:
  - security-director  (gpt-5.4)     — orchestrator (only premium model)
  - code-scanner       (gpt-4.1)     — line-by-line code review (free)
  - static-analyzer    (gpt-4o)      — semgrep + deps + configs (free)
  - report-synthesizer (gpt-5-mini)  — consolidation + report (free)

Token budgets are capped at 6000 per chunk to stay within free-tier
rate limits. Agents use Memory OS AI to persist context across chunks.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

from firm.llm.agent import AgentConfig
from firm.security_firm.agents import AgentSpec, _ROLE_DEFS


# ---------------------------------------------------------------------------
# Chunk-aware system prompt addendum
# ---------------------------------------------------------------------------

_CHUNK_PROMPT = (
    "\n\n## IMPORTANT — Chunked Execution\n"
    "You are running in CHUNKED mode with a 6000-token budget per request.\n"
    "After each chunk, your context will be saved to Memory OS AI.\n\n"
    "Rules:\n"
    "1. ALWAYS call contribute_memory to save your findings/progress BEFORE "
    "   your response ends. Do not wait — save incrementally.\n"
    "2. At the START of each chunk, call recall_memory to restore your context.\n"
    "3. Focus on ONE task per chunk. Be concise — avoid verbose explanations.\n"
    "4. If you haven't finished scanning all files, list what's done and "
    "   what remains so the next chunk can continue.\n"
    "5. Prioritize HIGH/CRITICAL findings over comprehensive coverage.\n"
)


# ---------------------------------------------------------------------------
# Free-tier agents (3 free + 1 premium orchestrator)
# ---------------------------------------------------------------------------

FREE_SECURITY_AGENTS: list[AgentSpec] = [
    AgentSpec(
        name="security-director",
        model="gpt-5.4",
        provider="copilot-pro",
        initial_authority=0.95,
        description="Orchestrator — plans scan, dispatches tasks, triages findings. (premium)",
        config=AgentConfig(
            max_iterations=30,
            max_tokens_budget=1_000_000,  # premium model — no chunk limit
            max_cost_usd=10.0,
            temperature=0.2,
            max_response_tokens=8192,
            system_prompt_extra=_ROLE_DEFS["security-director"] + _CHUNK_PROMPT,
        ),
        mcp_categories=["security", "compliance", "audit"],
        memory_categories=["search", "session"],
    ),
    AgentSpec(
        name="code-scanner",
        model="gpt-4.1",
        provider="copilot-pro",
        initial_authority=0.80,
        description="Code reviewer — scans source files for vulnerabilities. (free)",
        config=AgentConfig(
            max_iterations=50,
            max_tokens_budget=6_000,  # chunk budget
            max_cost_usd=0.0,        # free model
            temperature=0.1,
            max_response_tokens=4096,
            system_prompt_extra=_ROLE_DEFS["code-scanner"] + _CHUNK_PROMPT,
        ),
        mcp_categories=["security", "spec"],
        memory_categories=["search", "ingest"],
    ),
    AgentSpec(
        name="static-analyzer",
        model="gpt-4o",
        provider="copilot-pro",
        initial_authority=0.75,
        description="Static analysis — semgrep, deps, configs, secrets. (free)",
        config=AgentConfig(
            max_iterations=40,
            max_tokens_budget=6_000,  # chunk budget
            max_cost_usd=0.0,        # free model
            temperature=0.1,
            max_response_tokens=4096,
            system_prompt_extra=_ROLE_DEFS["static-analyzer"] + _CHUNK_PROMPT,
        ),
        mcp_categories=["security", "observability", "config"],
        memory_categories=["search", "ingest"],
    ),
    AgentSpec(
        name="report-synthesizer",
        model="gpt-5-mini",
        provider="copilot-pro",
        initial_authority=0.70,
        description="Report writer — consolidates findings, generates report. (free)",
        config=AgentConfig(
            max_iterations=20,
            max_tokens_budget=6_000,  # chunk budget
            max_cost_usd=0.0,        # free model
            temperature=0.3,
            max_response_tokens=4096,
            system_prompt_extra=_ROLE_DEFS["report-synthesizer"] + _CHUNK_PROMPT,
        ),
        mcp_categories=["delivery", "security"],
        memory_categories=["search", "session", "chat"],
    ),
]
