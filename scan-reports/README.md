# Security Scan Reports

> **8,785 files scanned across 5 major AI frameworks — 0 CRITICAL vulnerabilities found.**

This directory contains reproducible security scans performed with the [FIRM Protocol](../README.md) MCP Bridge on major open-source AI agent frameworks.

All scans were executed on **6 March 2026** using the `firm_security_scan` MCP tool (depth 5) plus specialized audit tools. Each scan includes a **Python reproduction script** and a **detailed Markdown report**.

## Combined Results

| Framework | Files | Findings | CRITICAL | HIGH | MEDIUM | Report | Script |
|-----------|------:|----------|---------:|-----:|-------:|--------|--------|
| [crewAI](https://github.com/crewAIInc/crewAI) | 412 | 17 | 0 | 13 | 4 | [REPORT](REPORT-crewai.md) | [scan.py](crewai_security_scan.py) |
| [LangGraph + LangChain](https://github.com/langchain-ai) | 2,205 | 42 | 0 | 33 | 9 | [REPORT](REPORT-langchain.md) | [scan.py](langchain_security_scan.py) |
| [Microsoft AutoGen](https://github.com/microsoft/autogen) | 355 | 15 | 0 | 13 | 2 | [REPORT](REPORT-autogen.md) | [scan.py](autogen_security_scan.py) |
| [designing-multiagent-systems](https://github.com/victordibia/designing-multiagent-systems) | 219 | 2 | 0 | 1 | 1 | [REPORT](REPORT-dmas.md) | [scan.py](dmas_security_scan.py) |
| [OpenClaw](https://github.com/openclaw/openclaw) (self-scan) | 5,594 | 224 | 0 | 117 | 107 | [REPORT](REPORT-openclaw.md) | [scan.py](openclaw_security_scan.py) |
| **Total** | **8,785** | **300** | **0** | **177** | **123** | | |

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

- **Scanner:** FIRM Protocol MCP Bridge v1.1.0
- **Scan depth:** 5 (maximum)
- **Pattern matching:** String concatenation in queries, raw SQL calls, template literal injection, hardcoded secrets
- **Classification:** OWASP-aligned severity scoring (CRITICAL / HIGH / MEDIUM)
- **False positive rate:** HIGH — many template literal matches are legitimate string formatting (not actual SQL injection)

## Disclaimer

⚠️ Contenu généré par IA — validation par un expert sécurité requise avant utilisation.

These scans are automated pattern-matching checks. They may produce false positives (especially for string concatenation in non-SQL contexts). All findings should be reviewed by a human security expert before taking action.
