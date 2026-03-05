"""Tests for firm.bounty.campaign — campaign orchestrator.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

import pytest
import time

from firm.bounty.campaign import Campaign, CampaignPhase, CampaignStats
from firm.bounty.dedup import DeduplicationEngine
from firm.bounty.triage import TriageDecision, TriagePipeline
from firm.bounty.vulnerability import Vulnerability, VulnDatabase, VulnSeverity, VulnStatus


@pytest.fixture
def campaign():
    db = VulnDatabase()
    dedup = DeduplicationEngine(db)
    triage = TriagePipeline()
    c = Campaign(programme_handle="test-prog", max_findings=5)
    c.wire(db, dedup, triage)
    c.start()
    return c


class TestCampaignLifecycle:
    def test_starts_in_recon(self, campaign):
        assert campaign.phase == CampaignPhase.RECON

    def test_advance_phase(self, campaign):
        campaign.advance_phase()
        assert campaign.phase == CampaignPhase.SCAN
        campaign.advance_phase()
        assert campaign.phase == CampaignPhase.EXPLOIT

    def test_advance_through_all_phases(self, campaign):
        phases = []
        for _ in range(10):
            phases.append(campaign.phase)
            campaign.advance_phase()
        assert CampaignPhase.COMPLETE in phases


class TestCampaignFindings:
    def test_add_unique_finding(self, campaign):
        v = Vulnerability(cwe_id=79, asset="a.com", endpoint="/x", parameter="q", confidence=0.5)
        result = campaign.add_finding(v)
        assert result is not None
        assert campaign.stats.unique_findings == 1
        assert campaign.stats.duplicates == 0

    def test_add_duplicate_finding(self, campaign):
        v1 = Vulnerability(cwe_id=79, asset="a.com", endpoint="/x", parameter="q")
        v2 = Vulnerability(cwe_id=79, asset="a.com", endpoint="/x", parameter="q")
        campaign.add_finding(v1)
        result = campaign.add_finding(v2)
        assert result is None  # duplicate → no triage
        assert campaign.stats.duplicates == 1

    def test_submit_finding(self, campaign):
        v = Vulnerability(cwe_id=79, asset="a.com")
        campaign.submit_finding(v)
        assert v.status == VulnStatus.SUBMITTED
        assert campaign.stats.submitted == 1

    def test_process_feedback_accepted(self, campaign):
        v = Vulnerability(cwe_id=79, asset="a.com", discovered_by="hunter")
        result = campaign.process_feedback(v, "bounty", 500.0)
        assert result["resolution"] is True
        assert campaign.stats.accepted == 1
        assert campaign.stats.total_bounty_usd == 500.0

    def test_process_feedback_rejected(self, campaign):
        v = Vulnerability(cwe_id=79, asset="a.com")
        campaign.process_feedback(v, "duplicate")
        assert campaign.stats.rejected == 1


class TestCampaignStopConditions:
    def test_stop_on_max_findings(self, campaign):
        for i in range(5):
            v = Vulnerability(
                cwe_id=i, asset="a.com", endpoint=f"/{i}", parameter=f"p{i}",
                confidence=0.5,
            )
            campaign.add_finding(v)
        assert campaign.should_stop()

    def test_stop_on_complete(self, campaign):
        campaign.phase = CampaignPhase.COMPLETE
        assert campaign.should_stop()

    def test_not_stopped_initially(self, campaign):
        assert not campaign.should_stop()


class TestCampaignSummary:
    def test_summary_keys(self, campaign):
        s = campaign.summary()
        assert "programme" in s
        assert "unique_findings" in s
        assert "total_bounty_usd" in s
        assert s["programme"] == "test-prog"
