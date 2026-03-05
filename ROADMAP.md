# FIRM Protocol — Roadmap

> Last updated: 5 mars 2026 | Current version: **v1.0.0**

## Vision

FIRM Protocol is a **zero-dependency Python framework** for self-evolving autonomous organizations.
The v2.0 goal is to add a **BountyHunter module** — a multi-agent bug bounty hunting platform
that orchestrates specialized AI agents to find vulnerabilities on HackerOne programs, using
prediction markets to prioritize attack surfaces and Hebbian authority to reward accurate hunters.

---

## Phase 1 — Housekeeping (v1.0.0) ✅

- [x] Merge `feat/prediction-markets` → `main`
- [x] Git tag `v1.0.0`
- [x] Copy E2E full loop test to `tests/test_e2e_full_loop.py`
- [x] Create `CHANGELOG.md`
- [x] Create `ROADMAP.md` (this file)

## Phase 2 — Security Hardening (v1.1)

Prerequisite for any public deployment or HackerOne integration.

- [ ] JWT / API key authentication on all FastAPI endpoints
- [ ] Sandbox mode for LLM tools: disable `python_run`/`terminal_run` in "public API" mode
- [ ] SSRF protection: block localhost/169.254.x/10.x/172.16.x in `http_get`/`http_post`
- [ ] Dashboard XSS fix: replace all `innerHTML` with `textContent`
- [ ] Security headers middleware: CSP, HSTS, X-Frame-Options, X-Content-Type-Options
- [ ] Rate limiting (`slowapi`) on critical endpoints
- [ ] CORS middleware with strict `allow_origins`
- [ ] WebSocket origin validation
- [ ] Create `SECURITY.md` with responsible disclosure policy
- [ ] Security tests (auth bypass, XSS, SSRF, RCE attempts)
- [ ] Dockerfile (non-root) + docker-compose for isolated deployment

## Phase 3 — API Federation & Coverage (v1.2)

- [ ] Federation REST routes: `/peers`, `/federation/messages`, `/federation/trust`
- [ ] LLM lazy imports (avoid crashes without optional deps)
- [ ] Remove coverage exclusions on `api/` and `llm/`, add tests (target 85%+)
- [ ] API version bump 0.5.0 → 1.0.0
- [ ] Launch GitHub Security Advisories VDP

## Phase 4 — Real Federation Transport (v1.5)

- [ ] `FederationTransport` ABC + HTTP/WebSocket implementation between FIRMs
- [ ] Ed25519 signatures on messages and attestations
- [ ] Peer discovery (centralized registry or simple gossip)
- [ ] Automatic cross-FIRM prediction broadcast
- [ ] Multi-process integration tests (2+ FIRMs in separate processes)

## Phase 5 — BountyHunter Module (v2.0) 🎯

The main new feature — transform FIRM into an autonomous bug bounty hunting platform.

### Sprint 5a — Foundation & Tools

- [ ] Install security tools (nuclei, semgrep, nmap, ffuf, sqlmap, nikto, httpx-toolkit,
      subfinder, amass, katana, dalfox, gau, waybackurls, frida-tools, jadx, slither, mythril)
- [ ] **Scope Engine** (`src/firm/bounty/scope.py`) — TargetScope model, ScopeEnforcer middleware,
      HackerOne/YAML import, integration with existing HTTP/terminal tools
- [ ] **Vulnerability Data Model** (`src/firm/bounty/vulnerability.py`) — CWE, CVSS 3.1 auto-calc,
      severity enum, PoC model, VulnReport formatter, SQLite-backed VulnDatabase
- [ ] **Security Toolkit** (`src/firm/bounty/tools/`) — 15+ LLM tools wrapping security tools:
      recon (subdomains, ports, tech, URLs), scanning (nuclei, semgrep, ffuf, sqlmap, xss, nikto,
      ssl), mobile (decompile, hook), web3 (slither, mythril), reporting
- [ ] **Sandbox Docker** (`src/firm/bounty/sandbox/`) — container per agent, network namespace
      filtered by scope, CPU/mem limits, read-only fs, timeout

### Sprint 5b — HackerOne Integration & Dedup

- [ ] **HackerOne API Client** (`src/firm/bounty/hackerone.py`) — API v4: list/get programs,
      import scope, submit reports, track status, manage credentials
- [ ] **Deduplication Engine** (`src/firm/bounty/dedup.py`) — embedding-based similarity +
      regex matching on CWE/endpoint/param, configurable threshold
- [ ] **Triage Pipeline** (`src/firm/bounty/triage.py`) — auto-triage by severity/confidence,
      exploit re-verification in sandbox, human review queue, HackerOne feedback → prediction
      resolution → calibration EMA → authority update

### Sprint 5c — Agent Specialization & Orchestration

- [ ] **BountyFirm Factory** (`src/firm/bounty/factory.py`) — pre-configured FIRM with
      8 specialized agents (hunt-director, recon, web-hunter, api-hunter, code-auditor,
      mobile-hunter, web3-hunter, report-writer), each with optimal LLM model assignment
- [ ] **Campaign Orchestrator** (`src/firm/bounty/campaign.py`) — campaign lifecycle
      (recon → markets → parallel hunting → dedup → triage → submit → feedback loop),
      budget tracking, live dashboard
- [ ] **Reward Engine** (`src/firm/bounty/reward.py`) — bounty-to-credits mapping,
      split rewards (hunter 70%, recon 20%, writer 10%), ROI-based authority boost

### Sprint 5d — CLI & Tests

- [ ] CLI commands: `firm bounty init`, `hunt`, `status`, `triage`, `submit`, `report`
- [ ] Tests: `test_bounty_scope.py`, `test_bounty_vuln.py`, `test_bounty_dedup.py`,
      `test_bounty_hackerone.py`, `test_bounty_campaign.py`, `test_bounty_tools.py`
- [ ] Coverage ≥ 80% on `firm.bounty` module

## Phase 6 — Ecosystem & Scale (v2.5)

- [ ] Plugin SDK with reference plugins (audit logger, Slack notifier, metrics exporter)
- [ ] MCP bridge: expose FIRM tools as an MCP server
- [ ] Multi-FIRM tournament: 5+ federated FIRMs, cross-org bounty sharing
- [ ] Real-time dashboard: WebSocket reconnection, live prediction markets
- [ ] HackerOne VDP for the FIRM API itself

---

## Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| Module additionnel (not pivot) | `firm/bounty/` lives alongside the core protocol — FIRM remains a general-purpose framework |
| All target types (web, API, mobile, web3) | Specialized agents in parallel via Copilot Pro multi-model access |
| SQLite for persistence | Zero-infra, sufficient for solo hunter, upgradeable to PostgreSQL later |
| Docker sandbox mandatory | Agents execute exploits — host isolation is non-negotiable |
| Human-in-the-loop for HIGH/CRITICAL | Auto-submit only for MEDIUM with high confidence |
| Homebrew for macOS security tools | Native package manager, reproducible installation |
| Ed25519 for federation crypto | Faster than RSA, shorter keys, modern standard |
| GitHub Security Advisories before HackerOne VDP | Natural progression for open-source projects |

## Metrics

| Metric | v1.0.0 (current) | v2.0 (target) |
|--------|-------------------|----------------|
| Tests | 883 | 1200+ |
| Coverage | 95.42% | 90%+ (with bounty module) |
| Tools (LLM) | 18 | 35+ |
| Modules | 21 core + 4 llm + 1 api | + 10 bounty |
| PyPI version | 1.0.0 | 2.0.0 |
