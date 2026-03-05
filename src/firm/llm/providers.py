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
    # Preserved raw API message (e.g. Gemini thinking-model thought_signature)
    _raw: Any = None


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
    # Raw provider message object — used to preserve Gemini thought_signatures
    raw_message: Any = None

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
            # If a raw message was preserved (e.g. Gemini thought_signature),
            # pass it through verbatim so the API receives it unchanged.
            if msg._raw is not None:
                converted.append(msg._raw)
                continue
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

    # Models requiring max_completion_tokens instead of max_tokens (and no temperature)
    _COMPLETION_TOKENS_MODELS = ("o1", "o1-mini", "o1-preview", "o3", "o3-mini", "o3-pro",
                                  "o4-mini", "gpt-5", "gpt-5-mini", "gpt-5-nano")

    def chat(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        # Some reasoning/newer models use max_completion_tokens instead of max_tokens
        use_completion_tokens = any(self.model.startswith(p) for p in self._COMPLETION_TOKENS_MODELS)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._convert_messages(messages),
        }
        if use_completion_tokens:
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens
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
            raw_message=choice.message.model_dump(exclude_none=True) if tool_calls else None,
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
    """GitHub Copilot/Models provider — OpenAI-compatible endpoint (free tier)."""

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


class CopilotProProvider(GPTProvider):
    """GitHub Copilot Pro provider — full catalog (Claude, GPT-5, Gemini, Grok).

    Uses the Copilot internal API (api.githubcopilot.com) which requires
    a JWT token obtained via OAuth device flow.

    Authentication flow:
      1. OAuth device flow with client_id = Iv1.b507a08c87ecfe98 (VS Code)
      2. Exchange OAuth token for Copilot JWT via /copilot_internal/v2/token
      3. Use JWT as Bearer token on api.githubcopilot.com/chat/completions

    The JWT expires every ~30 min — auto-refresh via cached OAuth token.
    """

    name = "copilot-pro"

    # VS Code Copilot OAuth App client_id (public, embedded in the extension)
    _CLIENT_ID = "Iv1.b507a08c87ecfe98"

    def __init__(self, model: str | None = None, api_key: str | None = None, **kwargs: Any):
        # api_key can be: (1) Copilot JWT directly, (2) OAuth token, (3) loaded from cache
        self._oauth_token: str | None = kwargs.pop("oauth_token", None)
        self._jwt_expires: int = 0
        jwt = api_key or os.environ.get("COPILOT_JWT")

        # Try loading cached tokens from /tmp/copilot_token.json
        if not jwt and not self._oauth_token:
            jwt, self._oauth_token, self._jwt_expires = self._load_cached_tokens()

        if not jwt and self._oauth_token:
            jwt = self._refresh_jwt()

        if not jwt:
            raise ValueError(
                "CopilotProProvider requires a Copilot JWT or OAuth token. "
                "Run the device flow first or set COPILOT_JWT env var."
            )

        super().__init__(
            model=model,
            api_key=jwt,
            base_url="https://api.githubcopilot.com",
            **kwargs,
        )

    def _default_model(self) -> str:
        return "claude-sonnet-4"

    @staticmethod
    def _load_cached_tokens() -> tuple[str | None, str | None, int]:
        """Load cached tokens from /tmp/copilot_token.json."""
        import json as _json
        try:
            with open("/tmp/copilot_token.json") as f:
                data = _json.load(f)
            jwt = data.get("copilot_jwt")
            oauth = data.get("oauth_token")
            exp = int(data.get("expires_at", 0))
            # Check if JWT still valid (> 60s remaining)
            if jwt and exp > int(time.time()) + 60:
                return jwt, oauth, exp
            # JWT expired but OAuth still available → refresh
            return None, oauth, 0
        except (FileNotFoundError, _json.JSONDecodeError, KeyError):
            return None, None, 0

    def _refresh_jwt(self) -> str | None:
        """Refresh Copilot JWT using cached OAuth token."""
        import httpx as _httpx
        import json as _json
        if not self._oauth_token:
            return None
        try:
            r = _httpx.get(
                "https://api.github.com/copilot_internal/v2/token",
                headers={
                    "Authorization": f"token {self._oauth_token}",
                    "Accept": "application/json",
                    "Editor-Version": "vscode/1.96.0",
                    "Editor-Plugin-Version": "copilot-chat/0.24.0",
                },
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                jwt = data.get("token")
                self._jwt_expires = int(data.get("expires_at", 0))
                # Cache for next use
                with open("/tmp/copilot_token.json", "w") as f:
                    _json.dump({
                        "oauth_token": self._oauth_token,
                        "copilot_jwt": jwt,
                        "expires_at": self._jwt_expires,
                    }, f)
                return jwt
        except Exception:
            pass
        return None

    def _ensure_valid_jwt(self):
        """Auto-refresh JWT if about to expire."""
        if self._jwt_expires and int(time.time()) > self._jwt_expires - 60:
            new_jwt = self._refresh_jwt()
            if new_jwt:
                self._client.api_key = new_jwt

    # Models that require the /responses API instead of /chat/completions
    _RESPONSES_MODELS = ("gpt-5.3-codex", "gpt-5.2-codex", "gpt-5.1-codex",
                         "gpt-5.1-codex-mini", "gpt-5.1-codex-max")

    def _is_responses_model(self) -> bool:
        return any(self.model.startswith(p) for p in self._RESPONSES_MODELS)

    def chat(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Chat with auto JWT refresh + multi-choice tool call merging.

        Routes Codex models to /responses API, others to /chat/completions.
        Copilot Pro wraps some Claude models with 2 choices — we merge them.
        """
        self._ensure_valid_jwt()
        self._inject_copilot_headers()

        if self._is_responses_model():
            return self._chat_responses(messages, tools, temperature, max_tokens)
        return self._chat_completions(messages, tools, temperature, max_tokens)

    def _inject_copilot_headers(self):
        """Inject Copilot-specific headers once."""
        if not hasattr(self, "_headers_injected"):
            self._client._custom_headers.update({
                "Editor-Version": "vscode/1.96.0",
                "Editor-Plugin-Version": "copilot-chat/0.24.0",
                "Copilot-Integration-Id": "vscode-chat",
                "Openai-Intent": "conversation-panel",
            })
            self._headers_injected = True

    # ── /responses API path (Codex models) ──────────────────────────────────

    def _convert_messages_to_responses_input(
        self, messages: list[LLMMessage]
    ) -> list[dict]:
        """Convert FIRM messages to OpenAI Responses API input items."""
        items: list[dict] = []
        for msg in messages:
            if msg.role == "system":
                # system → developer message in Responses API
                items.append({"type": "message", "role": "developer", "content": msg.content})
            elif msg.role == "user":
                items.append({"type": "message", "role": "user", "content": msg.content})
            elif msg.role == "assistant":
                # Assistant text
                if msg.content:
                    items.append({"type": "message", "role": "assistant", "content": msg.content})
                # Assistant tool calls
                for tc in msg.tool_calls:
                    items.append({
                        "type": "function_call",
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments) if isinstance(tc.arguments, dict) else tc.arguments,
                        "call_id": tc.id,
                    })
            elif msg.role == "tool":
                items.append({
                    "type": "function_call_output",
                    "call_id": msg.tool_call_id,
                    "output": msg.content,
                })
        return items

    def _convert_tools_for_responses(self, tools: list[ToolDefinition]) -> list[dict]:
        """Convert tool definitions to Responses API format (name at top level)."""
        return [
            {
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            }
            for t in tools
        ]

    def _chat_responses(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Call the /responses endpoint for Codex models."""
        import httpx as _httpx

        input_items = self._convert_messages_to_responses_input(messages)

        payload: dict[str, Any] = {
            "model": self.model,
            "input": input_items,
            "max_output_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = self._convert_tools_for_responses(tools)

        headers = {
            "Authorization": f"Bearer {self._client.api_key}",
            "Content-Type": "application/json",
            "Editor-Version": "vscode/1.96.0",
            "Editor-Plugin-Version": "copilot-chat/0.24.0",
            "Copilot-Integration-Id": "vscode-chat",
            "Openai-Intent": "conversation-panel",
        }

        t0 = time.monotonic()
        r = _httpx.post(
            "https://api.githubcopilot.com/responses",
            headers=headers,
            json=payload,
            timeout=120,
        )
        latency = (time.monotonic() - t0) * 1000

        if r.status_code != 200:
            raise openai.BadRequestError(
                message=f"Codex /responses error: {r.text[:300]}",
                response=r,
                body=r.text,
            )

        data = r.json()

        # Parse output items
        content = ""
        tool_calls: list[ToolCall] = []
        finish_reason = "stop"

        for item in data.get("output", []):
            if item.get("type") == "message":
                for c in item.get("content", []):
                    content += c.get("text", "")
            elif item.get("type") == "function_call":
                args_str = item.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError:
                    args = {"raw": args_str}
                tool_calls.append(ToolCall(
                    id=item.get("call_id", f"codex_{item.get('id', 'unknown')}"),
                    name=item["name"],
                    arguments=args,
                ))
                finish_reason = "tool_calls"

        usage = data.get("usage", {})
        in_tokens = usage.get("input_tokens", 0)
        out_tokens = usage.get("output_tokens", 0)
        self._total_requests += 1
        self._total_input_tokens += in_tokens
        self._total_output_tokens += out_tokens

        # Build raw_message for the agent loop (needed to feed back tool results)
        raw_msg = None
        if tool_calls:
            raw_msg = {"role": "assistant", "content": content or None, "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
                for tc in tool_calls
            ]}

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            model=self.model,
            latency_ms=latency,
            raw_message=raw_msg,
        )

    # ── /chat/completions API path (Claude, GPT, Gemini, Grok) ──────────────

    def _chat_completions(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Call the /chat/completions endpoint (standard path)."""
        use_completion_tokens = any(self.model.startswith(p) for p in self._COMPLETION_TOKENS_MODELS)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._convert_messages(messages),
        }
        if use_completion_tokens:
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        t0 = time.monotonic()
        response = self._client.chat.completions.create(**kwargs)
        latency = (time.monotonic() - t0) * 1000

        # Merge multi-choice responses (Copilot Pro Claude quirk)
        content = ""
        tool_calls: list[ToolCall] = []
        finish_reason = "stop"

        for choice in response.choices:
            if choice.message.content:
                content = choice.message.content
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    ))
            if choice.finish_reason:
                finish_reason = choice.finish_reason

        usage = response.usage
        self._total_requests += 1
        self._total_input_tokens += usage.prompt_tokens if usage else 0
        self._total_output_tokens += usage.completion_tokens if usage else 0

        # Fallback: if no API tool_calls but text contains XML tool invocations
        # (Claude models on Copilot Pro hallucinate XML when prompts are long)
        if not tool_calls and content and tools:
            parsed = self._parse_xml_tool_calls(content)
            import logging
            logging.getLogger(__name__).warning(
                "CopilotPro XML fallback: parsed %d tool calls from %d chars of text",
                len(parsed), len(content),
            )
            if parsed:
                tool_calls = [parsed[0]]
                finish_reason = "tool_use"
                import re
                content = re.split(
                    r"<(?:function_calls|invoke|anythingllm)", content, maxsplit=1
                )[0].strip()

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=self.model,
            latency_ms=latency,
            raw_message=self._build_merged_raw(response.choices) if tool_calls else None,
        )

    @staticmethod
    def _build_merged_raw(choices) -> dict:
        """Build a merged raw message from multi-choice response."""
        merged = {"role": "assistant", "content": None, "tool_calls": []}
        for choice in choices:
            if choice.message.content:
                merged["content"] = choice.message.content
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    merged["tool_calls"].append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    })
        return merged

    @staticmethod
    def _parse_xml_tool_calls(text: str) -> list[ToolCall]:
        """Parse XML-formatted tool calls hallucinated by Claude models.

        Handles multiple XML formats:
          <invoke name="tool_name"><parameter name="key">value</parameter></invoke>
          <function_calls><invoke ...>...</invoke></function_calls>
        """
        import re
        import uuid as _uuid

        tool_calls: list[ToolCall] = []

        # Find all <invoke name="...">...</invoke> blocks
        invoke_pattern = re.compile(
            r'<invoke\s+name="([^"]+)">(.*?)</invoke>',
            re.DOTALL,
        )
        param_pattern = re.compile(
            r'<parameter\s+name="([^"]+)">(.*?)</parameter>',
            re.DOTALL,
        )

        for match in invoke_pattern.finditer(text):
            func_name = match.group(1)
            body = match.group(2)

            arguments: dict[str, Any] = {}
            for param in param_pattern.finditer(body):
                key = param.group(1)
                val = param.group(2).strip()
                # Try to parse as JSON, fallback to string
                try:
                    arguments[key] = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    arguments[key] = val

            # Only add if we got valid args (or it's a zero-arg call)
            tool_calls.append(ToolCall(
                id=f"xml_{_uuid.uuid4().hex[:8]}",
                name=func_name,
                arguments=arguments,
            ))

        return tool_calls


# ─────────────────────────────────────────────────────────────────────────────
# Gemini (Google — OpenAI-compatible endpoint)
# ─────────────────────────────────────────────────────────────────────────────


class GeminiProvider(GPTProvider):
    """Google Gemini provider via OpenAI-compatible REST endpoint.

    Falls back automatically through free-tier models (newest → oldest)
    on 429 / RateLimitError.
    """

    name = "gemini"

    # Fallback chain: newest → oldest free flash models (non-thinking only —
    # thinking models like gemini-2.5+ require thought_signature in tool calls)
    FALLBACK_MODELS: list[str] = [
        "models/gemini-3-flash-preview",    # Gemini 3 — newest, free preview
        "models/gemini-flash-latest",        # latest stable flash alias
        "models/gemini-2.0-flash",           # 2.0 flash — stable free tier
        "models/gemini-2.0-flash-001",       # 2.0 flash pinned version
        "models/gemini-flash-lite-latest",   # latest lite alias
        "models/gemini-2.0-flash-lite",      # 2.0 flash lite — most generous free quota
        "models/gemini-2.0-flash-lite-001",  # 2.0 flash lite pinned version
    ]

    def __init__(self, model: str | None = None, api_key: str | None = None, **kwargs: Any):
        super().__init__(
            model=model,
            api_key=api_key or os.environ.get("GEMINI_API_KEY"),
            base_url=kwargs.pop(
                "base_url",
                "https://generativelanguage.googleapis.com/v1beta/openai/",
            ),
            **kwargs,
        )

    def _default_model(self) -> str:
        return "models/gemini-3-flash-preview"

    def chat(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Chat with automatic fallback through free models on rate-limit."""
        # Build the ordered list: requested model first, then fallbacks
        candidates = [self.model] + [m for m in self.FALLBACK_MODELS if m != self.model]

        last_exc: Exception | None = None
        for candidate in candidates:
            original = self.model
            self.model = candidate
            try:
                response = super().chat(messages, tools=tools, temperature=temperature, max_tokens=max_tokens)
                if candidate != original:
                    import logging
                    logging.getLogger(__name__).info(
                        "GeminiProvider: fell back to %s (original: %s)", candidate, original
                    )
                return response
            except openai.RateLimitError as e:
                last_exc = e
                self.model = original  # restore before next try
                import logging
                logging.getLogger(__name__).warning(
                    "GeminiProvider: rate-limited on %s, trying next fallback…", candidate
                )
                continue
            except Exception:
                self.model = original
                raise
        # All fallbacks exhausted
        raise last_exc  # type: ignore[misc]


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
    "copilot-pro": CopilotProProvider,
    "gemini": GeminiProvider,
    "google": GeminiProvider,
}


def get_provider(name: str, **kwargs: Any) -> LLMProvider:
    """Get a provider by name. Raises KeyError if not found."""
    key = name.lower()
    if key not in _PROVIDERS:
        raise KeyError(
            f"Unknown provider '{name}'. Available: {', '.join(_PROVIDERS.keys())}"
        )
    return _PROVIDERS[key](**kwargs)
