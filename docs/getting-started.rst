Getting Started
===============

Installation
------------

From source (development mode)::

   git clone https://github.com/firm-protocol/firm.git
   cd firm
   pip install -e ".[dev]"


Core Concepts
-------------

FIRM Protocol implements a 12-layer architecture for self-evolving autonomous organizations:

1. **Authority Engine** — Trust is earned through actions, not assigned by role.
2. **Responsibility Ledger** — Tamper-evident chain of all actions with economic consequences.
3. **Role Fluidity** — Roles are organic assignments based on authority, not static permissions.
4. **Collective Memory** — Shared organizational knowledge with tag-based retrieval.
5. **Constitutional Governance** — Proposals go through simulation → stress test → voting → finalize.
6. **Self-Evolution** — The organization can modify its own parameters through consensus.
7. **Spawn & Merge** — Agents can fork (spawn children) and merge (combine expertise).
8. **Internal Market** — Task marketplace with bounties, bids, and settlements.
9. **Federation** — Cross-organization collaboration via peer connections and agent secondments.
10. **Meta-Constitutional Layer** — The constitution itself can evolve through amendments.
11. **Reputation Bridge** — Import/export reputation attestations across organizations.
12. **Human Override** — The human (DAO, board, founder) always retains the kill switch.


Your First Organization
-----------------------

.. code-block:: python

   from firm.runtime import Firm

   # Create the organization
   org = Firm(name="acme-corp")

   # Add agents with initial authority
   ceo = org.add_agent("ceo", authority=0.9)
   dev = org.add_agent("dev-1", authority=0.5)

   # Record actions — authority adjusts based on outcomes
   org.record_action(ceo.id, success=True, description="Closed Series A")
   org.record_action(dev.id, success=True, description="Shipped v1.0")
   org.record_action(dev.id, success=False, description="Broke production")

   # Check authority
   print(org.get_agent(dev.id).authority)  # Lower after failure

   # Run audit
   report = org.run_audit()
   print(f"Findings: {len(report.findings)}")


Event-Driven Architecture
-------------------------

FIRM emits events for cross-layer communication:

.. code-block:: python

   from firm.runtime import Firm

   org = Firm(name="events-demo")

   # Subscribe to agent events
   def on_agent_added(event):
       print(f"New agent: {event.data['agent_id']}")

   org.events.subscribe("agent.added", on_agent_added)
   org.add_agent("alice")  # prints: New agent: ...


Plugin System
-------------

Extend FIRM with plugins:

.. code-block:: python

   from firm import FirmPlugin

   class AuditLogger(FirmPlugin):
       name = "audit-logger"
       version = "1.0.0"
       description = "Logs all actions to file"

       def on_activate(self, firm):
           firm.events.subscribe("action.recorded", self._log)

       def on_deactivate(self, firm):
           firm.events.unsubscribe("action.recorded", self._log)

       def _log(self, event):
           print(f"[AUDIT] {event.data}")


Serialization
-------------

Save and restore organization state:

.. code-block:: python

   from firm.runtime import Firm
   from firm import save_firm, load_firm, snapshot, diff_snapshots

   org = Firm(name="persistent")
   org.add_agent("alice", authority=0.8)

   # Save to file
   save_firm(org, "org-state.json")

   # Load from file
   restored = load_firm("org-state.json")

   # Snapshots for comparison
   before = snapshot(org)
   org.record_action("alice", success=True, description="Did work")
   after = snapshot(org)

   changes = diff_snapshots(before, after)
   print(changes)
