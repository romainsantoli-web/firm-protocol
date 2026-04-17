# Microsoft AutoGen Security Scan Report

> Scan date: 6 March 2026 · FIRM Protocol MCP Bridge · `firm_security_scan` depth 5

## Target

- **Repository:** [microsoft/autogen](https://github.com/microsoft/autogen)
- **Authors:** [Victor Dibia](https://github.com/victordibia), [Chi Wang](https://github.com/sonichi) (Microsoft Research)
- **Files scanned:** 355 (across 5 sub-packages)
- **Language:** Python

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 0 |
| HIGH | 13 |
| MEDIUM | 2 |
| **Total** | **15** |

## Breakdown by Target

| Target | Files | CRIT | HIGH | MED | Total |
|--------|------:|-----:|-----:|----:|------:|
| AutoGen Core | 92 | 0 | 3 | 0 | 3 |
| AutoGen AgentChat | 48 | 0 | 2 | 0 | 2 |
| AutoGen Extensions | 77 | 0 | 4 | 2 | 6 |
| AutoGen Studio | 79 | 0 | 0 | 0 | 0 |
| AutoGen Samples | 59 | 0 | 4 | 0 | 4 |
| **TOTAL** | **355** | **0** | **13** | **2** | **15** |

## Key Findings

- **13 HIGH:** String concatenation in queries — `code_executor/_func_with_reqs.py`, `_head_and_tail_chat_completion_context.py`, `task_centric_memory/` tests and samples, `_common.py` code executor
- **2 MEDIUM:** Raw SQL call patterns in Jupyter code executor tests
- **AutoGen Studio: 0 findings** — cleanest sub-module (79 files, zero issues)

## Verdict

**✅ PASS** — 0 CRITICAL vulnerabilities. AutoGen Studio is exemplary with zero findings.

## Reproduction

```bash
git clone --depth 1 https://github.com/microsoft/autogen.git /tmp/autogen
python scan-reports/autogen_security_scan.py
```

Requires FIRM MCP server on port 8012.

---

⚠️ Contenu généré par IA — validation par un expert sécurité requise avant utilisation.
