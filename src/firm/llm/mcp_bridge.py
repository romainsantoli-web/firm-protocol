"""
firm.llm.mcp_bridge — Bridge between MCP ecosystem tools and FIRM protocol.

Discovers MCP tools via JSON-RPC (tools/list) and wraps each one as a
firm.llm.tools.Tool so that LLMAgent can use the full 138+21 tool ecosystem
(security audit, hebbian memory, A2A, market research, semantic memory, etc.) natively.

Supports two MCP servers:
  - **OpenClaw** (143 tools) — JSON-RPC at http://127.0.0.1:8012/mcp
  - **Memory OS AI** (21 tools) — direct Python import (SSE transport bypassed)

Usage:
    from firm.runtime import Firm
    from firm.llm.agent import create_llm_agent
    from firm.llm.mcp_bridge import (
        create_mcp_toolkit, extend_agent_with_mcp,
        create_memory_toolkit, extend_agent_with_memory,
        extend_agent_with_all_mcp,
    )

    # Option 1 — OpenClaw tools only
    mcp_toolkit = create_mcp_toolkit()
    tools = mcp_toolkit.list_tools()   # 143 Tool objects

    # Option 2 — Memory OS AI tools only
    mem_toolkit = create_memory_toolkit()
    tools = mem_toolkit.list_tools()   # 21 Tool objects

    # Option 3 — ALL ecosystem tools (143 + 21 = 164)
    firm = Firm("my-startup")
    cto = create_llm_agent(firm, "CTO", provider_name="copilot-pro", authority=0.8)
    extend_agent_with_all_mcp(cto)  # adds 164 tools

    # Option 4 — filter by category
    security_kit = create_mcp_toolkit(categories=["security"])
    memory_kit   = create_memory_toolkit(filter_prefix="memory_search")

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any

from firm.llm.tools import Tool, ToolKit, ToolResult

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

MCP_DEFAULT_URL = os.getenv("FIRM_MCP_URL", "http://127.0.0.1:8012")
MCP_TIMEOUT = int(os.getenv("FIRM_MCP_TIMEOUT", "120"))

# ─────────────────────────────────────────────────────────────────────────────
# JSON-RPC client (stdlib only — no extra deps)
# ─────────────────────────────────────────────────────────────────────────────

_rpc_counter = 0


def _jsonrpc_call(
    method: str,
    params: dict[str, Any],
    mcp_url: str = MCP_DEFAULT_URL,
    timeout: int = MCP_TIMEOUT,
) -> dict[str, Any]:
    """Send a JSON-RPC 2.0 request to the MCP server."""
    global _rpc_counter
    _rpc_counter += 1

    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": _rpc_counter,
        "method": method,
        "params": params,
    }).encode()

    req = urllib.request.Request(
        f"{mcp_url}/mcp",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Cannot reach MCP server at {mcp_url}: {exc}"
        ) from exc

    if "error" in data:
        err = data["error"]
        raise RuntimeError(
            f"MCP error {err.get('code', '?')}: {err.get('message', str(err))}"
        )

    return data.get("result", data)


def _list_mcp_tools(mcp_url: str = MCP_DEFAULT_URL) -> list[dict[str, Any]]:
    """Discover all tools exposed by the MCP server."""
    result = _jsonrpc_call("tools/list", {}, mcp_url=mcp_url)
    return result.get("tools", []) if isinstance(result, dict) else []


def _call_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
    mcp_url: str = MCP_DEFAULT_URL,
) -> ToolResult:
    """Call a single MCP tool and return a FIRM ToolResult."""
    try:
        result = _jsonrpc_call(
            "tools/call",
            {"name": tool_name, "arguments": arguments},
            mcp_url=mcp_url,
        )
        # MCP tools return content as a list of text/json parts
        if isinstance(result, dict) and "content" in result:
            parts = result["content"]
            text_parts = [
                p.get("text", json.dumps(p))
                for p in parts
                if isinstance(p, dict)
            ]
            output = "\n".join(text_parts)
        else:
            output = json.dumps(result, indent=2, ensure_ascii=False)

        is_error = result.get("isError", False) if isinstance(result, dict) else False

        return ToolResult(
            success=not is_error,
            output=output,
            error="" if not is_error else output,
        )
    except (ConnectionError, RuntimeError) as exc:
        return ToolResult(success=False, output="", error=str(exc))
    except Exception as exc:
        return ToolResult(
            success=False,
            output="",
            error=f"{type(exc).__name__}: {exc}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tool wrapping
# ─────────────────────────────────────────────────────────────────────────────

def _wrap_mcp_tool(tool_def: dict[str, Any], mcp_url: str) -> Tool:
    """Convert an MCP tool definition to a FIRM Tool."""
    name = tool_def["name"]
    description = tool_def.get("description", name)
    input_schema = tool_def.get("inputSchema", {
        "type": "object",
        "properties": {},
        "required": [],
    })

    # Classify dangerous tools (security scans, sandbox exec, etc.)
    dangerous_prefixes = (
        "firm_sandbox", "firm_exec", "firm_workspace",
        "fleet_session_inject", "fleet_cron",
    )
    is_dangerous = any(name.startswith(p) for p in dangerous_prefixes)

    def _execute(*, _tool_name: str = name, _url: str = mcp_url, **kwargs: Any) -> ToolResult:
        return _call_mcp_tool(_tool_name, kwargs, mcp_url=_url)

    return Tool(
        name=name,
        description=description,
        parameters=input_schema,
        execute=_execute,
        dangerous=is_dangerous,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

# Category helpers — maps friendly names to tool name prefixes
MCP_CATEGORIES: dict[str, list[str]] = {
    "security": [
        "firm_security", "firm_sandbox", "firm_secrets",
        "firm_safe", "firm_voice", "firm_trust",
    ],
    "memory": ["firm_hebbian", "firm_pgvector", "firm_knowledge"],
    "a2a": ["firm_a2a"],
    "gateway": ["firm_gateway", "firm_credentials", "firm_webhook", "firm_log"],
    "fleet": ["fleet_cron", "fleet_session"],
    "audit": [
        "firm_node", "firm_http", "firm_session",
        "firm_rate", "firm_channel", "firm_doc",
        "firm_dm", "firm_shell", "firm_otel",
    ],
    "delivery": ["firm_export"],
    "compliance": [
        "firm_elicitation", "firm_tasks", "firm_oauth",
        "firm_token", "firm_prompt", "firm_gdpr",
        "firm_agent_identity", "firm_model_routing",
        "firm_resource", "firm_circuit",
    ],
    "observability": ["firm_observability", "firm_ci"],
    "config": [
        "firm_config", "firm_plugin", "firm_rpc",
        "firm_exec", "firm_hook", "firm_group",
    ],
    "orchestration": ["firm_agent_team"],
    "acp": ["acp_session", "firm_acpx", "firm_workspace"],
    "vs_bridge": ["vs_context", "vs_session"],
    "market_research": [
        "firm_market", "firm_supplier", "firm_location", "firm_legal",
    ],
    "spec": [
        "firm_sse", "firm_json", "firm_icon",
        "firm_audio", "firm_resources",
    ],
    "tools": [
        "firm_skill", "firm_i18n", "firm_n8n", "firm_browser",
        "firm_rag", "firm_mcp", "firm_content",
    ],
}


def create_mcp_toolkit(
    mcp_url: str | None = None,
    filter_prefix: str = "",
    categories: list[str] | None = None,
    timeout: int = 30,
) -> ToolKit:
    """
    Create a FIRM ToolKit populated with MCP ecosystem tools.

    Args:
        mcp_url: MCP server URL (default: $FIRM_MCP_URL or http://127.0.0.1:8012).
        filter_prefix: Only include tools whose name starts with this prefix.
        categories: Only include tools from these categories (see MCP_CATEGORIES).
        timeout: ToolKit execution timeout.

    Returns:
        A ToolKit containing Tool objects wrapping MCP tools.

    Raises:
        ConnectionError: If the MCP server is unreachable.

    Example:
        >>> kit = create_mcp_toolkit()
        >>> len(kit.list_tools())  # all 138 MCP tools
        138

        >>> sec = create_mcp_toolkit(categories=["security"])
        >>> [t.name for t in sec.list_tools()]
        ['openclaw_security_scan', 'openclaw_sandbox_audit', ...]

        >>> mem = create_mcp_toolkit(filter_prefix="openclaw_hebbian")
        >>> len(mem.list_tools())
        8
    """
    url = mcp_url or MCP_DEFAULT_URL
    toolkit = ToolKit(timeout=timeout)

    # Build prefix set from categories
    prefixes: set[str] = set()
    if categories:
        for cat in categories:
            cat_prefixes = MCP_CATEGORIES.get(cat)
            if cat_prefixes is None:
                available = ", ".join(sorted(MCP_CATEGORIES))
                raise ValueError(
                    f"Unknown category '{cat}'. Available: {available}"
                )
            prefixes.update(cat_prefixes)

    mcp_tools = _list_mcp_tools(url)
    logger.info("Discovered %d MCP tools at %s", len(mcp_tools), url)

    for tool_def in mcp_tools:
        name = tool_def.get("name", "")

        # Apply prefix filter
        if filter_prefix and not name.startswith(filter_prefix):
            continue

        # Apply category filter
        if prefixes and not any(name.startswith(p) for p in prefixes):
            continue

        tool = _wrap_mcp_tool(tool_def, url)
        toolkit.register(tool)

    logger.info("Registered %d tools in ToolKit", len(toolkit.list_tools()))
    return toolkit


def extend_agent_with_mcp(
    agent: Any,
    mcp_url: str | None = None,
    filter_prefix: str = "",
    categories: list[str] | None = None,
) -> int:
    """
    Add MCP ecosystem tools to an existing LLMAgent.

    This extends the agent's toolkit with MCP tools so it can use
    security audit, memory, A2A, delivery, and other ecosystem tools
    alongside its built-in git/terminal/file tools.

    Args:
        agent: An LLMAgent instance.
        mcp_url: MCP server URL.
        filter_prefix: Only include tools whose name starts with this prefix.
        categories: Only include tools from these categories.

    Returns:
        Number of MCP tools added.

    Example:
        >>> firm = Firm("my-startup")
        >>> cto = create_llm_agent(firm, "CTO", authority=0.8)
        >>> added = extend_agent_with_mcp(cto, categories=["security", "memory"])
        >>> print(f"Added {added} MCP tools")
        Added 12 MCP tools
    """
    mcp_toolkit = create_mcp_toolkit(
        mcp_url=mcp_url,
        filter_prefix=filter_prefix,
        categories=categories,
    )

    count = 0
    for tool in mcp_toolkit.list_tools():
        agent._toolkit.register(tool)
        count += 1

    logger.info("Extended agent '%s' with %d MCP tools", getattr(agent, "name", "?"), count)
    return count


def get_mcp_categories() -> dict[str, list[str]]:
    """Return available MCP tool categories and their prefixes."""
    return dict(MCP_CATEGORIES)


def check_mcp_server(mcp_url: str | None = None) -> dict[str, Any]:
    """
    Check if the MCP server is reachable and return basic info.

    Returns:
        Dict with 'ok', 'url', 'tool_count', and 'error' keys.
    """
    url = mcp_url or MCP_DEFAULT_URL
    try:
        tools = _list_mcp_tools(url)
        return {
            "ok": True,
            "url": url,
            "tool_count": len(tools),
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": url,
            "tool_count": 0,
            "error": str(exc),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Memory OS AI bridge (21 tools — direct Python import, no SSE)
# ─────────────────────────────────────────────────────────────────────────────

_memory_dispatch = None  # lazy import cache
_memory_tools_cache: list[dict[str, Any]] | None = None


def _get_memory_dispatch() -> Any:
    """Import memory_os_ai._dispatch lazily."""
    global _memory_dispatch
    if _memory_dispatch is None:
        try:
            from memory_os_ai.server import _dispatch
            _memory_dispatch = _dispatch
        except ImportError as exc:
            raise ImportError(
                "memory-os-ai is not installed. "
                "Install with: pip install memory-os-ai"
            ) from exc
    return _memory_dispatch


def _list_memory_tools() -> list[dict[str, Any]]:
    """Discover all tools from memory-os-ai (via direct import)."""
    global _memory_tools_cache
    if _memory_tools_cache is None:
        try:
            from memory_os_ai.server import TOOLS
            _memory_tools_cache = list(TOOLS)
        except ImportError:
            _memory_tools_cache = []
    return _memory_tools_cache


def _call_memory_tool(tool_name: str, arguments: dict[str, Any]) -> ToolResult:
    """Call a memory-os-ai tool directly via Python (no SSE round-trip)."""
    try:
        dispatch = _get_memory_dispatch()
        # Validate via Pydantic if available
        try:
            from memory_os_ai.server import TOOL_MODELS
            model_cls = TOOL_MODELS.get(tool_name)
            if model_cls:
                validated = model_cls(**arguments)
                arguments = validated.model_dump()
        except ImportError:
            pass

        result = dispatch(tool_name, arguments)
        output = json.dumps(result, indent=2, ensure_ascii=False) if not isinstance(result, str) else result
        is_error = isinstance(result, dict) and not result.get("ok", True)
        return ToolResult(
            success=not is_error,
            output=output,
            error="" if not is_error else output,
        )
    except Exception as exc:
        return ToolResult(
            success=False,
            output="",
            error=f"{type(exc).__name__}: {exc}",
        )


def _wrap_memory_tool(tool_def: dict[str, Any]) -> Tool:
    """Convert a memory-os-ai tool definition to a FIRM Tool."""
    name = tool_def["name"]
    description = tool_def.get("description", name)
    input_schema = tool_def.get("inputSchema", {
        "type": "object",
        "properties": {},
        "required": [],
    })

    def _execute(*, _tool_name: str = name, **kwargs: Any) -> ToolResult:
        return _call_memory_tool(_tool_name, kwargs)

    return Tool(
        name=name,
        description=f"[Memory] {description}",
        parameters=input_schema,
        execute=_execute,
        dangerous=False,
    )


# Memory tool categories for filtering
MEMORY_CATEGORIES: dict[str, list[str]] = {
    "search": ["memory_search", "memory_get_context"],
    "ingest": ["memory_ingest", "memory_list_documents", "memory_transcribe"],
    "chat": ["memory_chat_sync", "memory_chat_save", "memory_chat_source",
             "memory_chat_status", "memory_chat_auto_detect"],
    "session": ["memory_session_brief", "memory_compact", "memory_status"],
    "project": ["memory_project_link", "memory_project_unlink", "memory_project_list"],
    "cloud": ["memory_cloud_configure", "memory_cloud_status", "memory_cloud_sync"],
}


def create_memory_toolkit(
    filter_prefix: str = "",
    categories: list[str] | None = None,
    timeout: int = 30,
) -> ToolKit:
    """
    Create a FIRM ToolKit with Memory OS AI tools (21 tools).

    Args:
        filter_prefix: Only include tools whose name starts with this prefix.
        categories: Only include tools matching category prefixes.
        timeout: ToolKit execution timeout.

    Returns:
        A ToolKit containing Tool objects wrapping memory-os-ai tools.
    """
    toolkit = ToolKit(timeout=timeout)

    # Build prefix set from categories
    prefixes: set[str] = set()
    if categories:
        for cat in categories:
            cat_prefixes = MEMORY_CATEGORIES.get(cat)
            if cat_prefixes:
                prefixes.update(cat_prefixes)

    mem_tools = _list_memory_tools()
    logger.info("Discovered %d Memory OS AI tools", len(mem_tools))

    for tool_def in mem_tools:
        name = tool_def.get("name", "")
        if filter_prefix and not name.startswith(filter_prefix):
            continue
        if prefixes and not any(name.startswith(p) for p in prefixes):
            continue
        tool = _wrap_memory_tool(tool_def)
        toolkit.register(tool)

    logger.info("Registered %d memory tools in ToolKit", len(toolkit.list_tools()))
    return toolkit


def extend_agent_with_memory(
    agent: Any,
    filter_prefix: str = "",
    categories: list[str] | None = None,
) -> int:
    """
    Add Memory OS AI tools to an existing LLMAgent.

    Returns:
        Number of memory tools added.
    """
    mem_toolkit = create_memory_toolkit(
        filter_prefix=filter_prefix,
        categories=categories,
    )
    count = 0
    for tool in mem_toolkit.list_tools():
        agent._toolkit.register(tool)
        count += 1
    logger.info("Extended agent '%s' with %d memory tools", getattr(agent, "name", "?"), count)
    return count


def extend_agent_with_all_mcp(
    agent: Any,
    mcp_url: str | None = None,
    mcp_categories: list[str] | None = None,
    memory_categories: list[str] | None = None,
) -> int:
    """
    Add both OpenClaw MCP tools (143) and Memory OS AI tools (21) to an agent.

    Args:
        agent: An LLMAgent instance.
        mcp_url: OpenClaw MCP server URL.
        mcp_categories: Filter for OpenClaw tool categories.
        memory_categories: Filter for Memory OS AI tool categories.

    Returns:
        Total number of tools added.
    """
    total = 0

    # OpenClaw tools
    try:
        total += extend_agent_with_mcp(
            agent, mcp_url=mcp_url, categories=mcp_categories,
        )
    except Exception as exc:
        logger.warning("OpenClaw MCP bridge failed: %s", exc)

    # Memory OS AI tools
    try:
        total += extend_agent_with_memory(
            agent, categories=memory_categories,
        )
    except Exception as exc:
        logger.warning("Memory OS AI bridge failed: %s", exc)

    logger.info(
        "Total: %d ecosystem tools added to '%s'",
        total, getattr(agent, "name", "?"),
    )
    return total


def check_all_mcp_servers(mcp_url: str | None = None) -> dict[str, Any]:
    """Check both MCP servers and return status."""
    openclaw = check_mcp_server(mcp_url)

    try:
        mem_tools = _list_memory_tools()
        memory = {
            "ok": len(mem_tools) > 0,
            "source": "direct-import",
            "tool_count": len(mem_tools),
            "error": None,
        }
    except Exception as exc:
        memory = {
            "ok": False,
            "source": "direct-import",
            "tool_count": 0,
            "error": str(exc),
        }

    return {
        "openclaw": openclaw,
        "memory_os_ai": memory,
        "total_tools": openclaw["tool_count"] + memory["tool_count"],
    }
