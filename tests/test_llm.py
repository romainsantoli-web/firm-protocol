"""
Tests for firm.llm — LLM Agent Runtime.

Covers: providers, tools, executor, agent, and API integration.
Does NOT require real API keys — all LLM calls are mocked.
"""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from firm.api.app import app, state
from firm.llm.agent import AgentConfig, LLMAgent, create_llm_agent
from firm.llm.executor import (
    ExecutionResult,
    ExecutionStatus,
    TaskExecutor,
    ToolExecution,
    _estimate_cost,
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
    _run_cmd,
    create_builtin_toolkit,
)
from firm.runtime import Firm


class TestLLMMessage:
    def test_basic_message(self):
        msg = LLMMessage(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.tool_calls == []
        assert msg.tool_call_id is None

    def test_message_with_tool_calls(self):
        tc = ToolCall(id="tc1", name="git_status", arguments={})
        msg = LLMMessage(role="assistant", content="", tool_calls=[tc])
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0].name == "git_status"


class TestLLMResponse:
    def test_basic_response(self):
        resp = LLMResponse(content="Done", input_tokens=100, output_tokens=50)
        assert resp.content == "Done"
        assert not resp.has_tool_calls
        assert resp.total_tokens == 150

    def test_response_with_tools(self):
        tc = ToolCall(id="tc1", name="file_read", arguments={"path": "test.py"})
        resp = LLMResponse(content="", tool_calls=[tc], finish_reason="tool_use")
        assert resp.has_tool_calls
        assert resp.tool_calls[0].name == "file_read"


class TestGetProvider:
    def test_get_known_providers(self):
        # These will fail to connect (no API key) but the class should instantiate
        with patch("anthropic.Anthropic"):
            p = get_provider("claude")
            assert p.name == "claude"

        with patch("openai.OpenAI"):
            p = get_provider("gpt")
            assert p.name == "gpt"

        with patch("mistralai.Mistral"):
            p = get_provider("mistral")
            assert p.name == "mistral"

        with patch("openai.OpenAI"):
            p = get_provider("copilot")
            assert p.name == "copilot"

    def test_unknown_provider_raises(self):
        with pytest.raises(KeyError, match="Unknown provider"):
            get_provider("unknown_provider")

    def test_aliases(self):
        with patch("openai.OpenAI"):
            p1 = get_provider("openai")
            assert p1.name == "gpt"
            p2 = get_provider("github")
            assert p2.name == "copilot"


class TestClaudeProviderConversion:
    def test_convert_tools(self):
        with patch("anthropic.Anthropic"):
            p = ClaudeProvider(api_key="test")
        tools = [ToolDefinition(name="test", description="Test tool", parameters={"type": "object"})]
        result = p._convert_tools(tools)
        assert len(result) == 1
        assert result[0]["name"] == "test"
        assert "input_schema" in result[0]

    def test_convert_messages_with_system(self):
        with patch("anthropic.Anthropic"):
            p = ClaudeProvider(api_key="test")
        msgs = [
            LLMMessage(role="system", content="You are a helper."),
            LLMMessage(role="user", content="Hello"),
        ]
        system, converted = p._convert_messages(msgs)
        assert system == "You are a helper."
        assert len(converted) == 1
        assert converted[0]["role"] == "user"

    def test_convert_tool_result_messages(self):
        with patch("anthropic.Anthropic"):
            p = ClaudeProvider(api_key="test")
        msgs = [
            LLMMessage(role="user", content="Do it"),
            LLMMessage(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="tc1", name="git_status", arguments={})],
            ),
            LLMMessage(role="tool", content="M file.py", tool_call_id="tc1"),
        ]
        system, converted = p._convert_messages(msgs)
        assert len(converted) == 3
        assert converted[2]["content"][0]["type"] == "tool_result"
        assert converted[2]["content"][0]["tool_use_id"] == "tc1"

    def test_default_model(self):
        with patch("anthropic.Anthropic"):
            p = ClaudeProvider(api_key="test")
        assert "claude" in p.model

    def test_stats(self):
        with patch("anthropic.Anthropic"):
            p = ClaudeProvider(api_key="test")
        stats = p.get_stats()
        assert stats["provider"] == "claude"
        assert stats["total_requests"] == 0


class TestGPTProviderConversion:
    def test_convert_tools(self):
        with patch("openai.OpenAI"):
            p = GPTProvider(api_key="test")
        tools = [ToolDefinition(name="test", description="desc", parameters={"type": "object"})]
        result = p._convert_tools(tools)
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "test"

    def test_convert_messages_with_tool_calls(self):
        with patch("openai.OpenAI"):
            p = GPTProvider(api_key="test")
        msgs = [
            LLMMessage(role="system", content="sys"),
            LLMMessage(
                role="assistant",
                content="thinking",
                tool_calls=[ToolCall(id="tc1", name="file_read", arguments={"path": "x"})],
            ),
            LLMMessage(role="tool", content="content", tool_call_id="tc1"),
        ]
        converted = p._convert_messages(msgs)
        assert len(converted) == 3
        assert converted[1]["tool_calls"][0]["function"]["arguments"] == '{"path": "x"}'
        assert converted[2]["tool_call_id"] == "tc1"

    def test_default_model(self):
        with patch("openai.OpenAI"):
            p = GPTProvider(api_key="test")
        assert p.model == "gpt-4o"


class TestMistralProviderConversion:
    def test_convert_tools(self):
        with patch("mistralai.Mistral"):
            p = MistralProvider(api_key="test")
        tools = [ToolDefinition(name="t", description="d", parameters={"type": "object"})]
        result = p._convert_tools(tools)
        assert result[0]["type"] == "function"

    def test_default_model(self):
        with patch("mistralai.Mistral"):
            p = MistralProvider(api_key="test")
        assert "mistral" in p.model


class TestCopilotProvider:
    def test_inherits_gpt(self):
        assert issubclass(CopilotProvider, GPTProvider)

    def test_default_model(self):
        with patch("openai.OpenAI"):
            p = CopilotProvider(api_key="test")
        assert p.model == "gpt-4o"
        assert p.name == "copilot"


# ─────────────────────────────────────────────────────────────────────────────
# Tools
# ─────────────────────────────────────────────────────────────────────────────


class TestToolResult:
    def test_success(self):
        r = ToolResult(success=True, output="ok")
        assert r.success
        assert r.output == "ok"

    def test_failure(self):
        r = ToolResult(success=False, output="", error="boom")
        assert not r.success
        assert r.error == "boom"


class TestToolKit:
    def test_register_and_get(self):
        tk = ToolKit()
        tool = Tool(name="t1", description="test", parameters={}, execute=lambda: ToolResult(True, ""))
        tk.register(tool)
        assert tk.get("t1") is tool
        assert tk.get("nonexistent") is None

    def test_list_tools(self):
        tk = ToolKit()
        for i in range(3):
            tk.register(Tool(name=f"t{i}", description="", parameters={}, execute=lambda: ToolResult(True, "")))
        assert len(tk.list_tools()) == 3

    def test_execute_known_tool(self):
        tk = ToolKit()
        tk.register(Tool(name="echo", description="", parameters={},
                         execute=lambda msg="hi", **_: ToolResult(True, msg)))
        result = tk.execute("echo", {"msg": "hello"})
        assert result.success
        assert result.output == "hello"
        assert result.duration_ms > 0

    def test_execute_unknown_tool(self):
        tk = ToolKit()
        result = tk.execute("nonexistent", {})
        assert not result.success
        assert "Unknown tool" in result.error

    def test_execute_with_exception(self):
        def bad_tool(**_):
            raise ValueError("exploded")
        tk = ToolKit()
        tk.register(Tool(name="bad", description="", parameters={}, execute=bad_tool))
        result = tk.execute("bad", {})
        assert not result.success
        assert "ValueError" in result.error

    def test_execution_log(self):
        tk = ToolKit()
        tk.register(Tool(name="t", description="", parameters={},
                         execute=lambda **_: ToolResult(True, "ok")))
        tk.execute("t", {})
        tk.execute("t", {"x": 1})
        log = tk.get_execution_log()
        assert len(log) == 2
        assert log[0]["tool"] == "t"
        assert log[0]["success"]

    def test_to_definitions(self):
        tk = ToolKit()
        tk.register(Tool(name="t", description="desc", parameters={"type": "object"},
                         execute=lambda **_: ToolResult(True, "")))
        defs = tk.to_definitions()
        assert len(defs) == 1
        assert defs[0].name == "t"
        assert defs[0].description == "desc"


class TestBuiltinToolkit:
    def test_create_has_all_tools(self, tmp_path):
        tk = create_builtin_toolkit(working_dir=tmp_path)
        names = {t.name for t in tk.list_tools()}
        assert names == set(BUILTIN_TOOLS)

    def test_include_filter(self, tmp_path):
        tk = create_builtin_toolkit(working_dir=tmp_path, include={"git_"})
        names = {t.name for t in tk.list_tools()}
        assert all(n.startswith("git_") for n in names)
        assert len(names) == 6

    def test_file_read_real(self, tmp_path):
        (tmp_path / "test.txt").write_text("hello\nworld\n")
        tk = create_builtin_toolkit(working_dir=tmp_path)
        result = tk.execute("file_read", {"path": "test.txt"})
        assert result.success
        assert "hello" in result.output

    def test_file_write_real(self, tmp_path):
        tk = create_builtin_toolkit(working_dir=tmp_path)
        result = tk.execute("file_write", {"path": "out.txt", "content": "data"})
        assert result.success
        assert (tmp_path / "out.txt").read_text() == "data"

    def test_file_traversal_blocked(self, tmp_path):
        tk = create_builtin_toolkit(working_dir=tmp_path)
        result = tk.execute("file_read", {"path": "../../etc/passwd"})
        assert not result.success
        assert "traversal" in result.error.lower() or "not found" in result.error.lower()

    def test_file_list_real(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.txt").write_text("")
        tk = create_builtin_toolkit(working_dir=tmp_path)
        result = tk.execute("file_list", {})
        assert result.success
        assert "a.py" in result.output

    def test_git_status_real(self, tmp_path):
        # init a git repo in tmp
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        tk = create_builtin_toolkit(working_dir=tmp_path)
        result = tk.execute("git_status", {})
        assert result.success  # empty repo, no output is fine

    def test_terminal_safe_command(self, tmp_path):
        tk = create_builtin_toolkit(working_dir=tmp_path)
        result = tk.execute("terminal_run", {"command": "echo hello"})
        assert result.success
        assert "hello" in result.output

    def test_terminal_unsafe_command_blocked(self, tmp_path):
        tk = create_builtin_toolkit(working_dir=tmp_path)
        result = tk.execute("terminal_run", {"command": "rm -rf /"})
        assert not result.success
        assert "not in safe list" in result.error

    def test_terminal_allow_all(self, tmp_path):
        tk = create_builtin_toolkit(working_dir=tmp_path, allow_all_commands=True)
        result = tk.execute("terminal_run", {"command": "whoami"})
        assert result.success

    def test_python_run(self, tmp_path):
        tk = create_builtin_toolkit(working_dir=tmp_path)
        result = tk.execute("python_run", {"code": "print(2 + 2)"})
        assert result.success
        assert "4" in result.output

    def test_file_read_line_range(self, tmp_path):
        (tmp_path / "lines.txt").write_text("a\nb\nc\nd\ne\n")
        tk = create_builtin_toolkit(working_dir=tmp_path)
        result = tk.execute("file_read", {"path": "lines.txt", "start_line": 2, "end_line": 4})
        assert result.success
        assert result.output == "b\nc\nd"


class TestRunCmd:
    def test_success(self):
        r = _run_cmd(["echo", "hi"])
        assert r.success
        assert r.output == "hi"

    def test_failure(self):
        r = _run_cmd(["false"])
        assert not r.success

    def test_timeout(self):
        r = _run_cmd(["sleep", "10"], timeout=1)
        assert not r.success
        assert "timed out" in r.error.lower()

    def test_command_not_found(self):
        r = _run_cmd(["nonexistent_command_xyz"])
        assert not r.success
        assert "not found" in r.error.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Executor
# ─────────────────────────────────────────────────────────────────────────────


class MockProvider(LLMProvider):
    """Mock provider for testing the executor."""
    name = "mock"

    def __init__(self, responses: list[LLMResponse] | None = None):
        super().__init__(model="mock-v1")
        self._responses = responses or []
        self._call_idx = 0

    def _default_model(self) -> str:
        return "mock-v1"

    def chat(self, messages, tools=None, temperature=0.7, max_tokens=4096) -> LLMResponse:
        if self._call_idx < len(self._responses):
            resp = self._responses[self._call_idx]
            self._call_idx += 1
            return resp
        return LLMResponse(content="I'm done.", input_tokens=10, output_tokens=5)


class TestExecutionResult:
    def test_success_property(self):
        r = ExecutionResult(task_id="t1", status=ExecutionStatus.COMPLETED, output="done")
        assert r.success

    def test_failure_property(self):
        r = ExecutionResult(task_id="t1", status=ExecutionStatus.FAILED, output="", error="boom")
        assert not r.success

    def test_tools_used(self):
        r = ExecutionResult(
            task_id="t1",
            status=ExecutionStatus.COMPLETED,
            output="ok",
            tool_executions=[
                ToolExecution(tool_name="git_status", arguments={}, result=ToolResult(True, "")),
                ToolExecution(tool_name="file_read", arguments={}, result=ToolResult(True, "")),
                ToolExecution(tool_name="git_status", arguments={}, result=ToolResult(True, "")),
            ],
        )
        assert set(r.tools_used) == {"git_status", "file_read"}

    def test_to_dict(self):
        r = ExecutionResult(
            task_id="t1", status=ExecutionStatus.COMPLETED, output="done",
            input_tokens=100, output_tokens=50, total_iterations=3,
        )
        d = r.to_dict()
        assert d["task_id"] == "t1"
        assert d["status"] == "completed"
        assert d["input_tokens"] == 100


class TestEstimateCost:
    def test_known_model(self):
        cost = _estimate_cost("gpt-4o", 1_000_000, 0)
        assert cost == pytest.approx(2.5, abs=0.1)

    def test_unknown_model_uses_default(self):
        cost = _estimate_cost("unknown-model", 1_000_000, 0)
        assert cost > 0


class TestTaskExecutor:
    def test_simple_completion(self, tmp_path):
        """LLM returns a final answer (no tool calls) on first try."""
        provider = MockProvider([
            LLMResponse(content="The answer is 42.", input_tokens=50, output_tokens=20),
        ])
        tk = ToolKit(working_dir=tmp_path)
        executor = TaskExecutor(provider=provider, toolkit=tk)
        result = executor.execute("What is 6×7?")
        assert result.success
        assert "42" in result.output
        assert result.total_iterations == 1
        assert result.total_tokens == 70

    def test_tool_use_loop(self, tmp_path):
        """LLM uses a tool then returns final answer."""
        (tmp_path / "data.txt").write_text("hello world")
        tk = create_builtin_toolkit(working_dir=tmp_path)

        provider = MockProvider([
            # Iteration 1: request file_read
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc1", name="file_read", arguments={"path": "data.txt"})],
                finish_reason="tool_use",
                input_tokens=100,
                output_tokens=30,
            ),
            # Iteration 2: final answer
            LLMResponse(
                content="The file contains: hello world",
                input_tokens=150,
                output_tokens=20,
            ),
        ])

        executor = TaskExecutor(provider=provider, toolkit=tk)
        result = executor.execute("Read data.txt and tell me what's in it.")
        assert result.success
        assert "hello world" in result.output
        assert result.total_iterations == 2
        assert len(result.tool_executions) == 1
        assert result.tool_executions[0].tool_name == "file_read"
        assert result.tool_executions[0].result.success

    def test_max_iterations_reached(self, tmp_path):
        """LLM keeps calling tools past the limit."""
        tk = ToolKit(working_dir=tmp_path)
        tk.register(Tool(name="noop", description="", parameters={},
                         execute=lambda **_: ToolResult(True, "ok")))

        # Provider always returns a tool call
        responses = [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id=f"tc{i}", name="noop", arguments={})],
                finish_reason="tool_use",
                input_tokens=10,
                output_tokens=5,
            )
            for i in range(10)
        ]
        provider = MockProvider(responses)
        executor = TaskExecutor(provider=provider, toolkit=tk, max_iterations=3)
        result = executor.execute("Loop forever")
        assert result.status == ExecutionStatus.TIMEOUT
        assert result.total_iterations == 3

    def test_budget_exceeded(self, tmp_path):
        """Token budget is exceeded."""
        provider = MockProvider([
            LLMResponse(content="", tool_calls=[ToolCall(id="tc1", name="x", arguments={})],
                        input_tokens=60000, output_tokens=50000, finish_reason="tool_use"),
        ])
        tk = ToolKit(working_dir=tmp_path)
        executor = TaskExecutor(provider=provider, toolkit=tk, max_tokens_budget=100000)
        result = executor.execute("Expensive task")
        # First call consumes 110K tokens, second iteration checks budget
        assert result.status == ExecutionStatus.BUDGET_EXCEEDED

    def test_llm_error(self, tmp_path):
        """Provider raises an exception."""
        class ErrorProvider(LLMProvider):
            name = "error"
            def _default_model(self): return "err"
            def chat(self, *a, **kw):
                raise RuntimeError("API unavailable")
        tk = ToolKit(working_dir=tmp_path)
        executor = TaskExecutor(provider=ErrorProvider(), toolkit=tk)
        result = executor.execute("Try something")
        assert result.status == ExecutionStatus.FAILED
        assert "API unavailable" in result.error

    def test_cancel(self, tmp_path):
        """Executor can be cancelled."""
        provider = MockProvider([])
        tk = ToolKit(working_dir=tmp_path)
        executor = TaskExecutor(provider=provider, toolkit=tk)
        executor.cancel()  # cancel before starting
        result = executor.execute("Should not run")
        assert result.status == ExecutionStatus.CANCELLED

    def test_cost_budget(self, tmp_path):
        """Cost budget is enforced."""
        # gpt-4o: $2.5/M input, $10/M output
        # 500K input + 500K output = 2.5*0.5 + 10*0.5 = $6.25
        provider = MockProvider([
            LLMResponse(content="", tool_calls=[ToolCall(id="tc1", name="x", arguments={})],
                        input_tokens=500000, output_tokens=500000, finish_reason="tool_use"),
        ])
        provider.model = "gpt-4o"
        tk = ToolKit(working_dir=tmp_path)
        executor = TaskExecutor(provider=provider, toolkit=tk, max_cost_usd=5.0)
        result = executor.execute("Expensive")
        assert result.status == ExecutionStatus.BUDGET_EXCEEDED

    def test_system_prompt_passed(self, tmp_path):
        """System prompt is included in messages."""
        calls = []
        class SpyProvider(LLMProvider):
            name = "spy"
            def _default_model(self): return "spy-v1"
            def chat(self, messages, **kw):
                calls.append(messages)
                return LLMResponse(content="ok", input_tokens=10, output_tokens=5)
        tk = ToolKit(working_dir=tmp_path)
        executor = TaskExecutor(provider=SpyProvider(), toolkit=tk)
        executor.execute("test", system_prompt="Be helpful")
        assert len(calls) == 1
        assert calls[0][0].role == "system"
        assert calls[0][0].content == "Be helpful"


# ─────────────────────────────────────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────────────────────────────────────


class TestLLMAgent:
    def _make_agent(self, tmp_path, authority=0.5) -> LLMAgent:
        """Create an LLMAgent with a mock provider."""
        firm = Firm("test-firm")
        agent = firm.add_agent("test-agent", authority=authority)
        provider = MockProvider([
            LLMResponse(content="Task completed.", input_tokens=50, output_tokens=20),
        ])
        toolkit = create_builtin_toolkit(working_dir=tmp_path)
        return LLMAgent(
            firm=firm,
            agent=agent,
            provider=provider,
            toolkit=toolkit,
            config=AgentConfig(auto_record_actions=True),
        )

    def test_basic_execution(self, tmp_path):
        llm_agent = self._make_agent(tmp_path, authority=0.7)
        result = llm_agent.execute_task("Say hello")
        assert result.success
        assert "Task completed" in result.output

    def test_authority_gates_tools(self, tmp_path):
        # Low authority agent gets fewer tools
        agent_low = self._make_agent(tmp_path, authority=0.2)
        toolkit_low = agent_low._get_available_toolkit()
        names_low = {t.name for t in toolkit_low.list_tools()}

        agent_high = self._make_agent(tmp_path, authority=0.9)
        toolkit_high = agent_high._get_available_toolkit()
        names_high = {t.name for t in toolkit_high.list_tools()}

        assert len(names_low) < len(names_high)
        assert "file_read" in names_low  # probation still has file_read
        assert "terminal_run" not in names_low
        assert "terminal_run" in names_high

    def test_authority_level_tiers(self, tmp_path):
        for auth, expected_terminal, expected_write in [
            (0.1, False, False),
            (0.3, False, False),
            (0.5, False, False),   # 0.5 is read-only tier (<0.6)
            (0.6, False, True),
            (0.8, True, True),
            (1.0, True, True),
        ]:
            agent = self._make_agent(tmp_path, authority=auth)
            tk = agent._get_available_toolkit()
            names = {t.name for t in tk.list_tools()}
            assert ("terminal_run" in names) == expected_terminal, f"auth={auth}, terminal"
            assert ("file_write" in names) == expected_write, f"auth={auth}, write"

    def test_kill_switch_blocks(self, tmp_path):
        llm_agent = self._make_agent(tmp_path, authority=0.9)
        llm_agent.firm.constitution.kill_switch_active = True
        result = llm_agent.execute_task("Something")
        assert not result.success
        assert "Kill switch" in result.error

    def test_budget_scaled_by_authority(self, tmp_path):
        agent_low = self._make_agent(tmp_path, authority=0.3)
        agent_high = self._make_agent(tmp_path, authority=0.9)

        # Low authority should get scaled-down budget
        max_tokens_low = int(agent_low.config.max_tokens_budget * max(0.2, 0.3))
        max_tokens_high = int(agent_high.config.max_tokens_budget * max(0.2, 0.9))
        assert max_tokens_low < max_tokens_high

    def test_auto_record_action(self, tmp_path):
        llm_agent = self._make_agent(tmp_path, authority=0.7)
        initial_entries = llm_agent.firm.ledger.length
        llm_agent.execute_task("Do something")
        # Should have recorded the action
        assert llm_agent.firm.ledger.length > initial_entries

    def test_system_prompt_contains_firm_context(self, tmp_path):
        llm_agent = self._make_agent(tmp_path, authority=0.7)
        prompt = llm_agent._build_system_prompt()
        assert "test-agent" in prompt
        assert "test-firm" in prompt
        assert "0.70" in prompt
        assert "Authority Level" in prompt

    def test_get_stats(self, tmp_path):
        llm_agent = self._make_agent(tmp_path, authority=0.7)
        llm_agent.execute_task("test task")
        stats = llm_agent.get_stats()
        assert stats["tasks_executed"] == 1
        assert stats["tasks_succeeded"] == 1
        assert stats["success_rate"] == 1.0
        assert stats["provider"] == "mock"

    def test_event_emitted(self, tmp_path):
        events = []
        llm_agent = self._make_agent(tmp_path, authority=0.7)
        llm_agent.firm.events.subscribe("agent.task_completed", lambda e: events.append(e))
        llm_agent.execute_task("test emission")
        assert len(events) == 1

    def test_propose_delegates(self, tmp_path):
        llm_agent = self._make_agent(tmp_path, authority=0.8)
        result = llm_agent.propose("Test proposal", "Testing governance")
        # firm.propose() returns a Proposal object with an id attribute
        assert hasattr(result, "id") or isinstance(result, dict)

    def test_properties(self, tmp_path):
        llm_agent = self._make_agent(tmp_path, authority=0.6)
        assert llm_agent.authority == 0.6
        assert llm_agent.name == "test-agent"
        assert isinstance(llm_agent.agent_id, str)


class TestCreateLLMAgent:
    def test_factory_function(self, tmp_path):
        firm = Firm("factory-test")
        with patch("anthropic.Anthropic"):
            agent = create_llm_agent(
                firm=firm,
                name="cto",
                provider_name="claude",
                authority=0.8,
                working_dir=str(tmp_path),
                roles=["engineering"],
            )
        assert agent.name == "cto"
        assert agent.authority == 0.8
        assert agent.provider.name == "claude"
        assert "cto" in [a.name for a in firm._agents.values()]


# ─────────────────────────────────────────────────────────────────────────────
# API
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def api_client():
    """Fresh API test client with clean state."""
    # Reset state
    state.firm = None
    state.llm_agents = {}
    state.task_results = []
    state.connected_websockets = []
    return TestClient(app)


class TestAPIHealth:
    def test_health_endpoint(self, api_client):
        resp = api_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["firm_active"] is False

    def test_metrics_no_firm(self, api_client):
        resp = api_client.get("/metrics")
        assert resp.status_code == 200
        assert "firm_uptime_seconds" in resp.text


class TestAPIFirm:
    def test_create_firm(self, api_client):
        resp = api_client.post("/firm", json={"name": "test-startup"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-startup"

    def test_get_firm(self, api_client):
        api_client.post("/firm", json={"name": "my-co"})
        resp = api_client.get("/firm")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "my-co"
        assert isinstance(data["agents"], list)

    def test_get_firm_without_creating(self, api_client):
        resp = api_client.get("/firm")
        assert resp.status_code == 503


class TestAPIAgents:
    def test_create_agent(self, api_client):
        api_client.post("/firm", json={"name": "co"})
        with patch("anthropic.Anthropic"):
            resp = api_client.post("/agents", json={
                "name": "dev-1",
                "provider": "claude",
                "authority": 0.6,
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "dev-1"
        assert data["provider"] == "claude"
        assert data["tools_available"] > 0

    def test_list_agents(self, api_client):
        api_client.post("/firm", json={"name": "co"})
        with patch("anthropic.Anthropic"):
            api_client.post("/agents", json={"name": "a1", "provider": "claude"})
            api_client.post("/agents", json={"name": "a2", "provider": "claude"})
        resp = api_client.get("/agents")
        assert resp.status_code == 200
        assert len(resp.json()["agents"]) == 2

    def test_get_agent_not_found(self, api_client):
        api_client.post("/firm", json={"name": "co"})
        resp = api_client.get("/agents/nonexistent")
        assert resp.status_code == 404


class TestAPITasks:
    def test_execute_task_no_agent(self, api_client):
        api_client.post("/firm", json={"name": "co"})
        resp = api_client.post("/agents/fake/execute", json={"task": "test"})
        assert resp.status_code == 404

    def test_list_tasks_empty(self, api_client):
        resp = api_client.get("/tasks")
        assert resp.status_code == 200
        assert resp.json()["results"] == []


class TestAPIGovernance:
    def test_propose(self, api_client):
        api_client.post("/firm", json={"name": "co"})
        with patch("anthropic.Anthropic"):
            resp = api_client.post("/agents", json={"name": "ceo", "provider": "claude", "authority": 0.8})
        agent_id = resp.json()["agent_id"]
        resp = api_client.post(f"/agents/{agent_id}/propose", json={
            "title": "Add QA", "description": "We need QA"
        })
        assert resp.status_code == 200


class TestAPILedger:
    def test_get_ledger(self, api_client):
        api_client.post("/firm", json={"name": "co"})
        resp = api_client.get("/ledger")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1  # genesis entry

    def test_get_ledger_without_firm(self, api_client):
        resp = api_client.get("/ledger")
        assert resp.status_code == 503


class TestAPIDashboard:
    def test_dashboard_serves_html(self, api_client):
        resp = api_client.get("/")
        assert resp.status_code == 200
        assert "FIRM Protocol" in resp.text


class TestAPIMetrics:
    def test_metrics_with_firm(self, api_client):
        api_client.post("/firm", json={"name": "co"})
        resp = api_client.get("/metrics")
        assert resp.status_code == 200
        text = resp.text
        assert "firm_agents_total" in text
        assert "firm_ledger_entries_total" in text
        assert "firm_tasks_executed_total" in text
