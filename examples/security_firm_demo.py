#!/usr/bin/env python3
"""Security Firm demo — scan a repository with 4 AI agents.

Usage:
    python examples/security_firm_demo.py /path/to/repo
    python examples/security_firm_demo.py https://github.com/org/repo

The script will:
  1. Clone (if URL) or open the repo
  2. Spin up 4 agents: security-director, code-scanner, static-analyzer,
     report-synthesizer
  3. Scan in parallel (code review + static analysis + architecture mapping)
  4. Triage and deduplicate findings
  5. Generate a Markdown report → saved to security-report-{name}.md

Requirements:
  - Copilot Pro JWT (COPILOT_JWT env var or cached token)
  - MCP server at http://127.0.0.1:8012 (optional but recommended)

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# ── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("security-firm")


def main(repo_path: str) -> None:
    from firm.security_firm import create_security_firm

    print("=" * 70)
    print("  FIRM Security Firm — Multi-Agent Repository Scanner")
    print("=" * 70)
    print()
    print(f"  Target:  {repo_path}")
    print(f"  Agents:  4 (copilot-pro)")
    print(f"  Models:  claude-opus-4.6, gpt-5.4, gpt-5.3-codex, gemini-3.1-pro")
    print(f"  Budget:  1,000,000 tokens per agent")
    print()

    start = time.time()

    # Create and run the pipeline
    ctx = create_security_firm(
        repo_path=repo_path,
        use_mcp=True,
        max_workers=3,
    )

    pipeline = ctx["pipeline"]
    report = pipeline.run()

    elapsed = time.time() - start

    # Save report
    repo_name = Path(repo_path.rstrip("/")).name
    report_file = f"security-report-{repo_name}.md"
    Path(report_file).write_text(report)

    # Print summary
    stats = pipeline.stats
    print()
    print("=" * 70)
    print("  SCAN COMPLETE")
    print("=" * 70)
    print()
    print(f"  Duration:    {int(elapsed // 60)}m {int(elapsed % 60)}s")
    print(f"  Findings:    {stats['unique']} unique ({stats['duplicates']} duplicates filtered)")
    print(f"  Critical:    {stats['by_severity'].get('critical', 0)}")
    print(f"  High:        {stats['by_severity'].get('high', 0)}")
    print(f"  Medium:      {stats['by_severity'].get('medium', 0)}")
    print(f"  Low:         {stats['by_severity'].get('low', 0)}")
    print(f"  Info:        {stats['by_severity'].get('info', 0)}")
    print()
    print(f"  Report saved to: {report_file}")
    print()

    # Print agent stats
    for name, agent in pipeline.agents.items():
        s = agent.get_stats()
        print(f"  [{name}] model={s['model']} tokens={s['total_tokens']:,} "
              f"tasks={s['tasks_executed']} success={s['success_rate']:.0%}")

    print()
    print("⚠️ Contenu généré par IA — validation humaine requise avant utilisation.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python examples/security_firm_demo.py <repo_path_or_url>")
        print()
        print("Examples:")
        print("  python examples/security_firm_demo.py /tmp/my-project")
        print("  python examples/security_firm_demo.py https://github.com/org/repo")
        sys.exit(1)

    main(sys.argv[1])
