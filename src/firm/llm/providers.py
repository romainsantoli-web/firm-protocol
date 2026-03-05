"""
firm.llm.providers — LLM provider abstraction + real implementations.

Supports: Claude (Anthropic), GPT (OpenAI), Mistral, Copilot (OpenAI-compat).
Each provider converts FIRM tool definitions to native format and handles
streaming, retries, and token counting.
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generator

import anthropic
import openai
import mistralai


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LLMMessage:
    """A message in a conversation."""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolCall:
    """A tool call requested by the LLM."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Response from an LLM provider."""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    latency_ms: float = 0.0

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ToolDefinition:
    """Tool definition in provider-agnostic format."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema


# ─────────────────────────────────────────────────────────────────────────────
# Abstract base
# ─────────────────────────────────────────────────────────────────────────────

class LLMProvider(ABC):
    """Abstract LLM provider — all providers implement this interface."""

    name: str = "base"
    model: str = ""

    def __init__(self, model: str | None = None, api_key: str | None = None, **kwargs: Any):
        self.model = model or self._default_model()
        self.api_key = api_key
        self.config = kwargs
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_requests = 0

    @abstractmethod
    def _default_model(self) -> str:
        ...

    @abstractmethod
    def chat(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Send a chat completion request."""
        ...

    def get_stats(self) -> dict[str, Any]:
        """Return usage statistics."""
        return {
            "provider": self.name,
            "model": self.model,
            "total_requests": self._total_requests,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Claude (Anthropic)
# ─────────────────────────────────────────────────────────────────────────────


class ClaudeProvider(LLMProvider):
    """Anthropic Claude provider."""

    name = "claude"

    def __init__(self, model: str | None = None, api_key: str | None = None, **kwargs: Any):
        super().__init__(model, api_key, **kwargs)
        self._client = anthropic.Anthropic(
            api_key=self.api_key or os.environ.get("ANTHROPIC_API_KEY"),
        )

    def _default_model(self) -> str:
        return "claude-sonnet-4-20250514"

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        """Convert to Anthropic tool format."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    def _convert_messages(self, messages: list[LLMMessage]) -> tuple[str, list[dict]]:
        """Convert to Anthropic message format. Returns (system, messages)."""
        system = ""
        converted = []
        for msg in messages:
            if msg.role == "system":
                system += msg.content + "\n"
            elif msg.role == "assistant":
                content: list[dict] = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                converted.append({"role": "assistant", "content": content or msg.content})
            elif msg.role == "tool":
                converted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }],
                })
            else:
                converted.append({"role": msg.role, "content": msg.content})
        return system.strip(), converted

    def chat(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        system, msgs = self._convert_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": msgs,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        t0 = time.monotonic()
        response = self._client.messages.create(**kwargs)
        latency = (time.monotonic() - t0) * 1000

        # Parse response
        content = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input,
                ))

        self._total_requests += 1
        self._total_input_tokens += response.usage.input_tokens
        self._total_output_tokens += response.usage.output_tokens

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason="tool_use" if tool_calls else "stop",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self.model,
            latency_ms=latency,
        )


# ─────────────────────────────────────────────────────────────────────────────
# GPT (OpenAI)
# ─────────────────────────────────────────────────────────────────────────────


class GPTProvider(LLMProvider):
    """OpenAI GPT provider."""

    name = "gpt"

    def __init__(self, model: str | None = None, api_key: str | None = None, **kwargs: Any):
        super().__init__(model, api_key, **kwargs)
        self._client = openai.OpenAI(
            api_key=self.api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=kwargs.get("base_url"),
        )

    def _default_model(self) -> str:
        return "gpt-4o"

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def _convert_messages(self, messages: list[LLMMessage]) -> list[dict]:
        converted = []
        for msg in messages:
            if msg.role == "tool":
                converted.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id,
                })
            elif msg.role == "assistant" and msg.tool_calls:
                tc_list = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
                converted.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": tc_list,
                })
            else:
                converted.append({"role": msg.role, "content": msg.content})
        return converted

    def chat(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        t0 = time.monotonic()
        response = self._client.chat.completions.create(**kwargs)
        latency = (time.monotonic() - t0) * 1000

        choice = response.choices[0]
        content = choice.message.content or ""
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                ))

        usage = response.usage
        self._total_requests += 1
        self._total_input_tokens += usage.prompt_tokens if usage else 0
        self._total_output_tokens += usage.completion_tokens if usage else 0

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=self.model,
            latency_ms=latency,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Mistral
# ─────────────────────────────────────────────────────────────────────────────


class MistralProvider(LLMProvider):
    """Mistral AI provider."""

    name = "mistral"

    def __init__(self, model: str | None = None, api_key: str | None = None, **kwargs: Any):
        super().__init__(model, api_key, **kwargs)
        self._client = mistralai.Mistral(
            api_key=self.api_key or os.environ.get("MISTRAL_API_KEY"),
        )

    def _default_model(self) -> str:
        return "mistral-large-latest"

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def _convert_messages(self, messages: list[LLMMessage]) -> list[dict]:
        converted = []
        for msg in messages:
            if msg.role == "tool":
                converted.append({
                    "role": "tool",
                    "content": msg.content,
                    "tool_call_id": msg.tool_call_id,
                })
            elif msg.role == "assistant" and msg.tool_calls:
                tc_list = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
                converted.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": tc_list,
                })
            else:
                converted.append({"role": msg.role, "content": msg.content})
        return converted

    def chat(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        t0 = time.monotonic()
        response = self._client.chat.complete(**kwargs)
        latency = (time.monotonic() - t0) * 1000

        choice = response.choices[0]
        content = choice.message.content or ""
        tool_calls = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments)
                    if isinstance(tc.function.arguments, str)
                    else tc.function.arguments,
                ))

        usage = response.usage
        self._total_requests += 1
        self._total_input_tokens += usage.prompt_tokens if usage else 0
        self._total_output_tokens += usage.completion_tokens if usage else 0

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=self.model,
            latency_ms=latency,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Copilot (GitHub Models via OpenAI-compatible API)
# ─────────────────────────────────────────────────────────────────────────────


class CopilotProvider(GPTProvider):
    """GitHub Copilot/Models provider — OpenAI-compatible endpoint."""

    name = "copilot"

    def __init__(self, model: str | None = None, api_key: str | None = None, **kwargs: Any):
        super().__init__(
            model=model,
            api_key=api_key or os.environ.get("GITHUB_TOKEN"),
            base_url=kwargs.pop("base_url", "https://models.inference.ai.azure.com"),
            **kwargs,
        )

    def _default_model(self) -> str:
        return "gpt-4o"


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "claude": ClaudeProvider,
    "gpt": GPTProvider,
    "openai": GPTProvider,
    "mistral": MistralProvider,
    "copilot": CopilotProvider,
    "github": CopilotProvider,
}


def get_provider(name: str, **kwargs: Any) -> LLMProvider:
    """Get a provider by name. Raises KeyError if not found."""
    key = name.lower()
    if key not in _PROVIDERS:
        raise KeyError(
            f"Unknown provider '{name}'. Available: {', '.join(_PROVIDERS.keys())}"
        )
    return _PROVIDERS[key](**kwargs)
