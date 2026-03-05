"""LLM-callable security tools — recon, scan, report.

Every tool is scope-enforced and rate-limited so agents cannot go off-target.
CLI tools are invoked via subprocess; the Go ``httpx`` binary is called via
its full path (``/opt/homebrew/bin/httpx``) to avoid collision with the
Python ``httpx`` pip package.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from firm.bounty.scope import ScopeEnforcer


# ---------------------------------------------------------------------------
# Rate limiter (token-bucket per target)
# ---------------------------------------------------------------------------

@dataclass
class _Bucket:
    tokens: float
    last: float


class RateLimiter:
    """Per-host token-bucket rate limiter."""

    def __init__(self, rate: float = 10.0, burst: int = 20):
        self.rate = rate     # tokens per second
        self.burst = burst
        self._buckets: dict[str, _Bucket] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        b = self._buckets.get(key)
        if b is None:
            self._buckets[key] = _Bucket(tokens=self.burst - 1, last=now)
            return True
        elapsed = now - b.last
        b.tokens = min(self.burst, b.tokens + elapsed * self.rate)
        b.last = now
        if b.tokens >= 1:
            b.tokens -= 1
            return True
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _which(name: str) -> str | None:
    return shutil.which(name)


def _run(cmd: list[str], timeout: int = 120) -> str:
    """Run a subprocess and return stdout (capped to 50 KB)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = result.stdout or result.stderr or ""
        return out[:50_000]
    except subprocess.TimeoutExpired:
        return f"[TIMEOUT after {timeout}s]"
    except FileNotFoundError:
        return f"[TOOL NOT FOUND: {cmd[0]}]"


# Path to Go httpx binary (avoids Python httpx-cli collision)
_HTTPX_BIN = "/opt/homebrew/bin/httpx"


# ---------------------------------------------------------------------------
# Recon tools (4)
# ---------------------------------------------------------------------------

def make_recon_tools(
    enforcer: ScopeEnforcer,
    limiter: RateLimiter,
) -> list[dict[str, Any]]:
    """Return 4 LLM-callable recon tools."""

    def recon_subdomains(target: str) -> str:
        """Enumerate subdomains for a target domain using subfinder."""
        if not enforcer.allow_host(target):
            return f"BLOCKED: {target} is not in scope."
        if not limiter.allow(target):
            return "RATE LIMITED — retry later."
        return _run(["subfinder", "-d", target, "-silent", "-timeout", "30"])

    def recon_ports(target: str, ports: str = "top-1000") -> str:
        """Scan open ports on target using nmap (SYN scan)."""
        if not enforcer.allow_host(target):
            return f"BLOCKED: {target} is not in scope."
        if not limiter.allow(target):
            return "RATE LIMITED — retry later."
        port_flag = "--top-ports" if ports == "top-1000" else "-p"
        port_val = "1000" if ports == "top-1000" else ports
        return _run(
            ["nmap", "-sS", "-Pn", port_flag, port_val, "-T3",
             "--max-retries", "2", target],
            timeout=180,
        )

    def recon_tech(target: str) -> str:
        """Detect technologies on target using httpx (Go binary)."""
        if not enforcer.allow_host(target):
            return f"BLOCKED: {target} is not in scope."
        if not limiter.allow(target):
            return "RATE LIMITED — retry later."
        httpx_bin = _HTTPX_BIN if Path(_HTTPX_BIN).exists() else "httpx-toolkit"
        return _run(
            [httpx_bin, "-u", f"https://{target}",
             "-tech-detect", "-status-code", "-title", "-silent"],
        )

    def recon_urls(target: str) -> str:
        """Crawl URLs on target using katana."""
        if not enforcer.allow_host(target):
            return f"BLOCKED: {target} is not in scope."
        if not limiter.allow(target):
            return "RATE LIMITED — retry later."
        return _run(
            ["katana", "-u", f"https://{target}", "-d", "3",
             "-jc", "-silent", "-timeout", "30"],
            timeout=120,
        )

    return [
        {
            "name": "recon_subdomains",
            "description": "Enumerate subdomains for a target domain.",
            "parameters": {"target": "string — the base domain (e.g. example.com)"},
            "callable": recon_subdomains,
        },
        {
            "name": "recon_ports",
            "description": "Scan open TCP ports on a target host.",
            "parameters": {
                "target": "string — hostname or IP",
                "ports": "string — port spec ('top-1000' or '80,443,8080')",
            },
            "callable": recon_ports,
        },
        {
            "name": "recon_tech",
            "description": "Detect web technologies (server, framework, WAF).",
            "parameters": {"target": "string — hostname"},
            "callable": recon_tech,
        },
        {
            "name": "recon_urls",
            "description": "Crawl and list discovered URLs on a target.",
            "parameters": {"target": "string — hostname"},
            "callable": recon_urls,
        },
    ]


# ---------------------------------------------------------------------------
# Scanning tools (7)
# ---------------------------------------------------------------------------

def make_scanning_tools(
    enforcer: ScopeEnforcer,
    limiter: RateLimiter,
) -> list[dict[str, Any]]:
    """Return 7 LLM-callable scanning tools."""

    def scan_nuclei(target: str, templates: str = "") -> str:
        """Run nuclei vulnerability scanner."""
        if not enforcer.allow_host(target):
            return f"BLOCKED: {target} is not in scope."
        if not limiter.allow(target):
            return "RATE LIMITED — retry later."
        cmd = ["nuclei", "-u", f"https://{target}", "-silent",
               "-severity", "low,medium,high,critical",
               "-timeout", "15", "-retries", "1"]
        if templates:
            cmd += ["-t", templates]
        return _run(cmd, timeout=300)

    def scan_ffuf(target: str, wordlist: str = "", path: str = "/FUZZ") -> str:
        """Fuzz directories / endpoints with ffuf."""
        if not enforcer.allow_host(target):
            return f"BLOCKED: {target} is not in scope."
        if not limiter.allow(target):
            return "RATE LIMITED — retry later."
        wl = wordlist or "/usr/share/seclists/Discovery/Web-Content/common.txt"
        if not Path(wl).exists():
            wl_alt = Path.home() / "SecLists/Discovery/Web-Content/common.txt"
            if wl_alt.exists():
                wl = str(wl_alt)
            else:
                return "[WORDLIST NOT FOUND — install SecLists]"
        url = f"https://{target}{path}"
        return _run(
            ["ffuf", "-u", url, "-w", wl,
             "-mc", "200,201,301,302,403",
             "-t", "20", "-timeout", "10", "-s"],
            timeout=180,
        )

    def scan_sqli(target: str, url: str = "") -> str:
        """Test SQL injection with sqlmap on a specific URL."""
        test_url = url or f"https://{target}/"
        if not enforcer.allow_url(test_url):
            return f"BLOCKED: {test_url} is not in scope."
        if not limiter.allow(target):
            return "RATE LIMITED — retry later."
        if not _which("sqlmap"):
            return "[sqlmap NOT INSTALLED]"
        return _run(
            ["sqlmap", "-u", test_url, "--batch",
             "--level=2", "--risk=1", "--threads=4",
             "--timeout=15", "--retries=1",
             "--output-dir", tempfile.mkdtemp(prefix="sqlmap_")],
            timeout=300,
        )

    def scan_xss(target: str, url: str = "") -> str:
        """Test reflected XSS with dalfox."""
        test_url = url or f"https://{target}/"
        if not enforcer.allow_url(test_url):
            return f"BLOCKED: {test_url} is not in scope."
        if not limiter.allow(target):
            return "RATE LIMITED — retry later."
        if not _which("dalfox"):
            return "[dalfox NOT INSTALLED]"
        return _run(
            ["dalfox", "url", test_url,
             "--silence", "--timeout", "15",
             "--worker", "5"],
            timeout=180,
        )

    def scan_nikto(target: str) -> str:
        """Run nikto web-server scanner."""
        if not enforcer.allow_host(target):
            return f"BLOCKED: {target} is not in scope."
        if not limiter.allow(target):
            return "RATE LIMITED — retry later."
        return _run(
            ["nikto", "-h", f"https://{target}",
             "-maxtime", "120s", "-Tuning", "x6"],
            timeout=180,
        )

    def scan_semgrep(path: str, rules: str = "auto") -> str:
        """Run semgrep static analysis on local source code."""
        # source_code scans don't go through host scope
        if not Path(path).exists():
            return f"[PATH NOT FOUND: {path}]"
        return _run(
            ["semgrep", "scan", "--config", rules,
             "--json", "--quiet", path],
            timeout=300,
        )

    def scan_ssl(target: str) -> str:
        """Check TLS/SSL configuration using Python ssl module."""
        if not enforcer.allow_host(target):
            return f"BLOCKED: {target} is not in scope."
        if not limiter.allow(target):
            return "RATE LIMITED — retry later."
        import ssl
        import socket
        findings: list[str] = []
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((target, 443), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=target) as ssock:
                    cert = ssock.getpeercert()
                    proto = ssock.version()
                    cipher = ssock.cipher()
                    findings.append(f"Protocol: {proto}")
                    findings.append(f"Cipher: {cipher}")
                    not_after = cert.get("notAfter", "")
                    findings.append(f"Cert expires: {not_after}")
                    san = cert.get("subjectAltName", ())
                    findings.append(f"SANs: {[s[1] for s in san]}")
        except Exception as exc:
            findings.append(f"SSL error: {exc}")
        return "\n".join(findings)

    return [
        {
            "name": "scan_nuclei",
            "description": "Run nuclei templates against target.",
            "parameters": {
                "target": "string — hostname",
                "templates": "string — optional template path or tag",
            },
            "callable": scan_nuclei,
        },
        {
            "name": "scan_ffuf",
            "description": "Fuzz directories and endpoints.",
            "parameters": {
                "target": "string — hostname",
                "wordlist": "string — path to wordlist (optional)",
                "path": "string — URL path with FUZZ keyword",
            },
            "callable": scan_ffuf,
        },
        {
            "name": "scan_sqli",
            "description": "Test SQL injection on a URL.",
            "parameters": {
                "target": "string — hostname",
                "url": "string — full URL with parameters",
            },
            "callable": scan_sqli,
        },
        {
            "name": "scan_xss",
            "description": "Test reflected XSS on a URL.",
            "parameters": {
                "target": "string — hostname",
                "url": "string — full URL to test",
            },
            "callable": scan_xss,
        },
        {
            "name": "scan_nikto",
            "description": "Run nikto web-server vulnerability scan.",
            "parameters": {"target": "string — hostname"},
            "callable": scan_nikto,
        },
        {
            "name": "scan_semgrep",
            "description": "Run static analysis on local source code.",
            "parameters": {
                "path": "string — local directory to analyse",
                "rules": "string — semgrep rule config (default 'auto')",
            },
            "callable": scan_semgrep,
        },
        {
            "name": "scan_ssl",
            "description": "Check TLS/SSL certificate and protocol.",
            "parameters": {"target": "string — hostname"},
            "callable": scan_ssl,
        },
    ]


# ---------------------------------------------------------------------------
# Report tools (1)
# ---------------------------------------------------------------------------

def make_report_tools() -> list[dict[str, Any]]:
    """Return 1 LLM-callable report tool."""

    def report_generate(
        title: str,
        description: str,
        severity: str = "medium",
        cwe_id: int = 0,
        asset: str = "",
        endpoint: str = "",
        steps: str = "",
        impact: str = "",
        evidence: str = "",
    ) -> str:
        """Generate a HackerOne-formatted Markdown vulnerability report."""
        from firm.bounty.vulnerability import (
            Vulnerability,
            VulnSeverity,
        )

        vuln = Vulnerability(
            title=title,
            description=description,
            severity=VulnSeverity(severity.lower()),
            cwe_id=cwe_id,
            asset=asset,
            endpoint=endpoint,
            reproduction_steps=steps,
            impact=impact,
            evidence=evidence,
        )
        return vuln.to_markdown_report()

    return [
        {
            "name": "report_generate",
            "description": "Generate a Markdown vulnerability report.",
            "parameters": {
                "title": "string",
                "description": "string",
                "severity": "string — critical/high/medium/low/info",
                "cwe_id": "int — CWE number",
                "asset": "string — target domain",
                "endpoint": "string — affected path",
                "steps": "string — reproduction steps",
                "impact": "string — impact description",
                "evidence": "string — raw evidence",
            },
            "callable": report_generate,
        },
    ]


# ---------------------------------------------------------------------------
# Combined factory
# ---------------------------------------------------------------------------

def make_bounty_tools(
    enforcer: ScopeEnforcer,
    limiter: RateLimiter | None = None,
) -> list[dict[str, Any]]:
    """Return all 12 bounty-hunting tools."""
    if limiter is None:
        limiter = RateLimiter()
    return (
        make_recon_tools(enforcer, limiter)
        + make_scanning_tools(enforcer, limiter)
        + make_report_tools()
    )
