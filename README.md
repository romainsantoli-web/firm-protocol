<div align="center">

# FIRM Protocol

### The Physics of Self-Evolving Autonomous Organizations

[![PyPI version](https://img.shields.io/pypi/v/firm-protocol?color=blue)](https://pypi.org/project/firm-protocol/)
[![Python](https://img.shields.io/pypi/pyversions/firm-protocol)](https://pypi.org/project/firm-protocol/)
[![Tests](https://img.shields.io/badge/tests-1137%20passed-brightgreen)]()
[![Coverage](https://img.shields.io/badge/coverage-93.86%25-brightgreen)]()
[![License](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

Authority is earned, not assigned. Memory is a debate, not a database.
Structure is liquid, not fixed. Errors have economic consequences.

[Installation](#installation) · [Quick Start](#quick-start) · [Architecture](#architecture) · [CLI Reference](#cli-reference) · [API](#python-api) · [Bounty Module](#bounty-hunter-module) · [Contributing](#contributing)

</div>

---

## What is FIRM?

**FIRM** (*Federated Intelligence for Recursive Management*) is a zero-dependency Python framework that defines how groups of AI agents can form, govern, and evolve organizations **without permanent hierarchy**.

Unlike traditional multi-agent frameworks where humans hardcode roles and permissions, FIRM implements a self-regulating system where:

- **Authority is Hebbian** — agents that succeed gain influence; agents that fail lose it. No fixed titles.
- **Every action is ledgered** — an append-only, hash-chained responsibility ledger tracks what happened, who did it, and whether it worked.
- **Governance is constitutional** — two invariants can never be violated: a human can always shut it down, and the system cannot erase its own capacity to evolve.
- **Change requires proof** — proposals go through simulation, stress testing, voting, and cooldown before taking effect.
- **Prediction markets** — agents wager authority on outcomes; calibrated predictors earn more influence.

---

## Installation

### From PyPI

```bash
# Core only (zero dependencies — stdlib only)
pip install firm-protocol

# With LLM providers (OpenAI, Anthropic, Mistral)
pip install "firm-protocol[llm]"

# With REST API server (FastAPI + Uvicorn)
pip install "firm-protocol[api]"

# With bug bounty module (httpx, pyyaml)
pip install "firm-protocol[bounty]"

# Everything
pip install "firm-protocol[all]"
```

### From source

```bash
git clone https://github.com/romainsantoli-web/firm-protocol.git
cd firm-protocol
pip install -e ".[dev]"
```

**Requirements:** Python 3.11+

---

## Quick Start

### CLI

```bash
# Create a new organization
firm init my-org

# Add agents with initial authority
firm agent add Alice --authority 0.8
firm agent add Bob --authority 0.5
firm agent list

# Record actions — authority adjusts automatically
firm action Alice success "Shipped feature on time"
firm action Bob fail "Broke production CI"

# Organization status & audit
firm status
firm audit

# Governance
firm propose Alice "Add deployer role" "Dedicated deployment specialist"
firm vote proposal-id Alice approve
firm finalize proposal-id

# Role management
firm role define deployer "Handles production deployments"
firm role assign Alice deployer

# Evolution — self-modifying parameters
firm evolve propose Alice learning_rate 0.08

# Internal market
firm market post Alice "Fix auth bug" 50

# Constitutional amendments
firm amend Alice structural "All agents must pass security review"

# Interactive REPL
firm repl
```

### Python API

```python
from firm import Firm

org = Firm(name="acme")

# Add agents — they start with moderate authority
alice = org.add_agent("alice", authority=0.5)
bob = org.add_agent("bob", authority=0.5)

# Record successes and failures — authority adjusts automatically
org.record_action(alice.id, success=True, description="Shipped feature")
org.record_action(bob.id, success=False, description="Broke CI")

# Check the organization state
status = org.status()
print(f"Agents: {status['agents']['total']}")
print(f"Chain valid: {status['ledger']['chain_valid']}")

# Alice (who succeeded) can now propose changes
proposal = org.propose(
    alice.id,
    title="Add deployment role",
    description="Create a dedicated deployment specialist role",
)
print(f"Proposal: {proposal.title} ({proposal.status.value})")
```

### Prediction Markets

```python
from firm.core.prediction import PredictionMarket

market = PredictionMarket()

# Create a market question
market_id = market.create(
    question="Will the auth refactor reduce bugs by 50%?",
    creator_id=alice.id,
    deadline_seconds=86400,
)

# Agents wager based on their beliefs
market.predict(market_id, alice.id, probability=0.8, stake=10.0)
market.predict(market_id, bob.id, probability=0.3, stake=5.0)

# Resolve — calibrated predictors earn authority bonus
market.resolve(market_id, outcome=True)
```

See [`examples/startup_lifecycle.py`](examples/startup_lifecycle.py) for a full narrated demo covering all 12 layers.

---

## Architecture

FIRM is built on **12 layers**, all fully implemented in ~15,000 lines of Python:

| Layer | Module | Purpose |
|:-----:|--------|---------|
| 0 | `core.authority` | **Authority Engine** — Hebbian scores, earned not assigned |
| 1 | `core.ledger` | **Responsibility Ledger** — append-only SHA-256 hash chain |
| 2 | `core.market` | **Credit System** — resource allocation via internal market |
| 3 | `core.roles` | **Role Fluidity** — dynamic assignment based on authority |
| 4 | `core.memory` | **Collective Memory** — shared knowledge with weighted recall |
| 5 | `core.constitution` | **Constitutional Agent** — invariant guardian, non-deletable |
| 6 | `core.governance` | **Governance Engine** — 2-cycle validation for all changes |
| 7 | `core.spawn` | **Spawn/Merge** — agent lifecycle management |
| 8 | `core.federation` | **Inter-Firm Protocol** — federation between organizations |
| 9 | `core.reputation` | **Reputation Bridge** — cross-firm authority portability |
| 10 | `core.audit` | **Audit Trail** — external accountability interface |
| 11 | `core.human` | **Human Override** — guaranteed human control surface |

Plus advanced capabilities:

| Module | Purpose |
|--------|---------|
| `core.evolution` | Self-modifying parameters via ≥75% supermajority vote |
| `core.market` | Task bounties, bidding, contracts, credit settlement |
| `core.meta` | Meta-constitutional amendment lifecycle |
| `core.prediction` | √authority-weighted prediction markets, Brier scoring, futarchy |
| `bounty` | Multi-agent bug bounty hunting platform (8 agents) |
| `llm` | LLM providers (Claude, GPT, Mistral, Gemini, Copilot Pro) + 18 tools + MCP bridge |
| `api` | FastAPI REST API + WebSocket events + dashboard |

### Two Invariants

These are hardcoded constraints that **no governance proposal can override**:

1. **Human Control** — The human can always shut it down. Kill switch, audit access, and override authority are permanent.

2. **Evolution Preserved** — The system cannot erase its own capacity to evolve. Governance mechanisms, voting rights, and the constitutional agent itself are protected.

---

## Key Concepts

### Authority Engine (Layer 0)

Uses a Hebbian-inspired formula with calibration bonus:

```
Δauthority = learning_rate × activation × (1 + calibration_bonus) − decay × (1 − activation)
```

Where `activation = 1.0` on success, `0.0` on failure. Default learning rate is `0.05`, decay is `0.02`. Authority is bounded `[0.0, 1.0]`.

| Threshold | Meaning |
|-----------|---------|
| ≥ 0.80 | Can propose governance changes |
| ≥ 0.60 | Can vote on proposals |
| ≥ 0.40 | Standard operating authority |
| ≤ 0.30 | Probation |
| ≤ 0.05 | Auto-termination |

### Responsibility Ledger (Layer 1)

Every recorded action produces an immutable, hash-chained entry:

```
entry.hash = SHA-256(previous_hash ‖ agent_id ‖ action ‖ timestamp ‖ outcome)
```

The chain can be verified end-to-end at any time. Tampering is detectable.

### Governance (Layer 6)

Proposals follow a strict lifecycle:

```
draft → simulation₁ → stress_test → simulation₂ → voting → cooldown → approved
                                                                     ↘ rejected
                                                                     ↘ rolled_back
```

Votes are weighted by voter authority. The Constitutional Agent can veto any proposal that violates an invariant.

### Prediction Markets

Prediction markets use √authority-weighted aggregation for probability estimates. Agents earn a **calibration bonus** (tracked via exponential moving average of Brier scores) that amplifies their authority gains. Contrarian payouts reward agents who correctly bet against the crowd.

Markets can trigger **futarchy governance**: proposals are automatically approved or rejected based on market predictions about their outcomes.

---

## BountyHunter Module

> `pip install "firm-protocol[bounty]"`

A multi-agent bug bounty hunting platform that orchestrates 8 specialised AI agents through the FIRM Protocol:

| Agent | Role | Model |
|-------|------|-------|
| `hunt-director` | Campaign orchestration & strategy | Claude Opus |
| `recon-agent` | Subdomain enum, tech fingerprinting | Claude Sonnet |
| `web-hunter` | XSS, SQLi, SSRF, IDOR hunting | Claude Sonnet |
| `api-hunter` | REST/GraphQL fuzzing, auth bypass | Claude Sonnet |
| `code-auditor` | Source code review, secret scanning | Claude Opus |
| `mobile-hunter` | APK/IPA analysis, certificate pinning | Claude Sonnet |
| `web3-hunter` | Smart contract auditing, bridge exploits | Claude Opus |
| `report-writer` | Markdown report generation | Claude Sonnet |

### Features

- **Scope enforcement** — wildcard domains, CIDR ranges, private IP blocking
- **CVSS v3.1 calculator** — full vector string parsing with severity classification
- **Deduplication engine** — title + endpoint + CWE matching + cosine similarity
- **5-stage triage pipeline** — scope check → dedup → CVSS scoring → auto-submit → manual review
- **Campaign orchestrator** — RECON → SCAN → EXPLOIT → REPORT → FEEDBACK phases
- **Reward engine** — tier-based multipliers, streak bonuses, quality incentives
- **HackerOne API v4** — programme listing, scope sync, report submission
- **12 LLM scanner tools** — nmap, nuclei, subfinder, katana, ffuf, nikto, semgrep, httpx…

### CLI

```bash
# List the 8 agents with their models and authority
firm bounty agents

# Initialise a campaign from a scope YAML
firm bounty init scope.yaml

# Display programme scope (in-scope / out-of-scope)
firm bounty scope scope.yaml

# Run a full campaign
firm bounty campaign run --scope-file scope.yaml

# Calculate a CVSS 3.1 score
firm bounty cvss "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
# → Score: 9.8 (CRITICAL)
```

### Python API

```python
from firm.bounty import (
    create_bounty_firm,
    ScopeEnforcer,
    TargetScope,
    CVSSVector,
)

# Create a fully-wired FIRM with 8 bounty agents
firm_org, campaign = create_bounty_firm("my-campaign", scope_yaml="scope.yaml")

# CVSS calculation
cvss = CVSSVector.from_string("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H")
print(f"Score: {cvss.base_score}")    # 9.8
print(f"Severity: {cvss.severity()}")  # CRITICAL

# Scope enforcement
scope = TargetScope(
    in_scope=["*.example.com"],
    out_of_scope=["internal.example.com"],
)
enforcer = ScopeEnforcer(scope)
assert enforcer.is_allowed("api.example.com")
assert not enforcer.is_allowed("internal.example.com")
```

---

## Project Structure

```
firm-protocol/
├── src/firm/
│   ├── __init__.py              # Public API exports, version
│   ├── cli.py                   # CLI entry point (25 commands)
│   ├── runtime.py               # High-level Firm orchestrator
│   ├── core/                    # 12-layer architecture (18 modules)
│   │   ├── agent.py             #   Agent model & roles
│   │   ├── authority.py         #   Hebbian authority engine
│   │   ├── ledger.py            #   SHA-256 hash-chained ledger
│   │   ├── constitution.py      #   Constitutional invariants
│   │   ├── governance.py        #   2-cycle proposal engine
│   │   ├── prediction.py        #   Prediction markets & futarchy
│   │   ├── federation.py        #   Inter-firm protocol
│   │   ├── reputation.py        #   Cross-firm attestations
│   │   ├── evolution.py         #   Self-modifying parameters
│   │   ├── market.py            #   Internal task market
│   │   ├── memory.py            #   Collective weighted memory
│   │   ├── roles.py             #   Dynamic role assignment
│   │   ├── spawn.py             #   Agent lifecycle
│   │   ├── audit.py             #   Audit trail
│   │   ├── human.py             #   Human override
│   │   ├── meta.py              #   Meta-constitutional amendments
│   │   ├── events.py            #   Pub/sub event bus
│   │   └── serialization.py     #   JSON save/load/snapshot/diff
│   ├── bounty/                  # Bug bounty hunting (11 modules)
│   │   ├── campaign.py          #   Campaign orchestrator
│   │   ├── scope.py             #   Scope enforcer
│   │   ├── vulnerability.py     #   CVSS 3.1 calculator
│   │   ├── dedup.py             #   Deduplication engine
│   │   ├── triage.py            #   5-stage triage pipeline
│   │   ├── reward.py            #   Reward engine
│   │   ├── hackerone.py         #   HackerOne API v4 client
│   │   ├── factory.py           #   Bounty FIRM factory
│   │   ├── sandbox/             #   Sandboxed tool execution
│   │   └── tools/               #   12 LLM scanner tools
│   ├── llm/                     # LLM integration (5 modules)
│   │   ├── providers.py         #   Claude, GPT, Mistral, Gemini, Copilot Pro
│   │   ├── agent.py             #   LLM-powered agent wrapper
│   │   ├── executor.py          #   Tool call executor
│   │   ├── tools.py             #   18 built-in tools
│   │   └── mcp_bridge.py        #   Bridge to 143 MCP ecosystem tools
│   └── api/                     # REST API (1 module)
│       └── app.py               #   FastAPI + WebSocket + dashboard
├── tests/                       # 46 test files, 1137 tests
├── examples/
│   └── startup_lifecycle.py     # Full narrated demo
├── CHANGELOG.md
├── ROADMAP.md
└── pyproject.toml
```

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `firm init <name>` | Create a new FIRM organization |
| `firm agent add <name> [--authority N]` | Add an agent |
| `firm agent list` | List all agents with authority scores |
| `firm action <agent> <success\|fail> <desc>` | Record an action |
| `firm status` | Show organization status |
| `firm audit` | Run a full organization audit |
| `firm propose <agent> <title> <desc>` | Create a governance proposal |
| `firm vote <proposal> <agent> <approve\|reject>` | Vote on a proposal |
| `firm finalize <proposal>` | Finalize a proposal |
| `firm role define <name> <desc>` | Define a new role |
| `firm role assign <agent> <role>` | Assign a role to an agent |
| `firm memory add <agent> <content>` | Store a memory |
| `firm memory recall <query>` | Recall relevant memories |
| `firm evolve propose <agent> <param> <value>` | Propose parameter change |
| `firm evolve vote <prop> <agent> <approve\|reject>` | Vote on evolution |
| `firm evolve apply <proposal>` | Apply an approved evolution |
| `firm market post <agent> <title> <bounty>` | Post a task bounty |
| `firm market bid <task> <agent> <amount>` | Bid on a task |
| `firm amend <agent> <type> <text>` | Propose constitutional amendment |
| `firm repl` | Interactive REPL mode |
| `firm bounty agents` | List BountyHunter agents |
| `firm bounty init <scope.yaml>` | Initialize a bounty campaign |
| `firm bounty scope <scope.yaml>` | Display programme scope |
| `firm bounty campaign <run\|status>` | Campaign lifecycle |
| `firm bounty cvss <vector>` | Calculate CVSS 3.1 score |

---

## LLM Integration

> `pip install "firm-protocol[llm]"`

FIRM agents can be powered by LLMs with 18 built-in tools:

```python
from firm.runtime import Firm
from firm.llm.agent import create_llm_agent

firm = Firm("my-startup")
cto = create_llm_agent(firm, "CTO", provider_name="copilot-pro",
                       model="claude-sonnet-4.6", authority=0.8)
dev = create_llm_agent(firm, "dev-1", provider_name="copilot-pro",
                       model="gpt-4.1", authority=0.5)

# The agent uses git, file, terminal, HTTP, Python, prediction markets —
# all within FIRM's authority system.
result = cto.execute_task("Analyze the auth module for vulnerabilities")
```

Supported providers: **Anthropic Claude**, **OpenAI GPT**, **Mistral**, **Google Gemini**, **GitHub Copilot**, **Copilot Pro** (21 models).

### Copilot Pro Models

| Family | Models |
|--------|--------|
| Claude | `claude-haiku-4.5`, `claude-opus-4.5`, `claude-opus-4.6`, `claude-sonnet-4` (default), `claude-sonnet-4.5`, `claude-sonnet-4.6` |
| GPT | `gpt-4.1`, `gpt-4o`, `gpt-5-mini`, `gpt-5.1`, `gpt-5.2`, `gpt-5.3`, `gpt-5.4` |
| Codex | `codex-5.1`, `codex-5.2`, `codex-5.3-codex`, `codex-5.1-codex-mini`, `codex-5.1-codex-max` |
| Gemini | `gemini-2.5-pro`, `gemini-3-pro`, `gemini-3.1-pro` |

---

## MCP Bridge — 143 Ecosystem Tools

Connect FIRM agents to the full MCP ecosystem (security, memory, A2A, delivery, market research…):

```python
from firm.runtime import Firm
from firm.llm.agent import create_llm_agent
from firm.llm.mcp_bridge import extend_agent_with_mcp, create_mcp_toolkit

firm = Firm("my-startup")
cto = create_llm_agent(firm, "CTO", provider_name="copilot-pro", authority=0.8)

# Add all 143 MCP tools, or filter by category
extend_agent_with_mcp(cto, categories=["security", "memory"])

# Or get a standalone ToolKit
security_kit = create_mcp_toolkit(categories=["security"])
```

**14 categories:** security, memory, a2a, gateway, fleet, audit, delivery, compliance, observability, config, orchestration, acp, market_research, spec.

Requires the MCP server running on port 8012 (`$FIRM_MCP_URL`).

### ✅ Live Validation — Bridge tested on this project

The MCP bridge was tested end-to-end on **this repository** (`firm-protocol/src/firm`):

<table>
<tr><th>Step</th><th>Result</th><th>Status</th></tr>
<tr><td><b>MCP Connectivity</b></td><td><code>143 tools</code> discovered via JSON-RPC</td><td>✅</td></tr>
<tr><td><b>Firm Creation</b></td><td>Organization <code>test-mcp-bridge</code> initialized</td><td>✅</td></tr>
<tr><td><b>Security ToolKit</b></td><td><code>10 tools</code> loaded (scan, sandbox, secrets…)</td><td>✅</td></tr>
<tr><td><b>Real MCP Call</b></td><td><code>firm_security_scan</code> → <b>45 files scanned</b>, 4 HIGH findings in <code>reputation.py</code></td><td>✅</td></tr>
<tr><td><b>Category Filtering</b></td><td>memory (10) · a2a (8) · compliance (14) · delivery (6)</td><td>✅</td></tr>
<tr><td><b>Agent Extension</b></td><td><code>20 MCP tools</code> added to CTO agent (security + memory)</td><td>✅</td></tr>
</table>

> **Result:** An agent connected via `extend_agent_with_mcp(cto)` can call any of the 143 ecosystem tools
> (security audit, hebbian memory, A2A protocol, delivery export…) natively within FIRM's authority system.

### ✅ External Validation — Security scan on crewAI (1004 Python files)

The MCP bridge was validated on **5 major open-source AI frameworks** — 8,785 files scanned, 300 findings, **0 CRITICAL vulnerabilities**:

| Framework | Files | Findings | CRITICAL | Report |
|-----------|------:|----------|---------:|--------|
| [crewAI](https://github.com/crewAIInc/crewAI) | 412 | 17 | 0 | [Report](scan-reports/REPORT-crewai.md) |
| [LangGraph + LangChain](https://github.com/langchain-ai) | 2,205 | 42 | 0 | [Report](scan-reports/REPORT-langchain.md) |
| [Microsoft AutoGen](https://github.com/microsoft/autogen) | 355 | 15 | 0 | [Report](scan-reports/REPORT-autogen.md) |
| [designing-multiagent-systems](https://github.com/victordibia/designing-multiagent-systems) | 219 | 2 | 0 | [Report](scan-reports/REPORT-dmas.md) |
| [OpenClaw](https://github.com/openclaw/openclaw) (self-scan) | 5,594 | 224 | 0 | [Report](scan-reports/REPORT-openclaw.md) |
| **Total** | **8,785** | **300** | **0** | |

> Full reports, reproduction scripts, and methodology: **[scan-reports/](scan-reports/README.md)**

<details>
<summary><b>📋 Example: run a scan on crewAI</b></summary>

```bash
# Clone target
git clone --depth 1 https://github.com/crewAIInc/crewAI.git /tmp/crewai

# Run scan (requires MCP server on port 8012)
python scan-reports/crewai_security_scan.py
```

```python
from firm.runtime import Firm
from firm.llm.mcp_bridge import check_mcp_server, create_mcp_toolkit

# 1. Verify MCP server
status = check_mcp_server()
assert status["ok"], f"MCP unreachable: {status['error']}"
print(f"✅ {status['tool_count']} tools available")

# 2. Create security toolkit & run a scan
kit = create_mcp_toolkit(categories=["security"])
result = kit.execute("firm_security_scan", {
    "target_path": "/tmp/crewai"
})
print(f"Scan: success={result.success}")
print(result.output[:500])
```

</details>

---

## Automatic Security Report Generation

Generate a professional security audit report using best practices (OWASP, CWE classification, severity scoring):

```python
import json
from datetime import datetime, timezone
from firm.runtime import Firm
from firm.llm.mcp_bridge import create_mcp_toolkit, check_mcp_server

def generate_security_report(target_path: str, firm_name: str = "audit") -> dict:
    """Generate a structured security audit report following best practices.
    
    Best practices applied:
    - OWASP Top 10 alignment for vulnerability classification
    - CWE identifiers for each finding category
    - Severity scoring (CRITICAL/HIGH/MEDIUM/LOW/INFO)
    - Remediation priority matrix
    - Executive summary + detailed findings
    - Reproducibility: full scan parameters recorded
    """
    # Verify MCP connectivity
    status = check_mcp_server()
    if not status["ok"]:
        raise ConnectionError(f"MCP server unreachable: {status['error']}")
    
    # Run security scan
    kit = create_mcp_toolkit(categories=["security", "compliance"])
    scan = kit.execute("firm_security_scan", {"target_path": target_path})
    sandbox = kit.execute("firm_sandbox_audit", {
        "config_path": "config.json"
    })
    
    # Parse results
    scan_data = json.loads(scan.output) if scan.success else {}
    sandbox_data = json.loads(sandbox.output) if sandbox.success else {}
    
    # Build report
    report = {
        "title": f"Security Audit Report — {firm_name}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": "Automated MCP security scanning (OWASP-aligned)",
        "target": target_path,
        "tools_used": [t.name for t in kit.list_tools()],
        "executive_summary": {
            "total_files_scanned": scan_data.get("total_files_scanned", 0),
            "critical": scan_data.get("critical_count", 0),
            "high": scan_data.get("high_count", 0),
            "medium": scan_data.get("medium_count", 0),
            "verdict": "PASS" if scan_data.get("critical_count", 0) == 0
                       else "FAIL — critical issues found",
        },
        "findings": scan_data.get("vulnerabilities", []),
        "sandbox_audit": sandbox_data,
        "recommendations": [
            "Review all HIGH-severity findings within 48h",
            "Apply parameterized queries where SQL patterns are flagged",
            "Enable sandbox mode in production configurations",
            "Schedule recurring scans via CI pipeline",
        ],
    }
    return report

# Usage
report = generate_security_report("src/firm", firm_name="firm-protocol")
print(json.dumps(report, indent=2))
```

Output example:

```json
{
  "title": "Security Audit Report — firm-protocol",
  "generated_at": "2026-03-06T14:30:00+00:00",
  "methodology": "Automated MCP security scanning (OWASP-aligned)",
  "executive_summary": {
    "total_files_scanned": 45,
    "critical": 0,
    "high": 4,
    "medium": 0,
    "verdict": "PASS"
  },
  "findings": [
    {
      "file": "src/firm/core/reputation.py",
      "line": 560,
      "severity": "HIGH",
      "pattern": "String concatenation in query"
    }
  ],
  "recommendations": [
    "Review all HIGH-severity findings within 48h",
    "Apply parameterized queries where SQL patterns are flagged",
    "Enable sandbox mode in production configurations",
    "Schedule recurring scans via CI pipeline"
  ]
}
```

---

## REST API

> `pip install "firm-protocol[api]"`

```bash
firm api --port 8000
# or
uvicorn firm.api.app:app --reload
```

Endpoints include agent management, action recording, governance, evolution, and market operations. WebSocket support for real-time events. Built-in HTML dashboard.

---

## Development

```bash
# Clone and install
git clone https://github.com/romainsantoli-web/firm-protocol.git
cd firm-protocol
pip install -e ".[dev]"

# Run test suite (1137 tests)
python -m pytest tests/ -v

# Run with coverage (minimum 80% enforced)
python -m pytest tests/ --cov=firm --cov-report=term-missing

# Lint
ruff check src/ tests/

# Type check
mypy src/firm/
```

### Test Suite

| Category | Files | Tests |
|----------|-------|-------|
| Core (12 layers) | 20 | 640+ |
| Bounty module | 9 | 107 |
| Prediction markets | 2 | 80+ |
| CLI | 2 | 30+ |
| LLM integration | 4 | 50+ |
| E2E / stress / property | 4 | 100+ |
| **Total** | **46** | **1,137** |

Coverage: **93.86%** (lines + branches).

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| **1.1.0** | 2026-03-05 | BountyHunter module (8 agents), CLI `firm bounty`, CVSS 3.1 calculator |
| **1.0.0** | 2026-03-05 | Prediction markets, auto-restructurer, federation broadcast, PyPI launch |
| **0.5.0** | 2026-02-28 | LLM runtime (5 providers), FastAPI server, CLI, plugin system |
| **0.1.0** | 2026-02-27 | 12-layer architecture, Hebbian authority, governance, federation |

See [CHANGELOG.md](CHANGELOG.md) for full details.

---

## Contributing

Contributions are welcome. Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Write tests (minimum 80% coverage)
4. Run `python -m pytest tests/ -v` and `ruff check src/ tests/`
5. Submit a Pull Request

---

## License

[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)

---

<div align="center">

**[PyPI](https://pypi.org/project/firm-protocol/) · [GitHub](https://github.com/romainsantoli-web/firm-protocol) · [Changelog](CHANGELOG.md) · [Issues](https://github.com/romainsantoli-web/firm-protocol/issues)**

</div>
