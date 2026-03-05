# Changelog

All notable changes to FIRM Protocol are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), [Semantic Versioning](https://semver.org/).

## [1.1.0] — 2026-03-05

### Added
- **BountyHunter Module** (`firm.bounty`) — Multi-agent bug bounty hunting platform
  - 8 specialised agents: hunt-director, recon-agent, web-hunter, api-hunter, code-auditor, mobile-hunter, web3-hunter, report-writer
  - Scope enforcement with wildcard domains, CIDR ranges, private IP blocking
  - CVSS v3.1 calculator with severity classification
  - Deduplication engine (title + endpoint + CWE + cosine similarity)
  - Triage pipeline (5-stage: scope → dedup → CVSS → autosubmit → review)
  - Campaign orchestrator (RECON → SCAN → EXPLOIT → REPORT → FEEDBACK)
  - Reward engine with tier-based multipliers and streak bonuses
  - HackerOne API v4 client (programmes, scope, report submission)
  - 12 LLM tools for external scanners (nmap, nuclei, subfinder, katana, ffuf, nikto, semgrep, httpx)
  - Factory function creating a fully-wired FIRM with all 8 agents
- **CLI** — `firm bounty` subcommands: `agents`, `init`, `scope`, `campaign`, `cvss`
- `bounty` optional dependency group (`httpx`, `pyyaml`)
- 107 new tests (total: 1120), coverage 93.78%

## [1.0.0] — 2026-03-05

### Added
- **Prediction Markets** (Layer decision-economics) — √authority-weighted belief aggregation, Brier scores, calibration EMA, contrarian payouts, futarchy governance integration
- **Auto-Restructurer** — entropy-driven agent spawn, authority-based pruning, role-cosine merge recommendations
- **Federation Prediction Broadcast** — `PREDICTION_BROADCAST` message type for cross-FIRM market sharing
- **Global Authority** — `global_authority()` formula: 0.6α + 0.25β + 0.15γ (local + calibration + peer attestations)
- **Reputation Attestations** — `PredictionAccuracyAttestation` with seal/verify/to_dict for cross-org reputation
- **Calibration Bonus** in Hebbian authority — `delta = lr × activation × (1 + bonus) - decay × (1 - activation)`
- **Serialization v1.1.0** — JSON save/load/snapshot/diff with prediction market state
- **LLM Prediction Tools** — `firm_predict`, `firm_create_market`, `firm_view_market` for agent-driven markets
- 4 new test files: `test_prediction.py`, `test_prediction_runtime.py`, `test_restructurer.py`, `test_global_authority.py`
- E2E full loop test validating: Prediction → Calibration → Authority → Restructuring → Federation (30/30 assertions)
- Published to **PyPI** as `firm-protocol` v1.0.0

### Fixed
- `resolve_prediction()` was calling `.payouts` on `list[PredictionSettlement]`
- `view_predictions()` used wrong property names (`aggregated_probability`/`total_staked`)
- `create_prediction_market()` accepted `deadline_hours` instead of `deadline_seconds`
- `resolve_prediction()` passed `description=` instead of `reason=` to `AuthorityEngine.update()`

### Changed
- Test suite: 780 → **883 tests**, coverage 88% → **95.42%**

## [0.5.0] — 2026-02-28

### Added
- **LLM Runtime** — `ClaudeProvider`, `GPTProvider`, `MistralProvider`, `CopilotProProvider`, `GeminiProvider`
- **18 LLM tools** — git, file, terminal, HTTP, Python, prediction market tools
- **FastAPI server** (`firm.api`) — REST API + WebSocket events + Prometheus metrics + HTML dashboard
- **CLI** (`firm`) — `init`, `agent add/list`, `status`, `audit`, `repl`, state persistence
- **Serialization** — JSON save/load with full state round-tripping
- **Plugin system** — `FirmPlugin` ABC + `PluginManager`
- **Event bus** — pub/sub with wildcard subscriptions
- GeminiProvider with 7-model free-tier fallback chain
- Tutorial script and user acceptance tests (38 UAT)
- GitHub Actions CI (lint + test matrix Python 3.11-3.13)

## [0.1.0] — 2026-02-27

### Added
- **12-Layer Architecture** — Authority (L0), Ledger (L1), Constitution (L5), Governance (L6), Spawn (L7), Federation (L8), Reputation (L9), Audit (L10), Human Override (L11), plus Roles (L3), Memory (L4), Evolution
- **Hebbian Authority** — experience-weighted learning with activation-based decay
- **Append-only Ledger** — SHA-256 hash-chained responsibility log
- **Constitutional Safety** — 2 immutable invariants, kill switch
- **Governance** — 2-cycle proposal lifecycle (sim → stress → sim → vote → cooldown)
- **Federation** — peer registry, trust scoring, cross-firm messaging, agent secondment
- **Reputation Bridge** — cross-org attestations with import discount + decay
- **Internal Market** — task bounties, bidding, contracts, settlement, price EMA
- **Meta-Constitutional Amendments** — ≥80% supermajority, foundational invariants immutable
- **Self-Modifying Evolution** — parameter updates via ≥75% supermajority with hard safety bounds
- Property-based tests (Hypothesis), stress tests, E2E integration tests

[1.1.0]: https://github.com/romainsantoli-web/firm-protocol/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/romainsantoli-web/firm-protocol/compare/v0.5.0...v1.0.0
[0.5.0]: https://github.com/romainsantoli-web/firm-protocol/compare/v0.1.0...v0.5.0
[0.1.0]: https://github.com/romainsantoli-web/firm-protocol/releases/tag/v0.1.0
