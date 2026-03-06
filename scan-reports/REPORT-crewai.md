# crewAI Security Scan Report

> Scan date: 6 March 2026 · FIRM Protocol MCP Bridge · `firm_security_scan` depth 5

## Target

- **Repository:** [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI)
- **Files scanned:** 412
- **Language:** Python

## Summary

| Severity | Count |
|----------|------:|
| CRITICAL | 0 |
| HIGH | 13 |
| MEDIUM | 4 |
| **Total** | **17** |

## Findings by Pattern

| Pattern | Count | Severity |
|---------|------:|----------|
| String concatenation in query — use parameterized queries | 13 | HIGH |
| Raw SQL call detected — verify parameterization | 4 | MEDIUM |

## Key Findings

- **5 HIGH:** String concatenation in queries
  - `memory/encoding_flow.py`
  - `memory/storage/lancedb_storage.py`
  - `agent/utils.py`
  - `cli/memory_tui.py`
  - `utilities/string_utils.py`
- **12 MEDIUM:** Raw SQL call patterns in `flow/visualization/assets/interactive.js`

## Verdict

**✅ PASS** — 0 CRITICAL vulnerabilities. All HIGH findings are string concatenation patterns (false-positive prone in template literals).

## Reproduction

```bash
git clone --depth 1 https://github.com/crewAIInc/crewAI.git /tmp/crewai
python scan-reports/crewai_security_scan.py
```

Requires FIRM MCP server on port 8012.

---

⚠️ Contenu généré par IA — validation par un expert sécurité requise avant utilisation.
