#!/usr/bin/env python3
"""
Security Firm deep scan on crewAI — 4 multi-model agents, 164 ecosystem tools.

This script runs the FIRM Security Firm (multi-agent pipeline) on a local clone
of crewAI. It uses 164 MCP tools (143 OpenClaw + 21 Memory OS AI) for a deep
vulnerability analysis with CWE classification.

Prerequisites:
    1. Clone crewAI:  git clone --depth 1 https://github.com/crewAIInc/crewAI.git /tmp/crewAI
    2. MCP servers running (OpenClaw port 8012, Memory OS AI port 8765)
    3. COPILOT_API_KEY or GITHUB_TOKEN env set (Copilot Pro routing)

Usage:
    python scan-reports/crewai_v4_deep_scan.py                    # default: /tmp/crewAI
    python scan-reports/crewai_v4_deep_scan.py /path/to/repo      # custom target

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""
import argparse
import logging
import os
import sys
import time

# Ensure firm-protocol/src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from firm.security_firm.factory import create_security_firm


def main():
    parser = argparse.ArgumentParser(
        description="Run a 4-agent deep security scan on a repository."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="/tmp/crewAI",
        help="Path to the repository to scan (default: /tmp/crewAI)",
    )
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help="Disable MCP ecosystem tools (run with base tools only)",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output path for the report (default: /tmp/security-report-<repo>.md)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging (INFO level)",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )

    use_mcp = not args.no_mcp
    repo_name = os.path.basename(os.path.normpath(args.target))
    out_path = args.output or f"/tmp/security-report-{repo_name}.md"

    # ── Create Security Firm ──────────────────────────────────────
    print("=" * 60)
    print(f"FIRM Security Firm — Deep Scan")
    print(f"  Target: {args.target}")
    print(f"  MCP:    {'164 tools (143 OpenClaw + 21 Memory OS AI)' if use_mcp else 'disabled'}")
    print("=" * 60)
    print()

    ctx = create_security_firm(args.target, use_mcp=use_mcp)
    pipeline = ctx["pipeline"]
    print(f"Firm: {ctx['firm'].name}, Agents: {len(ctx['agents'])}")

    for name, agent in pipeline.agents.items():
        tool_count = len(agent._toolkit.list_tools())
        print(f"  {name}: {tool_count} tools")

    # ── Run scan pipeline ─────────────────────────────────────────
    print()
    print("Launching scan pipeline ...")
    t0 = time.time()
    report_md = pipeline.run()
    duration = time.time() - t0

    # ── Save report ───────────────────────────────────────────────
    with open(out_path, "w") as f:
        f.write(report_md)

    stats = pipeline.stats
    findings = pipeline.findings

    print()
    print("=" * 60)
    print(f"Report saved to: {out_path}")
    print(f"Findings: {len(findings)}")
    print(f"Duration: {duration:.1f}s")
    if stats:
        print(f"Stats: {stats}")
    print("=" * 60)

    # Preview first 80 lines
    for line in report_md.splitlines()[:80]:
        print(line)


if __name__ == "__main__":
    main()
