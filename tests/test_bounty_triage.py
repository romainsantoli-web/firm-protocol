"""Tests for firm.bounty.triage — triage pipeline.

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

import pytest

from firm.bounty.triage import TriageDecision, TriagePipeline
from firm.bounty.vulnerability import Vulnerability, VulnSeverity, VulnStatus


@pytest.fixture
def pipeline():
    return TriagePipeline()


class TestTriagePipeline:
    def test_critical_requires_human(self, pipeline):
        v = Vulnerability(severity=VulnSeverity.CRITICAL, confidence=0.99)
        result = pipeline.evaluate(v)
        assert result.decision == TriageDecision.HUMAN_REVIEW

    def test_high_requires_human(self, pipeline):
        v = Vulnerability(severity=VulnSeverity.HIGH, confidence=0.9)
        result = pipeline.evaluate(v)
        assert result.decision == TriageDecision.HUMAN_REVIEW

    def test_info_always_archived(self, pipeline):
        v = Vulnerability(severity=VulnSeverity.INFO, confidence=1.0)
        result = pipeline.evaluate(v)
        assert result.decision == TriageDecision.ARCHIVE

    def test_low_low_confidence_archived(self, pipeline):
        v = Vulnerability(severity=VulnSeverity.LOW, confidence=0.3)
        result = pipeline.evaluate(v)
        assert result.decision == TriageDecision.ARCHIVE

    def test_medium_high_confidence_auto_submit(self, pipeline):
        v = Vulnerability(severity=VulnSeverity.MEDIUM, confidence=0.8)
        result = pipeline.evaluate(v)
        assert result.decision == TriageDecision.AUTO_SUBMIT

    def test_medium_low_confidence_human_review(self, pipeline):
        v = Vulnerability(severity=VulnSeverity.MEDIUM, confidence=0.5)
        result = pipeline.evaluate(v)
        assert result.decision == TriageDecision.HUMAN_REVIEW

    def test_low_high_confidence_auto_submit(self, pipeline):
        v = Vulnerability(severity=VulnSeverity.LOW, confidence=0.8)
        result = pipeline.evaluate(v)
        assert result.decision == TriageDecision.AUTO_SUBMIT

    def test_customisable_threshold(self):
        p = TriagePipeline(auto_submit_threshold=0.9)
        v = Vulnerability(severity=VulnSeverity.MEDIUM, confidence=0.8)
        result = p.evaluate(v)
        assert result.decision == TriageDecision.HUMAN_REVIEW  # 0.8 < 0.9

    def test_no_human_for_high_override(self):
        p = TriagePipeline(require_human_for_high=False)
        v = Vulnerability(severity=VulnSeverity.HIGH, confidence=0.9)
        result = p.evaluate(v)
        assert result.decision == TriageDecision.AUTO_SUBMIT


class TestHackerOneFeedback:
    def test_bounty_resolves_true(self):
        v = Vulnerability(discovered_by="web-hunter")
        result = TriagePipeline.process_hackerone_feedback(v, "bounty", 500.0)
        assert result["resolution"] is True
        assert result["bounty_usd"] == 500.0
        assert v.status == VulnStatus.ACCEPTED

    def test_duplicate_resolves_false(self):
        v = Vulnerability()
        result = TriagePipeline.process_hackerone_feedback(v, "duplicate")
        assert result["resolution"] is False
        assert v.status == VulnStatus.DUPLICATE

    def test_new_resolves_none(self):
        v = Vulnerability()
        result = TriagePipeline.process_hackerone_feedback(v, "new")
        assert result["resolution"] is None
        assert v.status == VulnStatus.SUBMITTED

    def test_resolved_resolves_true(self):
        v = Vulnerability()
        result = TriagePipeline.process_hackerone_feedback(v, "resolved")
        assert result["resolution"] is True
        assert v.status == VulnStatus.RESOLVED

    def test_informative_resolves_false(self):
        v = Vulnerability()
        result = TriagePipeline.process_hackerone_feedback(v, "informative")
        assert result["resolution"] is False
        assert v.status == VulnStatus.INFORMATIVE
