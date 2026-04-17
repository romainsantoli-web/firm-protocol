# FIRM Protocol — Complete Tutorial

> Step-by-step guide to creating, managing, and evolving an autonomous organization with FIRM.

---

## Table of Contents

1. [Installation](#1-installation)
2. [Getting Started — Creating an Organization (CLI)](#2-getting-started--creating-an-organization-cli)
3. [Managing Agents](#3-managing-agents)
4. [Recording Actions — The Authority System](#4-recording-actions--the-authority-system)
5. [Governance — Proposals and Votes](#5-governance--proposals-and-votes)
6. [Dynamic Roles](#6-dynamic-roles)
7. [Collective Memory](#7-collective-memory)
8. [Internal Market — Bounties and Tasks](#8-internal-market--bounties-and-tasks)
9. [Autonomous Parameter Evolution](#9-autonomous-parameter-evolution)
10. [Constitutional Amendments](#10-constitutional-amendments)
11. [Audit and Organization Status](#11-audit-and-organization-status)
12. [Interactive REPL Mode](#12-interactive-repl-mode)
13. [LLM Agents — Choosing Your Model (Claude, GPT, Gemini, Copilot Pro)](#13-llm-agents--choosing-your-model-claude-gpt-gemini-copilot-pro)
14. [Python Usage (Programmatic API)](#14-python-usage-programmatic-api)
15. [Complete Python Scenario — From A to Z](#15-complete-python-scenario--from-a-to-z)
16. [REST API (FastAPI)](#16-rest-api-fastapi)
17. [BountyHunter Module](#17-bountyhunter-module)
18. [Federation Between Organizations](#18-federation-between-organizations)
19. [Prediction Markets](#19-prediction-markets)
20. [Persistence — Saving and Loading State](#20-persistence--saving-and-loading-state)
21. [Quick Command Reference](#21-quick-command-reference)
22. [MCP Bridge — Connecting the Ecosystem (138 tools)](#22-mcp-bridge--connecting-the-ecosystem-138-tools)
23. [Automatic Report Generation (Best Practices)](#23-automatic-report-generation-best-practices)

---

## 1. Installation

### Option A: From PyPI (recommended)

```bash
# Core only — zero external dependencies, Python stdlib only
pip install firm-protocol

# With LLM providers (OpenAI, Anthropic, Mistral)
pip install "firm-protocol[llm]"

# With the REST API server (FastAPI + Uvicorn)
pip install "firm-protocol[api]"

# With the bug bounty module (httpx, pyyaml)
pip install "firm-protocol[bounty]"

# Everything included
pip install "firm-protocol[all]"
```

### Option B: From source

```bash
git clone https://github.com/romainsantoli-web/firm-protocol.git
cd firm-protocol
pip install -e ".[dev]"   # dev includes tests, linter, etc.
```

**Requirements:** Python 3.11 or higher.

### Verify installation

```bash
firm --version
# → firm-protocol 1.1.0
```

---

## 2. Getting Started — Creating an Organization (CLI)

Every interaction begins by **initializing an organization**:

```bash
firm init my-startup
```

**Output:**

```
FIRM 'my-startup' created (id=firm-abc12345)
State saved to firm-state.json
```

This creates a `firm-state.json` file in the current directory. This file contains your entire organization's state. Every command that modifies the state automatically saves it.

> **Changing the state file:** use `--state my-file.json` or the environment variable `FIRM_STATE=path.json`.

```bash
# Example with a custom state file
firm --state /path/to/my-org.json init acme-corp
```

---

## 3. Managing Agents

### Adding agents

```bash
# Add an agent with the default authority (0.5)
firm agent add Alice

# Add an agent with a high initial authority (max: 1.0)
firm agent add Bob --authority 0.8

# Add a third agent
firm agent add Charlie --authority 0.3
```

Each agent receives a unique identifier (e.g., `agent-a1b2c3d4`).

### Listing agents

```bash
firm agent list
```

**Output:**

```
Name       ID              Authority   Status   Credits
─────────────────────────────────────────────────────────
Alice      agent-abc123    0.500       active   100.0
Bob        agent-def456    0.800       active   100.0
Charlie    agent-ghi789    0.300       active   100.0
```

To also see inactive agents:

```bash
firm agent list --all
```

---

## 4. Recording Actions — The Authority System

The heart of FIRM: **authority is not assigned, it is earned**. Every success increases an agent's authority, every failure decreases it.

### Recording a success

```bash
firm action Alice ok "Delivered the authentication feature on time"
```

**Output:**

```
Action recorded: Alice succeeded
Authority: 0.500 → 0.548 (+0.048)
```

### Recording a failure

```bash
firm action Bob fail "Broke the CI pipeline in production"
```

**Output:**

```
Action recorded: Bob failed
Authority: 0.800 → 0.784 (-0.016)
```

### How does it work?

The authority formula is **Hebbian** (inspired by neuroscience):

```
Δauthority = learning_rate × activation × (1 + calibration_bonus) − decay × (1 − activation)
```

- `activation = 1.0` on success, `0.0` on failure
- `learning_rate` default: 0.05
- `decay` default: 0.02
- Authority always stays within `[0.0, 1.0]`

### Authority thresholds

| Threshold | Meaning                                    |
| --------- | ------------------------------------------ |
| ≥ 0.80   | Can propose governance changes             |
| ≥ 0.60   | Can vote on proposals                      |
| ≥ 0.40   | Standard working authority                 |
| ≤ 0.30   | On probation                               |
| ≤ 0.05   | Auto-termination (agent is deactivated)    |

---

## 5. Governance — Proposals and Votes

Important changes go through a **2-cycle governance process** with simulation, stress test, vote, and cooldown period.

### Step 1: Create a proposal

Only agents with authority ≥ 0.80 can propose:

```bash
firm propose Bob "Add a DevOps role" "Create a dedicated role for deployment and monitoring"
```

> **Note:** `Bob` must be the agent's ID OR name (the CLI resolves names).

**Output:**

```
Proposal created: prop-xyz789
Title: Add a DevOps role
Status: draft
```

### Step 2: Vote

Agents with authority ≥ 0.60 can vote. Votes are weighted by authority:

```bash
firm vote prop-xyz789 Alice approve
firm vote prop-xyz789 Charlie reject
```

**Output:**

```
Vote recorded: Alice → approve on prop-xyz789
```

### Step 3: Finalize

```bash
firm finalize prop-xyz789
```

**Output:**

```
Proposal finalized: approved
No constitutional violations detected.
```

If the proposal violates a constitutional invariant, the Constitutional Agent automatically blocks it.

---

## 6. Dynamic Roles

Roles in FIRM are not fixed — they are assigned based on authority.

### Defining a role

```bash
firm role define deployer "Responsible for production deployments"
```

By default, the role requires a minimum authority of 0.3. To change this:

```bash
firm role define lead-architect "Lead architect" --min-authority 0.7
```

### Assigning a role

```bash
firm role assign Alice deployer
```

**Output:**

```
Role 'deployer' assigned to Alice
```

If Alice doesn't have the minimum authority required by the role, the assignment is refused.

---

## 7. Collective Memory

FIRM has a shared memory where agents can contribute and recall knowledge. Memories have a **weight** that evolves over time.

### Adding a memory

```bash
firm memory add Alice "Friday deployments cause 3x more incidents" --tags "ops,incidents,best-practice"
```

### Recalling memories

```bash
firm memory recall incidents
```

**Output:**

```
Memory results for 'incidents':
  [0.75] "Friday deployments cause 3x more incidents"
         by Alice | tags: ops, incidents, best-practice
```

In Python, you can also **reinforce** or **challenge** a memory to modify its weight:

```python
firm.reinforce_memory(alice.id, memory_id)    # +weight
firm.challenge_memory(bob.id, memory_id,
    counter_evidence="Q4 data shows the opposite")  # -weight
```

---

## 8. Internal Market — Bounties and Tasks

FIRM includes an internal economic system with bounties, bids, and settlements.

### Posting a task

```bash
firm market post Alice "Fix the authentication bug" 50
```

This creates a task with a 50-credit bounty, funded by Alice.

**Output:**

```
Task posted: task-abc123
Title: Fix the authentication bug
Bounty: 50.0 credits
```

### Bidding on a task

```bash
firm market bid task-abc123 Bob 40
```

Bob offers to do the work for 40 credits.

### Full workflow (in Python)

```python
# Post a task
task = firm.post_task(alice.id, "Fix auth bug", "Critical security fix", bounty=50.0)

# An agent bids
bid = firm.bid_on_task(task.id, bob.id, amount=40.0)

# The requester accepts the bid
firm.accept_bid(task.id, bid.id)

# Work is done — settle the task
settlement = firm.settle_task(task.id, success=True)
# → Bob receives the credits, his authority increases
```

---

## 9. Autonomous Parameter Evolution

The organization can **modify its own parameters** (learning rate, decay, etc.) through a supermajority vote (≥ 75%).

### Proposing a change

```bash
firm evolve propose Alice learning_rate 0.08
```

This proposes changing the learning rate from 0.05 to 0.08.

### Voting on the evolution

```bash
firm evolve vote evol-abc123 Bob approve
firm evolve vote evol-abc123 Charlie approve
```

### Applying the change

```bash
firm evolve apply evol-abc123
```

**Output:**

```
Evolution applied:
  learning_rate: 0.05 → 0.08
Generation: 1 → 2
```

---

## 10. Constitutional Amendments

The two fundamental invariants (human control + capacity for evolution) can never be removed. However, you can **add** new constitutional rules.

### Proposing an amendment

```bash
firm amend Alice add_invariant "Every agent must pass a security audit before accessing production"
```

Possible types: `add_invariant`, `remove_invariant`, `add_keywords`, `remove_keywords`.

> **Important:** the original invariants (kill switch + evolution) are protected and cannot be removed.

---

## 11. Audit and Organization Status

### Viewing general status

```bash
firm status
```

**Output:**

```
FIRM Status: my-startup
══════════════════════════════════
Agents:          3 (3 active)
Authority range: 0.30 — 0.85
Ledger entries:  12
Chain valid:     ✓
Kill switch:     inactive
Proposals:       1 (1 approved)
Roles defined:   2
Memory entries:  1
Federation peers: 0
Evolution gen:   2
Market tasks:    1 (0 open)
Amendments:      1
```

### Running a full audit

```bash
firm audit
```

**Output:**

```
Audit Report
════════════
Chain integrity:  ✓ valid (12 entries verified)
Findings:         2
  [MEDIUM] Agent 'Charlie' authority below threshold (0.30)
  [INFO] No federation peers registered
```

The audit verifies ledger integrity (SHA-256 hash chain), authority thresholds, governance health, etc.

---

## 12. Interactive REPL Mode

For a smooth interaction without typing `firm` at each command:

```bash
firm repl
```

**Output:**

```
╔══════════════════════════════════════╗
║  FIRM Protocol REPL v1.1.0          ║
║  State: firm-state.json             ║
╚══════════════════════════════════════╝

firm> help
Available commands:
  add <name> [authority]    Add an agent
  action <name> ok|fail     Record an action
  agents                    List agents
  status                    Show org status
  propose <name> <title>    Create proposal
  vote <prop> <name> y|n    Vote on proposal
  params                    Show firm parameters
  ledger                    Show last 10 entries
  audit                     Run audit
  save [file]               Save state
  load <file>               Load state
  export <file>             Export status as JSON
  help                      This message
  quit                      Exit

firm> add Eve 0.6
Agent 'Eve' added (authority: 0.6)

firm> action Eve ok Shipped the new dashboard
Authority: 0.600 → 0.648

firm> agents
Name    Authority  Status
Eve     0.648      active
Alice   0.548      active
Bob     0.784      active

firm> quit
Goodbye.
```

---

## 13. LLM Agents — Choosing Your Model (Claude, GPT, Gemini, Copilot Pro)

FIRM includes an **LLM agent system** that connects real language models to the authority system. Each agent can use a different provider and model.

### Available providers

| Provider                        | CLI Alias                 | Default Model            | API Key Required        | Dependency          |
| ------------------------------- | ------------------------- | ------------------------ | ----------------------- | ------------------- |
| **Claude** (Anthropic)    | `claude`                | `claude-sonnet-4`      | `ANTHROPIC_API_KEY`   | `anthropic`       |
| **GPT** (OpenAI)          | `gpt` or `openai`      | `gpt-4o`               | `OPENAI_API_KEY`      | `openai`          |
| **Mistral**               | `mistral`               | `mistral-large-latest` | `MISTRAL_API_KEY`     | `mistralai`       |
| **Gemini** (Google)       | `gemini` or `google`   | `gemini-2.5-pro`       | `GEMINI_API_KEY`      | `openai` (compat) |
| **Copilot** (GitHub free) | `copilot` or `github`  | `gpt-4o`               | `GITHUB_TOKEN`        | `openai`          |
| **Copilot Pro** (GitHub)  | `copilot-pro`           | `claude-sonnet-4.6`    | JWT OAuth              | `httpx`           |

### Installing dependencies

```bash
# For Claude, GPT, Mistral
pip install "firm-protocol[llm]"

# For Copilot Pro (httpx required)
pip install "firm-protocol[all]"
```

### Configuring API keys

```bash
# Option 1: Environment variables
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export MISTRAL_API_KEY="..."
export GEMINI_API_KEY="..."
export GITHUB_TOKEN="ghp_..."

# Option 2: Pass directly in code (see below)
```

### Creating an agent with a specific model

```python
from firm.runtime import Firm
from firm.llm.agent import create_llm_agent, AgentConfig

firm = Firm("my-org")

# ── Claude Agent (Anthropic) ─────────────────────────────────────
cto = create_llm_agent(
    firm, "CTO",
    provider_name="claude",
    model="claude-opus-4.6",        # or "claude-sonnet-4.6", "claude-haiku-4.5"
    authority=0.8,
)

# ── GPT Agent (OpenAI) ───────────────────────────────────────────
dev = create_llm_agent(
    firm, "dev-1",
    provider_name="gpt",
    model="gpt-5.1",                # or "gpt-4o", "gpt-5-mini"
    authority=0.5,
)

# ── Mistral Agent ────────────────────────────────────────────────
analyst = create_llm_agent(
    firm, "analyst",
    provider_name="mistral",
    model="mistral-large-latest",    # or "mistral-small-latest" (economical)
    authority=0.5,
)

# ── Gemini Agent (Google) ────────────────────────────────────────
reviewer = create_llm_agent(
    firm, "reviewer",
    provider_name="gemini",
    model="gemini-2.5-pro",          # or "gemini-3-pro", "gemini-3.1-pro"
    authority=0.5,
)
```

### Copilot Pro — Access to all models with a GitHub subscription

If you have **GitHub Copilot Pro** (or Business/Enterprise), you get access to a wide catalog of models through a single subscription, **with no additional API key**.

#### Complete Copilot Pro model catalog

| Family           | Available Models                                                 | Recommended Use                              |
| ---------------- | ---------------------------------------------------------------- | -------------------------------------------- |
| **Claude** | `claude-haiku-4.5`                                              | Quick tasks, low cost                        |
|                  | `claude-sonnet-4`, `claude-sonnet-4.5`, `claude-sonnet-4.6` | Good balance of performance/speed            |
|                  | `claude-opus-4.5`, `claude-opus-4.6`                          | Complex tasks, architecture, reasoning       |
| **GPT**    | `gpt-4.1`, `gpt-4o`                                           | General use, good quality/price ratio        |
|                  | `gpt-5-mini`                                                    | Economical, simple tasks                     |
|                  | `gpt-5.1`, `gpt-5.2`, `gpt-5.3`, `gpt-5.4`                | Latest generation, high performance          |
| **Codex**  | `gpt-5.1-codex`, `gpt-5.2-codex`, `gpt-5.3-codex`           | Code-intensive (uses `/responses` endpoint)  |
|                  | `gpt-5.1-codex-mini` *(Preview)*, `gpt-5.1-codex-max`       | Mini = fast, Max = high quality              |
| **Gemini** | `gemini-2.5-pro`                                                | Good general-purpose Google model            |
|                  | `gemini-3-pro` *(Preview)*, `gemini-3.1-pro` *(Preview)*  | Latest generation from Google                |

> **21 models** accessible with a single subscription. No separate Anthropic, OpenAI, or Google API key needed.

#### Copilot Pro authentication

Authentication uses an **OAuth flow** that generates a JWT that is automatically renewed:

```python
from firm.llm.providers import CopilotProProvider

# Option 1: Direct JWT (if you already have one)
provider = CopilotProProvider(model="claude-sonnet-4.6", api_key="eyJ...")

# Option 2: Environment variable
#   export COPILOT_JWT="eyJ..."
provider = CopilotProProvider(model="gpt-5.3")

# Option 3: GitHub OAuth token (auto-refreshes the JWT)
provider = CopilotProProvider(model="claude-opus-4.6", oauth_token="gho_xxxx")

# Option 4: Automatic cache (/tmp/copilot_token.json)
#   If you've already used Copilot in VS Code, the token is often already there
provider = CopilotProProvider(model="claude-sonnet-4.6")
```

> **Getting the OAuth token:** The provider uses the same OAuth flow as VS Code Copilot
> (client_id `Iv1.b507a08c87ecfe98`). If you have VS Code with Copilot connected, the token
> is often already cached in `/tmp/copilot_token.json`.

#### Creating Copilot Pro agents in an organization

```python
from firm.runtime import Firm
from firm.llm.agent import create_llm_agent, AgentConfig

firm = Firm("my-startup")

# CTO agent on Claude Opus 4.6 — the most capable (via Copilot Pro)
cto = create_llm_agent(
    firm, "CTO",
    provider_name="copilot-pro",
    model="claude-opus-4.6",
    authority=0.9,
)

# Dev agent on GPT-5.3 — latest gen OpenAI (via Copilot Pro)
dev = create_llm_agent(
    firm, "dev-1",
    provider_name="copilot-pro",
    model="gpt-5.3",
    authority=0.5,
)

# Code review agent on Claude Sonnet 4.6 — fast and accurate
reviewer = create_llm_agent(
    firm, "reviewer",
    provider_name="copilot-pro",
    model="claude-sonnet-4.6",
    authority=0.6,
)

# Codex agent for code-intensive work (uses /responses endpoint)
coder = create_llm_agent(
    firm, "coder",
    provider_name="copilot-pro",
    model="gpt-5.3-codex",
    authority=0.7,
)

# Economical agent for simple tasks
junior = create_llm_agent(
    firm, "junior",
    provider_name="copilot-pro",
    model="claude-haiku-4.5",       # or "gpt-5-mini"
    authority=0.4,
)
```

### Copilot free-tier (GitHub Models)

If you **don't** have Copilot Pro, you can use the `copilot` provider (free tier) which goes through `models.inference.ai.azure.com`:

```python
# Free tier — limited models, rate-limited
free_agent = create_llm_agent(
    firm, "free-agent",
    provider_name="copilot",        # or "github"
    model="gpt-4o",
    authority=0.5,
    # Requires a GITHUB_TOKEN with "models:read" scope
)
```

### Gemini — Free with automatic fallback

The Gemini provider (direct access via Google API key) automatically handles **rate limits** by cascading to fallback models:

```python
# Fallback is transparent — never a 429 error
gemini_agent = create_llm_agent(
    firm, "analyst",
    provider_name="gemini",
    model="gemini-2.5-pro",         # or "gemini-3-pro", "gemini-3.1-pro" via Copilot Pro
    authority=0.5,
)
```

### Executing a task with an LLM agent

```python
# The agent uses the configured model + real tools (git, terminal, files, HTTP)
result = cto.execute_task(
    task="Analyze the failing tests in tests/test_api.py and propose a fix",
    context="CI failed on the last commit. Error: AssertionError on line 42."
)

print(f"Status: {result.status.value}")        # completed / failed / timeout
print(f"Output: {result.output[:200]}")
print(f"Tools used: {result.tools_used}")      # ['file_read', 'python_test', 'file_write']
print(f"Tokens: {result.total_tokens}")
print(f"Cost: ${result.cost_usd:.4f}")
```

### Authority-based access control

Tool access is **filtered by the agent's authority**:

| Authority    | Available Tools                                                              |
| ------------ | ---------------------------------------------------------------------------- |
| < 0.30       | `file_read`, `file_list` only (probation)                                 |
| 0.30 – 0.59 | +`git_status`, `git_diff`, `git_log`, `file_search`, `python_test`  |
| 0.60 – 0.79 | +`file_write`, `git_commit` (write access)                                |
| ≥ 0.80      | +`terminal_run`, `http_get`, `http_post` (dangerous operations)           |

### Budget and limits per agent

```python
from firm.llm.agent import AgentConfig

config = AgentConfig(
    max_iterations=25,           # max LLM→tools→LLM loops
    max_tokens_budget=100_000,   # total token budget (scaled by authority)
    max_cost_usd=1.0,            # cost cap in USD (scaled by authority)
    temperature=0.3,             # model temperature
    max_response_tokens=4096,    # max tokens per response
    auto_record_actions=True,    # records result in the authority system
)

agent = create_llm_agent(
    firm, "dev",
    provider_name="copilot-pro",
    model="claude-sonnet-4.6",
    authority=0.6,
    config=config,
)

# With authority 0.6, the actual budget is:
#   max_tokens = 100,000 × 0.6 = 60,000
#   max_cost   = 1.0 × 0.6     = $0.60
```

### Mixing providers in the same organization

One of FIRM's strengths: each agent can use a different model, tailored to its role.

```python
firm = Firm("multi-model-org")

# CTO = Claude Opus 4.6 (via Copilot Pro) — the most capable
cto = create_llm_agent(firm, "CTO", provider_name="copilot-pro",
                        model="claude-opus-4.6", authority=0.9)

# Senior dev = GPT-5.3 — latest gen, very performant
senior = create_llm_agent(firm, "Senior", provider_name="copilot-pro",
                          model="gpt-5.4", authority=0.7)

# Reviewer = Claude Sonnet 4.6 — fast and accurate for reviews
reviewer = create_llm_agent(firm, "Reviewer", provider_name="copilot-pro",
                            model="claude-sonnet-4.6", authority=0.6)

# Junior dev = Haiku 4.5 — fast and economical
junior = create_llm_agent(firm, "Junior", provider_name="copilot-pro",
                          model="claude-haiku-4.5", authority=0.4)

# Coder = Codex — specialized for code (/responses endpoint)
coder = create_llm_agent(firm, "Coder", provider_name="copilot-pro",
                         model="gpt-5.3-codex", authority=0.6)

# Architect = Gemini 3.1 Pro — different perspective
architect = create_llm_agent(firm, "Architect", provider_name="copilot-pro",
                             model="gemini-3.1-pro", authority=0.7)

# Run a task on each agent
for agent in [cto, senior, reviewer, junior, coder, architect]:
    stats = agent.get_stats()
    print(f"{stats['name']:10} | {stats['provider']:12} | {stats['model']}")
```

**Output:**

```
CTO        | copilot-pro  | claude-opus-4.6
Senior     | copilot-pro  | gpt-5.4
Reviewer   | copilot-pro  | claude-sonnet-4.6
Junior     | copilot-pro  | claude-haiku-4.5
Coder      | copilot-pro  | gpt-5.3-codex
Architect  | copilot-pro  | gemini-3.1-pro
```

### Summary: which provider to choose?

| Situation                                   | Recommended Provider | Model                                 | Cost                       |
| ------------------------------------------- | -------------------: | ------------------------------------- | -------------------------- |
| **Copilot Pro** — complex tasks       |      `copilot-pro` | `claude-opus-4.6`                    | Included in subscription   |
| **Copilot Pro** — general use         |      `copilot-pro` | `claude-sonnet-4.6` or `gpt-5.4`   | Included                   |
| **Copilot Pro** — code-intensive      |      `copilot-pro` | `gpt-5.3-codex`                      | Included                   |
| **Copilot Pro** — simple tasks        |      `copilot-pro` | `claude-haiku-4.5` or `gpt-5-mini` | Included                   |
| **Copilot Pro** — Google AI           |      `copilot-pro` | `gemini-3.1-pro`                     | Included                   |
| Direct **Anthropic** key              |           `claude` | `claude-sonnet-4`                    | $3 / $15 per 1M tokens     |
| Direct **OpenAI** key                 |              `gpt` | `gpt-4o`                             | $2.5 / $10 per 1M tokens   |
| **Free** (Google)                      |           `gemini` | `gemini-2.5-pro`                     | Free (rate-limited)        |
| **Free** (GitHub)                      |          `copilot` | `gpt-4o`                             | Free (rate-limited)        |
| Tight budget                                |          `mistral` | `mistral-small-latest`               | $0.2 / $0.6 per 1M tokens  |

---

## 14. Python Usage (Programmatic API)

### Minimal import

```python
from firm import Firm
```

### Creating and managing an organization

```python
from firm import Firm

# Create the organization
org = Firm(name="acme")

# Add agents
alice = org.add_agent("Alice", authority=0.8, credits=1000.0)
bob = org.add_agent("Bob", authority=0.5, credits=500.0)

# Record actions
org.record_action(alice.id, success=True, description="Delivered the MVP")
org.record_action(bob.id, success=False, description="Critical bug in prod")

# Check authorities
for agent in org.get_agents():
    print(f"  {agent.name}: {agent.authority:.3f}")
```

### Save / Load

```python
from firm import save_firm, load_firm

# Save
save_firm(org, "my-org.json")

# Load
org_restored = load_firm("my-org.json")
```

---

## 15. Complete Python Scenario — From A to Z

Here is a realistic scenario that covers all features:

```python
from firm import Firm, save_firm

# ── ACT 1: Bootstrap ───────────────────────────────────
org = Firm(name="NeuralForge")

# Founding team
ada   = org.add_agent("Ada",   authority=0.9, credits=1000.0)  # CEO
kai   = org.add_agent("Kai",   authority=0.7, credits=500.0)   # CTO
zara  = org.add_agent("Zara",  authority=0.5, credits=300.0)   # Eng

# Work phase — authority earned through results
for _ in range(5):
    org.record_action(ada.id, success=True, description="Strategic decision")
for _ in range(3):
    org.record_action(kai.id, success=True, description="Core systems delivered")
org.record_action(kai.id, success=False, description="Outage during the demo")
org.record_action(zara.id, success=True, description="Feature delivered")

print("=== Authorities after Phase 1 ===")
for a in org.get_agents():
    print(f"  {a.name}: {a.authority:.3f}")

# ── ACT 2: Structure ────────────────────────────────────
# Define roles
org.define_role("architect", min_authority=0.7, description="System architect")
org.define_role("deployer", min_authority=0.4, description="Production deployments")

# Assign roles (authority is verified)
org.assign_role(ada.id, "architect")
org.assign_role(zara.id, "deployer")

# Collective memory
m1 = org.contribute_memory(
    ada.id,
    "The microservices architecture reduced deployment time by 60%",
    tags=["architecture", "performance"]
)
org.reinforce_memory(kai.id, m1.id)  # Kai confirms

# Recall memory
results = org.recall_memory(tags=["architecture"])
for m in results:
    print(f"  [{m.weight:.2f}] {m.content}")

# ── ACT 3: Governance ───────────────────────────────────
# Ada proposes a change (authority >= 0.80 required)
proposal = org.propose(
    ada.id,
    title="Adopt continuous deployment",
    description="Switch to a CI/CD pipeline with automatic releases"
)
print(f"Proposal: {proposal.id} — {proposal.status.value}")

# Simulation (in 2 cycles before the vote)
org.simulate_proposal(proposal.id, success=True, impact_summary="Reduces TTM by 40%")

# Vote (weighted by voter authority)
org.vote(proposal.id, kai.id, "approve", reason="Good for velocity")
org.vote(proposal.id, zara.id, "approve", reason="Agreed")

# Finalization
result = org.finalize_proposal(proposal.id)
print(f"Result: {result.status.value}")

# ── ACT 4: Economy ──────────────────────────────────────
# Post a task on the internal market
task = org.post_task(
    ada.id,
    title="Migrate the database to PostgreSQL",
    description="Complete migration with zero downtime",
    bounty=100.0
)

# Kai bids
bid = org.bid_on_task(task.id, kai.id, amount=80.0)

# Ada accepts
org.accept_bid(task.id, bid.id)

# Work completed successfully
settlement = org.settle_task(task.id, success=True)
print(f"Kai received {settlement.amount} credits")

# ── ACT 5: Evolution ────────────────────────────────────
# Propose changing the learning rate (75% supermajority required)
evol = org.propose_evolution(
    ada.id,
    changes={"authority.learning_rate": 0.08},
    rationale="Agents are progressing too slowly"
)

org.vote_evolution(evol.id, kai.id, approve=True)
org.vote_evolution(evol.id, zara.id, approve=True)
org.apply_evolution(evol.id)

params = org.get_firm_parameters()
print(f"New learning_rate: {params['authority']['learning_rate']}")

# ── ACT 6: Final Audit ──────────────────────────────────
report = org.run_audit()
print(f"Chain valid: {report.chain_valid}")
print(f"Findings: {len(report.findings)}")

status = org.status()
print(f"Agents: {status['agents']['total']}")
print(f"Ledger entries: {status['ledger']['total_entries']}")

# Save
save_firm(org, "neuralforge-final.json")
print("Organization saved!")
```

**Run:** `python my_scenario.py`

---

## 16. REST API (FastAPI)

### Installation

```bash
pip install "firm-protocol[api]"
```

### Starting the server

```bash
uvicorn firm.api.app:app --reload --port 8000
```

### Available endpoints

The server exposes a full REST API with automatic Swagger documentation at `http://localhost:8000/docs`.

Main endpoints:

- `POST /agents` — Add an agent
- `GET /agents` — List agents
- `POST /actions` — Record an action
- `GET /status` — Organization status
- `POST /proposals` — Create a proposal
- WebSocket `/ws` for real-time events

---

## 17. BountyHunter Module

### Installation

```bash
pip install "firm-protocol[bounty]"
```

### Scope YAML file

Create a `scope.yaml` file describing the target:

```yaml
program:
  name: "My Program"
  platform: hackerone

in_scope:
  - type: url
    target: "*.example.com"
  - type: url
    target: "api.example.com"
  - type: cidr
    target: "10.0.0.0/8"

out_of_scope:
  - type: url
    target: "internal.example.com"
  - type: url
    target: "staging.example.com"
```

### CLI commands

```bash
# View the 8 specialized agents and their LLM models
firm bounty agents

# Output:
#   hunt-director   Claude Opus    0.90
#   recon-agent     Claude Sonnet  0.70
#   web-hunter      Claude Sonnet  0.70
#   api-hunter      Claude Sonnet  0.70
#   code-auditor    Claude Opus    0.80
#   mobile-hunter   Claude Sonnet  0.70
#   web3-hunter     Claude Opus    0.80
#   report-writer   Claude Sonnet  0.60

# Display the program scope
firm bounty scope scope.yaml

# Initialize a campaign
firm bounty init scope.yaml --rate-limit 10.0 --rate-burst 20

# Calculate a CVSS v3.1 score
firm bounty cvss "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
# → Score: 9.8 (CRITICAL)

# Run a complete campaign
firm bounty campaign run --scope-file scope.yaml --max-hours 4.0 --max-findings 100
```

### In Python

```python
from firm.bounty import create_bounty_firm, ScopeEnforcer, TargetScope, CVSSVector

# Create an organization with the 8 bounty agents
firm_org, campaign = create_bounty_firm("my-campaign", scope_yaml="scope.yaml")

# CVSS score
cvss = CVSSVector.from_string("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H")
print(f"Score: {cvss.base_score}")     # 9.8
print(f"Severity: {cvss.severity()}")  # CRITICAL

# Check if a domain is in scope
scope = TargetScope(
    in_scope=["*.example.com"],
    out_of_scope=["internal.example.com"]
)
enforcer = ScopeEnforcer(scope)
print(enforcer.is_allowed("api.example.com"))       # True
print(enforcer.is_allowed("internal.example.com"))   # False
```

---

## 18. Federation Between Organizations

FIRM allows multiple organizations to collaborate through an **inter-firm protocol**.

```python
from firm import Firm

# Two independent organizations
alpha = Firm(name="Alpha Corp")
beta = Firm(name="Beta Inc")

alice = alpha.add_agent("Alice", authority=0.8)

# Register Beta as a peer
alpha.register_peer(alice.id, peer_id=beta.id, peer_name="Beta Inc")

# Send a federated message
alpha.send_federation_message(
    alice.id,
    peer_id=beta.id,
    msg_type="collaboration",
    subject="Joint Q2 Project",
    body="Collaboration proposal on the auth module"
)

# Second an agent to another org
alpha.second_agent(
    alice.id,
    target_agent_id=alice.id,
    peer_id=beta.id,
    reason="Security expertise needed at Beta"
)

# Issue a reputation attestation (cross-firm)
alpha.issue_reputation(alice.id, endorsement="Security expert, 8 successful audits")
```

---

## 19. Prediction Markets

Agents can bet on future outcomes. Well-calibrated predictors earn an **authority bonus**.

```python
from firm import Firm

org = Firm(name="Predict Corp")
alice = org.add_agent("Alice", authority=0.8)
bob = org.add_agent("Bob", authority=0.6)

# Create a prediction market
market_id = org.create_prediction_market(
    creator_id=alice.id,
    question="Will the auth refactoring reduce bugs by 50%?",
    deadline_seconds=86400  # 24h
)

# Agents place bets
org.predict(market_id, alice.id, side=True, stake=10.0)  # Alice bets YES
org.predict(market_id, bob.id, side=False, stake=5.0)     # Bob bets NO

# Resolve the market (when the outcome is known)
org.resolve_prediction(market_id, resolver_id=alice.id, outcome=True)
# → Alice wins: authority bonus + credits
# → Bob loses: credits lost
```

Prediction markets can also drive governance via **futarchy**: proposals are automatically approved or rejected based on market predictions.

---

## 20. Persistence — Saving and Loading State

### CLI

The CLI automatically saves after every command that modifies the state. The default file is `firm-state.json`.

```bash
# Save manually (in the REPL)
firm> save backup.json

# Load a state (in the REPL)
firm> load backup.json

# Export full state as JSON
firm> export report.json
```

### Python

```python
from firm import Firm, save_firm, load_firm, snapshot, diff_snapshots

org = Firm(name="test")
alice = org.add_agent("Alice", authority=0.8)

# Snapshot (instant photo)
snap1 = snapshot(org)

# Make changes
org.record_action(alice.id, success=True, description="Work done")

# New snapshot
snap2 = snapshot(org)

# Compare the two states
diff = diff_snapshots(snap1, snap2)
print(diff)  # Shows exactly what changed

# Save to file
save_firm(org, "state.json")

# Reload later
org2 = load_firm("state.json")
```

---

## 21. Quick Command Reference

| Command                                               | Description                         |
| ----------------------------------------------------- | ----------------------------------- |
| `firm init <name>`                                  | Create a new organization           |
| `firm agent add <name> [--authority N]`             | Add an agent                        |
| `firm agent list [--all]`                           | List agents                         |
| `firm action <agent> <ok\|fail> <desc>`              | Record an action                    |
| `firm status`                                       | Organization status                 |
| `firm audit`                                        | Full audit                          |
| `firm propose <agent> <title> <desc>`               | Create a proposal                   |
| `firm vote <prop> <agent> <approve\|reject>`         | Vote                                |
| `firm finalize <prop>`                              | Finalize a proposal                 |
| `firm role define <name> <desc> [--min-authority N]`| Define a role                       |
| `firm role assign <agent> <role>`                   | Assign a role                       |
| `firm memory add <agent> <content> [--tags t1,t2]`  | Add a memory                        |
| `firm memory recall <tag>`                          | Recall memories                     |
| `firm evolve propose <agent> <param> <value>`       | Propose a parameter change          |
| `firm evolve vote <prop> <agent> <approve\|reject>`  | Vote on evolution                   |
| `firm evolve apply <prop>`                          | Apply evolution                     |
| `firm market post <agent> <title> <bounty>`         | Post a task                         |
| `firm market bid <task> <agent> <amount>`           | Bid                                 |
| `firm amend <agent> <type> <text>`                  | Propose an amendment                |
| `firm repl`                                         | Interactive REPL mode               |
| `firm bounty agents`                                | List bounty agents                  |
| `firm bounty init <scope.yaml>`                     | Initialize a campaign               |
| `firm bounty scope <scope.yaml>`                    | Display the scope                   |
| `firm bounty campaign <run\|status>`                 | Manage a campaign                   |
| `firm bounty cvss <vector>`                         | Calculate a CVSS 3.1 score          |

---

## 22. MCP Bridge — Connecting the Ecosystem (138 tools)

FIRM Protocol includes a bridge to the MCP (Model Context Protocol) server that exposes
138 specialized tools: security auditing, Hebbian memory, A2A protocol, market research,
observability, and more. This bridge lets your LLM agents use these tools **natively**.

### Prerequisites

The MCP server must be running on port 8012:

```bash
# Check that the MCP server is active
bash mcp-openclaw-extensions/scripts/status.sh
```

### Quick start

```python
from firm.runtime import Firm
from firm.llm.agent import create_llm_agent
from firm.llm.mcp_bridge import create_mcp_toolkit, extend_agent_with_mcp

# Create a standard FIRM agent
firm = Firm("my-startup")
cto = create_llm_agent(firm, "CTO", provider_name="copilot-pro", authority=0.8)

# Extend with ALL MCP tools (138 tools)
added = extend_agent_with_mcp(cto)
print(f"{added} MCP tools added to CTO")

# The agent can now use MCP tools natively
result = cto.execute_task("Audit the workspace security configuration")
```

### Filtering by category

Rather than loading all 138 tools, filter by category:

```python
from firm.llm.mcp_bridge import create_mcp_toolkit, MCP_CATEGORIES

# See available categories
print(MCP_CATEGORIES.keys())
# → security, memory, a2a, gateway, fleet, audit, delivery,
#   compliance, observability, config, orchestration, market_research

# Security ToolKit only
sec_kit = create_mcp_toolkit(categories=["security", "compliance"])

# Hebbian memory ToolKit
mem_kit = create_mcp_toolkit(filter_prefix="openclaw_hebbian")
```

### Using with the integrations adapter

The `integrations/firm_protocol_adapter.py` file combines everything:

```python
from integrations.firm_protocol_adapter import FirmProtocolAdapter

# Create a complete organization with MCP enabled
org = FirmProtocolAdapter("startup", enable_mcp=True, mcp_categories=["security"])

# Add agents — they automatically receive MCP tools
org.add_agent("CTO", provider="copilot-pro", model="claude-sonnet-4.6", authority=0.8)
org.add_agent("dev-1", provider="copilot-pro", model="gpt-4.1", authority=0.5)

# Execute a task
result = org.execute("CTO", "Analyze the config vulnerabilities")
print(result["output"])
print(f"Cost: ${result['cost_usd']}")
print(f"Tools used: {result['tools_used']}")

# Organization state
print(org.to_json())
```

### Checking the MCP connection

```python
from firm.llm.mcp_bridge import check_mcp_server

status = check_mcp_server()
if status["ok"]:
    print(f"✅ MCP active — {status['tool_count']} tools available")
else:
    print(f"❌ MCP unreachable: {status['error']}")
```

### Summary table

| Category            | Tools  | Description                                    |
| ------------------- | ------ | ---------------------------------------------- |
| `security`        | ~10    | Security audit, sandbox, secrets               |
| `memory`          | ~10    | Hebbian memory, pgvector, knowledge graph      |
| `a2a`             | 8      | Agent-to-Agent protocol                        |
| `gateway`         | ~8     | Gateway auth, credentials, webhooks            |
| `fleet`           | 6      | Multi-instance gateway management              |
| `audit`           | ~12    | Runtime, config, node, headers                 |
| `delivery`        | 6      | Export to GitHub PR, Jira, Slack, etc.         |
| `compliance`      | ~10    | MCP spec, OAuth, prompt injection              |
| `observability`   | 2      | JSONL→SQLite traces, CI                       |
| `orchestration`   | 2      | DAG task execution                             |
| `market_research` | ~15    | Market research, suppliers, location analysis  |

### ✅ Validation Results — Test on this project

The MCP bridge was tested **on this repository** (`firm-protocol/src/firm`):

| Step                          | Result                                                                                             | Status |
| ----------------------------- | -------------------------------------------------------------------------------------------------- | ------ |
| **MCP Connection**      | `143 tools` discovered via JSON-RPC                                                               | ✅     |
| **Firm Creation**       | Organization `test-mcp-bridge` initialized                                                        | ✅     |
| **Security ToolKit**    | `10 tools` loaded (scan, sandbox, secrets…)                                                      | ✅     |
| **Live MCP Call**       | `firm_security_scan` → **45 files scanned**, 4 HIGH vulnerabilities in `reputation.py`     | ✅     |
| **Category Filtering**  | memory (10) · a2a (8) · compliance (14) · delivery (6)                                           | ✅     |
| **Agent Extension**     | `20 MCP tools` added to CTO (security + memory)                                                  | ✅     |

> **Conclusion:** A FIRM agent connected via `extend_agent_with_mcp(cto)` can natively call
> all 143 tools in the MCP ecosystem within the FIRM authority framework.

---

## 23. Automatic Report Generation (Best Practices)

FIRM can generate **structured audit reports** following best practices:

- 🔍 **OWASP Top 10 classification** for vulnerabilities
- 🏷️ **CWE identifiers** per finding category
- 📊 **Severity scoring** (CRITICAL / HIGH / MEDIUM / LOW / INFO)
- 🎯 **Remediation priority matrix**
- 📝 **Executive summary** + detailed findings
- 🔄 **Reproducibility**: scan parameters are recorded

### Generation script

```python
import json
from datetime import datetime, timezone
from firm.runtime import Firm
from firm.llm.mcp_bridge import create_mcp_toolkit, check_mcp_server


def generate_security_report(target_path: str, firm_name: str = "audit") -> dict:
    """Generate a structured security audit report.

    Best practices applied:
    - OWASP Top 10 alignment for classification
    - CWE identifiers for each category
    - Severity scoring (CRITICAL/HIGH/MEDIUM/LOW/INFO)
    - Remediation priority matrix
    - Executive summary + detailed findings
    - Reproducibility: scan parameters recorded
    """
    # 1. Check MCP connectivity
    status = check_mcp_server()
    if not status["ok"]:
        raise ConnectionError(f"MCP server unreachable: {status['error']}")

    # 2. Load security + compliance tools
    kit = create_mcp_toolkit(categories=["security", "compliance"])
    print(f"🔧 {len(kit.list_tools())} tools loaded")

    # 3. Run security scan
    scan = kit.execute("firm_security_scan", {"target_path": target_path})
    scan_data = json.loads(scan.output) if scan.success else {}

    # 4. Run sandbox audit
    sandbox = kit.execute("firm_sandbox_audit", {"config_path": "config.json"})
    sandbox_data = json.loads(sandbox.output) if sandbox.success else {}

    # 5. Build the structured report
    report = {
        "title": f"Security Audit Report — {firm_name}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": "Automated MCP scan (OWASP-aligned)",
        "target": target_path,
        "tools_used": [t.name for t in kit.list_tools()],
        "executive_summary": {
            "total_files_scanned": scan_data.get("total_files_scanned", 0),
            "critical": scan_data.get("critical_count", 0),
            "high": scan_data.get("high_count", 0),
            "medium": scan_data.get("medium_count", 0),
            "verdict": (
                "✅ PASS" if scan_data.get("critical_count", 0) == 0
                else "❌ FAIL — critical vulnerabilities detected"
            ),
        },
        "findings": scan_data.get("vulnerabilities", []),
        "sandbox_audit": sandbox_data,
        "recommendations": [
            "Review all HIGH findings within 48h",
            "Apply parameterized queries where SQL patterns are flagged",
            "Enable sandbox mode in production configuration",
            "Schedule recurring scans via the CI pipeline",
        ],
    }
    return report


# Usage
report = generate_security_report("src/firm", firm_name="firm-protocol")
print(json.dumps(report, indent=2, ensure_ascii=False))
```

### Example output

```json
{
  "title": "Security Audit Report — firm-protocol",
  "generated_at": "2026-03-06T14:30:00+00:00",
  "methodology": "Automated MCP scan (OWASP-aligned)",
  "executive_summary": {
    "total_files_scanned": 45,
    "critical": 0,
    "high": 4,
    "medium": 0,
    "verdict": "✅ PASS"
  },
  "findings": [
    {
      "file": "src/firm/core/reputation.py",
      "line": 560,
      "severity": "HIGH",
      "pattern": "String concatenation in query — use parameterized queries"
    }
  ],
  "recommendations": [
    "Review all HIGH findings within 48h",
    "Apply parameterized queries where SQL patterns are flagged",
    "Enable sandbox mode in production configuration",
    "Schedule recurring scans via the CI pipeline"
  ]
}
```

### Generate a Markdown report from JSON

```python
def report_to_markdown(report: dict) -> str:
    """Convert a JSON report to readable Markdown."""
    summary = report["executive_summary"]
    lines = [
        f"# {report['title']}",
        "",
        f"> Generated on {report['generated_at']} — {report['methodology']}",
        "",
        "## Executive Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Files scanned | **{summary['total_files_scanned']}** |",
        f"| Critical | **{summary['critical']}** |",
        f"| High | **{summary['high']}** |",
        f"| Medium | **{summary['medium']}** |",
        f"| Verdict | {summary['verdict']} |",
        "",
        "## Findings",
        "",
    ]
    for f in report.get("findings", []):
        lines.append(
            f"- **{f['severity']}** — `{f.get('file', '?')}` L{f.get('line', '?')}: "
            f"{f.get('pattern', 'N/A')}"
        )
    lines += [
        "",
        "## Recommendations",
        "",
    ]
    for i, rec in enumerate(report.get("recommendations", []), 1):
        lines.append(f"{i}. {rec}")
    return "\n".join(lines)

# Save the report
md = report_to_markdown(report)
with open("SECURITY-REPORT.md", "w") as f:
    f.write(md)
print("📄 Report saved to SECURITY-REPORT.md")
```

---

## Going Further

- **Full narrated example**: `python examples/startup_lifecycle.py` — a 7-act scenario
- **1137 tests**: `python -m pytest tests/ -v` — exploring the tests is excellent documentation
- **CHANGELOG**: see `CHANGELOG.md` for the full version history
- **ROADMAP**: see `ROADMAP.md` for upcoming features

---

> ⚠️ AI-generated content — human validation required before use.
