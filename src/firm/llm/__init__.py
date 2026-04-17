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
from firm.llm.mcp_bridge import (
    check_mcp_server,
    create_mcp_toolkit,
    extend_agent_with_mcp,
    get_mcp_categories,
    MCP_CATEGORIES,
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
    # MCP Bridge
    "create_mcp_toolkit",
    "extend_agent_with_mcp",
    "check_mcp_server",
    "get_mcp_categories",
    "MCP_CATEGORIES",
    # Executor
    "TaskExecutor",
    "ExecutionResult",
    "ExecutionStatus",
    # Agent
    "LLMAgent",
    "AgentConfig",
    "create_llm_agent",
]
