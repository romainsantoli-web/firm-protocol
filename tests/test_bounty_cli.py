"""Tests for the `firm bounty` CLI subcommands.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from firm.cli import main, build_parser


# ── Parser tests ─────────────────────────────────────────────────────────────


class TestBountyParser:
    """Parser correctly wires bounty subcommands."""

    def test_bounty_agents(self):
        parser = build_parser()
        args = parser.parse_args(["bounty", "agents"])
        assert args.command == "bounty"
        assert args.bounty_cmd == "agents"

    def test_bounty_init(self):
        parser = build_parser()
        args = parser.parse_args(["bounty", "init", "scope.yaml"])
        assert args.command == "bounty"
        assert args.bounty_cmd == "init"
        assert args.scope_file == "scope.yaml"
        assert args.rate_limit == 10.0
        assert args.rate_burst == 20

    def test_bounty_init_custom_rate(self):
        parser = build_parser()
        args = parser.parse_args(["bounty", "init", "s.yaml", "--rate-limit", "5.0", "--rate-burst", "10"])
        assert args.rate_limit == 5.0
        assert args.rate_burst == 10

    def test_bounty_scope(self):
        parser = build_parser()
        args = parser.parse_args(["bounty", "scope", "scope.yaml"])
        assert args.bounty_cmd == "scope"
        assert args.scope_file == "scope.yaml"

    def test_bounty_campaign_status(self):
        parser = build_parser()
        args = parser.parse_args(["bounty", "campaign", "status", "--handle", "acme"])
        assert args.bounty_cmd == "campaign"
        assert args.bounty_action == "status"
        assert args.handle == "acme"

    def test_bounty_campaign_run(self):
        parser = build_parser()
        args = parser.parse_args([
            "bounty", "campaign", "run",
            "--scope-file", "s.yaml",
            "--max-hours", "2.0",
            "--max-findings", "50",
        ])
        assert args.bounty_action == "run"
        assert args.scope_file == "s.yaml"
        assert args.max_hours == 2.0
        assert args.max_findings == 50

    def test_bounty_cvss(self):
        parser = build_parser()
        args = parser.parse_args(["bounty", "cvss", "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"])
        assert args.bounty_cmd == "cvss"
        assert args.vector == "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"


# ── Functional tests ─────────────────────────────────────────────────────────


class TestBountyAgentsCommand:
    """firm bounty agents prints the 8 agents."""

    def test_agents_output(self, capsys):
        main(["bounty", "agents"])
        out = capsys.readouterr().out
        assert "hunt-director" in out
        assert "recon-agent" in out
        assert "report-writer" in out
        assert "8 agents total" in out


class TestBountyCvssCommand:
    """firm bounty cvss calculates CVSS scores."""

    def test_cvss_critical(self, capsys):
        main(["bounty", "cvss", "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"])
        out = capsys.readouterr().out
        assert "9.8" in out
        assert "critical" in out.lower()

    def test_cvss_invalid_exits(self):
        with pytest.raises(SystemExit):
            main(["bounty", "cvss", "INVALID_VECTOR"])


class TestBountyScopeCommand:
    """firm bounty scope displays scope from a YAML file."""

    def test_scope_display(self, tmp_path, capsys):
        scope_file = tmp_path / "scope.yaml"
        scope_file.write_text(textwrap.dedent("""\
            programme_name: Acme Corp
            programme_handle: acme-corp
            in_scope:
              - identifier: "*.acme.com"
                type: wildcard
                eligible: true
                max_severity: critical
              - identifier: "api.acme.com"
                type: domain
            out_of_scope:
              - identifier: "staging.acme.com"
                type: domain
        """))
        main(["bounty", "scope", str(scope_file)])
        out = capsys.readouterr().out
        assert "acme-corp" in out
        assert "*.acme.com" in out
        assert "staging.acme.com" in out

    def test_scope_missing_file(self):
        with pytest.raises(SystemExit):
            main(["bounty", "scope", "/nonexistent/scope.yaml"])


class TestBountyInitCommand:
    """firm bounty init wires up a BountyFirm."""

    def test_init_from_yaml(self, tmp_path, capsys):
        scope_file = tmp_path / "scope.yaml"
        scope_file.write_text(textwrap.dedent("""\
            programme_name: Test Prog
            programme_handle: test-prog
            in_scope:
              - identifier: "*.test.com"
                type: wildcard
        """))
        main(["bounty", "init", str(scope_file)])
        out = capsys.readouterr().out
        assert "test-prog" in out
        assert "Agents:" in out
        assert "Tools:" in out


class TestBountyCampaignCommand:
    """firm bounty campaign status / run."""

    def test_campaign_status(self, capsys):
        main(["bounty", "campaign", "status", "--handle", "demo"])
        out = capsys.readouterr().out
        assert "demo" in out
        assert "Phase:" in out

    def test_campaign_run_missing_scope(self):
        with pytest.raises(SystemExit):
            main(["bounty", "campaign", "run"])

    def test_campaign_run(self, tmp_path, capsys):
        scope_file = tmp_path / "scope.yaml"
        scope_file.write_text(textwrap.dedent("""\
            programme_name: Run Test
            programme_handle: run-test
            in_scope:
              - identifier: "*.run.com"
                type: wildcard
        """))
        main(["bounty", "campaign", "run", "--scope-file", str(scope_file)])
        out = capsys.readouterr().out
        assert "Campaign started: run-test" in out
        assert "recon" in out.lower()
