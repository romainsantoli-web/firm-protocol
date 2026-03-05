"""
firm.llm.executor — Agentic task execution engine.

Runs the core loop: LLM reasons → calls tools → observes results → repeats
until the task is complete or budget is exhausted. Connects execution results
back to FIRM's authority/governance system.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from firm.llm.providers import LLMProvider, LLMMessage, LLMResponse, ToolCall
from firm.llm.tools import ToolKit, ToolResult


class ExecutionStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"
    CANCELLED = "cancelled"


@dataclass
class ToolExecution:
    """Record of a single tool execution within a task."""
    tool_name: str
    arguments: dict[str, Any]
    result: ToolResult
    timestamp: float = field(default_factory=time.time)


@dataclass
class ExecutionResult:
    """Complete result from executing a task."""
    task_id: str
    status: ExecutionStatus
    output: str
    error: str = ""
    tool_executions: list[ToolExecution] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    total_iterations: int = 0
    duration_ms: float = 0.0
    cost_usd: float = 0.0

    @property
    def success(self) -> bool:
        return self.status == ExecutionStatus.COMPLETED

    @property
    def tools_used(self) -> list[str]:
        return list({te.tool_name for te in self.tool_executions})

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "tools_used": self.tools_used,
            "tool_executions": len(self.tool_executions),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_iterations": self.total_iterations,
            "duration_ms": round(self.duration_ms, 1),
            "cost_usd": round(self.cost_usd, 6),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Cost estimation (approximate $/1M tokens)
# ─────────────────────────────────────────────────────────────────────────────

_COST_PER_M_TOKENS: dict[str, tuple[float, float]] = {
    # (input, output) per 1M tokens
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-3-5-sonnet-20241022": (3.0, 15.0),
    "claude-3-haiku-20240307": (0.25, 1.25),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-4-turbo": (10.0, 30.0),
    "mistral-large-latest": (2.0, 6.0),
    "mistral-small-latest": (0.2, 0.6),
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate cost in USD."""
    rates = _COST_PER_M_TOKENS.get(model, (5.0, 15.0))  # default: assume expensive
    return (input_tokens * rates[0] + output_tokens * rates[1]) / 1_000_000


# ─────────────────────────────────────────────────────────────────────────────
# Task Executor
# ─────────────────────────────────────────────────────────────────────────────

class TaskExecutor:
    """
    Executes tasks using an LLM provider and toolkit.

    The executor runs the agentic loop:
    1. Send messages + tools to LLM
    2. If LLM wants to use tools → execute them → feed results back
    3. Repeat until LLM gives a final answer or budget exhausted
    """

    def __init__(
        self,
        provider: LLMProvider,
        toolkit: ToolKit,
        max_iterations: int = 25,
        max_tokens_budget: int = 100_000,
        max_cost_usd: float = 1.0,
        temperature: float = 0.3,
        max_response_tokens: int = 4096,
    ):
        self.provider = provider
        self.toolkit = toolkit
        self.max_iterations = max_iterations
        self.max_tokens_budget = max_tokens_budget
        self.max_cost_usd = max_cost_usd
        self.temperature = temperature
        self.max_response_tokens = max_response_tokens
        self._cancelled = False

    def cancel(self):
        """Cancel the current execution."""
        self._cancelled = True

    def execute(
        self,
        task: str,
        system_prompt: str = "",
        context: str = "",
    ) -> ExecutionResult:
        """
        Execute a task as an agentic loop.

        Args:
            task: The task description/instruction.
            system_prompt: System prompt for the LLM.
            context: Additional context to prepend to the task.
        """
        task_id = str(uuid.uuid4())[:8]
        if self._cancelled:
            return ExecutionResult(
                task_id=task_id,
                status=ExecutionStatus.CANCELLED,
                output="",
                error="Execution cancelled.",
                tool_executions=[],
                input_tokens=0,
                output_tokens=0,
                total_iterations=0,
                duration_ms=0,
                cost_usd=0.0,
            )
        t0 = time.monotonic()

        # Build initial messages
        messages: list[LLMMessage] = []
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))

        user_content = task
        if context:
            user_content = f"Context:\n{context}\n\nTask:\n{task}"
        messages.append(LLMMessage(role="user", content=user_content))

        tool_definitions = self.toolkit.to_definitions()
        tool_executions: list[ToolExecution] = []
        total_input = 0
        total_output = 0
        iteration = 0

        while iteration < self.max_iterations:
            if self._cancelled:
                return ExecutionResult(
                    task_id=task_id,
                    status=ExecutionStatus.CANCELLED,
                    output="",
                    error="Execution cancelled.",
                    tool_executions=tool_executions,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    total_iterations=iteration,
                    duration_ms=(time.monotonic() - t0) * 1000,
                    cost_usd=_estimate_cost(self.provider.model, total_input, total_output),
                )

            iteration += 1

            # Budget check
            if total_input + total_output > self.max_tokens_budget:
                return ExecutionResult(
                    task_id=task_id,
                    status=ExecutionStatus.BUDGET_EXCEEDED,
                    output="",
                    error=f"Token budget exceeded: {total_input + total_output} > {self.max_tokens_budget}",
                    tool_executions=tool_executions,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    total_iterations=iteration,
                    duration_ms=(time.monotonic() - t0) * 1000,
                    cost_usd=_estimate_cost(self.provider.model, total_input, total_output),
                )

            current_cost = _estimate_cost(self.provider.model, total_input, total_output)
            if current_cost > self.max_cost_usd:
                return ExecutionResult(
                    task_id=task_id,
                    status=ExecutionStatus.BUDGET_EXCEEDED,
                    output="",
                    error=f"Cost budget exceeded: ${current_cost:.4f} > ${self.max_cost_usd:.2f}",
                    tool_executions=tool_executions,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    total_iterations=iteration,
                    duration_ms=(time.monotonic() - t0) * 1000,
                    cost_usd=current_cost,
                )

            # Call LLM
            try:
                response = self.provider.chat(
                    messages=messages,
                    tools=tool_definitions if tool_definitions else None,
                    temperature=self.temperature,
                    max_tokens=self.max_response_tokens,
                )
            except Exception as e:
                return ExecutionResult(
                    task_id=task_id,
                    status=ExecutionStatus.FAILED,
                    output="",
                    error=f"LLM error: {type(e).__name__}: {e}",
                    tool_executions=tool_executions,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    total_iterations=iteration,
                    duration_ms=(time.monotonic() - t0) * 1000,
                    cost_usd=_estimate_cost(self.provider.model, total_input, total_output),
                )

            total_input += response.input_tokens
            total_output += response.output_tokens

            # No tool calls → final answer
            if not response.has_tool_calls:
                return ExecutionResult(
                    task_id=task_id,
                    status=ExecutionStatus.COMPLETED,
                    output=response.content,
                    tool_executions=tool_executions,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    total_iterations=iteration,
                    duration_ms=(time.monotonic() - t0) * 1000,
                    cost_usd=_estimate_cost(self.provider.model, total_input, total_output),
                )

            # Process tool calls
            messages.append(LLMMessage(
                role="assistant",
                content=response.content,
                tool_calls=response.tool_calls,
            ))

            for tc in response.tool_calls:
                result = self.toolkit.execute(tc.name, tc.arguments)
                tool_executions.append(ToolExecution(
                    tool_name=tc.name,
                    arguments=tc.arguments,
                    result=result,
                ))

                # Feed tool result back
                tool_output = result.output
                if result.error:
                    tool_output += f"\n[ERROR] {result.error}"
                if not tool_output:
                    tool_output = "(no output)"

                messages.append(LLMMessage(
                    role="tool",
                    content=tool_output,
                    tool_call_id=tc.id,
                    name=tc.name,
                ))

        # Max iterations reached
        return ExecutionResult(
            task_id=task_id,
            status=ExecutionStatus.TIMEOUT,
            output="",
            error=f"Max iterations reached ({self.max_iterations}).",
            tool_executions=tool_executions,
            input_tokens=total_input,
            output_tokens=total_output,
            total_iterations=iteration,
            duration_ms=(time.monotonic() - t0) * 1000,
            cost_usd=_estimate_cost(self.provider.model, total_input, total_output),
        )
