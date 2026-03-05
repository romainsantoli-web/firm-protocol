"""
firm.api.app — FastAPI application for FIRM Protocol.

Exposes the full FIRM API over HTTP:
  - /agents — Agent management + LLM task execution
  - /tasks — Submit tasks to agents, track results
  - /governance — Proposals, voting, finalization
  - /market — Task marketplace
  - /metrics — Usage metrics (Prometheus-compatible)
  - /ws/events — Real-time WebSocket event stream
  - / — Dashboard (served as static HTML)
"""

from __future__ import annotations

import logging
import time
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from firm.runtime import Firm
from firm.llm.agent import LLMAgent, AgentConfig, create_llm_agent
from firm.llm.executor import ExecutionResult
from firm.llm.providers import get_provider

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# App state (module-level singleton)
# ─────────────────────────────────────────────────────────────────────────────

class AppState:
    """Shared application state."""
    def __init__(self):
        self.firm: Firm | None = None
        self.llm_agents: dict[str, LLMAgent] = {}
        self.task_results: list[dict] = []
        self.connected_websockets: list[WebSocket] = []
        self.start_time: float = time.time()

    def get_firm(self) -> Firm:
        if self.firm is None:
            raise HTTPException(status_code=503, detail="FIRM not initialized. POST /firm to create one.")
        return self.firm


state = AppState()


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan
# ─────────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FIRM API starting up")
    yield
    logger.info("FIRM API shutting down")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="FIRM Protocol API",
    description="Self-evolving autonomous organization runtime with real LLM agents.",
    version="0.5.0",
    lifespan=lifespan,
)


# ─────────────────────────────────────────────────────────────────────────────
# Request/Response models
# ─────────────────────────────────────────────────────────────────────────────

class CreateFirmRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    learning_rate: float = 0.05
    decay: float = 0.02


class CreateAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    provider: str = Field(default="claude", description="LLM provider: claude, gpt, mistral, copilot")
    model: str | None = None
    api_key: str | None = Field(default=None, description="API key (uses env var if not set)")
    authority: float = Field(default=0.5, ge=0.0, le=1.0)
    roles: list[str] = Field(default_factory=list)
    working_dir: str | None = None


class ExecuteTaskRequest(BaseModel):
    task: str = Field(min_length=1, max_length=10000)
    context: str = ""


class ProposeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)


class VoteRequest(BaseModel):
    voter_id: str
    choice: str = Field(description="approve or reject")
    reason: str = ""


class PostMarketTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    bounty: float = Field(default=10.0, ge=0.0)


class BidRequest(BaseModel):
    agent_id: str
    amount: float = Field(ge=0.0)


# ─────────────────────────────────────────────────────────────────────────────
# Routes: FIRM lifecycle
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/firm", tags=["firm"])
def create_firm(req: CreateFirmRequest):
    """Create a new FIRM organization."""
    state.firm = Firm(name=req.name, learning_rate=req.learning_rate, decay=req.decay)

    # Wire event broadcasting to WebSocket clients
    def _broadcast(event):
        import asyncio
        for ws in list(state.connected_websockets):
            try:
                asyncio.get_event_loop().call_soon_threadsafe(
                    asyncio.ensure_future, ws.send_json(event)
                )
            except Exception:
                pass

    state.firm.events.subscribe("*", _broadcast)

    return {
        "name": state.firm.name,
        "id": state.firm.id,
        "created_at": state.firm.created_at,
    }


@app.get("/firm", tags=["firm"])
def get_firm():
    """Get FIRM organization info."""
    firm = state.get_firm()
    agents_info = []
    for aid, agent in firm._agents.items():
        agents_info.append({
            "id": agent.id,
            "name": agent.name,
            "authority": round(agent.authority, 4),
            "credits": round(agent.credits, 2),
            "status": agent.status.value if hasattr(agent.status, "value") else str(agent.status),
            "roles": [r.name for r in agent.roles] if agent.roles else [],
            "has_llm": agent.id in state.llm_agents,
        })
    return {
        "name": firm.name,
        "id": firm.id,
        "agents": agents_info,
        "ledger_size": firm.ledger.length,
        "kill_switch": firm.constitution.kill_switch_active,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Routes: Agents
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/agents", tags=["agents"])
def create_agent(req: CreateAgentRequest):
    """Create a new LLM-powered agent."""
    firm = state.get_firm()

    llm_agent = create_llm_agent(
        firm=firm,
        name=req.name,
        provider_name=req.provider,
        model=req.model,
        api_key=req.api_key,
        authority=req.authority,
        working_dir=req.working_dir,
        roles=req.roles if req.roles else None,
    )

    state.llm_agents[llm_agent.agent_id] = llm_agent

    return {
        "agent_id": llm_agent.agent_id,
        "name": llm_agent.name,
        "authority": llm_agent.authority,
        "provider": llm_agent.provider.name,
        "model": llm_agent.provider.model,
        "tools_available": len(llm_agent._get_available_toolkit().list_tools()),
    }


@app.get("/agents", tags=["agents"])
def list_agents():
    """List all agents with their stats."""
    firm = state.get_firm()
    agents = []
    for aid, agent in firm._agents.items():
        info = {
            "id": agent.id,
            "name": agent.name,
            "authority": round(agent.authority, 4),
            "credits": round(agent.credits, 2),
            "status": agent.status.value if hasattr(agent.status, "value") else str(agent.status),
            "roles": [r.name for r in agent.roles] if agent.roles else [],
        }
        if agent.id in state.llm_agents:
            llm = state.llm_agents[agent.id]
            info["llm"] = llm.get_stats()
        agents.append(info)
    return {"agents": agents}


@app.get("/agents/{agent_id}", tags=["agents"])
def get_agent(agent_id: str):
    """Get detailed agent info."""
    firm = state.get_firm()
    agent = firm._agents.get(agent_id)
    if not agent:
        raise HTTPException(404, f"Agent not found: {agent_id}")

    info = {
        "id": agent.id,
        "name": agent.name,
        "authority": round(agent.authority, 4),
        "credits": round(agent.credits, 2),
        "status": agent.status.value if hasattr(agent.status, "value") else str(agent.status),
        "roles": [r.name for r in agent.roles] if agent.roles else [],
    }
    if agent.id in state.llm_agents:
        info["llm"] = state.llm_agents[agent.id].get_stats()
    return info


# ─────────────────────────────────────────────────────────────────────────────
# Routes: Task execution (the core!)
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/agents/{agent_id}/execute", tags=["tasks"])
def execute_task(agent_id: str, req: ExecuteTaskRequest):
    """
    Execute a task with an LLM agent.

    The agent uses real tools (git, terminal, files, HTTP) and results
    are automatically recorded in FIRM's authority system.
    """
    if agent_id not in state.llm_agents:
        raise HTTPException(404, f"LLM agent not found: {agent_id}. Create one first with POST /agents.")

    llm_agent = state.llm_agents[agent_id]
    result = llm_agent.execute_task(task=req.task, context=req.context)

    result_dict = result.to_dict()
    result_dict["agent_name"] = llm_agent.name
    result_dict["authority_after"] = round(llm_agent.authority, 4)
    state.task_results.append(result_dict)

    return result_dict


@app.get("/tasks", tags=["tasks"])
def list_task_results(limit: int = Query(default=50, ge=1, le=500)):
    """List recent task execution results."""
    return {"results": state.task_results[-limit:]}


# ─────────────────────────────────────────────────────────────────────────────
# Routes: Governance
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/agents/{agent_id}/propose", tags=["governance"])
def propose(agent_id: str, req: ProposeRequest):
    """Create a governance proposal."""
    firm = state.get_firm()
    return firm.propose(agent_id, req.title, req.description)


@app.post("/governance/{proposal_id}/vote", tags=["governance"])
def vote(proposal_id: str, req: VoteRequest):
    """Vote on a proposal."""
    firm = state.get_firm()
    return firm.vote(proposal_id, req.voter_id, req.choice, req.reason)


@app.post("/governance/{proposal_id}/simulate", tags=["governance"])
def simulate(proposal_id: str, success: bool = True, impact: str = "nominal", risk: float = 0.1):
    """Run a simulation round for a proposal (must run 3 times)."""
    firm = state.get_firm()
    return firm.simulate_proposal(proposal_id, success, impact, risk)


@app.post("/governance/{proposal_id}/finalize", tags=["governance"])
def finalize(proposal_id: str):
    """Finalize a proposal after voting + simulations."""
    firm = state.get_firm()
    return firm.finalize_proposal(proposal_id)


# ─────────────────────────────────────────────────────────────────────────────
# Routes: Market
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/market/tasks", tags=["market"])
def post_market_task(req: PostMarketTaskRequest, poster_id: str = Query(...)):
    """Post a task on the market."""
    firm = state.get_firm()
    return firm.post_task(poster_id, req.title, req.description, req.bounty)


@app.post("/market/tasks/{task_id}/bid", tags=["market"])
def market_bid(task_id: str, req: BidRequest):
    """Bid on a market task."""
    firm = state.get_firm()
    return firm.bid_on_task(task_id, req.agent_id, req.amount)


# ─────────────────────────────────────────────────────────────────────────────
# Routes: Metrics
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/metrics", tags=["metrics"])
def metrics():
    """Prometheus-compatible metrics endpoint."""
    lines = []
    lines.append("# HELP firm_uptime_seconds Time since server start.")
    lines.append("# TYPE firm_uptime_seconds gauge")
    lines.append(f"firm_uptime_seconds {time.time() - state.start_time:.1f}")

    if state.firm:
        lines.append("# HELP firm_agents_total Number of agents.")
        lines.append("# TYPE firm_agents_total gauge")
        lines.append(f"firm_agents_total {len(state.firm._agents)}")

        lines.append("# HELP firm_ledger_entries_total Ledger entry count.")
        lines.append("# TYPE firm_ledger_entries_total counter")
        lines.append(f"firm_ledger_entries_total {state.firm.ledger.length}")

        lines.append("# HELP firm_tasks_executed_total Tasks executed.")
        lines.append("# TYPE firm_tasks_executed_total counter")
        lines.append(f"firm_tasks_executed_total {len(state.task_results)}")

        lines.append("# HELP firm_tasks_succeeded_total Successful tasks.")
        lines.append("# TYPE firm_tasks_succeeded_total counter")
        success = sum(1 for r in state.task_results if r.get("status") == "completed")
        lines.append(f"firm_tasks_succeeded_total {success}")

        # Per-agent authority
        for aid, agent in state.firm._agents.items():
            lines.append(f'firm_agent_authority{{agent="{agent.name}"}} {agent.authority:.4f}')

        # Token usage
        total_tokens = sum(r.get("input_tokens", 0) + r.get("output_tokens", 0) for r in state.task_results)
        lines.append("# HELP firm_tokens_total Total tokens used.")
        lines.append("# TYPE firm_tokens_total counter")
        lines.append(f"firm_tokens_total {total_tokens}")

        total_cost = sum(r.get("cost_usd", 0) for r in state.task_results)
        lines.append("# HELP firm_cost_usd_total Total cost in USD.")
        lines.append("# TYPE firm_cost_usd_total counter")
        lines.append(f"firm_cost_usd_total {total_cost:.6f}")

    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain")


# ─────────────────────────────────────────────────────────────────────────────
# Routes: Ledger
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/ledger", tags=["ledger"])
def get_ledger(limit: int = Query(default=50, ge=1, le=1000)):
    """Get recent ledger entries."""
    firm = state.get_firm()
    entries = firm.ledger._entries[-limit:]
    return {
        "entries": [
            {
                "agent_id": str(e.agent_id),
                "action": e.action.value if hasattr(e.action, "value") else str(e.action),
                "description": e.description,
                "outcome": e.outcome,
                "timestamp": e.timestamp,
            }
            for e in entries
        ],
        "total": firm.ledger.length,
    }


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket: Real-time events
# ─────────────────────────────────────────────────────────────────────────────

@app.websocket("/ws/events")
async def websocket_events(ws: WebSocket):
    """Stream FIRM events in real-time via WebSocket."""
    await ws.accept()
    state.connected_websockets.append(ws)
    logger.info("WebSocket client connected (total: %d)", len(state.connected_websockets))
    try:
        while True:
            # Keep connection alive by receiving pings
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        state.connected_websockets.remove(ws)
        logger.info("WebSocket client disconnected (total: %d)", len(state.connected_websockets))


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard (served at /)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", tags=["dashboard"], response_class=HTMLResponse)
def dashboard():
    """Serve the FIRM dashboard."""
    dashboard_path = Path(__file__).parent.parent / "dashboard" / "index.html"
    if dashboard_path.exists():
        return HTMLResponse(dashboard_path.read_text())
    return HTMLResponse("<h1>FIRM Protocol</h1><p>Dashboard not found. Place index.html in src/firm/dashboard/</p>")


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "uptime_s": round(time.time() - state.start_time, 1),
        "firm_active": state.firm is not None,
        "agents": len(state.llm_agents),
        "tasks_executed": len(state.task_results),
    }
