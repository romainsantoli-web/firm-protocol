"""Chunked security pipeline for free-tier models.

Extends ``SecurityPipeline`` with a chunked execution strategy:
each free-tier agent runs in repeated 6000-token batches, saving
progress to Memory OS AI between chunks. The premium orchestrator
(gpt-5.4) runs unchunked.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from firm.llm.agent import AgentConfig, LLMAgent, create_llm_agent
from firm.llm.executor import ExecutionResult, ExecutionStatus
from firm.llm.tools import ToolKit
from firm.runtime import Firm
from firm.security_firm.agents_free import FREE_SECURITY_AGENTS
from firm.security_firm.findings import Finding, FindingsDB
from firm.security_firm.pipeline import (
    SecurityPipeline,
    _register_memory_tools,
    _register_repo_tools,
)
from firm.security_firm.report import ReportGenerator

logger = logging.getLogger(__name__)

# Max tokens per chunk for free-tier agents
CHUNK_TOKEN_BUDGET = 6_000

# Number of chunks per free agent (max attempts before giving up)
MAX_CHUNKS = 15


class ChunkedSecurityPipeline(SecurityPipeline):
    """Multi-agent security pipeline with chunked execution for free models.

    The key difference: free-tier agents (code-scanner, static-analyzer,
    report-synthesizer) execute in multiple 6000-token chunks. Between
    chunks, progress is saved to FIRM shared memory so the next chunk
    can resume where the previous one left off.

    The premium orchestrator (security-director, gpt-5.4) runs unchunked.
    """

    def __init__(
        self,
        repo_path: str,
        firm_name: str = "SecurityFirm-Free",
        db_path: str = ":memory:",
        use_mcp: bool = True,
        max_workers: int = 3,
        chunk_budget: int = CHUNK_TOKEN_BUDGET,
        max_chunks: int = MAX_CHUNKS,
    ) -> None:
        # Don't call super().__init__() — we override _create_agents to use FREE_SECURITY_AGENTS
        self.repo_path = str(Path(repo_path).resolve())
        self.repo_name = Path(self.repo_path).name
        self.firm_name = firm_name
        self.use_mcp = use_mcp
        self.max_workers = max_workers
        self.chunk_budget = chunk_budget
        self.max_chunks = max_chunks

        # Core state
        self.firm = Firm(firm_name)
        self.db = FindingsDB(db_path)
        self.agents: dict[str, LLMAgent] = {}
        self._start_time = 0.0

        # Track which agents are premium (unchunked) vs free (chunked)
        self._premium_agents: set[str] = set()
        self._free_agents: set[str] = set()

        # Wire up with free agents
        self._create_agents()

    def _create_agents(self) -> None:
        """Instantiate agents using FREE_SECURITY_AGENTS specs."""
        for spec in FREE_SECURITY_AGENTS:
            agent = create_llm_agent(
                firm=self.firm,
                name=spec.name,
                provider_name=spec.provider,
                model=spec.model,
                authority=spec.initial_authority,
                working_dir=self.repo_path,
                config=spec.config,
            )

            # Register tools
            _register_repo_tools(agent._toolkit, self.repo_path)
            _register_memory_tools(agent._toolkit, self.firm, agent.agent_id)

            # MCP bridge
            if self.use_mcp:
                try:
                    from firm.llm.mcp_bridge import extend_agent_with_all_mcp
                    added = extend_agent_with_all_mcp(
                        agent,
                        mcp_categories=spec.mcp_categories,
                        memory_categories=spec.memory_categories,
                    )
                    logger.info(
                        "Ecosystem tools loaded for %s: %d tools (mcp=%s, memory=%s)",
                        spec.name, added,
                        spec.mcp_categories, spec.memory_categories,
                    )
                except Exception as exc:
                    logger.warning(
                        "MCP bridge unavailable for %s: %s", spec.name, exc,
                    )

            self.agents[spec.name] = agent

            # Classify premium vs free based on token budget
            if spec.config.max_tokens_budget > self.chunk_budget:
                self._premium_agents.add(spec.name)
            else:
                self._free_agents.add(spec.name)

            tier = "premium" if spec.name in self._premium_agents else "free"
            logger.info(
                "Agent '%s' ready (model=%s, tier=%s, budget=%d)",
                spec.name, spec.model, tier,
                spec.config.max_tokens_budget,
            )

    # ── Chunked execution helper ────────────────────────────────────

    def _execute_chunked(
        self,
        agent: LLMAgent,
        base_task: str,
        agent_name: str,
    ) -> ExecutionResult:
        """Execute a task in multiple 6000-token chunks.

        Between each chunk:
        1. Extract findings from the chunk's output
        2. Save progress summary to FIRM memory
        3. Build a continuation prompt with remaining work

        Returns a merged ExecutionResult across all chunks.
        """
        all_tool_executions = []
        total_input = 0
        total_output = 0
        total_iterations = 0
        chunk_outputs: list[str] = []
        last_status = ExecutionStatus.COMPLETED

        t0 = time.monotonic()

        for chunk_idx in range(self.max_chunks):
            # Build chunk prompt
            if chunk_idx == 0:
                prompt = (
                    f"{base_task}\n\n"
                    f"[CHUNK 1/{self.max_chunks}] Start by calling recall_memory "
                    f"to check if there's prior context. Then begin your work. "
                    f"Save findings with contribute_memory as you go."
                )
            else:
                prompt = (
                    f"CONTINUE your previous work on: {base_task[:200]}\n\n"
                    f"[CHUNK {chunk_idx + 1}/{self.max_chunks}] "
                    f"1. Call recall_memory to restore your context.\n"
                    f"2. Review what's already been done.\n"
                    f"3. Continue scanning from where you left off.\n"
                    f"4. Save new findings with contribute_memory.\n"
                    f"5. If DONE, say 'ALL_CHUNKS_COMPLETE' in your response."
                )

            logger.info(
                "Chunk %d/%d for %s (budget=%d tokens)",
                chunk_idx + 1, self.max_chunks, agent_name, self.chunk_budget,
            )

            # Temporarily set the agent's budget to chunk size
            original_budget = agent.config.max_tokens_budget
            original_cost = agent.config.max_cost_usd
            agent.config.max_tokens_budget = self.chunk_budget
            agent.config.max_cost_usd = 100.0  # free models — no cost limit

            try:
                result = agent.execute_task(prompt)
            finally:
                # Restore original budget
                agent.config.max_tokens_budget = original_budget
                agent.config.max_cost_usd = original_cost

            # Accumulate stats
            all_tool_executions.extend(result.tool_executions)
            total_input += result.input_tokens
            total_output += result.output_tokens
            total_iterations += result.total_iterations
            last_status = result.status

            if result.output:
                chunk_outputs.append(result.output)

            # Extract findings from this chunk
            self._extract_findings_from_output(result.output, agent_name)
            self._extract_findings_from_tool_results(result, agent_name)

            logger.info(
                "Chunk %d done: status=%s, tokens=%d, tools=%s",
                chunk_idx + 1, result.status.value, result.total_tokens,
                ", ".join(result.tools_used) if result.tools_used else "none",
            )

            # Check if agent signaled completion
            if result.output and "ALL_CHUNKS_COMPLETE" in result.output:
                logger.info("Agent %s signaled completion at chunk %d", agent_name, chunk_idx + 1)
                break

            # Also stop if agent produced no output (failed/rate-limited)
            if result.status == ExecutionStatus.FAILED and not result.output:
                logger.warning(
                    "Chunk %d failed for %s — pausing 5s before retry",
                    chunk_idx + 1, agent_name,
                )
                time.sleep(5)  # cooldown before retry

        # Merge all chunk outputs
        merged_output = "\n\n---\n\n".join(chunk_outputs)
        duration_ms = (time.monotonic() - t0) * 1000

        return ExecutionResult(
            task_id=f"chunked-{agent_name}",
            status=last_status,
            output=merged_output,
            tool_executions=all_tool_executions,
            input_tokens=total_input,
            output_tokens=total_output,
            total_iterations=total_iterations,
            duration_ms=duration_ms,
            cost_usd=0.0,  # free models
        )

    # ── Override Phase 2: Parallel scan with chunking ───────────────

    def _phase_scan(self) -> None:
        """Three agents scan in parallel, free agents run chunked."""
        logger.info("Phase 2: Parallel scanning (chunked for free-tier agents)...")

        tasks = {
            "code-scanner": (
                f"Scan the repository at '{self.repo_path}' for code vulnerabilities.\n"
                "1. Use repo_tree to see the structure.\n"
                "2. Use repo_file_read to review source files.\n"
                "3. Look for: SQL injection, command injection, XSS, SSRF, "
                "   path traversal, unsafe deserialization, auth bypass, "
                "   race conditions, crypto misuse, info disclosure.\n"
                "4. For EACH vulnerability, call contribute_memory with:\n"
                '   JSON: {"title": "...", "severity": "high|medium|low",\n'
                '          "file_path": "...", "line_start": N, "cwe_id": N,\n'
                '          "description": "...", "remediation": "..."}\n'
                "   Tags: ['finding', '<severity>']\n"
                "5. Be thorough but avoid false positives."
            ),
            "static-analyzer": (
                f"Run static analysis on '{self.repo_path}'.\n"
                "1. Use repo_grep_secrets to find hardcoded secrets.\n"
                "2. Use repo_dependency_audit to check for vulnerable deps.\n"
                "3. Use repo_config_scan for Docker/CI/env configs.\n"
                "4. Use repo_git_history_secrets to check git history.\n"
                "5. For EACH finding, call contribute_memory with:\n"
                '   JSON: {"title": "...", "severity": "...", "file_path": "...",\n'
                '          "description": "...", "cwe_id": N, "remediation": "..."}\n'
                "   Tags: ['finding', '<severity>']"
            ),
            "report-synthesizer": (
                f"Understand the architecture of '{self.repo_path}'.\n"
                "1. Use repo_tree and repo_file_stats for overview.\n"
                "2. Read key files: README, main entry points, configs.\n"
                "3. Store your analysis with contribute_memory:\n"
                "   Tags: ['architecture', 'context']\n"
                "4. This context will help you write the final report."
            ),
        }

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for agent_name, task_prompt in tasks.items():
                agent = self.agents[agent_name]

                if agent_name in self._free_agents:
                    # Chunked execution for free agents
                    future = executor.submit(
                        self._execute_chunked, agent, task_prompt, agent_name,
                    )
                else:
                    # Normal execution for premium agents
                    future = executor.submit(agent.execute_task, task_prompt)

                futures[future] = agent_name

            for future in as_completed(futures):
                agent_name = futures[future]
                try:
                    result = future.result()
                    logger.info(
                        "Agent '%s' finished: %s (tokens=%d, tools=%s)",
                        agent_name, result.status.value,
                        result.total_tokens,
                        ", ".join(result.tools_used) if result.tools_used else "none",
                    )
                    # For non-chunked agents, extract findings here
                    if agent_name in self._premium_agents:
                        self._extract_findings_from_output(result.output, agent_name)
                        self._extract_findings_from_tool_results(result, agent_name)
                except Exception as exc:
                    logger.error("Agent '%s' failed: %s", agent_name, exc)

    # ── Override Phase 3: Triage (premium orchestrator, unchunked) ──

    def _phase_triage(self) -> None:
        """Director triages findings — unchunked (premium model)."""
        logger.info("Phase 3: Triage and deduplication (premium orchestrator)...")
        director = self.agents["security-director"]

        task = (
            "Recall all findings from FIRM memory.\n"
            "1. Use recall_memory with query='finding' to get all findings.\n"
            "2. For each finding, evaluate if it's real or a false positive.\n"
            "3. Assign correct severity and add CVSS if possible.\n"
            "4. Store confirmed findings with tags ['triage', 'confirmed'].\n"
            "5. Be decisive — remove clear false positives."
        )
        result = director.execute_task(task)
        logger.info(
            "Phase 3 complete: %s (tokens=%d)",
            result.status.value, result.total_tokens,
        )

        self._extract_findings_from_output(result.output, "security-director")
        self._extract_findings_from_memory()
