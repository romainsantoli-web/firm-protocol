"""Tests for firm.bounty.tools.scanner — security toolkit.

Tests tool construction and scope enforcement. Does NOT invoke real
CLI tools (all subprocess calls are mocked).

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from unittest.mock import patch

import pytest

from firm.bounty.scope import Asset, AssetType, ScopeEnforcer, TargetScope
from firm.bounty.tools.scanner import (
    RateLimiter,
    _resolve_ffuf_wordlist,
    _resolve_httpx_bin,
    make_bounty_tools,
    make_recon_tools,
    make_report_tools,
    make_scanning_tools,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def scope():
    return TargetScope(
        in_scope=[Asset("target.com", AssetType.DOMAIN)],
        out_of_scope=[],
    )


@pytest.fixture
def enforcer(scope):
    return ScopeEnforcer(scope)


@pytest.fixture
def limiter():
    return RateLimiter(rate=100.0, burst=100)


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    def test_allows_burst(self):
        rl = RateLimiter(rate=1.0, burst=5)
        for _ in range(5):
            assert rl.allow("key")

    def test_blocks_after_burst(self):
        rl = RateLimiter(rate=0.0, burst=2)
        assert rl.allow("key")
        assert rl.allow("key")
        assert not rl.allow("key")

    def test_separate_keys(self):
        rl = RateLimiter(rate=0.0, burst=1)
        assert rl.allow("a")
        assert rl.allow("b")
        assert not rl.allow("a")


# ---------------------------------------------------------------------------
# Tool construction
# ---------------------------------------------------------------------------

class TestToolConstruction:
    def test_make_bounty_tools_count(self, enforcer, limiter):
        tools = make_bounty_tools(enforcer, limiter)
        assert len(tools) == 12  # 4 recon + 7 scan + 1 report

    def test_recon_tools_count(self, enforcer, limiter):
        assert len(make_recon_tools(enforcer, limiter)) == 4

    def test_scanning_tools_count(self, enforcer, limiter):
        assert len(make_scanning_tools(enforcer, limiter)) == 7

    def test_report_tools_count(self):
        assert len(make_report_tools()) == 1

    def test_tools_have_required_keys(self, enforcer, limiter):
        for tool in make_bounty_tools(enforcer, limiter):
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool
            assert "callable" in tool
            assert callable(tool["callable"])


# ---------------------------------------------------------------------------
# Scope enforcement in tools
# ---------------------------------------------------------------------------

class TestScopeEnforcement:
    @patch("firm.bounty.tools.scanner._run", return_value="mock output")
    def test_recon_blocks_out_of_scope(self, mock_run, enforcer, limiter):
        tools = {t["name"]: t["callable"] for t in make_recon_tools(enforcer, limiter)}
        result = tools["recon_subdomains"]("evil.com")
        assert "BLOCKED" in result
        mock_run.assert_not_called()

    @patch("firm.bounty.tools.scanner._run", return_value="sub.target.com")
    def test_recon_allows_in_scope(self, mock_run, enforcer, limiter):
        tools = {t["name"]: t["callable"] for t in make_recon_tools(enforcer, limiter)}
        result = tools["recon_subdomains"]("target.com")
        assert "BLOCKED" not in result
        mock_run.assert_called_once()

    @patch("firm.bounty.tools.scanner._run", return_value="nuclei output")
    def test_scan_blocks_out_of_scope(self, mock_run, enforcer, limiter):
        tools = {t["name"]: t["callable"] for t in make_scanning_tools(enforcer, limiter)}
        result = tools["scan_nuclei"]("evil.com")
        assert "BLOCKED" in result
        mock_run.assert_not_called()

    @patch("firm.bounty.tools.scanner._run", return_value="nuclei: 0 vulns")
    def test_scan_allows_in_scope(self, mock_run, enforcer, limiter):
        tools = {t["name"]: t["callable"] for t in make_scanning_tools(enforcer, limiter)}
        result = tools["scan_nuclei"]("target.com")
        assert "BLOCKED" not in result


# ---------------------------------------------------------------------------
# Rate limiter in tools
# ---------------------------------------------------------------------------

class TestRateLimitInTools:
    @patch("firm.bounty.tools.scanner._run", return_value="output")
    def test_rate_limited_after_burst(self, mock_run, enforcer):
        limiter = RateLimiter(rate=0.0, burst=1)
        tools = {t["name"]: t["callable"] for t in make_recon_tools(enforcer, limiter)}
        tools["recon_subdomains"]("target.com")  # first call OK
        result = tools["recon_subdomains"]("target.com")  # second blocked
        assert "RATE LIMITED" in result


# ---------------------------------------------------------------------------
# Report tool
# ---------------------------------------------------------------------------

class TestReportTool:
    def test_report_generate(self):
        tools = {t["name"]: t["callable"] for t in make_report_tools()}
        result = tools["report_generate"](
            title="XSS in search",
            description="Reflected XSS via q parameter.",
            severity="medium",
            cwe_id=79,
            asset="target.com",
        )
        assert "# XSS in search" in result
        assert "CWE-79" in result


# ---------------------------------------------------------------------------
# Binary / wordlist resolution
# ---------------------------------------------------------------------------

class TestResolveHttpxBin:
    def test_env_var_takes_priority(self, monkeypatch):
        monkeypatch.setenv("HTTPX_BIN", "/custom/httpx")
        assert _resolve_httpx_bin() == "/custom/httpx"

    def test_env_var_empty_falls_through(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HTTPX_BIN", "")
        # Ensure no tool is found on PATH and Homebrew path does not exist
        with patch("shutil.which", return_value=None), \
             patch("firm.bounty.tools.scanner.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            result = _resolve_httpx_bin()
        assert result == "httpx-toolkit"

    def test_shutil_which_used_when_no_env(self, monkeypatch):
        monkeypatch.delenv("HTTPX_BIN", raising=False)
        with patch("shutil.which", side_effect=lambda name: "/usr/bin/httpx-toolkit" if name == "httpx-toolkit" else None):
            result = _resolve_httpx_bin()
        assert result == "/usr/bin/httpx-toolkit"


class TestResolveFfufWordlist:
    def test_explicit_wordlist_returned_if_exists(self, tmp_path):
        wl = tmp_path / "wordlist.txt"
        wl.write_text("admin\nlogin\n")
        assert _resolve_ffuf_wordlist(str(wl)) == str(wl)

    def test_explicit_wordlist_returns_none_if_missing(self):
        assert _resolve_ffuf_wordlist("/does/not/exist.txt") is None

    def test_env_var_used_when_no_explicit(self, monkeypatch, tmp_path):
        wl = tmp_path / "custom.txt"
        wl.write_text("secret\n")
        monkeypatch.setenv("FFUF_WORDLIST", str(wl))
        assert _resolve_ffuf_wordlist() == str(wl)

    def test_env_var_missing_file_returns_none(self, monkeypatch):
        monkeypatch.setenv("FFUF_WORDLIST", "/nonexistent/wordlist.txt")
        assert _resolve_ffuf_wordlist() is None

    def test_returns_none_when_nothing_available(self, monkeypatch):
        monkeypatch.delenv("FFUF_WORDLIST", raising=False)
        with patch("firm.bounty.tools.scanner.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            mock_path.home.return_value.__truediv__ = lambda *_: mock_path.return_value
            result = _resolve_ffuf_wordlist()
        assert result is None

    @patch("firm.bounty.tools.scanner._run", return_value="")
    def test_scan_ffuf_wordlist_not_found_message(self, mock_run, enforcer, limiter, monkeypatch):
        monkeypatch.delenv("FFUF_WORDLIST", raising=False)
        with patch("firm.bounty.tools.scanner._resolve_ffuf_wordlist", return_value=None):
            tools = {t["name"]: t["callable"] for t in make_scanning_tools(enforcer, limiter)}
            result = tools["scan_ffuf"]("target.com")
        assert "WORDLIST NOT FOUND" in result
        mock_run.assert_not_called()

    @patch("firm.bounty.tools.scanner._run", return_value="ffuf output")
    def test_scan_ffuf_uses_env_wordlist(self, mock_run, enforcer, limiter, monkeypatch, tmp_path):
        wl = tmp_path / "wl.txt"
        wl.write_text("index\n")
        monkeypatch.setenv("FFUF_WORDLIST", str(wl))
        tools = {t["name"]: t["callable"] for t in make_scanning_tools(enforcer, limiter)}
        result = tools["scan_ffuf"]("target.com")
        assert "BLOCKED" not in result
        assert "WORDLIST NOT FOUND" not in result
        mock_run.assert_called_once()
