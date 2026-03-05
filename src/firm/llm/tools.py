"""
firm.llm.tools — Real tool system for LLM agents.

Provides actual tools that agents can use: git, terminal, file operations,
HTTP requests. Each tool has sandboxing (working directory, timeouts,
command allowlists).
"""

from __future__ import annotations

import json
import os
import subprocess
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    """Result from executing a tool."""
    success: bool
    output: str
    error: str = ""
    duration_ms: float = 0.0


@dataclass
class Tool:
    """A tool that LLM agents can use."""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    execute: Callable[..., ToolResult] = field(repr=False)
    dangerous: bool = False  # requires human approval if True

    def to_definition(self):
        from firm.llm.providers import ToolDefinition
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )


class ToolKit:
    """Collection of tools with execution, conversion, and sandboxing."""

    def __init__(self, working_dir: str | Path | None = None, timeout: int = 30):
        self._tools: dict[str, Tool] = {}
        self.working_dir = Path(working_dir) if working_dir else Path.cwd()
        self.timeout = timeout
        self._execution_log: list[dict] = []

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def to_definitions(self):
        """Convert all tools to provider-agnostic definitions."""
        return [t.to_definition() for t in self._tools.values()]

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a tool by name with arguments."""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown tool: {name}",
            )

        t0 = time.monotonic()
        try:
            result = tool.execute(**arguments)
            result.duration_ms = (time.monotonic() - t0) * 1000
        except Exception as e:
            result = ToolResult(
                success=False,
                output="",
                error=f"{type(e).__name__}: {e}",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        self._execution_log.append({
            "tool": name,
            "arguments": arguments,
            "success": result.success,
            "duration_ms": result.duration_ms,
            "timestamp": time.time(),
        })
        return result

    def get_execution_log(self) -> list[dict]:
        return list(self._execution_log)


# ─────────────────────────────────────────────────────────────────────────────
# Built-in tools: Git
# ─────────────────────────────────────────────────────────────────────────────

def _run_cmd(
    cmd: list[str],
    cwd: str | Path | None = None,
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> ToolResult:
    """Run a subprocess with timeout and capture output."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, **(env or {})},
        )
        return ToolResult(
            success=result.returncode == 0,
            output=result.stdout.strip(),
            error=result.stderr.strip(),
        )
    except subprocess.TimeoutExpired:
        return ToolResult(success=False, output="", error=f"Command timed out ({timeout}s)")
    except FileNotFoundError:
        return ToolResult(success=False, output="", error=f"Command not found: {cmd[0]}")


def _make_git_tools(working_dir: Path, timeout: int = 30) -> list[Tool]:
    """Create git tools bound to a working directory."""

    def git_status() -> ToolResult:
        return _run_cmd(["git", "status", "--short"], cwd=working_dir, timeout=timeout)

    def git_diff(staged: bool = False) -> ToolResult:
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--cached")
        return _run_cmd(cmd, cwd=working_dir, timeout=timeout)

    def git_log(count: int = 10) -> ToolResult:
        return _run_cmd(
            ["git", "log", f"-{min(count, 50)}", "--oneline", "--no-decorate"],
            cwd=working_dir,
            timeout=timeout,
        )

    def git_add(files: str = ".") -> ToolResult:
        return _run_cmd(["git", "add", files], cwd=working_dir, timeout=timeout)

    def git_commit(message: str) -> ToolResult:
        return _run_cmd(
            ["git", "commit", "-m", message],
            cwd=working_dir,
            timeout=timeout,
        )

    def git_branch() -> ToolResult:
        return _run_cmd(["git", "branch", "--list"], cwd=working_dir, timeout=timeout)

    return [
        Tool(
            name="git_status",
            description="Show working tree status (short format).",
            parameters={"type": "object", "properties": {}, "required": []},
            execute=lambda **_: git_status(),
        ),
        Tool(
            name="git_diff",
            description="Show changes in the working tree or staging area.",
            parameters={
                "type": "object",
                "properties": {
                    "staged": {"type": "boolean", "description": "Show staged changes only.", "default": False},
                },
                "required": [],
            },
            execute=lambda staged=False, **_: git_diff(staged=staged),
        ),
        Tool(
            name="git_log",
            description="Show recent commit history (oneline format).",
            parameters={
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "Number of commits (max 50).", "default": 10},
                },
                "required": [],
            },
            execute=lambda count=10, **_: git_log(count=count),
        ),
        Tool(
            name="git_add",
            description="Stage files for commit.",
            parameters={
                "type": "object",
                "properties": {
                    "files": {"type": "string", "description": "File pattern to add.", "default": "."},
                },
                "required": [],
            },
            execute=lambda files=".", **_: git_add(files=files),
            dangerous=True,
        ),
        Tool(
            name="git_commit",
            description="Create a git commit with the given message.",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message."},
                },
                "required": ["message"],
            },
            execute=lambda message, **_: git_commit(message=message),
            dangerous=True,
        ),
        Tool(
            name="git_branch",
            description="List all local branches.",
            parameters={"type": "object", "properties": {}, "required": []},
            execute=lambda **_: git_branch(),
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Built-in tools: Terminal
# ─────────────────────────────────────────────────────────────────────────────

# Commands that are always allowed
_SAFE_COMMANDS = {
    "ls", "cat", "head", "tail", "wc", "grep", "find", "echo", "date",
    "pwd", "whoami", "env", "which", "tree", "less", "sort", "uniq",
    "awk", "sed", "tr", "cut", "tee", "diff", "file", "stat",
    "python", "python3", "pip", "pip3", "node", "npm", "npx",
    "pytest", "ruff", "black", "mypy",
}


def _make_terminal_tools(working_dir: Path, timeout: int = 30, allow_all: bool = False) -> list[Tool]:
    """Create terminal tools bound to a working directory."""

    def terminal_run(command: str) -> ToolResult:
        # Parse command to check the first word
        parts = shlex.split(command)
        if not parts:
            return ToolResult(success=False, output="", error="Empty command.")
        base_cmd = Path(parts[0]).name
        if not allow_all and base_cmd not in _SAFE_COMMANDS:
            return ToolResult(
                success=False,
                output="",
                error=f"Command '{base_cmd}' not in safe list. Set allow_all=True to override.",
            )
        return _run_cmd(
            ["bash", "-c", command],
            cwd=working_dir,
            timeout=timeout,
        )

    return [
        Tool(
            name="terminal_run",
            description="Execute a shell command and return stdout/stderr. Only safe commands allowed by default.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute."},
                },
                "required": ["command"],
            },
            execute=lambda command, **_: terminal_run(command=command),
            dangerous=True,
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Built-in tools: File operations
# ─────────────────────────────────────────────────────────────────────────────

def _make_file_tools(working_dir: Path) -> list[Tool]:
    """Create file tools bound to a working directory."""

    def _resolve(path: str) -> Path:
        """Resolve path relative to working_dir, block traversal."""
        resolved = (working_dir / path).resolve()
        if not str(resolved).startswith(str(working_dir.resolve())):
            raise PermissionError(f"Path traversal blocked: {path}")
        return resolved

    def file_read(path: str, start_line: int = 0, end_line: int = 0) -> ToolResult:
        try:
            filepath = _resolve(path)
            if not filepath.exists():
                return ToolResult(success=False, output="", error=f"File not found: {path}")
            content = filepath.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            if start_line or end_line:
                s = max(0, start_line - 1)
                e = end_line or len(lines)
                lines = lines[s:e]
            return ToolResult(success=True, output="\n".join(lines))
        except PermissionError as e:
            return ToolResult(success=False, output="", error=str(e))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def file_write(path: str, content: str) -> ToolResult:
        try:
            filepath = _resolve(path)
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")
            return ToolResult(success=True, output=f"Wrote {len(content)} bytes to {path}")
        except PermissionError as e:
            return ToolResult(success=False, output="", error=str(e))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def file_list(path: str = ".", pattern: str = "*") -> ToolResult:
        try:
            dirpath = _resolve(path)
            if not dirpath.is_dir():
                return ToolResult(success=False, output="", error=f"Not a directory: {path}")
            entries = sorted(dirpath.glob(pattern))
            lines = []
            for entry in entries[:200]:  # limit output
                rel = entry.relative_to(working_dir)
                suffix = "/" if entry.is_dir() else ""
                lines.append(f"{rel}{suffix}")
            return ToolResult(success=True, output="\n".join(lines))
        except PermissionError as e:
            return ToolResult(success=False, output="", error=str(e))
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def file_search(query: str, path: str = ".", max_results: int = 20) -> ToolResult:
        """Search for text in files using grep."""
        return _run_cmd(
            ["grep", "-rn", "--include=*.py", "--include=*.ts", "--include=*.js",
             "--include=*.md", "--include=*.json", "--include=*.yaml", "--include=*.yml",
             "-l", query, str(_resolve(path))],
            cwd=working_dir,
            timeout=10,
        )

    return [
        Tool(
            name="file_read",
            description="Read a file's contents. Optionally specify line range.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path."},
                    "start_line": {"type": "integer", "description": "Start line (1-based).", "default": 0},
                    "end_line": {"type": "integer", "description": "End line (inclusive).", "default": 0},
                },
                "required": ["path"],
            },
            execute=lambda path, start_line=0, end_line=0, **_: file_read(path, start_line, end_line),
        ),
        Tool(
            name="file_write",
            description="Write content to a file. Creates parent directories if needed.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path."},
                    "content": {"type": "string", "description": "File content to write."},
                },
                "required": ["path", "content"],
            },
            execute=lambda path, content, **_: file_write(path, content),
            dangerous=True,
        ),
        Tool(
            name="file_list",
            description="List files and directories.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path.", "default": "."},
                    "pattern": {"type": "string", "description": "Glob pattern.", "default": "*"},
                },
                "required": [],
            },
            execute=lambda path=".", pattern="*", **_: file_list(path, pattern),
        ),
        Tool(
            name="file_search",
            description="Search for text in files (grep). Returns matching filenames.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to search for."},
                    "path": {"type": "string", "description": "Directory to search.", "default": "."},
                },
                "required": ["query"],
            },
            execute=lambda query, path=".", **_: file_search(query, path),
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Built-in tools: HTTP
# ─────────────────────────────────────────────────────────────────────────────

def _make_http_tools(timeout: int = 15) -> list[Tool]:
    """Create HTTP tools."""

    def http_get(url: str, headers: dict[str, str] | None = None) -> ToolResult:
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url, headers=headers or {})
            body = resp.text[:10000]  # limit response size
            return ToolResult(
                success=resp.is_success,
                output=f"HTTP {resp.status_code}\n{body}",
                error="" if resp.is_success else f"HTTP {resp.status_code}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def http_post(url: str, body: str = "", headers: dict[str, str] | None = None) -> ToolResult:
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, content=body, headers=headers or {})
            rbody = resp.text[:10000]
            return ToolResult(
                success=resp.is_success,
                output=f"HTTP {resp.status_code}\n{rbody}",
                error="" if resp.is_success else f"HTTP {resp.status_code}",
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    return [
        Tool(
            name="http_get",
            description="Make an HTTP GET request and return the response.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to request."},
                    "headers": {"type": "object", "description": "Optional headers."},
                },
                "required": ["url"],
            },
            execute=lambda url, headers=None, **_: http_get(url, headers),
        ),
        Tool(
            name="http_post",
            description="Make an HTTP POST request and return the response.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to request."},
                    "body": {"type": "string", "description": "Request body.", "default": ""},
                    "headers": {"type": "object", "description": "Optional headers."},
                },
                "required": ["url"],
            },
            execute=lambda url, body="", headers=None, **_: http_post(url, body, headers),
            dangerous=True,
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Built-in tools: Python execution
# ─────────────────────────────────────────────────────────────────────────────

def _make_python_tools(working_dir: Path, timeout: int = 30) -> list[Tool]:
    """Create Python execution tools."""

    def python_run(code: str) -> ToolResult:
        """Execute Python code and return output."""
        return _run_cmd(
            ["python3", "-c", code],
            cwd=working_dir,
            timeout=timeout,
        )

    def python_test(path: str = ".", verbose: bool = True) -> ToolResult:
        """Run pytest."""
        cmd = ["python3", "-m", "pytest", path]
        if verbose:
            cmd.append("-v")
        return _run_cmd(cmd, cwd=working_dir, timeout=120)

    return [
        Tool(
            name="python_run",
            description="Execute Python code and return stdout/stderr.",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute."},
                },
                "required": ["code"],
            },
            execute=lambda code, **_: python_run(code=code),
            dangerous=True,
        ),
        Tool(
            name="python_test",
            description="Run pytest on a path.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to test.", "default": "."},
                    "verbose": {"type": "boolean", "description": "Verbose output.", "default": True},
                },
                "required": [],
            },
            execute=lambda path=".", verbose=True, **_: python_test(path=path, verbose=verbose),
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Toolkit factory
# ─────────────────────────────────────────────────────────────────────────────

def create_builtin_toolkit(
    working_dir: str | Path | None = None,
    timeout: int = 30,
    allow_all_commands: bool = False,
    include: set[str] | None = None,
) -> ToolKit:
    """
    Create a ToolKit with all built-in tools.

    Args:
        working_dir: Base directory for file/git/terminal operations.
        timeout: Default command timeout in seconds.
        allow_all_commands: If True, terminal allows any command.
        include: If set, only include tools whose names match these prefixes.
    """
    wd = Path(working_dir) if working_dir else Path.cwd()
    toolkit = ToolKit(working_dir=wd, timeout=timeout)

    all_tools = (
        _make_git_tools(wd, timeout)
        + _make_terminal_tools(wd, timeout, allow_all_commands)
        + _make_file_tools(wd)
        + _make_http_tools(timeout)
        + _make_python_tools(wd, timeout)
    )

    for tool in all_tools:
        if include is None or any(tool.name.startswith(p) for p in include):
            toolkit.register(tool)

    return toolkit


# Re-export for convenience
BUILTIN_TOOLS = [
    "git_status", "git_diff", "git_log", "git_add", "git_commit", "git_branch",
    "terminal_run",
    "file_read", "file_write", "file_list", "file_search",
    "http_get", "http_post",
    "python_run", "python_test",
]
