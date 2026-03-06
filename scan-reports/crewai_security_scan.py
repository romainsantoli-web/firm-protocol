#!/usr/bin/env python3
"""
User test: MCP security scan on crewAI (https://github.com/crewAIInc/crewAI)

Uses the FIRM Protocol MCP bridge to run a real security audit
on the crewAI open-source repository.
"""
import json
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, "/Users/romain/analyse/firm-protocol")

# ── Step 1: Check MCP server ─────────────────────────────────────
print("=" * 70)
print("  FIRM Protocol — MCP Security Scan on crewAI")
print("  Target: https://github.com/crewAIInc/crewAI.git")
print("=" * 70)
print()

from firm.llm.mcp_bridge import check_mcp_server, create_mcp_toolkit

print("[1/6] Checking MCP server connectivity...")
status = check_mcp_server()
if not status["ok"]:
    print(f"  ❌ MCP server unreachable: {status['error']}")
    sys.exit(1)
print(f"  ✅ MCP active — {status['tool_count']} tools available")
print()

# ── Step 2: Create FIRM organization ─────────────────────────────
from firm.runtime import Firm
from firm.llm.agent import create_llm_agent

print("[2/6] Creating FIRM organization for the scan...")
firm = Firm("crewai-audit")
cto = firm.add_agent("SecurityAuditor", authority=0.9)
print(f"  ✅ Organization 'crewai-audit' created")
print(f"  ✅ Agent 'SecurityAuditor' (authority: {cto.authority})")
print()

# ── Step 3: Load security toolkit ────────────────────────────────
print("[3/6] Loading MCP security + compliance toolkit...")
sec_kit = create_mcp_toolkit(categories=["security", "compliance"])
tools = sec_kit.list_tools()
print(f"  ✅ {len(tools)} security tools loaded")
for t in tools[:5]:
    print(f"     • {t.name}")
if len(tools) > 5:
    print(f"     ... and {len(tools) - 5} more")
print()

# ── Step 4: Run security scan on crewAI ─────────────────────────
TARGET = "/tmp/crewAI/lib/crewai/src/crewai"
print(f"[4/6] Running firm_security_scan on {TARGET} ...")
t0 = time.time()
scan_result = sec_kit.execute("firm_security_scan", {"target_path": TARGET})
elapsed = time.time() - t0

if scan_result.success:
    scan_data = json.loads(scan_result.output)
    print(f"  ✅ Scan completed in {elapsed:.1f}s")
    print(f"  📁 Files scanned: {scan_data.get('total_files_scanned', '?')}")
    print(f"  🔴 CRITICAL: {scan_data.get('critical_count', 0)}")
    print(f"  🟠 HIGH:     {scan_data.get('high_count', 0)}")
    print(f"  🟡 MEDIUM:   {scan_data.get('medium_count', 0)}")
    print(f"  🔵 LOW:      {scan_data.get('low_count', 0)}")
else:
    print(f"  ❌ Scan failed: {scan_result.error}")
    scan_data = {}
print()

# ── Step 5: Show detailed findings ───────────────────────────────
print("[5/6] Detailed findings:")
vulns = scan_data.get("vulnerabilities", [])
if not vulns:
    print("  No vulnerabilities found (or scan returned no details)")
else:
    # Group by severity
    by_sev = {}
    for v in vulns:
        sev = v.get("severity", "UNKNOWN")
        by_sev.setdefault(sev, []).append(v)

    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
        items = by_sev.get(sev, [])
        if items:
            print(f"\n  [{sev}] — {len(items)} finding(s)")
            for v in items[:10]:  # show max 10 per severity
                fpath = v.get("file", "?")
                # shorten path
                if "/crewai/" in fpath:
                    fpath = fpath.split("/crewai/", 1)[-1]
                line = v.get("line", "?")
                pattern = v.get("pattern", v.get("description", "N/A"))
                print(f"    • {fpath}:{line} — {pattern}")
            if len(items) > 10:
                print(f"    ... and {len(items) - 10} more {sev} findings")
print()

# ── Step 6: Build structured report ─────────────────────────────
print("[6/6] Generating structured report...")
report = {
    "title": "Security Audit Report — crewAI",
    "repository": "https://github.com/crewAIInc/crewAI",
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "methodology": "Automated MCP scan (OWASP-aligned) via FIRM Protocol",
    "target": TARGET,
    "scan_duration_seconds": round(elapsed, 1),
    "executive_summary": {
        "total_files_scanned": scan_data.get("total_files_scanned", 0),
        "critical": scan_data.get("critical_count", 0),
        "high": scan_data.get("high_count", 0),
        "medium": scan_data.get("medium_count", 0),
        "low": scan_data.get("low_count", 0),
        "total_findings": len(vulns),
        "verdict": (
            "✅ PASS — no critical vulnerabilities"
            if scan_data.get("critical_count", 0) == 0
            else "❌ FAIL — critical vulnerabilities detected"
        ),
    },
    "findings": vulns,
    "recommendations": [
        "Review all HIGH findings within 48h",
        "Apply parameterized queries where SQL patterns are flagged",
        "Sanitize user inputs in all agent/tool interfaces",
        "Review hardcoded credentials or API key patterns",
        "Enable security linting in CI pipeline",
    ],
}

report_path = "/tmp/crewai_security_report.json"
with open(report_path, "w") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
print(f"  ✅ Full report saved to {report_path}")

# Also generate Markdown
def report_to_markdown(r: dict) -> str:
    s = r["executive_summary"]
    lines = [
        f"# {r['title']}",
        "",
        f"> **Repository:** {r['repository']}",
        f"> **Generated:** {r['generated_at']}",
        f"> **Methodology:** {r['methodology']}",
        f"> **Scan duration:** {r['scan_duration_seconds']}s",
        "",
        "## Executive Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Files scanned | **{s['total_files_scanned']}** |",
        f"| Critical | **{s['critical']}** |",
        f"| High | **{s['high']}** |",
        f"| Medium | **{s['medium']}** |",
        f"| Low | **{s['low']}** |",
        f"| Total findings | **{s['total_findings']}** |",
        f"| Verdict | {s['verdict']} |",
        "",
        "## Findings",
        "",
    ]
    by_sev = {}
    for v in r.get("findings", []):
        sev = v.get("severity", "UNKNOWN")
        by_sev.setdefault(sev, []).append(v)
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
        items = by_sev.get(sev, [])
        if items:
            lines.append(f"### {sev} ({len(items)})")
            lines.append("")
            for v in items:
                fp = v.get("file", "?")
                if "/crewai/" in fp:
                    fp = fp.split("/crewai/src/crewai/", 1)[-1] if "/src/crewai/" in fp else fp
                ln = v.get("line", "?")
                pat = v.get("pattern", v.get("description", "N/A"))
                lines.append(f"- **{fp}:{ln}** — {pat}")
            lines.append("")
    lines += [
        "## Recommendations",
        "",
    ]
    for i, rec in enumerate(r.get("recommendations", []), 1):
        lines.append(f"{i}. {rec}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("> ⚠️ AI-generated content — human validation required before use.")
    return "\n".join(lines)

md = report_to_markdown(report)
md_path = "/tmp/crewai_security_report.md"
with open(md_path, "w") as f:
    f.write(md)
print(f"  ✅ Markdown report saved to {md_path}")

print()
print("=" * 70)
summary = report["executive_summary"]
print(f"  SCAN COMPLETE — {summary['total_files_scanned']} files, "
      f"{summary['total_findings']} findings")
print(f"  Verdict: {summary['verdict']}")
print("=" * 70)
