"""
firm.llm.agent — LLMAgent bridges FIRM agents with LLM backends.

An LLMAgent wraps a FIRM Agent with:
  - An LLM provider (Claude, GPT, Mistral, Copilot)
  - A toolkit of real tools
  - Authority-gated capabilities
  - Automatic FIRM integration (record_action, governance, market)
"""

from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from firm.llm.providers import LLMProvider
from firm.llm.tools import ToolKit, Tool, ToolResult, create_builtin_toolkit
from firm.llm.executor import TaskExecutor, ExecutionResult, ExecutionStatus

if TYPE_CHECKING:
    from firm.runtime import Firm
    from firm.core.agent import Agent

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for an LLM-powered agent."""
    max_iterations: int = 25
    max_tokens_budget: int = 100_000
    max_cost_usd: float = 1.0
    temperature: float = 0.3
    max_response_tokens: int = 4096
    auto_record_actions: bool = True  # Automatically call firm.record_action
    system_prompt_extra: str = ""     # Appended to auto-generated system prompt


class LLMAgent:
    """
    A FIRM Agent powered by a real LLM.

    Connects FIRM's authority/governance/evolution system to actual LLM
    execution with real tools. The agent's authority in FIRM determines
    what it can do:

    - authority < 0.3 → read-only tools (file_read, git_status, etc.)
    - authority < 0.6 → + write tools (file_write, git_commit)
    - authority < 0.8 → + dangerous tools (terminal_run, http_post)
    - authority >= 0.8 → full access + can propose governance changes
    """

    def __init__(
        self,
        firm: Firm,
        agent: Agent,
        provider: LLMProvider,
        toolkit: ToolKit | None = None,
        config: AgentConfig | None = None,
    ):
        self.firm = firm
        self.agent = agent
        self.provider = provider
        self.config = config or AgentConfig()
        self._toolkit = toolkit or create_builtin_toolkit()
        self._execution_history: list[ExecutionResult] = []

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def agent_id(self) -> str:
        return self.agent.id

    @property
    def authority(self) -> float:
        return self.agent.authority

    @property
    def name(self) -> str:
        return self.agent.name

    # ── System prompt ──────────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """Build a system prompt from FIRM context."""
        roles = ", ".join(r.name for r in self.agent.roles) if self.agent.roles else "unassigned"
        status = self.agent.status.value if hasattr(self.agent.status, "value") else str(self.agent.status)

        prompt = f"""You are {self.agent.name}, an autonomous agent in the FIRM organization "{self.firm.name}".

## Your Identity
- Agent ID: {self.agent.id}
- Authority: {self.agent.authority:.2f} (0.0 = no trust, 1.0 = full trust)
- Roles: {roles}
- Status: {status}
- Credits: {self.agent.credits:.1f}

## FIRM Rules
1. You earn authority through successful actions. Failed actions reduce your authority.
2. Changes to the organization require governance proposals approved by voting.
3. The Constitutional Agent enforces invariants — some actions may be blocked.
4. A human kill-switch can halt all operations at any time.
5. Every action is recorded in an append-only ledger.

## Your Objective
Execute the given task using available tools. Be precise, thorough, and efficient.
Report your results clearly. If you encounter errors, try to fix them.
Do not fabricate results — if a tool fails, report the failure honestly.

## Authority Level
Your current authority ({self.agent.authority:.2f}) grants you access to:"""

        if self.agent.authority >= 0.8:
            prompt += "\n- ALL tools including dangerous operations"
            prompt += "\n- Can propose governance changes to the organization"
        elif self.agent.authority >= 0.6:
            prompt += "\n- Read/write tools (files, git, basic commands)"
            prompt += "\n- Cannot use dangerous operations (terminal_run, http_post)"
        elif self.agent.authority >= 0.3:
            prompt += "\n- Read-only tools (file_read, git_status, git_log)"
            prompt += "\n- Cannot modify files or run commands"
        else:
            prompt += "\n- Minimal access — you are on probation"
            prompt += "\n- Can only observe (file_read, file_list)"

        if self.config.system_prompt_extra:
            prompt += f"\n\n{self.config.system_prompt_extra}"

        return prompt

    # ── Tool filtering ──────────────────────────────────────────────

    def _get_available_toolkit(self) -> ToolKit:
        """Filter tools based on agent authority."""
        filtered = ToolKit(
            working_dir=self._toolkit.working_dir,
            timeout=self._toolkit.timeout,
        )

        read_only = {"git_status", "git_diff", "git_log", "git_branch",
                      "file_read", "file_list", "file_search",
                      "python_test"}

        write_tools = {"git_add", "git_commit", "file_write", "python_run"}

        dangerous = {"terminal_run", "http_get", "http_post"}

        for tool in self._toolkit.list_tools():
            if self.agent.authority >= 0.8:
                # Full access
                filtered.register(tool)
            elif self.agent.authority >= 0.6:
                # No dangerous tools
                if tool.name not in dangerous:
                    filtered.register(tool)
            elif self.agent.authority >= 0.3:
                # Read-only
                if tool.name in read_only:
                    filtered.register(tool)
            else:
                # Probation — minimal
                if tool.name in {"file_read", "file_list"}:
                    filtered.register(tool)

        return filtered

    # ── Task execution ──────────────────────────────────────────────

    def execute_task(
        self,
        task: str,
        context: str = "",
    ) -> ExecutionResult:
        """
        Execute a task using the LLM with real tools.

        The agent:
        1. Gets a filtered toolkit based on authority
        2. Receives a system prompt with FIRM context
        3. Runs the agentic loop (LLM → tools → LLM → ...)
        4. Records the result in FIRM (success/failure → authority change)
        """
        # Check kill switch
        if self.firm.constitution.kill_switch_active:
            result = ExecutionResult(
                task_id="blocked",
                status=ExecutionStatus.FAILED,
                output="",
                error="Kill switch active — all agent operations are halted.",
            )
            return result

        # Get authority-filtered toolkit
        toolkit = self._get_available_toolkit()

        # Scale budget by authority
        budget_scale = max(0.2, self.agent.authority)
        max_tokens = int(self.config.max_tokens_budget * budget_scale)
        max_cost = self.config.max_cost_usd * budget_scale

        # Create executor
        executor = TaskExecutor(
            provider=self.provider,
            toolkit=toolkit,
            max_iterations=self.config.max_iterations,
            max_tokens_budget=max_tokens,
            max_cost_usd=max_cost,
            temperature=self.config.temperature,
            max_response_tokens=self.config.max_response_tokens,
        )

        system_prompt = self._build_system_prompt()

        logger.info(
            "Agent '%s' (authority=%.2f) executing task: %s",
            self.name, self.authority, task[:100],
        )

        # Execute
        result = executor.execute(
            task=task,
            system_prompt=system_prompt,
            context=context,
        )

        # Record in FIRM
        if self.config.auto_record_actions:
            self._record_in_firm(task, result)

        # Track history
        self._execution_history.append(result)

        # Emit event
        self.firm.events.emit("agent.task_completed", {
            "agent_id": self.agent_id,
            "task": task[:200],
            "status": result.status.value,
            "tools_used": result.tools_used,
            "tokens": result.total_tokens,
            "cost_usd": result.cost_usd,
            "duration_ms": result.duration_ms,
        }, source="llm_agent")

        return result

    def _record_in_firm(self, task: str, result: ExecutionResult) -> None:
        """Record the execution result in FIRM's authority system."""
        success = result.success
        description = f"Task: {task[:100]}"
        if result.tools_used:
            description += f" | Tools: {', '.join(result.tools_used)}"
        description += f" | Status: {result.status.value}"

        # Credit delta based on outcome
        if success:
            credit_delta = 5.0 + len(result.tool_executions) * 0.5
        else:
            credit_delta = -2.0

        try:
            self.firm.record_action(
                agent_id=self.agent_id,
                success=success,
                description=description,
                credit_delta=credit_delta,
            )
        except Exception as e:
            logger.warning("Failed to record action in FIRM: %s", e)

    # ── Governance shortcuts ────────────────────────────────────────

    def propose(self, title: str, description: str) -> dict[str, Any]:
        """Create a governance proposal (requires authority >= 0.6)."""
        return self.firm.propose(self.agent_id, title, description)

    def vote(self, proposal_id: str, choice: str, reason: str = "") -> dict[str, Any]:
        """Vote on a governance proposal."""
        return self.firm.vote(proposal_id, self.agent_id, choice, reason)

    # ── Market shortcuts ────────────────────────────────────────────

    def post_task(self, title: str, description: str, bounty: float = 10.0) -> dict[str, Any]:
        """Post a task on the market."""
        return self.firm.post_task(self.agent_id, title, description, bounty)

    def bid_on_task(self, task_id: str, amount: float) -> dict[str, Any]:
        """Bid on a market task."""
        return self.firm.bid_on_task(task_id, self.agent_id, amount)

    # ── Stats ──────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get agent stats including LLM usage."""
        total_tokens = sum(r.total_tokens for r in self._execution_history)
        total_cost = sum(r.cost_usd for r in self._execution_history)
        successes = sum(1 for r in self._execution_history if r.success)
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "authority": self.authority,
            "provider": self.provider.name,
            "model": self.provider.model,
            "tasks_executed": len(self._execution_history),
            "tasks_succeeded": successes,
            "success_rate": successes / len(self._execution_history)
            if self._execution_history else 0.0,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 4),
            "provider_stats": self.provider.get_stats(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Factory: Create an LLM agent within a FIRM
# ─────────────────────────────────────────────────────────────────────────────

def create_llm_agent(
    firm: Firm,
    name: str,
    provider_name: str = "claude",
    model: str | None = None,
    api_key: str | None = None,
    authority: float = 0.5,
    working_dir: str | None = None,
    roles: list[str] | None = None,
    config: AgentConfig | None = None,
    **provider_kwargs: Any,
) -> LLMAgent:
    """
    Create a new LLM-powered agent in a FIRM.

    This is the main entry point for creating agents:

        from firm.runtime import Firm
        from firm.llm.agent import create_llm_agent

        firm = Firm("my-startup")
        cto = create_llm_agent(firm, "CTO", provider_name="claude", authority=0.8)
        dev = create_llm_agent(firm, "dev-1", provider_name="gpt", authority=0.5)

        result = dev.execute_task("Fix the failing test in tests/test_api.py")
    """
    from firm.llm.providers import get_provider

    # Create FIRM agent
    agent = firm.add_agent(name, authority=authority, roles=roles)

    # Create LLM provider
    provider = get_provider(provider_name, model=model, api_key=api_key, **provider_kwargs)

    # Create toolkit
    toolkit = create_builtin_toolkit(
        working_dir=working_dir or ".",
        timeout=30,
    )

    return LLMAgent(
        firm=firm,
        agent=agent,
        provider=provider,
        toolkit=toolkit,
        config=config,
    )
