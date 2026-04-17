"""Tests for the firm.security_firm module.

Covers: agents, findings, tools, report, pipeline, factory.
No real LLM calls — all provider interactions are mocked.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import smoke tests
# ---------------------------------------------------------------------------


class TestImports:
    """Verify all public symbols import correctly."""

    def test_top_level_imports(self):
        from firm.security_firm import (
            SECURITY_AGENTS,
            create_security_firm,
            make_repo_tools,
        )
        assert len(SECURITY_AGENTS) == 4
        assert callable(create_security_firm)
        assert callable(make_repo_tools)

    def test_version(self):
        from firm.security_firm import __version__
        assert __version__ == "0.1.0"


# ---------------------------------------------------------------------------
# Agents tests
# ---------------------------------------------------------------------------


class TestAgents:
    def test_agent_count(self):
        from firm.security_firm.agents import SECURITY_AGENTS
        assert len(SECURITY_AGENTS) == 4

    def test_agent_names(self):
        from firm.security_firm.agents import SECURITY_AGENTS
        names = {a.name for a in SECURITY_AGENTS}
        assert names == {"security-director", "code-scanner", "static-analyzer", "report-synthesizer"}

    def test_agent_models(self):
        from firm.security_firm.agents import SECURITY_AGENTS
        models = {a.model for a in SECURITY_AGENTS}
        assert "claude-opus-4.6" in models
        assert "gpt-5.4" in models
        assert "gpt-5.3-codex" in models
        assert "gemini-3.1-pro-preview" in models

    def test_all_use_copilot_pro(self):
        from firm.security_firm.agents import SECURITY_AGENTS
        for agent in SECURITY_AGENTS:
            assert agent.provider == "copilot-pro"

    def test_token_budget_1m(self):
        from firm.security_firm.agents import SECURITY_AGENTS
        for agent in SECURITY_AGENTS:
            assert agent.config.max_tokens_budget == 1_000_000

    def test_director_highest_authority(self):
        from firm.security_firm.agents import SECURITY_AGENTS
        director = next(a for a in SECURITY_AGENTS if a.name == "security-director")
        for agent in SECURITY_AGENTS:
            assert director.initial_authority >= agent.initial_authority

    def test_role_defs_exist(self):
        from firm.security_firm.agents import SECURITY_AGENTS, get_role_def
        for agent in SECURITY_AGENTS:
            role = get_role_def(agent.name)
            assert len(role) > 50, f"Role definition too short for {agent.name}"

    def test_role_def_unknown(self):
        from firm.security_firm.agents import get_role_def
        assert get_role_def("nonexistent") == ""

    def test_mcp_categories_defined(self):
        from firm.security_firm.agents import SECURITY_AGENTS
        for agent in SECURITY_AGENTS:
            assert isinstance(agent.mcp_categories, list)
            assert len(agent.mcp_categories) >= 1


# ---------------------------------------------------------------------------
# Findings tests
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_finding():
    from firm.security_firm.findings import Finding, Severity
    return Finding(
        title="SQL Injection in login handler",
        description="User input passed directly to SQL query",
        severity=Severity.CRITICAL,
        file_path="src/auth.py",
        line_start=42,
        line_end=55,
        code_snippet='cursor.execute(f"SELECT * FROM users WHERE id={user_id}")',
        cwe_id=89,
        cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
        cvss_score=9.8,
        impact="Full database compromise",
        remediation="Use parameterized queries",
        found_by="code-scanner",
    )


@pytest.fixture
def findings_db():
    from firm.security_firm.findings import FindingsDB
    db = FindingsDB(":memory:")
    yield db
    db.close()


class TestFinding:
    def test_creation(self, sample_finding):
        assert sample_finding.title == "SQL Injection in login handler"
        assert sample_finding.severity.value == "critical"
        assert sample_finding.cwe_id == 89

    def test_fingerprint_deterministic(self, sample_finding):
        fp1 = sample_finding.fingerprint
        fp2 = sample_finding.fingerprint
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex

    def test_fingerprint_differs(self):
        from firm.security_firm.findings import Finding, Severity
        f1 = Finding(title="A", description="", severity=Severity.HIGH, file_path="a.py", line_start=1)
        f2 = Finding(title="B", description="", severity=Severity.HIGH, file_path="b.py", line_start=2)
        assert f1.fingerprint != f2.fingerprint

    def test_to_dict(self, sample_finding):
        d = sample_finding.to_dict()
        assert d["severity"] == "critical"
        assert d["cwe_id"] == 89
        assert "fingerprint" in d

    def test_from_dict_roundtrip(self, sample_finding):
        from firm.security_firm.findings import Finding
        d = sample_finding.to_dict()
        restored = Finding.from_dict(d)
        assert restored.title == sample_finding.title
        assert restored.severity == sample_finding.severity
        assert restored.cwe_id == sample_finding.cwe_id

    def test_severity_from_string(self):
        from firm.security_firm.findings import Finding
        f = Finding(title="Test", description="", severity="high")
        assert f.severity.value == "high"

    def test_severity_rank(self):
        from firm.security_firm.findings import Finding, Severity
        critical = Finding(title="A", description="", severity=Severity.CRITICAL)
        info = Finding(title="B", description="", severity=Severity.INFO)
        assert critical.severity_rank < info.severity_rank

    def test_auto_id_from_fingerprint(self, sample_finding):
        assert len(sample_finding.id) == 12
        assert sample_finding.id == sample_finding.fingerprint[:12]


class TestFindingsDB:
    def test_add_and_get(self, findings_db, sample_finding):
        assert findings_db.add(sample_finding) is True
        got = findings_db.get(sample_finding.id)
        assert got is not None
        assert got.title == sample_finding.title

    def test_duplicate_rejected(self, findings_db, sample_finding):
        assert findings_db.add(sample_finding) is True
        # Same fingerprint → rejected
        assert findings_db.add(sample_finding) is False

    def test_add_many(self, findings_db):
        from firm.security_firm.findings import Finding, Severity
        findings = [
            Finding(title=f"Finding {i}", description="", severity=Severity.MEDIUM,
                    file_path=f"file{i}.py", line_start=i)
            for i in range(5)
        ]
        inserted, dupes = findings_db.add_many(findings)
        assert inserted == 5
        assert dupes == 0

    def test_all(self, findings_db):
        from firm.security_firm.findings import Finding, Severity
        for i in range(3):
            findings_db.add(Finding(
                title=f"F{i}", description="", severity=Severity.HIGH,
                file_path=f"f{i}.py", line_start=i,
            ))
        assert len(findings_db.all()) == 3

    def test_by_severity(self, findings_db):
        from firm.security_firm.findings import Finding, Severity
        findings_db.add(Finding(title="Crit", description="", severity=Severity.CRITICAL,
                                file_path="a.py", line_start=1))
        findings_db.add(Finding(title="Low", description="", severity=Severity.LOW,
                                file_path="b.py", line_start=2))
        assert len(findings_db.by_severity(Severity.CRITICAL)) == 1
        assert len(findings_db.by_severity(Severity.LOW)) == 1
        assert len(findings_db.by_severity(Severity.INFO)) == 0

    def test_by_agent(self, findings_db):
        from firm.security_firm.findings import Finding, Severity
        findings_db.add(Finding(title="A", description="", severity=Severity.HIGH,
                                file_path="a.py", line_start=1, found_by="code-scanner"))
        findings_db.add(Finding(title="B", description="", severity=Severity.MEDIUM,
                                file_path="b.py", line_start=2, found_by="static-analyzer"))
        assert len(findings_db.by_agent("code-scanner")) == 1
        assert len(findings_db.by_agent("static-analyzer")) == 1

    def test_stats(self, findings_db):
        from firm.security_firm.findings import Finding, Severity
        findings_db.add(Finding(title="C1", description="", severity=Severity.CRITICAL,
                                file_path="a.py", line_start=1, found_by="code-scanner"))
        findings_db.add(Finding(title="H1", description="", severity=Severity.HIGH,
                                file_path="b.py", line_start=2, found_by="static-analyzer"))
        stats = findings_db.stats()
        assert stats["total"] == 2
        assert stats["unique"] == 2
        assert stats["duplicates"] == 0
        assert stats["by_severity"]["critical"] == 1
        assert stats["by_severity"]["high"] == 1
        assert stats["by_agent"]["code-scanner"] == 1

    def test_confirm(self, findings_db, sample_finding):
        findings_db.add(sample_finding)
        findings_db.confirm(sample_finding.id, "security-director")
        got = findings_db.get(sample_finding.id)
        assert got.status.value == "confirmed"
        assert "security-director" in got.confirmed_by

    def test_mark_false_positive(self, findings_db, sample_finding):
        findings_db.add(sample_finding)
        findings_db.mark_false_positive(sample_finding.id)
        got = findings_db.get(sample_finding.id)
        assert got.status.value == "false_positive"


# ---------------------------------------------------------------------------
# Tools tests
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_repo(tmp_path):
    """Create a minimal repo structure for testing tools."""
    # Source files
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        "import os\n"
        "password = 'my_secret_123'\n"  # deliberate secret
        "def query(user_id):\n"
        '    return f"SELECT * FROM users WHERE id={user_id}"\n'
    )
    (src / "utils.py").write_text("def helper(): pass\n")

    # Config
    (tmp_path / "Dockerfile").write_text("FROM python:latest\nRUN pip install flask\n")
    (tmp_path / "requirements.txt").write_text("flask==3.0.0\nrequests==2.31.0\n")
    (tmp_path / ".env").write_text("DATABASE_URL=postgres://user:pass@localhost/db\n")

    # README
    (tmp_path / "README.md").write_text("# Sample Project\nA test repo.\n")

    return tmp_path


class TestRepoTools:
    def test_make_repo_tools_count(self):
        from firm.security_firm.tools.repo_scanner import make_repo_tools
        tools = make_repo_tools()
        assert len(tools) == 10
        for t in tools:
            assert "name" in t
            assert "description" in t
            assert "parameters" in t
            assert "callable" in t

    def test_repo_clone_or_open_local(self, sample_repo):
        from firm.security_firm.tools.repo_scanner import _repo_clone_or_open
        result = json.loads(_repo_clone_or_open(str(sample_repo)))
        assert result["status"] == "local"
        assert "path" in result

    def test_repo_clone_or_open_missing(self):
        from firm.security_firm.tools.repo_scanner import _repo_clone_or_open
        result = json.loads(_repo_clone_or_open("/nonexistent/path/abc123"))
        assert "error" in result

    def test_repo_tree(self, sample_repo):
        from firm.security_firm.tools.repo_scanner import _repo_tree
        result = json.loads(_repo_tree(str(sample_repo)))
        assert result["total_files"] >= 5
        assert ".py" in result["extensions"]

    def test_repo_tree_not_a_dir(self):
        from firm.security_firm.tools.repo_scanner import _repo_tree
        result = json.loads(_repo_tree("/nonexistent"))
        assert "error" in result

    def test_repo_file_read(self, sample_repo):
        from firm.security_firm.tools.repo_scanner import _repo_file_read
        result = json.loads(_repo_file_read(str(sample_repo), "src/app.py"))
        assert result["total_lines"] == 4
        assert "password" in result["content"]

    def test_repo_file_read_traversal_blocked(self, sample_repo):
        from firm.security_firm.tools.repo_scanner import _repo_file_read
        result = json.loads(_repo_file_read(str(sample_repo), "../../etc/passwd"))
        assert "error" in result
        assert "traversal" in result["error"].lower() or "not a file" in result["error"].lower()

    def test_repo_grep_secrets(self, sample_repo):
        from firm.security_firm.tools.repo_scanner import _repo_grep_secrets
        result = json.loads(_repo_grep_secrets(str(sample_repo)))
        # Should find at least the password and database URL
        assert result["count"] >= 1
        patterns_found = {f["pattern"] for f in result["findings"]}
        assert len(patterns_found) >= 1

    def test_repo_dependency_audit(self, sample_repo):
        from firm.security_firm.tools.repo_scanner import _repo_dependency_audit
        result = json.loads(_repo_dependency_audit(str(sample_repo)))
        assert result["count"] >= 1  # requirements.txt
        dep_files = [d["file"] for d in result["dependency_files"]]
        assert "requirements.txt" in dep_files

    def test_repo_config_scan(self, sample_repo):
        from firm.security_firm.tools.repo_scanner import _repo_config_scan
        result = json.loads(_repo_config_scan(str(sample_repo)))
        # Should find :latest in Dockerfile + secrets in .env
        assert result["count"] >= 1

    def test_repo_file_stats(self, sample_repo):
        from firm.security_firm.tools.repo_scanner import _repo_file_stats
        result = json.loads(_repo_file_stats(str(sample_repo)))
        assert result["total_files"] >= 5
        assert result["total_size_bytes"] > 0

    def test_repo_summarize_findings_valid(self):
        from firm.security_firm.tools.repo_scanner import _repo_summarize_findings
        data = json.dumps({
            "findings": [
                {"pattern": "AWS Key", "file": "a.py", "line": 1},
                {"pattern": "AWS Key", "file": "b.py", "line": 2},
                {"pattern": "JWT", "file": "c.py", "line": 3},
            ]
        })
        result = json.loads(_repo_summarize_findings(data))
        assert result["total"] == 3
        assert result["by_type"]["AWS Key"] == 2
        assert result["by_type"]["JWT"] == 1

    def test_repo_summarize_findings_invalid(self):
        from firm.security_firm.tools.repo_scanner import _repo_summarize_findings
        result = json.loads(_repo_summarize_findings("not json at all"))
        assert "error" in result

    def test_repo_git_history_secrets_not_git(self, sample_repo):
        from firm.security_firm.tools.repo_scanner import _repo_git_history_secrets
        result = json.loads(_repo_git_history_secrets(str(sample_repo)))
        assert "error" in result
        assert "not a git" in result["error"].lower()

    def test_safe_path_blocks_traversal(self):
        from firm.security_firm.tools.repo_scanner import _safe_path
        assert _safe_path("/tmp/repo", "../../etc/passwd") is None

    def test_safe_path_allows_valid(self, tmp_path):
        from firm.security_firm.tools.repo_scanner import _safe_path
        (tmp_path / "file.txt").write_text("ok")
        result = _safe_path(str(tmp_path), "file.txt")
        assert result is not None
        assert "file.txt" in result


# ---------------------------------------------------------------------------
# Report tests
# ---------------------------------------------------------------------------


class TestReportGenerator:
    def test_generate_empty(self):
        from firm.security_firm.findings import FindingsDB
        from firm.security_firm.report import ReportGenerator

        db = FindingsDB(":memory:")
        gen = ReportGenerator(db=db, repo_name="test-repo", repo_path="/tmp/test")
        report = gen.generate()
        assert "# 🔒 Security Audit Report" in report
        assert "test-repo" in report
        assert "Executive Summary" in report
        db.close()

    def test_generate_with_findings(self, findings_db):
        from firm.security_firm.findings import Finding, Severity
        from firm.security_firm.report import ReportGenerator

        findings_db.add(Finding(
            title="SQL Injection",
            description="Direct SQL",
            severity=Severity.CRITICAL,
            file_path="auth.py",
            line_start=42,
            cwe_id=89,
            cvss_score=9.8,
            found_by="code-scanner",
            remediation="Use parameterized queries",
        ))
        findings_db.add(Finding(
            title="Hardcoded Secret",
            description="API key in source",
            severity=Severity.HIGH,
            file_path="config.py",
            line_start=10,
            cwe_id=798,
            found_by="static-analyzer",
        ))

        gen = ReportGenerator(db=findings_db, repo_name="test", repo_path="/tmp/test")
        report = gen.generate()

        assert "CRITICAL" in report
        assert "HIGH" in report
        assert "SQL Injection" in report
        assert "CWE-89" in report
        assert "auth.py" in report
        assert "Hardcoded Secret" in report

    def test_risk_score(self):
        from firm.security_firm.report import ReportGenerator

        # 2 critical + 1 high = 2*25 + 1*10 = 60
        score = ReportGenerator._risk_score({"critical": 2, "high": 1})
        assert score == 60

        # Cap at 100
        score = ReportGenerator._risk_score({"critical": 10})
        assert score == 100

    def test_agent_performance_section(self, findings_db):
        from firm.security_firm.report import ReportGenerator

        gen = ReportGenerator(
            db=findings_db,
            repo_name="test",
            repo_path="/tmp/test",
            agent_stats=[
                {"name": "code-scanner", "model": "gpt-5.4", "tasks_executed": 1,
                 "success_rate": 1.0, "total_tokens": 50000, "findings_count": 3,
                 "total_cost_usd": 0.0},
            ],
        )
        report = gen.generate()
        assert "Agent Performance" in report
        assert "code-scanner" in report
        assert "gpt-5.4" in report


# ---------------------------------------------------------------------------
# Pipeline tests (mocked — no real LLM calls)
# ---------------------------------------------------------------------------


class TestPipeline:
    @patch("firm.security_firm.pipeline.create_llm_agent")
    def test_pipeline_creates_4_agents(self, mock_create, tmp_path):
        """Pipeline should create 4 agents."""
        # Mock the agent creation
        mock_agent = MagicMock()
        mock_agent._toolkit = MagicMock()
        mock_agent._toolkit.working_dir = str(tmp_path)
        mock_agent._toolkit.timeout = 30
        mock_agent._toolkit.list_tools.return_value = []
        mock_create.return_value = mock_agent

        from firm.security_firm.pipeline import SecurityPipeline
        pipeline = SecurityPipeline(
            repo_path=str(tmp_path),
            use_mcp=False,
        )
        assert len(pipeline.agents) == 4
        assert mock_create.call_count == 4

    @patch("firm.security_firm.pipeline.create_llm_agent")
    def test_pipeline_agent_names(self, mock_create, tmp_path):
        mock_agent = MagicMock()
        mock_agent._toolkit = MagicMock()
        mock_agent._toolkit.working_dir = str(tmp_path)
        mock_agent._toolkit.timeout = 30
        mock_agent._toolkit.list_tools.return_value = []
        mock_create.return_value = mock_agent

        from firm.security_firm.pipeline import SecurityPipeline
        pipeline = SecurityPipeline(repo_path=str(tmp_path), use_mcp=False)

        expected = {"security-director", "code-scanner", "static-analyzer", "report-synthesizer"}
        assert set(pipeline.agents.keys()) == expected

    def test_dict_to_finding(self):
        from firm.security_firm.pipeline import SecurityPipeline
        d = {
            "title": "XSS in template",
            "severity": "high",
            "file_path": "views.py",
            "line_start": 15,
            "cwe_id": 79,
        }
        finding = SecurityPipeline._dict_to_finding(d, "code-scanner")
        assert finding.title == "XSS in template"
        assert finding.severity.value == "high"
        assert finding.found_by == "code-scanner"
        assert finding.cwe_id == 79

    def test_dict_to_finding_invalid_severity(self):
        from firm.security_firm.pipeline import SecurityPipeline
        d = {"title": "Test", "severity": "bogus"}
        finding = SecurityPipeline._dict_to_finding(d, "test")
        assert finding.severity.value == "medium"  # fallback

    def test_find_json_arrays(self):
        from firm.security_firm.pipeline import _find_json_arrays
        text = 'Some text [{"title": "A"}, {"title": "B"}] more text'
        arrays = _find_json_arrays(text)
        assert len(arrays) == 1
        parsed = json.loads(arrays[0])
        assert len(parsed) == 2

    def test_find_json_arrays_nested(self):
        from firm.security_firm.pipeline import _find_json_arrays
        text = '[[1, 2], [3, 4]]'
        arrays = _find_json_arrays(text)
        assert len(arrays) == 1

    def test_find_json_arrays_none(self):
        from firm.security_firm.pipeline import _find_json_arrays
        assert _find_json_arrays("no arrays here") == []


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


class TestFactory:
    @patch("firm.security_firm.pipeline.create_llm_agent")
    def test_create_security_firm(self, mock_create, tmp_path):
        mock_agent = MagicMock()
        mock_agent._toolkit = MagicMock()
        mock_agent._toolkit.working_dir = str(tmp_path)
        mock_agent._toolkit.timeout = 30
        mock_agent._toolkit.list_tools.return_value = []
        mock_create.return_value = mock_agent

        from firm.security_firm import create_security_firm
        ctx = create_security_firm(
            repo_path=str(tmp_path),
            use_mcp=False,
        )

        assert "pipeline" in ctx
        assert "firm" in ctx
        assert "agents" in ctx
        assert "tools" in ctx
        assert "db" in ctx
        assert len(ctx["agents"]) == 4
        assert len(ctx["tools"]) == 10
