"""Markdown report generator for Security Firm scan results.

Takes a populated ``FindingsDB`` and agent stats to produce a professional
security audit report.
"""

from __future__ import annotations

import time
from typing import Any

from firm.security_firm.findings import Finding, FindingsDB, Severity

# ---------------------------------------------------------------------------
# Severity → emoji + color hint
# ---------------------------------------------------------------------------

_SEV_EMOJI = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH: "🟠",
    Severity.MEDIUM: "🟡",
    Severity.LOW: "🔵",
    Severity.INFO: "⚪",
}


class ReportGenerator:
    """Generates a Markdown security audit report from FindingsDB."""

    def __init__(
        self,
        db: FindingsDB,
        repo_name: str = "unknown",
        repo_path: str = "",
        agent_stats: list[dict[str, Any]] | None = None,
        scan_duration_s: float = 0.0,
    ):
        self.db = db
        self.repo_name = repo_name
        self.repo_path = repo_path
        self.agent_stats = agent_stats or []
        self.scan_duration_s = scan_duration_s

    def generate(self) -> str:
        """Generate the full Markdown report."""
        stats = self.db.stats()
        sections = [
            self._header(),
            self._executive_summary(stats),
            self._findings_by_severity(stats),
            self._agent_performance(),
            self._scan_metadata(stats),
            self._footer(),
        ]
        return "\n\n".join(sections)

    # ── Sections ────────────────────────────────────────────────────

    def _header(self) -> str:
        date = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
        return (
            f"# 🔒 Security Audit Report — {self.repo_name}\n\n"
            f"**Date:** {date}  \n"
            f"**Repository:** `{self.repo_path}`  \n"
            f"**Scanner:** FIRM Security Firm (4 agents, copilot-pro)  \n"
            f"**Protocol:** firm-protocol v1.1.0"
        )

    def _executive_summary(self, stats: dict) -> str:
        by_sev = stats["by_severity"]
        total = stats["unique"]
        risk = self._risk_score(by_sev)

        lines = [
            "## Executive Summary\n",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total findings | **{total}** |",
            f"| Critical | **{by_sev.get('critical', 0)}** |",
            f"| High | **{by_sev.get('high', 0)}** |",
            f"| Medium | **{by_sev.get('medium', 0)}** |",
            f"| Low | **{by_sev.get('low', 0)}** |",
            f"| Info | **{by_sev.get('info', 0)}** |",
            f"| Duplicates filtered | {stats['duplicates']} |",
            f"| Overall risk score | **{risk}/100** |",
        ]
        return "\n".join(lines)

    def _findings_by_severity(self, stats: dict) -> str:
        sections: list[str] = ["## Findings"]

        for severity in Severity:
            findings = self.db.by_severity(severity)
            if not findings:
                continue

            emoji = _SEV_EMOJI[severity]
            sections.append(f"\n### {emoji} {severity.value.upper()} ({len(findings)})\n")

            for i, f in enumerate(findings, 1):
                sections.append(self._format_finding(f, i))

        return "\n".join(sections)

    def _format_finding(self, f: Finding, index: int) -> str:
        lines = [
            f"#### {index}. {f.title}",
            "",
            "| Field | Value |",
            "|-------|-------|",
            f"| Severity | **{f.severity.value.upper()}** |",
        ]
        if f.cwe_id:
            lines.append(f"| CWE | [CWE-{f.cwe_id}](https://cwe.mitre.org/data/definitions/{f.cwe_id}.html) |")
        if f.cvss_score:
            lines.append(f"| CVSS | {f.cvss_score} ({f.cvss_vector}) |")
        if f.file_path:
            loc = f"`{f.file_path}"
            if f.line_start:
                loc += f":{f.line_start}"
                if f.line_end and f.line_end != f.line_start:
                    loc += f"-{f.line_end}"
            loc += "`"
            lines.append(f"| Location | {loc} |")
        if f.found_by:
            lines.append(f"| Found by | {f.found_by} |")
        if f.confirmed_by:
            lines.append(f"| Confirmed by | {', '.join(f.confirmed_by)} |")

        lines.append("")

        if f.description:
            lines.append(f"**Description:** {f.description}\n")
        if f.code_snippet:
            lines.append("```")
            lines.append(f.code_snippet[:500])
            lines.append("```\n")
        if f.impact:
            lines.append(f"**Impact:** {f.impact}\n")
        if f.reproduction_steps:
            lines.append(f"**Reproduction:**\n{f.reproduction_steps}\n")
        if f.remediation:
            lines.append(f"**Remediation:** {f.remediation}\n")

        lines.append("---\n")
        return "\n".join(lines)

    def _agent_performance(self) -> str:
        if not self.agent_stats:
            return "## Agent Performance\n\n_No agent stats available._"

        lines = [
            "## Agent Performance\n",
            "| Agent | Model | Tasks | Success Rate | Tokens | Findings |",
            "|-------|-------|-------|-------------|--------|----------|",
        ]
        for s in self.agent_stats:
            lines.append(
                f"| {s.get('name', '?')} "
                f"| {s.get('model', '?')} "
                f"| {s.get('tasks_executed', 0)} "
                f"| {s.get('success_rate', 0):.0%} "
                f"| {s.get('total_tokens', 0):,} "
                f"| {s.get('findings_count', 0)} |"
            )

        total_tokens = sum(s.get("total_tokens", 0) for s in self.agent_stats)
        total_cost = sum(s.get("total_cost_usd", 0) for s in self.agent_stats)
        lines.append("")
        lines.append(f"**Total tokens:** {total_tokens:,}  ")
        lines.append(f"**Estimated cost:** ${total_cost:.4f} (copilot-pro = $0.00 actual)")

        return "\n".join(lines)

    def _scan_metadata(self, stats: dict) -> str:
        duration = self.scan_duration_s
        mins = int(duration // 60)
        secs = int(duration % 60)

        lines = [
            "## Scan Metadata\n",
            "| Field | Value |",
            "|-------|-------|",
            f"| Duration | {mins}m {secs}s |",
            f"| Repository | `{self.repo_path}` |",
            "| Agents | 4 (copilot-pro) |",
            "| Models | claude-opus-4.6, gpt-5.4, gpt-5.3-codex, gemini-3.1-pro |",
            "| Token budget | 1,000,000 per agent |",
            f"| Total findings | {stats['unique']} unique + {stats['duplicates']} duplicates |",
        ]
        return "\n".join(lines)

    def _footer(self) -> str:
        return (
            "---\n\n"
            "*Report generated by FIRM Security Firm — firm-protocol v1.1.0*"
        )

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _risk_score(by_severity: dict[str, int]) -> int:
        """Compute a 0-100 risk score from severity counts."""
        weights = {"critical": 25, "high": 10, "medium": 3, "low": 1, "info": 0}
        raw = sum(by_severity.get(k, 0) * v for k, v in weights.items())
        # Cap at 100
        return min(100, raw)
