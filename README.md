# FIRM Protocol

**The physics of self-evolving autonomous organizations.**

Authority is earned, not assigned. Memory is a debate, not a database.
Structure is liquid, not fixed.

---

## What is FIRM?

FIRM (*Federated Intelligence for Recursive Management*) is a protocol that
defines how groups of AI agents can form, govern, and evolve organizations
**without permanent hierarchy**.

Unlike traditional multi-agent frameworks where humans hardcode roles and
permissions, FIRM implements a self-regulating system where:

- **Authority is Hebbian** — agents that succeed gain influence; agents that
  fail lose it. No fixed titles.
- **Every action is ledgered** — an append-only, hash-chained responsibility
  ledger tracks what happened, who did it, and whether it worked.
- **Governance is constitutional** — two invariants can never be violated:
  a human can always shut it down, and the system cannot erase its own
  capacity to evolve.
- **Change requires proof** — proposals go through simulation, stress testing,
  voting, and cooldown before taking effect.

## Architecture

FIRM is built on 12 layers (S0 implements the first 7):

| Layer | Name | Purpose |
|-------|------|---------|
| 0 | Authority Engine | Hebbian authority scores — earned, not assigned |
| 1 | Responsibility Ledger | Append-only hash-chained action log |
| 2 | Credit System | Resource allocation based on contribution |
| 3 | Role Fluidity | Dynamic role assignment based on authority |
| 4 | Collective Memory | Shared knowledge with weighted recall |
| 5 | Constitutional Agent | Invariant guardian — non-deletable watchdog |
| 6 | Governance Engine | 2-cycle validation for all structural changes |
| 7 | Spawn/Merge | Agent lifecycle management |
| 8 | Inter-Firm Protocol | Federation between organizations |
| 9 | Reputation Bridge | Cross-firm authority portability |
| 10 | Audit Trail | External accountability interface |
| 11 | Human Override | Guaranteed human control surface |

### Two Invariants

These are hardcoded constraints that **no governance proposal can override**:

1. **Human Control** — The human can always shut it down.
   Kill switch, audit access, and override authority are permanent.

2. **Evolution Preserved** — The system cannot erase its own capacity to evolve.
   Governance mechanisms, voting rights, and the constitutional agent itself
   are protected.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Try it
python -c "
from firm import Firm

org = Firm(name='acme')

# Add agents — they start with moderate authority
alice = org.add_agent('alice', authority=0.5)
bob = org.add_agent('bob', authority=0.5)

# Record successes and failures — authority adjusts automatically
org.record_action(alice.id, success=True, description='Shipped feature')
org.record_action(bob.id, success=False, description='Broke CI')

# Check the organization state
status = org.status()
print(f'Agents: {status[\"agent_count\"]}')
print(f'Ledger entries: {status[\"ledger_entries\"]}')
print(f'Chain valid: {status[\"chain_valid\"]}')

# Alice (who succeeded) can now propose changes
proposal = org.propose(
    alice.id,
    title='Add deployment role',
    description='Create a dedicated deployment specialist role',
)
print(f'Proposal: {proposal.title} ({proposal.status.value})')
"
```

## Key Concepts

### Authority Engine (Layer 0)

Uses a Hebbian-inspired formula:

```
Δauthority = learning_rate × activation − decay × (1 − activation)
```

Where `activation = 1.0` on success, `0.0` on failure. Default learning rate
is 0.05, decay is 0.02. Authority is bounded `[0.0, 1.0]`.

Thresholds:
- **0.8** — Can propose governance changes
- **0.6** — Can vote on proposals
- **0.4** — Standard operating authority
- **0.3** — Probation threshold
- **0.05** — Termination threshold

### Responsibility Ledger (Layer 1)

Every recorded action produces an immutable, hash-chained entry:

```
entry.hash = SHA-256(previous_hash + agent_id + action + timestamp + ...)
```

The chain can be verified end-to-end at any time. Tampering is detectable.

### Governance (Layer 6)

Proposals follow a strict lifecycle:

```
draft → simulation_1 → stress_test → simulation_2 → voting → cooldown → approved
                                                                       → rejected
                                                                       → rolled_back
```

Votes are weighted by voter authority. The Constitutional Agent can veto
any proposal that violates an invariant.

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests with coverage
python -m pytest tests/ -v --cov=firm --cov-report=term-missing

# Lint
ruff check src/ tests/
```

## License

MIT

---

⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
