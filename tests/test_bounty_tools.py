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
