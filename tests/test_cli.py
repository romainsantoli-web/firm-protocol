"""
test_cli — Tests for the FIRM Protocol CLI.

Tests the CLI entry point by calling main(argv=[...]) and capturing stdout.
"""

import json
from io import StringIO
from unittest import mock

import pytest

from firm.cli import main, _firm, build_parser
import firm.cli as cli_module


@pytest.fixture(autouse=True)
def reset_global_firm():
    """Reset the global firm instance between tests."""
    cli_module._firm = None
    yield
    cli_module._firm = None


class TestCLIVersion:
    """Test --version and --help."""

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "firm" in out
        assert "0.5.0" in out

    def test_no_args_shows_help(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 0


class TestCLIInit:
    """Test the init command."""

    def test_init_creates_firm(self, capsys):
        main(["init", "TestCo"])
        out = capsys.readouterr().out
        assert "TestCo" in out
        assert "created" in out
        assert cli_module._firm is not None
        assert cli_module._firm.name == "TestCo"


class TestCLIAgentCommands:
    """Test agent add/list commands."""

    def test_agent_add(self, capsys):
        main(["init", "TestFirm"])
        main(["agent", "add", "Alice", "--authority", "0.8"])
        out = capsys.readouterr().out
        assert "Alice" in out
        assert "added" in out

    def test_agent_add_default_authority(self, capsys):
        main(["init", "TestFirm"])
        main(["agent", "add", "Bob"])
        out = capsys.readouterr().out
        assert "Bob" in out

    def test_agent_list(self, capsys):
        main(["init", "TestFirm"])
        main(["agent", "add", "Alice"])
        main(["agent", "add", "Bob"])
        main(["agent", "list"])
        out = capsys.readouterr().out
        assert "Alice" in out
        assert "Bob" in out

    def test_agent_list_empty(self, capsys):
        main(["init", "EmptyFirm"])
        main(["agent", "list"])
        out = capsys.readouterr().out
        # Should show header or "No agents" or list with 0 items
        # (Actually no agents case — the firm starts with no agents)
        assert "No agents" in out or "Name" in out


class TestCLIAction:
    """Test action recording."""

    def test_record_success(self, capsys):
        main(["init", "TestFirm"])
        capsys.readouterr()  # clear init output
        main(["agent", "add", "Alice", "--authority", "0.6"])
        out = capsys.readouterr().out
        agent_id = _extract_agent_id(out)

        main(["action", agent_id, "ok", "Shipped feature"])
        out2 = capsys.readouterr().out
        assert "authority" in out2.lower() or "success" in out2.lower()

    def test_record_failure(self, capsys):
        main(["init", "TestFirm"])
        capsys.readouterr()  # clear init output
        main(["agent", "add", "Bob", "--authority", "0.5"])
        out = capsys.readouterr().out
        agent_id = _extract_agent_id(out)

        main(["action", agent_id, "fail", "Broke build"])
        out2 = capsys.readouterr().out
        assert "authority" in out2.lower() or "fail" in out2.lower()


class TestCLIStatus:
    """Test status command."""

    def test_status(self, capsys):
        main(["init", "TestFirm"])
        main(["agent", "add", "Alice"])
        main(["status"])
        out = capsys.readouterr().out
        assert "TestFirm" in out


class TestCLIGovernance:
    """Test propose/vote/finalize."""

    def test_propose(self, capsys):
        main(["init", "TestFirm"])
        capsys.readouterr()
        main(["agent", "add", "CEO", "--authority", "0.9"])
        out = capsys.readouterr().out
        agent_id = _extract_agent_id(out)

        main(["propose", agent_id, "New rule", "A new governance rule"])
        out2 = capsys.readouterr().out
        assert "Proposal" in out2 or "proposal" in out2


class TestCLIRoles:
    """Test role define/assign."""

    def test_role_define(self, capsys):
        main(["init", "TestFirm"])
        main(["role", "define", "Engineer", "Software development"])
        out = capsys.readouterr().out
        assert "Engineer" in out

    def test_role_assign(self, capsys):
        main(["init", "TestFirm"])
        capsys.readouterr()
        main(["agent", "add", "Alice", "--authority", "0.7"])
        out = capsys.readouterr().out
        agent_id = _extract_agent_id(out)

        main(["role", "define", "Dev", "Developer", "--min-authority", "0.3"])
        main(["role", "assign", agent_id, "Dev"])
        out2 = capsys.readouterr().out
        assert "assigned" in out2.lower() or "Dev" in out2


class TestCLIMemory:
    """Test memory add/recall."""

    def test_memory_add(self, capsys):
        main(["init", "TestFirm"])
        capsys.readouterr()
        main(["agent", "add", "Alice", "--authority", "0.6"])
        out = capsys.readouterr().out
        agent_id = _extract_agent_id(out)

        main(["memory", "add", agent_id, "Use TDD for critical paths", "--tags", "process,testing"])
        out2 = capsys.readouterr().out
        assert "Memory" in out2 or "memory" in out2

    def test_memory_recall(self, capsys):
        main(["init", "TestFirm"])
        capsys.readouterr()
        main(["agent", "add", "Alice", "--authority", "0.6"])
        out = capsys.readouterr().out
        agent_id = _extract_agent_id(out)

        main(["memory", "add", agent_id, "TDD is essential", "--tags", "process"])
        main(["memory", "recall", "process"])
        out2 = capsys.readouterr().out
        assert "TDD" in out2 or "process" in out2 or "No memories" not in out2


class TestCLIAudit:
    """Test audit command."""

    def test_audit(self, capsys):
        main(["init", "TestFirm"])
        main(["agent", "add", "Alice", "--authority", "0.6"])
        main(["audit"])
        out = capsys.readouterr().out
        assert "Audit" in out or "audit" in out or "TestFirm" in out


class TestCLIMarket:
    """Test market post/bid."""

    def test_market_post(self, capsys):
        main(["init", "TestFirm"])
        capsys.readouterr()
        main(["agent", "add", "Alice", "--authority", "0.7"])
        out = capsys.readouterr().out
        agent_id = _extract_agent_id(out)

        main(["market", "post", agent_id, "Build feature X", "30.0"])
        out2 = capsys.readouterr().out
        assert "Task" in out2 or "task" in out2 or "posted" in out2


class TestCLINoFirm:
    """Test commands fail gracefully when no firm is initialized."""

    def test_status_no_firm(self):
        with pytest.raises(SystemExit):
            main(["status"])

    def test_agent_list_no_firm(self):
        with pytest.raises(SystemExit):
            main(["agent", "list"])

    def test_audit_no_firm(self):
        with pytest.raises(SystemExit):
            main(["audit"])


class TestBuildParser:
    """Test parser construction."""

    def test_parser_commands(self):
        parser = build_parser()
        assert parser.prog == "firm"

    def test_parser_init(self):
        parser = build_parser()
        args = parser.parse_args(["init", "MyFirm"])
        assert args.command == "init"
        assert args.name == "MyFirm"

    def test_parser_agent_add(self):
        parser = build_parser()
        args = parser.parse_args(["agent", "add", "Alice", "--authority", "0.8"])
        assert args.command == "agent"
        assert args.agent_cmd == "add"
        assert args.name == "Alice"
        assert args.authority == 0.8

    def test_parser_action(self):
        parser = build_parser()
        args = parser.parse_args(["action", "agent-1", "ok", "Shipped"])
        assert args.command == "action"
        assert args.agent == "agent-1"
        assert args.outcome == "ok"

    def test_parser_evolve_propose(self):
        parser = build_parser()
        args = parser.parse_args(["evolve", "propose", "agent-1", "learning_rate", "0.08"])
        assert args.command == "evolve"
        assert args.evolve_cmd == "propose"
        assert args.param == "learning_rate"
        assert args.value == "0.08"

    def test_parser_market_post(self):
        parser = build_parser()
        args = parser.parse_args(["market", "post", "agent-1", "Task title", "50.0"])
        assert args.command == "market"
        assert args.market_cmd == "post"
        assert args.bounty == 50.0


# ── Helper functions ────────────────────────────────────────────────────────


def _extract_agent_id(output: str) -> str:
    """Extract agent ID from CLI output like "Agent 'X' added (id=abc123, ...)"."""
    # Look for id=<something>
    for line in output.split("\n"):
        if "id=" in line:
            start = line.index("id=") + 3
            end = line.index(",", start) if "," in line[start:] else line.index(")", start)
            return line[start:end]
    raise ValueError(f"Could not extract agent ID from output: {output!r}")
