Architecture
============

FIRM Protocol implements a 12-layer architecture. Each layer is independent
but communicates through the Event Bus.

.. code-block:: text

   ┌─────────────────────────────────────────────┐
   │ Layer 12: Human Override (Kill Switch)       │
   ├─────────────────────────────────────────────┤
   │ Layer 11: Reputation Bridge                  │
   ├─────────────────────────────────────────────┤
   │ Layer 10: Meta-Constitutional                │
   ├─────────────────────────────────────────────┤
   │ Layer 9:  Federation                         │
   ├─────────────────────────────────────────────┤
   │ Layer 8:  Internal Market                    │
   ├─────────────────────────────────────────────┤
   │ Layer 7:  Spawn & Merge                      │
   ├─────────────────────────────────────────────┤
   │ Layer 6:  Self-Evolution                     │
   ├─────────────────────────────────────────────┤
   │ Layer 5:  Constitutional Governance          │
   ├─────────────────────────────────────────────┤
   │ Layer 4:  Collective Memory                  │
   ├─────────────────────────────────────────────┤
   │ Layer 3:  Role Fluidity                      │
   ├─────────────────────────────────────────────┤
   │ Layer 2:  Responsibility Ledger              │
   ├─────────────────────────────────────────────┤
   │ Layer 1:  Authority Engine                   │
   └─────────────────────────────────────────────┘


Two Non-Negotiable Invariants
-----------------------------

1. **The human can always shut it down** — Layer 12 cannot be disabled or removed.
2. **The system cannot erase its own capacity to evolve** — Layer 6 is immutable at the protocol level.


Cross-Layer Communication
-------------------------

All layers communicate through the :class:`~firm.core.events.EventBus`:

- ``firm.created`` — FIRM initialized
- ``agent.added`` — New agent registered
- ``action.recorded`` — Agent action logged
- ``proposal.*`` — Governance lifecycle events
- ``evolution.*`` — Parameter change events
- ``market.*`` — Task/bid events

Plugins can subscribe to any event pattern, including wildcards (e.g., ``agent.*``).


Governance Flow
---------------

Proposals go through a 5-phase lifecycle:

1. **DRAFT** — Proposal created
2. **SIMULATION_1** — First impact simulation
3. **STRESS_TEST** — Adversarial stress test
4. **SIMULATION_2** — Post-stress validation
5. **VOTING** — Authority-weighted voting

Only after all simulations pass can voting begin. Voting is weighted by
agent authority — higher-authority agents have more influence.
