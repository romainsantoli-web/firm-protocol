"""Repository scanner tools for the Security Firm.

10 LLM-callable tools that scan local Git repositories for security issues.
Each tool returns a string result suitable for LLM consumption.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Path-traversal guard
# ---------------------------------------------------------------------------

def _safe_path(base: str, relative: str) -> str | None:
    """Resolve *relative* under *base* and reject traversal."""
    try:
        resolved = Path(base).resolve() / relative
        resolved = resolved.resolve()
        if not str(resolved).startswith(str(Path(base).resolve())):
            return None
        return str(resolved)
    except (ValueError, OSError):
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MAX_OUTPUT = 50_000  # 50 KB cap


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 120) -> str:
    """Run a subprocess, return stdout (capped)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        out = result.stdout or result.stderr or ""
        return out[:_MAX_OUTPUT]
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT after {timeout}s]"
    except FileNotFoundError:
        return f"[TOOL NOT FOUND: {cmd[0]}]"


# ---------------------------------------------------------------------------
# Secret patterns (compiled once)
# ---------------------------------------------------------------------------

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}", re.IGNORECASE)),
    ("AWS Secret Key", re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*\S{20,}")),
    ("Generic API Key", re.compile(r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"]?\S{16,}['\"]?")),
    ("Generic Secret", re.compile(r"(?i)(secret|password|passwd|token)\s*[=:]\s*['\"]?\S{8,}['\"]?")),
    ("Private Key", re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    ("GitHub Token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}")),
    ("Slack Token", re.compile(r"xox[baprs]-[0-9]{10,}-[A-Za-z0-9]+")),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("Heroku API Key", re.compile(r"(?i)heroku.*[=:]\s*[0-9a-f]{8}-[0-9a-f]{4}-")),
    ("Base64 High Entropy", re.compile(r"(?i)(key|secret|token|password)\s*[=:]\s*['\"]?[A-Za-z0-9+/]{40,}={0,2}['\"]?")),
    ("Database URL", re.compile(r"(?i)(postgres|mysql|mongodb|redis)://\S+:\S+@\S+")),
    ("SendGrid Key", re.compile(r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}")),
    ("Stripe Key", re.compile(r"[sr]k_(live|test)_[A-Za-z0-9]{20,}")),
]

# Extensions worth scanning for secrets
_TEXT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".rb",
    ".php", ".cs", ".c", ".cpp", ".h", ".sh", ".bash", ".zsh",
    ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg", ".conf",
    ".env", ".env.example", ".env.local", ".env.prod",
    ".xml", ".html", ".htm", ".md", ".txt", ".sql",
    ".tf", ".hcl", ".dockerfile",
}

# Binary / large file extensions to skip
_SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar", ".7z",
    ".exe", ".dll", ".so", ".dylib", ".o", ".a",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".mp3", ".mp4", ".avi", ".mov", ".wav", ".flac",
    ".pyc", ".pyo", ".class", ".wasm",
    ".npy", ".npz", ".h5", ".hdf5", ".pkl", ".pickle",
    ".db", ".sqlite", ".sqlite3",
}

_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", "egg-info", ".eggs",
}


# ---------------------------------------------------------------------------
# Dependency file patterns
# ---------------------------------------------------------------------------

_DEP_FILES = {
    "requirements.txt", "requirements-dev.txt", "requirements-test.txt",
    "Pipfile", "Pipfile.lock", "pyproject.toml", "setup.cfg", "setup.py",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "go.mod", "go.sum", "Cargo.toml", "Cargo.lock",
    "Gemfile", "Gemfile.lock", "composer.json", "composer.lock",
}


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _repo_clone_or_open(repo_path: str) -> str:
    """Clone a Git repo (URL) or verify a local path exists."""
    if repo_path.startswith(("http://", "https://", "git@")):
        dest = Path("/tmp") / Path(repo_path.rstrip("/").split("/")[-1]).stem
        if dest.exists():
            return json.dumps({"path": str(dest), "status": "already_cloned"})
        result = _run(["git", "clone", "--depth=1", repo_path, str(dest)], timeout=120)
        if dest.exists():
            return json.dumps({"path": str(dest), "status": "cloned", "output": result[:500]})
        return json.dumps({"error": f"Clone failed: {result[:500]}"})
    path = Path(repo_path).resolve()
    if not path.exists():
        return json.dumps({"error": f"Path not found: {repo_path}"})
    return json.dumps({"path": str(path), "status": "local", "is_git": (path / ".git").is_dir()})


def _repo_tree(repo_path: str, max_depth: int = 4, extensions: str = "") -> str:
    """List directory tree with file counts per extension."""
    base = Path(repo_path).resolve()
    if not base.is_dir():
        return json.dumps({"error": f"Not a directory: {repo_path}"})

    ext_filter = set(extensions.split(",")) if extensions else None
    tree: list[str] = []
    ext_counts: dict[str, int] = {}
    total_files = 0

    for root_str, dirs, files in os.walk(base):
        root = Path(root_str)
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        depth = len(root.relative_to(base).parts)
        if depth > max_depth:
            dirs.clear()
            continue

        indent = "  " * depth
        tree.append(f"{indent}{root.name}/")

        for f in sorted(files):
            ext = Path(f).suffix.lower()
            if ext_filter and ext not in ext_filter:
                continue
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            total_files += 1
            if depth < max_depth:
                tree.append(f"{indent}  {f}")

    return json.dumps({
        "total_files": total_files,
        "extensions": dict(sorted(ext_counts.items(), key=lambda x: -x[1])),
        "tree": "\n".join(tree[:2000]),  # cap at 2000 lines
    })


def _repo_file_read(repo_path: str, file_path: str, max_lines: int = 500) -> str:
    """Read a file within the repo (path-traversal protected)."""
    safe = _safe_path(repo_path, file_path)
    if not safe:
        return json.dumps({"error": f"Path traversal blocked: {file_path}"})
    target = Path(safe)
    if not target.is_file():
        return json.dumps({"error": f"Not a file: {file_path}"})
    if target.stat().st_size > 1_000_000:
        return json.dumps({"error": f"File too large: {target.stat().st_size} bytes"})
    try:
        lines = target.read_text(errors="replace").splitlines()
        total = len(lines)
        content = "\n".join(f"{i + 1:4d} | {line}" for i, line in enumerate(lines[:max_lines]))
        return json.dumps({
            "file": file_path,
            "total_lines": total,
            "shown_lines": min(total, max_lines),
            "content": content,
        })
    except Exception as exc:
        return json.dumps({"error": str(exc)})


def _repo_grep_secrets(repo_path: str) -> str:
    """Scan all text files in repo for hardcoded secrets."""
    base = Path(repo_path).resolve()
    findings: list[dict] = []

    for root_str, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext in _SKIP_EXTENSIONS:
                continue
            # Also skip non-text extensions not in our list
            if ext and ext not in _TEXT_EXTENSIONS:
                continue
            fpath = Path(root_str) / fname
            if fpath.stat().st_size > 500_000:
                continue
            try:
                content = fpath.read_text(errors="replace")
            except Exception:
                continue
            rel = str(fpath.relative_to(base))
            for line_num, line in enumerate(content.splitlines(), 1):
                for pattern_name, pattern in _SECRET_PATTERNS:
                    if pattern.search(line):
                        # Skip obvious test/example patterns
                        lower_line = line.lower()
                        if any(skip in lower_line for skip in
                               ["example", "placeholder", "xxx", "your_", "changeme",
                                "test_", "fake_", "dummy", "sample"]):
                            continue
                        findings.append({
                            "pattern": pattern_name,
                            "file": rel,
                            "line": line_num,
                            "snippet": line.strip()[:200],
                        })
                        if len(findings) >= 200:
                            return json.dumps({
                                "findings": findings,
                                "truncated": True,
                                "message": "200+ secrets found — output truncated",
                            })
    return json.dumps({"findings": findings, "count": len(findings)})


def _repo_dependency_audit(repo_path: str) -> str:
    """Find and parse dependency files, flag known-risky patterns."""
    base = Path(repo_path).resolve()
    dep_files_found: list[dict] = []

    for root_str, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in files:
            if fname in _DEP_FILES:
                fpath = Path(root_str) / fname
                rel = str(fpath.relative_to(base))
                try:
                    content = fpath.read_text(errors="replace")
                    dep_files_found.append({
                        "file": rel,
                        "size": fpath.stat().st_size,
                        "content_preview": content[:3000],
                    })
                except Exception:
                    pass

    # Try pip-audit if available
    pip_audit_output = ""
    if shutil.which("pip-audit"):
        reqs = base / "requirements.txt"
        if reqs.exists():
            pip_audit_output = _run(
                ["pip-audit", "-r", str(reqs), "--format=json", "--progress-spinner=off"],
                cwd=str(base),
                timeout=60,
            )

    # Try npm audit if available
    npm_audit_output = ""
    if shutil.which("npm") and (base / "package.json").exists():
        npm_audit_output = _run(
            ["npm", "audit", "--json"],
            cwd=str(base),
            timeout=60,
        )

    return json.dumps({
        "dependency_files": dep_files_found,
        "count": len(dep_files_found),
        "pip_audit": pip_audit_output[:10000] if pip_audit_output else None,
        "npm_audit": npm_audit_output[:10000] if npm_audit_output else None,
    })


def _repo_config_scan(repo_path: str) -> str:
    """Scan Dockerfiles, CI configs, and env files for misconfigurations."""
    base = Path(repo_path).resolve()
    findings: list[dict] = []

    config_patterns = {
        "Dockerfile": [
            (r"(?i)FROM\s+\S+:latest", "Using :latest tag — pin specific version"),
            (r"(?i)RUN\s+.*curl\s+.*\|\s*sh", "Piping curl to shell — supply chain risk"),
            (r"(?i)--privileged", "Privileged container — security risk"),
            (r"(?i)USER\s+root", "Running as root — use non-root user"),
        ],
        ".github/workflows": [
            (r"(?i)pull_request_target", "pull_request_target — pwn request risk"),
            (r"(?i)\$\{\{\s*github\.event\.\S*\.body", "Untrusted input in expression — injection risk"),
            (r"(?i)permissions:\s*write-all", "Overly broad permissions"),
        ],
        ".env": [
            (r"(?i)(password|secret|key|token)\s*=\s*\S+", "Secret in .env file"),
        ],
    }

    for root_str, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in files:
            fpath = Path(root_str) / fname
            rel = str(fpath.relative_to(base))

            for pattern_key, patterns in config_patterns.items():
                if pattern_key in rel or fname == pattern_key:
                    try:
                        content = fpath.read_text(errors="replace")
                    except Exception:
                        continue
                    for regex, msg in patterns:
                        for match in re.finditer(regex, content):
                            line_num = content[:match.start()].count("\n") + 1
                            findings.append({
                                "file": rel,
                                "line": line_num,
                                "issue": msg,
                                "match": match.group()[:200],
                            })

    return json.dumps({"findings": findings, "count": len(findings)})


def _repo_semgrep_run(repo_path: str, rules: str = "auto") -> str:
    """Run semgrep static analysis if installed."""
    if not shutil.which("semgrep"):
        return json.dumps({"error": "semgrep not installed", "install": "pip install semgrep"})
    output = _run(
        ["semgrep", "scan", "--config", rules,
         "--json", "--quiet", "--max-target-bytes=500000", repo_path],
        timeout=300,
    )
    return output[:_MAX_OUTPUT]


def _repo_git_history_secrets(repo_path: str) -> str:
    """Scan git log for secrets that were committed then removed."""
    base = Path(repo_path).resolve()
    if not (base / ".git").is_dir():
        return json.dumps({"error": "Not a git repository"})

    # Get diff of all commits (limit to last 500 commits)
    diff_output = _run(
        ["git", "log", "-p", "--all", "-n", "500", "--diff-filter=D",
         "--no-color", "--", "*.env", "*.key", "*.pem", "*.p12"],
        cwd=str(base),
        timeout=60,
    )

    # Also search for secret patterns in git log
    findings: list[dict] = []
    for pattern_name, pattern in _SECRET_PATTERNS[:5]:  # Top 5 patterns only
        grep_out = _run(
            ["git", "log", "--all", "-p", "-n", "200",
             f"--grep-reflog={pattern_name}", "--no-color"],
            cwd=str(base),
            timeout=30,
        )
        if grep_out and "[TIMEOUT" not in grep_out and "[TOOL" not in grep_out:
            for line in grep_out.splitlines()[:50]:
                if pattern.search(line):
                    findings.append({
                        "pattern": pattern_name,
                        "line": line.strip()[:200],
                    })

    return json.dumps({
        "deleted_sensitive_files": diff_output[:5000] if diff_output else "none",
        "secrets_in_history": findings,
        "count": len(findings),
    })


def _repo_file_stats(repo_path: str) -> str:
    """Compute file statistics: counts, sizes, languages detected."""
    base = Path(repo_path).resolve()
    ext_counts: dict[str, int] = {}
    ext_sizes: dict[str, int] = {}
    total_files = 0
    total_size = 0
    largest_files: list[tuple[str, int]] = []

    for root_str, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in files:
            fpath = Path(root_str) / fname
            try:
                size = fpath.stat().st_size
            except OSError:
                continue
            ext = Path(fname).suffix.lower() or "(no ext)"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
            ext_sizes[ext] = ext_sizes.get(ext, 0) + size
            total_files += 1
            total_size += size
            largest_files.append((str(fpath.relative_to(base)), size))

    largest_files.sort(key=lambda x: -x[1])

    return json.dumps({
        "total_files": total_files,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / 1_048_576, 2),
        "extensions": dict(sorted(ext_counts.items(), key=lambda x: -x[1])[:30]),
        "largest_files": [{"file": f, "size": s} for f, s in largest_files[:20]],
    })


def _repo_summarize_findings(findings_json: str) -> str:
    """Parse a JSON list of findings and produce a summary."""
    try:
        data = json.loads(findings_json)
        if isinstance(data, dict):
            findings = data.get("findings", [])
        elif isinstance(data, list):
            findings = data
        else:
            return json.dumps({"error": "Invalid input — expected list or dict with 'findings'"})

        summary: dict[str, int] = {}
        for f in findings:
            key = f.get("pattern", f.get("issue", "unknown"))
            summary[key] = summary.get(key, 0) + 1

        return json.dumps({
            "total": len(findings),
            "by_type": dict(sorted(summary.items(), key=lambda x: -x[1])),
        })
    except (json.JSONDecodeError, TypeError) as exc:
        return json.dumps({"error": f"JSON parse error: {exc}"})


# ---------------------------------------------------------------------------
# Tool factory
# ---------------------------------------------------------------------------

def make_repo_tools() -> list[dict[str, Any]]:
    """Return 10 LLM-callable repo-scanning tools as dicts.

    Each dict has: name, description, parameters, callable.
    These are compatible with firm.llm.tools.ToolKit registration.
    """
    return [
        {
            "name": "repo_clone_or_open",
            "description": "Clone a Git repo (URL) or verify a local repo path exists.",
            "parameters": {
                "repo_path": "string — Git URL (https/ssh) or local filesystem path",
            },
            "callable": _repo_clone_or_open,
        },
        {
            "name": "repo_tree",
            "description": "List the directory tree of a repository with file counts.",
            "parameters": {
                "repo_path": "string — local path to the repo root",
                "max_depth": "int — max directory depth (default 4)",
                "extensions": "string — comma-separated extensions to filter (e.g. '.py,.js')",
            },
            "callable": _repo_tree,
        },
        {
            "name": "repo_file_read",
            "description": "Read a file within the repo with line numbers (path-traversal protected).",
            "parameters": {
                "repo_path": "string — repo root path",
                "file_path": "string — relative file path within repo",
                "max_lines": "int — max lines to return (default 500)",
            },
            "callable": _repo_file_read,
        },
        {
            "name": "repo_grep_secrets",
            "description": "Scan all text files for hardcoded secrets (API keys, tokens, passwords).",
            "parameters": {
                "repo_path": "string — repo root path",
            },
            "callable": _repo_grep_secrets,
        },
        {
            "name": "repo_dependency_audit",
            "description": "Find dependency files and audit for known vulnerabilities.",
            "parameters": {
                "repo_path": "string — repo root path",
            },
            "callable": _repo_dependency_audit,
        },
        {
            "name": "repo_config_scan",
            "description": "Scan Dockerfiles, CI workflows, and .env files for misconfigurations.",
            "parameters": {
                "repo_path": "string — repo root path",
            },
            "callable": _repo_config_scan,
        },
        {
            "name": "repo_semgrep_run",
            "description": "Run semgrep static analysis with security rules.",
            "parameters": {
                "repo_path": "string — repo root path",
                "rules": "string — semgrep config (default 'auto')",
            },
            "callable": _repo_semgrep_run,
        },
        {
            "name": "repo_git_history_secrets",
            "description": "Scan git history for secrets that were committed then deleted.",
            "parameters": {
                "repo_path": "string — repo root path",
            },
            "callable": _repo_git_history_secrets,
        },
        {
            "name": "repo_file_stats",
            "description": "Compute file statistics: counts, sizes, languages, largest files.",
            "parameters": {
                "repo_path": "string — repo root path",
            },
            "callable": _repo_file_stats,
        },
        {
            "name": "repo_summarize_findings",
            "description": "Parse a JSON list of findings and produce a grouped summary.",
            "parameters": {
                "findings_json": "string — JSON string of findings list",
            },
            "callable": _repo_summarize_findings,
        },
    ]
