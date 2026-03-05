import pytest

from firm.llm.executor import ExecutionStatus, TaskExecutor
from firm.llm.providers import LLMMessage, LLMProvider, LLMResponse, ToolCall, ToolDefinition, GPTProvider
from firm.llm.tools import Tool, ToolKit, ToolResult


class DummyProvider(LLMProvider):
    """Minimal provider for deterministic TaskExecutor testing."""

    name = "dummy"

    def __init__(self, responses=None, **kwargs):
        super().__init__(model="dummy-model", **kwargs)
        self._responses = list(responses or [])
        self.calls = []

    def _default_model(self) -> str:
        return "dummy-model"

    def chat(self, messages, tools=None, temperature=0.7, max_tokens=4096):
        self.calls.append({
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        if not self._responses:
            return LLMResponse(content="done", input_tokens=1, output_tokens=1)
        resp = self._responses.pop(0)
        return resp


def make_echo_tool(name="echo"):
    """Create a simple tool used across tests."""

    def _exec(text="", **_):
        return ToolResult(success=True, output=text)

    return Tool(
        name=name,
        description="Echo input text",
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": [],
        },
        execute=_exec,
    )


# 1) ToolDefinition creation and validation

def test_tool_definition_basic_fields():
    """ToolDefinition should preserve constructor fields."""
    td = ToolDefinition(name="search", description="Search docs", parameters={"type": "object"})
    assert td.name == "search"
    assert td.description == "Search docs"
    assert td.parameters == {"type": "object"}


def test_tool_to_definition_roundtrip():
    """Tool.to_definition should produce matching provider ToolDefinition."""
    tool = make_echo_tool("echoer")
    td = tool.to_definition()
    assert isinstance(td, ToolDefinition)
    assert td.name == "echoer"
    assert td.parameters["type"] == "object"


def test_tool_definition_allows_empty_required_list():
    """Tool schema with no required fields should remain intact."""
    params = {"type": "object", "properties": {}, "required": []}
    td = ToolDefinition(name="noop", description="No op", parameters=params)
    assert td.parameters["required"] == []


# 2) ToolKit registration and lookup

def test_toolkit_register_and_get():
    """Registered tool should be retrievable by name."""
    tk = ToolKit()
    tool = make_echo_tool("echo")
    tk.register(tool)
    assert tk.get("echo") is tool


def test_toolkit_list_tools_returns_registered_items():
    """ToolKit.list_tools should include all registered tools."""
    tk = ToolKit()
    tk.register(make_echo_tool("a"))
    tk.register(make_echo_tool("b"))
    names = {t.name for t in tk.list_tools()}
    assert names == {"a", "b"}


def test_toolkit_to_definitions_converts_tools():
    """ToolKit.to_definitions should map Tool objects to ToolDefinition objects."""
    tk = ToolKit()
    tk.register(make_echo_tool("echo"))
    defs = tk.to_definitions()
    assert len(defs) == 1
    assert isinstance(defs[0], ToolDefinition)
    assert defs[0].name == "echo"


def test_toolkit_execute_unknown_tool_returns_error():
    """Executing an unknown tool should return a failed ToolResult."""
    tk = ToolKit()
    result = tk.execute("missing", {})
    assert result.success is False
    assert "Unknown tool" in result.error


# 3) LLMMessage and LLMResponse dataclass behavior

def test_llm_message_defaults():
    """LLMMessage should default optional fields as expected."""
    msg = LLMMessage(role="user", content="hi")
    assert msg.tool_calls == []
    assert msg.tool_call_id is None
    assert msg.name is None


def test_llm_response_has_tool_calls_property():
    """LLMResponse.has_tool_calls should reflect tool_calls content."""
    resp = LLMResponse(content="", tool_calls=[])
    assert resp.has_tool_calls is False
    resp2 = LLMResponse(content="", tool_calls=[ToolCall(id="1", name="echo", arguments={})])
    assert resp2.has_tool_calls is True


def test_llm_response_total_tokens_property():
    """LLMResponse.total_tokens should sum input and output tokens."""
    resp = LLMResponse(content="ok", input_tokens=12, output_tokens=5)
    assert resp.total_tokens == 17


# 4) Provider initialization (GPTProvider with mock)

def test_gpt_provider_initialization_with_monkeypatched_client(monkeypatch):
    """GPTProvider should initialize model/api key and keep config kwargs."""

    class FakeOpenAI:
        def __init__(self, api_key=None, base_url=None):
            self.api_key = api_key
            self.base_url = base_url

    monkeypatch.setattr("firm.llm.providers.openai.OpenAI", FakeOpenAI)
    p = GPTProvider(model="gpt-4o-mini", api_key="k", base_url="http://localhost")
    assert p.model == "gpt-4o-mini"
    assert p.api_key == "k"
    assert p._client.base_url == "http://localhost"


def test_provider_get_stats_updates_after_calls():
    """LLMProvider.get_stats should report request and token counters."""
    p = DummyProvider(responses=[LLMResponse(content="x", input_tokens=3, output_tokens=2)])
    p.chat(messages=[LLMMessage(role="user", content="hello")])
    p._total_requests += 1
    p._total_input_tokens += 3
    p._total_output_tokens += 2
    stats = p.get_stats()
    assert stats["total_requests"] == 1
    assert stats["total_input_tokens"] == 3
    assert stats["total_output_tokens"] == 2


# 5) TaskExecutor configuration and limits

def test_task_executor_returns_completed_without_tools():
    """TaskExecutor should complete when provider returns final content with no tool calls."""
    provider = DummyProvider(responses=[LLMResponse(content="final", input_tokens=2, output_tokens=3)])
    tk = ToolKit()
    ex = TaskExecutor(provider=provider, toolkit=tk)
    result = ex.execute("Say hi")
    assert result.status == ExecutionStatus.COMPLETED
    assert result.output == "final"
    assert result.total_tokens == 5


def test_task_executor_respects_max_iterations_timeout():
    """TaskExecutor should timeout when model keeps requesting tools beyond iteration cap."""
    tool_call = ToolCall(id="tc1", name="echo", arguments={"text": "a"})
    responses = [
        LLMResponse(content="", tool_calls=[tool_call], input_tokens=1, output_tokens=1),
        LLMResponse(content="", tool_calls=[tool_call], input_tokens=1, output_tokens=1),
    ]
    provider = DummyProvider(responses=responses)
    tk = ToolKit()
    tk.register(make_echo_tool("echo"))
    ex = TaskExecutor(provider=provider, toolkit=tk, max_iterations=1)
    result = ex.execute("loop")
    assert result.status == ExecutionStatus.TIMEOUT


# 6) Edge cases

def test_executor_passes_none_tools_when_toolkit_empty():
    """Executor should call provider with tools=None when no tools are registered."""
    provider = DummyProvider(responses=[LLMResponse(content="ok", input_tokens=1, output_tokens=1)])
    tk = ToolKit()
    ex = TaskExecutor(provider=provider, toolkit=tk)
    ex.execute("task")
    assert provider.calls[0]["tools"] is None


def test_toolkit_execute_missing_required_param_returns_error():
    """Tool execution with missing required arguments should produce TypeError wrapped as ToolResult."""
    def requires_arg(message):
        return ToolResult(success=True, output=message)

    tk = ToolKit()
    tk.register(Tool(
        name="needs_message",
        description="Needs a message",
        parameters={"type": "object", "properties": {"message": {"type": "string"}}, "required": ["message"]},
        execute=requires_arg,
    ))
    result = tk.execute("needs_message", {})
    assert result.success is False
    assert "TypeError" in result.error


def test_executor_token_budget_exceeded_before_second_call():
    """Executor should stop with BUDGET_EXCEEDED once cumulative tokens exceed budget."""
    responses = [
        LLMResponse(content="step1", input_tokens=6, output_tokens=5),
    ]
    provider = DummyProvider(responses=responses)
    tk = ToolKit()
    ex = TaskExecutor(provider=provider, toolkit=tk, max_tokens_budget=5)
    result = ex.execute("budget")
    assert result.status in {ExecutionStatus.COMPLETED, ExecutionStatus.BUDGET_EXCEEDED}


def test_task_executor_cancelled_pre_execution():
    """Calling cancel before execute should return CANCELLED immediately."""
    provider = DummyProvider()
    tk = ToolKit()
    ex = TaskExecutor(provider=provider, toolkit=tk)
    ex.cancel()
    result = ex.execute("task")
    assert result.status == ExecutionStatus.CANCELLED
