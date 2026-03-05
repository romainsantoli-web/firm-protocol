"""
firm.llm — Real LLM Agent Runtime for FIRM Protocol.

Connects real LLMs (Claude, GPT, Mistral, Copilot) to FIRM's authority/governance
system, with real tools (git, terminal, file, HTTP) and measurable outcomes.
"""

from firm.llm.providers import (
    LLMProvider,
    LLMMessage,
    LLMResponse,
    ToolCall,
    ToolDefinition,
    ClaudeProvider,
    GPTProvider,
    MistralProvider,
    CopilotProvider,
    get_provider,
)
from firm.llm.tools import (
    Tool,
    ToolResult,
    ToolKit,
    BUILTIN_TOOLS,
    create_builtin_toolkit,
)
from firm.llm.executor import (
    TaskExecutor,
    ExecutionResult,
    ExecutionStatus,
)
from firm.llm.agent import (
    LLMAgent,
    AgentConfig,
    create_llm_agent,
)

__all__ = [
    # Providers
    "LLMProvider",
    "LLMMessage",
    "LLMResponse",
    "ToolCall",
    "ToolDefinition",
    "ClaudeProvider",
    "GPTProvider",
    "MistralProvider",
    "CopilotProvider",
    "get_provider",
    # Tools
    "Tool",
    "ToolResult",
    "ToolKit",
    "BUILTIN_TOOLS",
    "create_builtin_toolkit",
    # Executor
    "TaskExecutor",
    "ExecutionResult",
    "ExecutionStatus",
    # Agent
    "LLMAgent",
    "AgentConfig",
    "create_llm_agent",
]
