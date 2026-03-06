"""Tests for firm.bounty.reward — reward engine.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

import pytest

from firm.bounty.reward import RewardEngine
from firm.bounty.vulnerability import Vulnerability, VulnSeverity


@pytest.fixture
def engine():
    return RewardEngine()


class TestRewardEngine:
    def test_basic_distribution(self, engine):
        v = Vulnerability(severity=VulnSeverity.MEDIUM, discovered_by="web-hunter")
        dist = engine.distribute(v, bounty_usd=100.0)
        assert dist.bounty_usd == 100.0
        assert dist.total_credits == 100.0 * 10.0 * 1.5  # medium mult
        assert len(dist.allocations) >= 1

    def test_critical_multiplier(self, engine):
        v = Vulnerability(severity=VulnSeverity.CRITICAL, discovered_by="hunter")
        dist = engine.distribute(v, bounty_usd=1000.0)
        assert dist.total_credits == 1000.0 * 10.0 * 4.0  # 40000

    def test_hunter_gets_60_percent(self, engine):
        v = Vulnerability(severity=VulnSeverity.HIGH, discovered_by="web-hunter")
        dist = engine.distribute(v, bounty_usd=100.0)
        hunter_alloc = [a for a in dist.allocations if a.role == "hunter"]
        assert len(hunter_alloc) == 1
        expected_base = 100.0 * 10.0 * 2.5 * 0.60  # 1500
        assert hunter_alloc[0].base_credits == expected_base

    def test_authority_bonus(self, engine):
        v = Vulnerability(severity=VulnSeverity.MEDIUM, discovered_by="web-hunter")
        dist = engine.distribute(
            v,
            bounty_usd=100.0,
            contributors={"hunter": "web-hunter"},
            authority_scores={"web-hunter": 1.0},  # max authority → +50%
        )
        alloc = dist.allocations[0]
        assert alloc.authority_bonus > 0
        assert alloc.total_credits > alloc.base_credits

    def test_low_authority_penalty(self, engine):
        v = Vulnerability(severity=VulnSeverity.MEDIUM, discovered_by="web-hunter")
        dist = engine.distribute(
            v,
            bounty_usd=100.0,
            contributors={"hunter": "web-hunter"},
            authority_scores={"web-hunter": 0.0},  # min authority → -50%
        )
        alloc = dist.allocations[0]
        assert alloc.authority_bonus < 0
        assert alloc.total_credits < alloc.base_credits

    def test_info_severity_zero_credits(self, engine):
        v = Vulnerability(severity=VulnSeverity.INFO, discovered_by="hunter")
        dist = engine.distribute(v, bounty_usd=100.0)
        assert dist.total_credits == 0.0

    def test_multiple_contributors(self, engine):
        v = Vulnerability(severity=VulnSeverity.HIGH, discovered_by="web-hunter")
        dist = engine.distribute(
            v,
            bounty_usd=200.0,
            contributors={
                "hunter": "web-hunter",
                "recon": "recon-agent",
                "writer": "report-writer",
            },
        )
        assert len(dist.allocations) == 3
        names = {a.agent_name for a in dist.allocations}
        assert names == {"web-hunter", "recon-agent", "report-writer"}

    def test_penalty(self, engine):
        result = engine.penalty("bad-agent", reason="duplicate", amount=10.0)
        assert result["penalty_credits"] == -10.0
        assert result["agent"] == "bad-agent"
