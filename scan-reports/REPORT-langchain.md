# LangGraph + LangChain Security Scan Report

> Scan date: 6 March 2026 · FIRM Protocol MCP Bridge · `firm_security_scan` depth 5

## Target

- **Repositories:** [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) + [langchain-ai/langchain](https://github.com/langchain-ai/langchain)
- **Files scanned:** 2,205 (across 6 sub-modules)
- **Language:** Python

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 0 |
| HIGH | 33 |
| MEDIUM | 9 |
| **Total** | **42** |

## Breakdown by Target

| Target | Files | CRIT | HIGH | MED | Total |
|--------|------:|-----:|-----:|----:|------:|
| LangGraph (core) | 113 | 0 | 2 | 0 | 2 |
| LangGraph Checkpoint | 24 | 0 | 1 | 0 | 1 |
| LangGraph CLI | 51 | 0 | 4 | 0 | 4 |
| LangChain Core | 318 | 0 | 16 | 9 | 25 |
| LangChain (main) | 1,410 | 0 | 5 | 0 | 5 |
| LangChain Partners | 289 | 0 | 5 | 0 | 5 |
| **TOTAL** | **2,205** | **0** | **33** | **9** | **42** |

## Key Findings

- **33 HIGH:** Mostly string concatenation in queries — pattern matches in test files (`test_pregel.py`, `test_utils.py`, `test_config.py`) and production code (`constitutional_ai/base.py`, `flare/base.py`, `anthropic_tools.py`)
- **9 MEDIUM:** Raw SQL call patterns in `langchain_core/runnables/graph*.py` and `output_parsers/`
- **LangChain Core** has the most findings (25) due to its large surface area (318 files)

## Verdict

**✅ PASS** — 0 CRITICAL vulnerabilities across 2,205 files and 6 sub-modules.

## Reproduction

```bash
git clone --depth 1 https://github.com/langchain-ai/langgraph.git /tmp/langgraph
git clone --depth 1 https://github.com/langchain-ai/langchain.git /tmp/langchain
python scan-reports/langchain_security_scan.py
```

Requires FIRM MCP server on port 8012.

---

⚠️ Contenu généré par IA — validation par un expert sécurité requise avant utilisation.
