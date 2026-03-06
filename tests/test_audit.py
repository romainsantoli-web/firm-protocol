"""Tests for Audit Trail (Layer 10)."""
from firm.core.agent import Agent
from firm.core.audit import (
    AuditEngine,
    AuditFinding,
    AuditReport,
)
from firm.core.authority import AuthorityEngine
from firm.core.ledger import ResponsibilityLedger
from firm.core.types import AgentId, LedgerAction, Severity


def _make_ledger_with_entries(agents: list[Agent]) -> ResponsibilityLedger:
    """Build a ledger with some actions for testing."""
    ledger = ResponsibilityLedger()
    for agent in agents:
        ledger.append(
            agent_id=agent.id,
            action=LedgerAction.TASK_COMPLETED,
            description=f"{agent.name} completed a task",
            authority_at_time=agent.authority,
            credit_delta=10.0,
            outcome="success",
        )
    return ledger


class TestFullAudit:
    def test_audit_healthy_org(self):
        engine = AuditEngine()
        agents = [
            Agent(name="alice", authority=0.7, credits=100.0),
            Agent(name="bob", authority=0.5, credits=80.0),
        ]
        ledger = _make_ledger_with_entries(agents)
        auth_engine = AuthorityEngine()
        report = engine.full_audit("test-firm", ledger, agents, auth_engine)
        assert report.chain_valid
        assert report.is_healthy
        assert report.firm_name == "test-firm"
        assert len(report.agent_summaries) == 2

    def test_audit_detects_authority_concentration(self):
        engine = AuditEngine()
        agents = [
            Agent(name="dictator", authority=0.95),
            Agent(name="peon", authority=0.2),
        ]
        ledger = _make_ledger_with_entries(agents)
        auth_engine = AuthorityEngine()
        report = engine.full_audit("test", ledger, agents, auth_engine)
        authority_findings = [f for f in report.findings if f.category == "authority"]
        assert len(authority_findings) >= 1
        assert any("concentration" in f.title.lower() for f in authority_findings)

    def test_audit_detects_negative_credits(self):
        engine = AuditEngine()
        agents = [Agent(name="spender", authority=0.5, credits=-50.0)]
        ledger = _make_ledger_with_entries(agents)
        auth_engine = AuthorityEngine()
        report = engine.full_audit("test", ledger, agents, auth_engine)
        credit_findings = [f for f in report.findings if f.category == "credits"]
        assert len(credit_findings) >= 1
        assert any("negative" in f.title.lower() for f in credit_findings)

    def test_audit_detects_high_credits(self):
        engine = AuditEngine()
        agents = [Agent(name="rich", authority=0.5, credits=15000.0)]
        ledger = _make_ledger_with_entries(agents)
        auth_engine = AuthorityEngine()
        report = engine.full_audit("test", ledger, agents, auth_engine)
        credit_findings = [f for f in report.findings if f.category == "credits"]
        assert any("high" in f.title.lower() for f in credit_findings)

    def test_audit_broken_chain(self):
        engine = AuditEngine()
        agents = [Agent(name="alice", authority=0.5)]
        ledger = ResponsibilityLedger()
        ledger.append(
            agent_id=AgentId("a1"),
            action=LedgerAction.TASK_COMPLETED,
            description="task 1",
            outcome="ok",
        )
        # Tamper with the chain
        if ledger._entries:
            ledger._entries[0].entry_hash = "tampered"
        auth_engine = AuthorityEngine()
        report = engine.full_audit("test", ledger, agents, auth_engine)
        assert not report.chain_valid
        assert not report.is_healthy

    def test_audit_empty_org(self):
        engine = AuditEngine()
        ledger = ResponsibilityLedger()
        auth_engine = AuthorityEngine()
        report = engine.full_audit("empty", ledger, [], auth_engine)
        assert report.chain_valid
        assert report.is_healthy


class TestAuditTimeline:
    def test_timeline(self):
        engine = AuditEngine()
        ledger = ResponsibilityLedger()
        ledger.append(
            agent_id=AgentId("a1"),
            action=LedgerAction.TASK_COMPLETED,
            description="did a thing",
            authority_at_time=0.5,
            credit_delta=10.0,
            outcome="success",
        )
        timeline = engine.get_timeline(ledger)
        assert len(timeline) == 1
        assert timeline[0]["action"] == "task_completed"
        assert timeline[0]["credit_delta"] == 10.0

    def test_timeline_filter_by_agent(self):
        engine = AuditEngine()
        ledger = ResponsibilityLedger()
        ledger.append(agent_id=AgentId("a1"), action=LedgerAction.TASK_COMPLETED,
                       description="a1 task", outcome="ok")
        ledger.append(agent_id=AgentId("a2"), action=LedgerAction.TASK_COMPLETED,
                       description="a2 task", outcome="ok")
        timeline = engine.get_timeline(ledger, agent_id="a1")
        assert len(timeline) == 1
        assert timeline[0]["agent_id"] == "a1"

    def test_timeline_filter_by_action(self):
        engine = AuditEngine()
        ledger = ResponsibilityLedger()
        ledger.append(agent_id=AgentId("a1"), action=LedgerAction.TASK_COMPLETED,
                       description="done", outcome="ok")
        ledger.append(agent_id=AgentId("a1"), action=LedgerAction.TASK_FAILED,
                       description="failed", outcome="fail")
        timeline = engine.get_timeline(ledger, action_filter=LedgerAction.TASK_FAILED)
        assert len(timeline) == 1
        assert timeline[0]["action"] == "task_failed"

    def test_timeline_limit(self):
        engine = AuditEngine()
        ledger = ResponsibilityLedger()
        for i in range(20):
            ledger.append(agent_id=AgentId("a1"), action=LedgerAction.TASK_COMPLETED,
                           description=f"task {i}", outcome="ok")
        timeline = engine.get_timeline(ledger, limit=5)
        assert len(timeline) == 5


class TestAuditReport:
    def test_severity_counts(self):
        report = AuditReport(firm_name="test")
        report.findings = [
            AuditFinding(severity=Severity.CRITICAL, category="x", title="a", description=""),
            AuditFinding(severity=Severity.HIGH, category="x", title="b", description=""),
            AuditFinding(severity=Severity.CRITICAL, category="x", title="c", description=""),
        ]
        counts = report.severity_counts
        assert counts["critical"] == 2
        assert counts["high"] == 1

    def test_is_healthy_true(self):
        report = AuditReport(firm_name="test")
        report.findings = [
            AuditFinding(severity=Severity.LOW, category="x", title="a", description=""),
        ]
        assert report.is_healthy

    def test_is_healthy_false(self):
        report = AuditReport(firm_name="test")
        report.findings = [
            AuditFinding(severity=Severity.HIGH, category="x", title="a", description=""),
        ]
        assert not report.is_healthy

    def test_to_dict(self):
        report = AuditReport(firm_name="test")
        d = report.to_dict()
        assert d["firm_name"] == "test"
        assert "is_healthy" in d
        assert "severity_counts" in d

    def test_finding_to_dict(self):
        finding = AuditFinding(
            severity=Severity.MEDIUM,
            category="credits",
            title="Test",
            description="desc",
            agent_id=AgentId("a1"),
        )
        d = finding.to_dict()
        assert d["severity"] == "medium"
        assert d["agent_id"] == "a1"


class TestAuditQueries:
    def test_get_reports(self):
        engine = AuditEngine()
        agents = [Agent(name="a", authority=0.5)]
        ledger = _make_ledger_with_entries(agents)
        auth_engine = AuthorityEngine()
        engine.full_audit("r1", ledger, agents, auth_engine)
        engine.full_audit("r2", ledger, agents, auth_engine)
        reports = engine.get_reports()
        assert len(reports) == 2

    def test_get_latest_report(self):
        engine = AuditEngine()
        agents = [Agent(name="a", authority=0.5)]
        ledger = _make_ledger_with_entries(agents)
        auth_engine = AuthorityEngine()
        engine.full_audit("r1", ledger, agents, auth_engine)
        engine.full_audit("r2", ledger, agents, auth_engine)
        latest = engine.get_latest_report()
        assert latest is not None
        assert latest.firm_name == "r2"

    def test_get_latest_empty(self):
        engine = AuditEngine()
        assert engine.get_latest_report() is None

    def test_get_stats(self):
        engine = AuditEngine()
        stats = engine.get_stats()
        assert stats["total_audits"] == 0
        assert stats["last_audit"] is None
