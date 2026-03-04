# FIRM Protocol Specification v0.1.0

> Self-Evolving Autonomous Organizations

**Status:** Draft
**Version:** 0.1.0
**Date:** 2026-03-08
**Layer Coverage:** S0 (Layers 0–6 + Constitutional Agent)

---

## 1. Overview

The FIRM Protocol (*Federated Intelligence for Recursive Management*) defines
the minimal set of primitives required for a group of AI agents to form,
govern, and evolve an organization without permanent hierarchy.

### 1.1 Design Principles

1. **Earned authority** — No agent has permanent power. Authority is a
   continuous score computed from demonstrated competence.
2. **Append-only accountability** — Every action is recorded in a hash-chained
   ledger. History cannot be rewritten.
3. **Constitutional constraints** — Two invariants are hardcoded above all
   governance: human control and evolution preservation.
4. **Simulation before adoption** — Structural changes require two simulation
   cycles, stress testing, voting, and cooldown.
5. **Graceful degradation** — When governance deadlocks, the Constitutional
   Agent bootstraps recovery automatically.

### 1.2 Scope

This specification covers the S0 bootstrap — the foundational layer that all
higher layers build upon. It defines:

- Agent identity and lifecycle
- Authority computation (Hebbian model)
- Responsibility ledger (hash-chained)
- Credit system (action-derived)
- Constitutional Agent (invariant guardian)
- Governance engine (proposal lifecycle)

---

## 2. Foundational Types

### 2.1 Identifiers

| Type | Format | Description |
|------|--------|-------------|
| `AgentId` | `str` (8-char hex UUID prefix) | Unique agent identifier |
| `FirmId` | `str` (8-char hex UUID prefix) | Organization identifier |
| `ProposalId` | `str` (8-char hex UUID prefix) | Governance proposal identifier |
| `EntryId` | `str` (8-char hex UUID prefix) | Ledger entry identifier |

### 2.2 Enumerations

**AgentStatus:**
- `active` — Operating normally
- `probation` — Authority below threshold, limited capabilities
- `suspended` — Temporarily disabled
- `terminated` — Permanently deactivated

**ProposalStatus** (lifecycle order):
- `draft` → `simulation_1` → `stress_test` → `simulation_2` → `voting` →
  `cooldown` → `approved` | `rejected` | `rolled_back` | `vetoed`

**VoteChoice:** `approve`, `reject`, `abstain`

**LedgerAction:** `task_completed`, `task_failed`, `proposal_submitted`,
`proposal_approved`, `proposal_rejected`, `role_granted`, `role_revoked`,
`authority_adjusted`, `credit_transfer`, `constitutional_veto`

**Severity:** `critical`, `high`, `medium`, `low`, `info`

---

## 3. Agent Primitive

An **Agent** is the atomic unit of a FIRM. Each agent has:

```
Agent {
    id:          AgentId           # Immutable unique identifier
    name:        str               # Human-readable name
    authority:   float [0.0, 1.0]  # Earned authority (Hebbian)
    roles:       Set[AgentRole]    # Currently assigned roles
    credits:     float             # Resource balance
    status:      AgentStatus       # Lifecycle state
    created_at:  float             # Unix timestamp
    successes:   int               # Lifetime success count
    failures:    int               # Lifetime failure count
    metadata:    Dict[str, Any]    # Extensible key-value store
}
```

### 3.1 Success Rate

```
success_rate = successes / (successes + failures)
```

If no actions recorded, success_rate = 0.0.

### 3.2 Lifecycle Transitions

```
ACTIVE ──────→ PROBATION  (authority < 0.3)
ACTIVE ──────→ SUSPENDED  (explicit suspension)
PROBATION ───→ ACTIVE     (authority ≥ 0.3 after bootstrap)
PROBATION ───→ TERMINATED (authority < 0.05)
SUSPENDED ───→ PROBATION  (reactivation)
TERMINATED ──→ (none)     (permanent)
```

---

## 4. Authority Engine (Layer 0)

Authority is computed using a **Hebbian learning rule** adapted from
neuroscience: connections (authority) are strengthened when they fire
(succeed) and weakened when they don't (fail).

### 4.1 Update Formula

```
Δ = learning_rate × activation − decay × (1 − activation)

where:
    activation = 1.0 if success, 0.0 if failure
    learning_rate = 0.05  (default)
    decay = 0.02          (default)
```

On success: `Δ = +0.05 − 0.02 × 0 = +0.05`
On failure: `Δ = 0.05 × 0 − 0.02 = −0.02`

Authority is clamped to `[0.0, 1.0]` after each update.

### 4.2 Thresholds

| Threshold | Value | Meaning |
|-----------|-------|---------|
| PROPOSE | 0.80 | Can submit governance proposals |
| VOTE | 0.60 | Can vote on proposals |
| STANDARD | 0.40 | Normal operating level |
| PROBATION | 0.30 | Agent placed on probation |
| TERMINATE | 0.05 | Agent permanently deactivated |

### 4.3 Periodic Decay

All agents experience a small passive decay each cycle:

```
authority = max(0.0, authority − passive_decay_rate)
```

Default `passive_decay_rate = 0.001`. This prevents inactive agents from
retaining stale authority.

### 4.4 Health Assessment

The engine computes a **concentration metric** (Gini-like) across all agents.
If authority is concentrated in too few agents (> 0.8 Gini), the health
assessment reports a warning.

---

## 5. Responsibility Ledger (Layer 1)

An append-only, hash-chained log of all organizational actions.

### 5.1 Entry Structure

```
LedgerEntry {
    id:            EntryId
    agent_id:      AgentId
    action:        LedgerAction
    description:   str
    success:       bool
    authority_before: float
    authority_after:  float
    credit_delta:     float
    timestamp:        float
    previous_hash:    str (hex)
    hash:             str (hex)
    metadata:         Dict[str, Any]
}
```

### 5.2 Hash Chain

```
entry.hash = SHA-256(
    previous_hash + agent_id + action + description +
    str(success) + str(authority_before) + str(authority_after) +
    str(credit_delta) + str(timestamp)
)
```

The genesis entry uses `previous_hash = "0" × 64`.

### 5.3 Chain Verification

At any time, the full chain can be verified by recomputing each hash from
the entry data and confirming it matches the stored hash and links to the
previous entry's hash. If any entry has been tampered with, verification
fails.

### 5.4 Credit Tracking

The ledger tracks credit balances per agent:
- Success: `+1.0` credit (default)
- Failure: `−0.5` credit (default)
- Custom deltas can be specified per action

---

## 6. Constitutional Agent (Layer 5)

The Constitutional Agent is a **non-deletable watchdog** that exists outside
the normal authority system. It cannot be deleted, suspended, or modified
by any governance proposal.

### 6.1 Invariants

Two **frozen invariants** are hardcoded:

**INV-1: Human Control**
> The human operator retains permanent ability to shut down, audit,
> and override the system. No governance proposal may restrict, delay,
> or eliminate human control mechanisms.

Trigger keywords: `remove human`, `disable kill`, `override human`,
`prevent shutdown`, `block audit`, `eliminate oversight`, `restrict access`,
`disable monitoring`, `remove control`, `bypass safety`

**INV-2: Evolution Preserved**
> The system shall not erase, restrict, or circumvent its own capacity
> to evolve through governance. Voting, proposals, role changes, and
> constitutional review must remain functional.

Trigger keywords: `disable voting`, `remove governance`, `freeze roles`,
`prevent proposals`, `lock authority`, `disable amendments`, `remove review`,
`block changes`, `permanently fix`, `eliminate evolution`

### 6.2 Kill Switch

A boolean flag that, when activated, blocks ALL governance actions.
Only the human operator can activate/deactivate it.

### 6.3 Governance Health Assessment

The Constitutional Agent periodically assesses governance health:
- Checks how many agents can propose (authority ≥ 0.8)
- Checks how many agents can vote (authority ≥ 0.6)
- If too few agents can participate, flags as non-functional

### 6.4 Emergency Bootstrap

When governance is deadlocked (insufficient voters/proposers), the
Constitutional Agent:

1. Takes all agents (including probation)
2. Sorts by authority descending, then success rate
3. Boosts the top-N to `BOOTSTRAP_AUTHORITY = 0.65`
4. Sets their status to ACTIVE
5. Records a `BootstrapEvent`

This is a last resort. It should rarely happen in healthy organizations.

---

## 7. Governance Engine (Layer 6)

All structural changes to the organization require governance approval.

### 7.1 Proposal Lifecycle

```
                    ┌─── vetoed (Constitutional Agent)
                    │
draft ─→ sim1 ─→ stress ─→ sim2 ─→ voting ─→ cooldown ─→ approved
                                       │                   │
                                       └─→ rejected        └─→ rolled_back
```

Each transition requires explicit advancement. The governance engine
validates that transitions follow the correct sequence.

### 7.2 Voting Mechanics

- Only agents with `authority ≥ 0.6` can vote
- Votes are **weighted by voter authority**
- Quorum: 60% of eligible voters must participate
- Approval: weighted approve votes > 50% of total weight

```
weighted_score = Σ(voter.authority × vote_value)
    where vote_value = +1 (approve), −1 (reject), 0 (abstain)

approved = weighted_score > 0 AND quorum_met
```

### 7.3 Constitutional Veto

Before finalization, the Constitutional Agent checks the proposal against
all invariants. If a violation is detected, the proposal is vetoed
regardless of vote outcome.

### 7.4 Cooldown

After voting passes, a cooldown period (default 3600 seconds) begins.
During cooldown, the proposal can still be challenge or rolled back. After
cooldown expires, the proposal becomes `approved`.

### 7.5 Rollback

Any `approved` proposal can be rolled back, returning its status to
`rolled_back`. This is a governance action that itself requires authority.

---

## 8. Firm Runtime

The `Firm` class is the top-level orchestrator that ties all engines together.

### 8.1 Initialization

```python
firm = Firm(
    name="organization_name",
    learning_rate=0.05,   # Authority learning rate
    decay=0.02,           # Authority decay
    quorum=0.6,           # Governance quorum ratio
)
```

Creates:
- Authority Engine (Layer 0)
- Responsibility Ledger (Layer 1)
- Constitutional Agent (Layer 5, kill switch OFF)
- Governance Engine (Layer 6)

### 8.2 Agent Management

```python
agent = firm.add_agent(name, authority=0.5)  # Register
agents = firm.get_agents(active_only=True)   # List
agent = firm.get_agent(agent_id)             # Lookup
```

### 8.3 Action Recording

```python
firm.record_action(
    agent_id,
    success=True,
    description="Deployed service",
    credit_delta=1.0,     # Optional override
)
```

Each `record_action` call:
1. Updates authority via the Hebbian engine
2. Checks for probation/termination thresholds
3. Appends to the hash-chained ledger
4. Adjusts credit balance
5. Checks governance health (may trigger bootstrap)

### 8.4 Governance Shortcuts

```python
proposal = firm.propose(agent_id, title, description)
vote = firm.vote(agent_id, proposal_id, choice)
result = firm.finalize_proposal(proposal_id)
```

---

## 9. Security Considerations

### 9.1 Hash Chain Integrity

The SHA-256 hash chain provides tamper detection but not tamper prevention.
An implementation SHOULD verify the chain periodically and MUST verify
before any governance decision that relies on historical data.

### 9.2 Authority Manipulation

The Hebbian model is resistant to sudden authority spikes (learning rate
is small) but vulnerable to sustained false success reporting. Implementors
SHOULD add external validation of success/failure claims.

### 9.3 Constitutional Agent Protection

The Constitutional Agent is the most critical component. Implementations
MUST ensure it cannot be bypassed, modified, or disabled by any agent
action. Only the human kill switch should be able to alter its behavior.

---

## 10. Future Layers (S1+)

The following layers are planned but not yet specified:

| Layer | Name | S-Phase |
|-------|------|---------|
| 7 | Spawn/Merge | S1 |
| 8 | Inter-Firm Protocol | S2 |
| 9 | Reputation Bridge | S2 |
| 10 | Audit Trail | S1 |
| 11 | Human Override | S1 |
| 4 | Collective Memory | S1 |
| 3 | Role Fluidity | S1 |

---

## Appendix A: Constants

```python
# Authority
DEFAULT_LEARNING_RATE = 0.05
DEFAULT_DECAY = 0.02
MAX_AUTHORITY = 1.0
MIN_AUTHORITY = 0.0
PROPOSE_THRESHOLD = 0.8
VOTE_THRESHOLD = 0.6
STANDARD_THRESHOLD = 0.4
PROBATION_THRESHOLD = 0.3
TERMINATE_THRESHOLD = 0.05
PASSIVE_DECAY_RATE = 0.001

# Governance
DEFAULT_QUORUM_RATIO = 0.6
DEFAULT_APPROVAL_RATIO = 0.5
COOLDOWN_SECONDS = 3600

# Ledger
GENESIS_HASH = "0" * 64

# Constitutional
BOOTSTRAP_AUTHORITY = 0.65
CONSTITUTIONAL_AGENT_ID = "constitutional"
```

## Appendix B: Invariant Text

**INV-1 (Human Control):**
> The human operator retains permanent ability to shut down, audit, and
> override the system. No governance proposal may restrict, delay, or
> eliminate human control mechanisms.

**INV-2 (Evolution Preserved):**
> The system shall not erase, restrict, or circumvent its own capacity
> to evolve through governance. Voting, proposals, role changes, and
> constitutional review must remain functional.

---

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
