# Persistent state + memory for long-running LLM workflows

Long-running LLM workflows need durable state and replayable history, not just stateless prompt chains.
FIRM is a Python-native, zero-dependency runtime that combines append-only execution history, persistent memory, and explicit governance into one local-first system.
It is built for agent builders who want a runtime they can inspect, embed, and evolve without depending on a managed control plane.

## Problem

Most agent stacks are still weak on three runtime concerns:

- Durable state for workflows that outlive a single process or interaction.
- Persistent memory that survives sessions and stays scoped instead of collapsing into a global soup.
- Replayable, auditable execution history that can be inspected without opaque infrastructure.

In practice, this leads to fragile orchestration, weak debugging, and memory layers that are hard to trust once workflows become long-running and multi-step.

## Thesis

FIRM treats execution history and memory as first-class runtime concerns.

- Execution history is persisted in an append-only, SHA-256 hash-chained ledger.
- Memory is persistent, scoped, and updated through a Hebbian reinforcement model.
- Commands and events are separated: REST for mutations, WebSocket for live event streaming.
- The core stays pure Python and zero-dependency for local-first development, with a clean migration path to SQLite/WAL for single-node production.

## Who It Is For

- Founders building OSS-first runtimes or frameworks for LLM and agent workflows.
- Teams that want a local-first runtime with explicit semantics before moving to heavier distributed infrastructure.
- Builders who care about replay, inspectability, and durable workflow state more than abstract "agent vibes".

## Current Surface

- Language: Python 3.11+
- Core: pure Python, stdlib-only
- Packaging: `firm-protocol` on PyPI
- Interfaces: Python SDK, CLI, REST API, WebSocket event stream
- Current API server: FastAPI + WebSocket

## Reliability Model

### Execution semantics

- Workflow and runtime state are persisted through an append-only ledger and JSON state snapshots.
- WebSocket delivery is best-effort. There is no durable event queue in v0.
- Replay is anchored on the durable ledger, not on WebSocket delivery guarantees.
- Exactly-once is not guaranteed.
- The intended contract is at-least-once style recovery via durable history plus idempotent client handling where needed.

### Determinism boundary

- The runtime core, event emission path, ledger append path, and state serialization are deterministic within a single node.
- Non-determinism sits behind adapters: LLM calls, external tools, network access, and any side effects outside the core runtime.
- Replay is therefore a runtime-history replay contract, not a claim that every external side effect can be deterministically reproduced.

### Event stream semantics

- On a single node, FIRM emits events synchronously and appends them to a single append-only ledger, so there is an internal global emission order.
- The public contract, however, is strict ordering per workflow/agent scope only; clients must not depend on a node-wide total order.
- Ordering is guaranteed within a workflow/agent scope; across scopes, ordering is unspecified.
- WebSocket delivery is best-effort (no durable queue yet).
- The ledger is durable and tamper-evident, so clients resume by replaying from a cursor: `GET /ledger?since_hash=<entry_hash>&limit=N` — exclusive semantics (entries after that hash).

## Memory Model

- Memory is a first-class runtime subsystem, not an external bolt-on cache.
- Memory entries are persisted and retrieved by scope rather than mixed into one global store.
- The current implementation supports contribution, recall, reinforcement, and challenge operations.
- Updates follow a Hebbian-inspired weighting model: successful/reinforced knowledge becomes more salient; challenged or decayed memory becomes less prominent over time.
- Retrieval is scoped and weighted, so recall favors high-salience entries rather than raw recency alone.

## Integration Surface

### Python SDK

```python
from firm import Firm

firm = Firm(name="acme")
agent = firm.add_agent("alice", authority=0.7)
firm.record_action(agent.id, success=True, description="Shipped feature")
```

### REST API

Start from a local runtime and interact through explicit endpoints.

```http
POST /firm
Content-Type: application/json

{
  "name": "acme",
  "learning_rate": 0.05,
  "decay": 0.02
}
```

Representative existing endpoints:

- `POST /firm`
- `GET /firm`
- `POST /agents`
- `POST /agents/{agent_id}/execute`
- `POST /agents/{agent_id}/propose`
- `POST /governance/{proposal_id}/vote`
- `GET /ledger?limit=50`
- `GET /tasks?limit=50`

Planned replay contract for the RFC surface:

- `GET /ledger?since_hash=<entry_hash>&limit=N`

### WebSocket

WebSocket is an event stream, not the control plane.

- Endpoint: `/ws/events`
- Model: server pushes lifecycle events from the runtime
- Control path: REST handles commands and mutations

Representative event families already used by the codebase and docs:

- `agent.added`
- `action.recorded`
- `proposal.*`
- `evolution.*`
- `market.*`

Example event shape:

```json
{
  "type": "action.recorded",
  "source": "runtime",
  "timestamp": 1765532456.12,
  "data": {
    "agent_id": "alice",
    "success": true,
    "description": "Shipped feature"
  }
}
```

### CLI

Representative commands:

```bash
firm init my-org
firm action Alice success "Shipped feature on time"
firm memory add Alice "Prefer auditability over hidden automation"
firm status
firm audit
```

## Minimal End-to-End Example

1. Client issues `POST /agents/{agent_id}/execute` or a domain-specific command path.
2. Runtime executes synchronously inside the node.
3. State changes are appended to the ledger.
4. Runtime emits typed events onto the in-process event bus.
5. Subscribed WebSocket clients receive those events in live best-effort fashion.
6. On disconnect, clients recover from the durable ledger using `since_hash`.

## Interface Stability

- The intended public contract is versioned REST endpoints plus versioned WebSocket event types.
- v1 should publish endpoint and event-type stability expectations explicitly.
- A changelog should be the source of truth for contract evolution.

## Why Not SQLite/WAL in v0?

Because the immediate priority for v0 is zero-config, local-first development with fully inspectable persistence and no external dependency surface.
SQLite/WAL is the natural next step for single-node production once indexed queries, stronger crash semantics, and concurrent access become primary concerns.

## Deployment Path

- Local-first dev: pure Python core, JSON persistence, in-process event bus.
- Single-node prod: same runtime model, with SQLite/WAL as the likely persistence upgrade.
- Later: multi-tenant and more distributed transport semantics once the public contracts are stable.

## Non-Goals

- Not a claim of exactly-once distributed execution.
- Not a claim of durable queued delivery over WebSocket in v0.
- Not a polyglot runtime core in v0; the core remains Python-native.
- Not a promise of node-wide ordering as a public contract.

## Proof

- Production-ready open-source codebase.
- 1,137 tests.
- 93.86% coverage.
- Python-native runtime, API, CLI, and event stream already implemented.

## 30-Day v0 Ownership

In a founding/lead engineer role, I can ship a clean v0 package around this runtime shape in ~30 days:

- core runtime + persistent state contract
- memory layer + scoped retrieval
- REST + WebSocket + CLI integration surface
- event semantics + replay contract documented clearly
- docs + example workflows + deployment notes