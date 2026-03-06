#!/usr/bin/env python3
"""
FIRM Protocol — MCP Security Scan on LangGraph + LangChain

Scans 6 sub-modules across both repositories:
  - LangGraph core, Checkpoint, CLI
  - LangChain Core, main, Partners

Prerequisites:
  1. MCP server running on port 8012
  2. Clone the repos:
       git clone --depth 1 https://github.com/langchain-ai/langgraph.git /tmp/langgraph
       git clone --depth 1 https://github.com/langchain-ai/langchain.git /tmp/langchain

Usage:
  python examples/langchain_security_scan.py

⚠️ AI-generated content — human validation required before use.
"""
import json
import sys
import time
from datetime import datetime, timezone

from firm.llm.mcp_bridge import check_mcp_server, create_mcp_toolkit
from firm.runtime import Firm


# ── Helpers ───────────────────────────────────────────────────────


def run_scan(target_path: str, label: str, kit):
    """Run firm_security_scan and return parsed results."""
    print(f"\n{'─' * 60}")
    print(f"  Scanning: {label}")
    print(f"  Path:     {target_path}")
    print(f"{'─' * 60}")
    t0 = time.time()
    result = kit.execute("firm_security_scan", {"target_path": target_path})
    elapsed = time.time() - t0
    if result.success:
        data = json.loads(result.output)
        print(f"  ✅ Completed in {elapsed:.1f}s")
        print(f"  📁 Files:    {data.get('total_files_scanned', '?')}")
        print(f"  🔴 CRITICAL: {data.get('critical_count', 0)}")
        print(f"  🟠 HIGH:     {data.get('high_count', 0)}")
        print(f"  🟡 MEDIUM:   {data.get('medium_count', 0)}")
        print(f"  🔵 LOW:      {data.get('low_count', 0)}")
        return data, elapsed
    else:
        print(f"  ❌ Failed: {result.error}")
        return {}, elapsed


def print_findings(data: dict, short_prefix: str = ""):
    """Print grouped findings."""
    vulns = data.get("vulnerabilities", [])
    if not vulns:
        print("  No findings.")
        return
    by_sev = {}
    for v in vulns:
        by_sev.setdefault(v.get("severity", "UNKNOWN"), []).append(v)
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
        items = by_sev.get(sev, [])
        if items:
            print(f"\n  [{sev}] — {len(items)} finding(s)")
            for v in items[:8]:
                fp = v.get("file", "?")
                if short_prefix and short_prefix in fp:
                    fp = fp.split(short_prefix, 1)[-1]
                ln = v.get("line", "?")
                pat = v.get("pattern", v.get("description", "N/A"))
                print(f"    • {fp}:{ln} — {pat}")
            if len(items) > 8:
                print(f"    ... and {len(items) - 8} more {sev} findings")


def build_report(scan_data, elapsed, repo_url, target_path, label):
    """Build structured JSON report."""
    vulns = scan_data.get("vulnerabilities", [])
    return {
        "title": f"Security Audit Report — {label}",
        "repository": repo_url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": "Automated MCP scan (OWASP-aligned) via FIRM Protocol",
        "target": target_path,
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


def report_to_markdown(r: dict) -> str:
    """Convert JSON report to Markdown."""
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
        by_sev.setdefault(v.get("severity", "UNKNOWN"), []).append(v)
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
        items = by_sev.get(sev, [])
        if items:
            lines.append(f"### {sev} ({len(items)})")
            lines.append("")
            for v in items:
                fp = v.get("file", "?")
                ln = v.get("line", "?")
                pat = v.get("pattern", v.get("description", "N/A"))
                lines.append(f"- **{fp}:{ln}** — {pat}")
            lines.append("")
    lines += ["## Recommendations", ""]
    for i, rec in enumerate(r.get("recommendations", []), 1):
        lines.append(f"{i}. {rec}")
    lines += [
        "",
        "---",
        "",
        "> ⚠️ AI-generated content — human validation required before use.",
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  TARGETS
# ══════════════════════════════════════════════════════════════════

TARGETS = [
    {
        "path": "/tmp/langgraph/libs/langgraph",
        "label": "LangGraph (core)",
        "url": "https://github.com/langchain-ai/langgraph",
        "short": "langgraph/",
    },
    {
        "path": "/tmp/langgraph/libs/checkpoint",
        "label": "LangGraph Checkpoint",
        "url": "https://github.com/langchain-ai/langgraph",
        "short": "checkpoint/",
    },
    {
        "path": "/tmp/langgraph/libs/cli",
        "label": "LangGraph CLI",
        "url": "https://github.com/langchain-ai/langgraph",
        "short": "cli/",
    },
    {
        "path": "/tmp/langchain/libs/core",
        "label": "LangChain Core",
        "url": "https://github.com/langchain-ai/langchain",
        "short": "core/",
    },
    {
        "path": "/tmp/langchain/libs/langchain",
        "label": "LangChain (main)",
        "url": "https://github.com/langchain-ai/langchain",
        "short": "langchain/",
    },
    {
        "path": "/tmp/langchain/libs/partners",
        "label": "LangChain Partners",
        "url": "https://github.com/langchain-ai/langchain",
        "short": "partners/",
    },
]


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("  FIRM Protocol — MCP Security Scan")
    print("  Targets: LangGraph + LangChain")
    print("=" * 70)

    # Step 1: MCP check
    print("\n[1/5] Checking MCP server connectivity...")
    status = check_mcp_server()
    if not status["ok"]:
        print(f"  ❌ MCP unreachable: {status['error']}")
        sys.exit(1)
    print(f"  ✅ MCP active — {status['tool_count']} tools available")

    # Step 2: FIRM org
    print("\n[2/5] Creating FIRM organization...")
    firm = Firm("langchain-audit")
    auditor = firm.add_agent("SecurityAuditor", authority=0.9)
    print(
        f"  ✅ Organization 'langchain-audit' — agent authority {auditor.authority}"
    )

    # Step 3: Load toolkit
    print("\n[3/5] Loading security + compliance toolkit...")
    kit = create_mcp_toolkit(categories=["security", "compliance"])
    tools = kit.list_tools()
    print(f"  ✅ {len(tools)} tools loaded")

    # Step 4: Scan all targets
    print("\n[4/5] Running scans...")

    all_reports = []
    for t in TARGETS:
        data, elapsed = run_scan(t["path"], t["label"], kit)
        print_findings(data, t["short"])
        report = build_report(data, elapsed, t["url"], t["path"], t["label"])
        all_reports.append(report)

    # Step 5: Generate reports
    print(f"\n\n[5/5] Generating reports...")
    for t, report in zip(TARGETS, all_reports):
        slug = (
            t["label"].lower().replace(" ", "_").replace("(", "").replace(")", "")
        )
        json_path = f"/tmp/{slug}_security_report.json"
        md_path = f"/tmp/{slug}_security_report.md"
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        with open(md_path, "w") as f:
            f.write(report_to_markdown(report))
        print(f"  ✅ {t['label']:25s} → {json_path}")

    # Combined summary
    print("\n" + "=" * 70)
    print("  COMBINED RESULTS")
    print("=" * 70)
    fmt_h = f"\n  {'Target':<28} {'Files':>6}  {'CRIT':>5} {'HIGH':>5} {'MED':>5} {'LOW':>5}  {'Total':>6}  Verdict"
    fmt_sep = f"  {'─' * 28} {'─' * 6}  {'─' * 5} {'─' * 5} {'─' * 5} {'─' * 5}  {'─' * 6}  {'─' * 20}"
    print(fmt_h)
    print(fmt_sep)
    grand_files = 0
    grand_findings = 0
    for t, report in zip(TARGETS, all_reports):
        s = report["executive_summary"]
        grand_files += s["total_files_scanned"]
        grand_findings += s["total_findings"]
        v = "PASS" if s["critical"] == 0 else "FAIL"
        print(
            f"  {t['label']:<28} {s['total_files_scanned']:>6}  "
            f"{s['critical']:>5} {s['high']:>5} {s['medium']:>5} {s['low']:>5}  "
            f"{s['total_findings']:>6}  {v}"
        )
    print(f"  {'─' * 28} {'─' * 6}  {'─' * 5} {'─' * 5} {'─' * 5} {'─' * 5}  {'─' * 6}")
    print(
        f"  {'TOTAL':<28} {grand_files:>6}  "
        f"{sum(r['executive_summary']['critical'] for r in all_reports):>5} "
        f"{sum(r['executive_summary']['high'] for r in all_reports):>5} "
        f"{sum(r['executive_summary']['medium'] for r in all_reports):>5} "
        f"{sum(r['executive_summary']['low'] for r in all_reports):>5}  "
        f"{grand_findings:>6}"
    )
    print(f"\n  📁 {grand_files} files scanned across 6 targets")
    print(f"  🔍 {grand_findings} total findings")
    print("=" * 70)


if __name__ == "__main__":
    main()
