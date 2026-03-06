#!/usr/bin/env python3
"""
FIRM Protocol — MCP Security Scan on designing-multiagent-systems

Repository: https://github.com/victordibia/designing-multiagent-systems
Author: Victor Dibia (Microsoft Research, AutoGen lead contributor)
Book/course companion repo for designing multi-agent AI systems.

Scans 4 sub-modules:
  - picoagents (lightweight agent library — core + tests + webui)
  - course (course samples: book_generator, deep_research, MCP, RAG, etc.)
  - examples (agents, evaluation, frameworks, orchestration, memory, tools)
  - research (analysis scripts and data)

Prerequisites:
  1. MCP server running on port 8012
  2. Clone the repo:
       git clone --depth 1 https://github.com/victordibia/designing-multiagent-systems.git /tmp/dmas

Usage:
  python examples/dmas_security_scan.py

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


# ══════════════════════════════════════════════════════════════════
#  TARGETS
# ══════════════════════════════════════════════════════════════════

REPO_URL = "https://github.com/victordibia/designing-multiagent-systems"

TARGETS = [
    {
        "path": "/tmp/dmas/picoagents",
        "label": "PicoAgents (lib)",
        "short": "picoagents/",
    },
    {
        "path": "/tmp/dmas/course",
        "label": "Course Samples",
        "short": "course/",
    },
    {
        "path": "/tmp/dmas/examples",
        "label": "Examples",
        "short": "examples/",
    },
    {
        "path": "/tmp/dmas/research",
        "label": "Research",
        "short": "research/",
    },
]


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════


def main():
    print("=" * 70)
    print("  FIRM Protocol — MCP Security Scan")
    print("  Target: designing-multiagent-systems (Victor Dibia)")
    print("=" * 70)

    # Step 1: MCP check
    print("\n[1/4] Checking MCP server connectivity...")
    status = check_mcp_server()
    if not status["ok"]:
        print(f"  ❌ MCP unreachable: {status['error']}")
        sys.exit(1)
    print(f"  ✅ MCP active — {status['tool_count']} tools available")

    # Step 2: FIRM org
    print("\n[2/4] Creating FIRM organization...")
    firm = Firm("dmas-audit")
    auditor = firm.add_agent("SecurityAuditor", authority=0.9)
    print(
        f"  ✅ Organization 'dmas-audit' — agent authority {auditor.authority}"
    )

    # Step 3: Load toolkit
    print("\n[3/4] Loading security + compliance toolkit...")
    kit = create_mcp_toolkit(categories=["security", "compliance"])
    tools = kit.list_tools()
    print(f"  ✅ {len(tools)} tools loaded")

    # Step 4: Scan all targets
    print("\n[4/4] Running scans...")
    all_results = []
    for t in TARGETS:
        data, elapsed = run_scan(t["path"], t["label"], kit)
        print_findings(data, t["short"])
        all_results.append((t, data, elapsed))

    # Combined summary
    print("\n" + "=" * 70)
    print("  COMBINED RESULTS — designing-multiagent-systems")
    print("=" * 70)
    fmt_h = (
        f"\n  {'Target':<22} {'Files':>6}  {'CRIT':>5} {'HIGH':>5}"
        f" {'MED':>5} {'LOW':>5}  {'Total':>6}  Verdict"
    )
    fmt_sep = (
        f"  {'─' * 22} {'─' * 6}  {'─' * 5} {'─' * 5}"
        f" {'─' * 5} {'─' * 5}  {'─' * 6}  {'─' * 20}"
    )
    print(fmt_h)
    print(fmt_sep)
    gf = gt = gc = gh = gm = gl = 0
    for t, data, _ in all_results:
        f = data.get("total_files_scanned", 0)
        c = data.get("critical_count", 0)
        h = data.get("high_count", 0)
        m = data.get("medium_count", 0)
        lo = data.get("low_count", 0)
        tot = len(data.get("vulnerabilities", []))
        v = "PASS" if c == 0 else "FAIL"
        gf += f
        gc += c
        gh += h
        gm += m
        gl += lo
        gt += tot
        print(
            f"  {t['label']:<22} {f:>6}  {c:>5} {h:>5} {m:>5} {lo:>5}  "
            f"{tot:>6}  {v}"
        )
    print(
        f"  {'─' * 22} {'─' * 6}  {'─' * 5} {'─' * 5}"
        f" {'─' * 5} {'─' * 5}  {'─' * 6}"
    )
    print(
        f"  {'TOTAL':<22} {gf:>6}  {gc:>5} {gh:>5} {gm:>5} {gl:>5}  {gt:>6}"
    )
    print(f"\n  📁 {gf} files scanned across {len(TARGETS)} targets")
    print(f"  🔍 {gt} total findings")
    print("=" * 70)


if __name__ == "__main__":
    main()
