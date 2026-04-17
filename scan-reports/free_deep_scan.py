#!/usr/bin/env python3
"""
Security Firm FREE deep scan — 3 free models + 1 premium orchestrator.

Same pipeline as crewai_v4_deep_scan.py but uses free Copilot Pro models
with 6000-token chunked execution + Memory OS AI for cross-chunk context.

Models:
  - security-director:  gpt-5.4     (premium, unchunked)
  - code-scanner:       gpt-4.1     (free, 6000-token chunks)
  - static-analyzer:    gpt-4o      (free, 6000-token chunks)
  - report-synthesizer: gpt-5-mini  (free, 6000-token chunks)

Prerequisites:
    1. Clone target:  git clone --depth 1 <url> /tmp/<repo>
    2. MCP servers running (OpenClaw port 8012, Memory OS AI port 8765)
    3. COPILOT_API_KEY or GITHUB_TOKEN env set

Usage:
    python scan-reports/free_deep_scan.py /tmp/langchain
    python scan-reports/free_deep_scan.py /tmp/crewAI -v -o /tmp/report.md
    python scan-reports/free_deep_scan.py /tmp/autogen --chunks 20

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""
import argparse
import logging
import os
import sys
import time

# Ensure firm-protocol/src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from firm.security_firm.factory_free import create_free_security_firm


def main():
    parser = argparse.ArgumentParser(
        description="Run a 4-agent deep security scan using free-tier models."
    )
    parser.add_argument(
        "target",
        help="Path to the repository to scan",
    )
    parser.add_argument(
        "--no-mcp",
        action="store_true",
        help="Disable MCP ecosystem tools",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output path for the report (default: /tmp/security-report-<repo>-free.md)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging (INFO level)",
    )
    parser.add_argument(
        "--chunks",
        type=int,
        default=15,
        help="Max chunks per free agent (default: 15)",
    )
    parser.add_argument(
        "--chunk-budget",
        type=int,
        default=6000,
        help="Token budget per chunk (default: 6000)",
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
    out_path = args.output or f"/tmp/security-report-{repo_name}-free.md"

    # ── Banner ────────────────────────────────────────────────────
    print("=" * 60)
    print(f"FIRM Security Firm — FREE Deep Scan")
    print(f"  Target:      {args.target}")
    print(f"  Models:      gpt-5.4 (orchestrator) + gpt-4.1/gpt-4o/gpt-5-mini (free)")
    print(f"  Chunk:       {args.chunk_budget} tokens x {args.chunks} max chunks")
    print(f"  MCP:         {'164 tools' if use_mcp else 'disabled'}")
    print("=" * 60)
    print()

    # ── Create Free Security Firm ─────────────────────────────────
    ctx = create_free_security_firm(
        args.target,
        use_mcp=use_mcp,
        chunk_budget=args.chunk_budget,
        max_chunks=args.chunks,
    )
    pipeline = ctx["pipeline"]
    print(f"Firm: {ctx['firm'].name}, Agents: {len(ctx['agents'])}")

    for name, agent in pipeline.agents.items():
        tool_count = len(agent._toolkit.list_tools())
        tier = "premium" if name in pipeline._premium_agents else "FREE"
        print(f"  {name}: {tool_count} tools [{tier}] ({agent.provider.model})")

    # ── Run scan pipeline ─────────────────────────────────────────
    print()
    print("Launching chunked scan pipeline ...")
    t0 = time.time()
    report_md = pipeline.run()
    duration = time.time() - t0

    # ── Save report ───────────────────────────────────────────────
    with open(out_path, "w") as f:
        f.write(report_md)

    findings = pipeline.findings

    print()
    print("=" * 60)
    print(f"Report saved to: {out_path}")
    print(f"Findings: {len(findings)}")
    print(f"Duration: {duration:.1f}s")
    print("=" * 60)

    # Preview first 80 lines
    for line in report_md.splitlines()[:80]:
        print(line)


if __name__ == "__main__":
    main()
