# Security Scan Reports

> **8,785 files scanned across 5 major AI frameworks — 0 CRITICAL vulnerabilities found.**

This directory contains reproducible security scans performed with the [FIRM Protocol](../README.md) MCP Bridge on major open-source AI agent frameworks.

## Scan Methods

### 1. MCP Pattern Scan (v1)
Single-tool `firm_security_scan` at depth 5. Fast (~30s), regex-based pattern matching. Good first filter but high false-positive rate on string concatenation patterns.

### 2. Security Firm Deep Scan (v4)
4 multi-model LLM agents (claude-opus-4.6, gpt-5.4, gpt-5.3-codex, gemini-3.1-pro) with **164 ecosystem tools** (143 OpenClaw + 21 Memory OS AI). Finds real vulnerabilities with CWE classification, code snippets, impact analysis and remediation. ~7 min per repo.

## Combined Results

| Framework | Files | v1 Findings | v4 Deep | CRITICAL | Report (v1) | Report (v4) |
|-----------|------:|-------------|---------|----------|-------------|-------------|
| [crewAI](https://github.com/crewAIInc/crewAI) | 412 | 17 (13H/4M) | **13 (7H/6M)** | 0 | [v1](REPORT-crewai.md) / [scan.py](crewai_security_scan.py) | [**v4 deep**](REPORT-crewai-v4-deep.md) / [scan.py](crewai_v4_deep_scan.py) |
| [LangGraph + LangChain](https://github.com/langchain-ai) | 2,205 | 42 (33H/9M) | — | 0 | [v1](REPORT-langchain.md) | — |
| [Microsoft AutoGen](https://github.com/microsoft/autogen) | 355 | 15 (13H/2M) | — | 0 | [v1](REPORT-autogen.md) | — |
| [designing-multiagent-systems](https://github.com/victordibia/designing-multiagent-systems) | 219 | 2 (1H/1M) | — | 0 | [v1](REPORT-dmas.md) | — |
| [OpenClaw](https://github.com/openclaw/openclaw) (self-scan) | 5,594 | 224 (117H/107M) | — | 0 | [v1](REPORT-openclaw.md) | — |
| **Total** | **8,785** | **300** | **13** | **0** | | |

### crewAI: v1 vs v4 Comparison

| Aspect | v1 (MCP pattern scan) | v4 (Security Firm deep scan) |
|---|---|---|
| Findings | 17 (2 patterns) | 13 (10 CWE unique) |
| CWE coverage | 0 CWE | 8 CWE (78, 89, 94, 287, 502, 611, 79, 918) |
| Detail level | Pattern name + file | File + line + snippet + impact + remediation |
| False positives | High (13 string concat in templates) | Low (multi-agent triage) |
| Unique vulns found | SQL patterns only | exec() RCE, pickle RCE, SSRF, XSS, CI injection, JWT bypass |
| Duration | ~30s | 7m 30s |
| Tokens | ~5K | 1,331,475 |

## How to Run

### Prerequisites

1. FIRM MCP server running on port 8012
2. Python 3.11+
3. Target repository cloned locally

### Quick Start

```bash
# Clone any target repo
git clone --depth 1 https://github.com/crewAIInc/crewAI.git /tmp/crewai

# Run the scan
python scan-reports/crewai_security_scan.py
```

### MCP Tools Used

Each scan uses a combination of these FIRM MCP tools:

| Tool | Purpose |
|------|---------|
| `firm_security_scan` | Code-level vulnerability scanning (patterns: SQL injection, string concatenation, raw calls) |
| `firm_sandbox_audit` | Container sandbox mode verification |
| `firm_session_config_check` | Session secret persistence audit |
| `firm_rate_limit_check` | Rate limiting configuration check |
| `firm_ci_pipeline_check` | GitHub Actions CI workflow validation |
| `firm_channel_audit` | Messaging channel dependency audit |
| `firm_workspace_integrity_check` | Workspace file integrity check |
| `firm_doc_sync_check` | Documentation vs dependency sync check |
| `firm_browser_context_check` | Browser automation config audit |
| `firm_prompt_injection_batch` | Prompt injection pattern detection (16 patterns) |
| `firm_elicitation_audit` | MCP 2025-11-25 elicitation compliance |
| `firm_node_version_check` | Node.js version validation |
| `firm_plugin_sdk_check` | Plugin SDK configuration audit |
| `firm_icon_metadata_audit` | MCP icon metadata compliance |

## Methodology

### v1 — MCP Pattern Scan
- **Scanner:** FIRM Protocol MCP Bridge v1.1.0
- **Scan depth:** 5 (maximum)
- **Pattern matching:** String concatenation in queries, raw SQL calls, template literal injection, hardcoded secrets
- **Classification:** OWASP-aligned severity scoring (CRITICAL / HIGH / MEDIUM)
- **False positive rate:** HIGH — many template literal matches are legitimate string formatting

### v4 — Security Firm Deep Scan
- **Scanner:** FIRM Security Firm v1.1.0 — 4 multi-model agents
- **Models:** claude-opus-4.6, gpt-5.4, gpt-5.3-codex, gemini-3.1-pro-preview
- **Tools:** 164 ecosystem tools (143 OpenClaw MCP + 21 Memory OS AI)
- **Phases:** discovery → scan → static analysis → report synthesis
- **CWE mapping:** Each finding mapped to MITRE CWE + code snippet + remediation
- **False positive rate:** LOW — multi-agent triage with cross-validation

## Disclaimer

⚠️ Contenu généré par IA — validation par un expert sécurité requise avant utilisation.

These scans are automated checks. v1 pattern scans may produce false positives (especially for string concatenation in non-SQL contexts). v4 deep scans significantly reduce false positives via multi-agent triage, but all findings should still be reviewed by a human security expert before taking action.
