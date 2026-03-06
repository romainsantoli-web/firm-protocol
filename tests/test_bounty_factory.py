"""Tests for firm.bounty.factory — BountyFirm factory.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

import pytest

from firm.bounty.factory import BOUNTY_AGENTS, _resolve_model, create_bounty_firm
from firm.bounty.scope import Asset, AssetType, TargetScope


@pytest.fixture
def scope():
    return TargetScope(
        programme_name="Test",
        programme_handle="test",
        in_scope=[Asset("example.com", AssetType.DOMAIN)],
    )


class TestFactory:
    def test_creates_all_components(self, scope):
        ctx = create_bounty_firm(scope)
        assert "agents" in ctx
        assert "enforcer" in ctx
        assert "db" in ctx
        assert "dedup" in ctx
        assert "triage" in ctx
        assert "reward" in ctx
        assert "tools" in ctx
        assert "role_defs" in ctx
        assert "limiter" in ctx

    def test_agents_count(self, scope):
        ctx = create_bounty_firm(scope)
        assert len(ctx["agents"]) == 8

    def test_tools_count(self, scope):
        ctx = create_bounty_firm(scope)
        assert len(ctx["tools"]) == 12

    def test_role_defs_for_all_agents(self, scope):
        ctx = create_bounty_firm(scope)
        for agent in ctx["agents"]:
            assert agent.name in ctx["role_defs"]


class TestAgentSpecs:
    def test_bounty_agents_list(self):
        assert len(BOUNTY_AGENTS) == 8
        names = {a.name for a in BOUNTY_AGENTS}
        assert "hunt-director" in names
        assert "recon-agent" in names
        assert "report-writer" in names

    def test_authority_range(self):
        for agent in BOUNTY_AGENTS:
            assert 0.0 <= agent.initial_authority <= 1.0


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------

class TestResolveModel:
    def test_default_model_returned_without_env(self, monkeypatch):
        monkeypatch.delenv("FIRM_HUNT_DIRECTOR_MODEL", raising=False)
        monkeypatch.delenv("FIRM_DEFAULT_MODEL", raising=False)
        assert _resolve_model("hunt-director", "claude-default") == "claude-default"

    def test_specific_env_var_overrides_default(self, monkeypatch):
        monkeypatch.setenv("FIRM_HUNT_DIRECTOR_MODEL", "my-custom-model")
        monkeypatch.delenv("FIRM_DEFAULT_MODEL", raising=False)
        assert _resolve_model("hunt-director", "claude-default") == "my-custom-model"

    def test_global_default_env_var(self, monkeypatch):
        monkeypatch.delenv("FIRM_HUNT_DIRECTOR_MODEL", raising=False)
        monkeypatch.setenv("FIRM_DEFAULT_MODEL", "gpt-4-turbo")
        assert _resolve_model("hunt-director", "claude-default") == "gpt-4-turbo"

    def test_specific_env_var_takes_priority_over_global(self, monkeypatch):
        monkeypatch.setenv("FIRM_RECON_AGENT_MODEL", "specific-model")
        monkeypatch.setenv("FIRM_DEFAULT_MODEL", "global-model")
        assert _resolve_model("recon-agent", "fallback") == "specific-model"

    def test_hyphen_to_underscore_conversion(self, monkeypatch):
        monkeypatch.setenv("FIRM_REPORT_WRITER_MODEL", "report-model")
        monkeypatch.delenv("FIRM_DEFAULT_MODEL", raising=False)
        assert _resolve_model("report-writer", "fallback") == "report-model"
