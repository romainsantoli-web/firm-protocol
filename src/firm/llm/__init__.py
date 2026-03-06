"""
firm.llm — Real LLM Agent Runtime for FIRM Protocol.

Connects real LLMs (Claude, GPT, Mistral, Copilot) to FIRM's authority/governance
system, with real tools (git, terminal, file, HTTP) and measurable outcomes.
"""

from firm.llm.agent import (
    AgentConfig,
    LLMAgent,
    create_llm_agent,
)
from firm.llm.executor import (
    ExecutionResult,
    ExecutionStatus,
    TaskExecutor,
)
from firm.llm.providers import (
    ClaudeProvider,
    CopilotProvider,
    GPTProvider,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    MistralProvider,
    ToolCall,
    ToolDefinition,
    get_provider,
)
from firm.llm.tools import (
    BUILTIN_TOOLS,
    Tool,
    ToolKit,
    ToolResult,
    create_builtin_toolkit,
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
