"""
FastAPI main application — REST endpoints and WebSocket for real-time updates.
"""

import asyncio
import json
import logging
import uuid
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models import RunRequest, RunSummary, AgentEvent, RunPhase
from app.agent import Agent

# ── Logging ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── App ──────────────────────────────────────────────────────

app = FastAPI(
    title="Autonomous DevOps Agent",
    description="AI-powered CI/CD pipeline fixer",
    version="1.0.0",
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory state ──────────────────────────────────────────

# Active runs: run_id -> RunSummary
active_runs: dict[str, dict] = {}

# WebSocket connections: run_id -> list of WebSocket
ws_connections: dict[str, list[WebSocket]] = {}

# ── REST Endpoints ───────────────────────────────────────────


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Autonomous DevOps Agent",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    """Health check."""
    return {"status": "ok"}


@app.post("/api/runs", response_model=dict)
async def start_run(request: RunRequest):
    """
    Start a new agent run.
    Returns immediately with a run_id; progress is streamed via WebSocket.
    """
    run_id = str(uuid.uuid4())[:8]

    active_runs[run_id] = {
        "run_id": run_id,
        "status": "started",
        "request": request.model_dump(),
        "summary": None,
    }

    # Launch the agent in the background
    asyncio.create_task(_execute_run(run_id, request))

    return {
        "run_id": run_id,
        "status": "started",
        "message": f"Agent run started. Connect to WebSocket at /ws/{run_id} for live updates.",
    }


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    """Get the status/summary of a run."""
    if run_id not in active_runs:
        raise HTTPException(status_code=404, detail="Run not found")
    return active_runs[run_id]


@app.get("/api/runs")
async def list_runs():
    """List all runs."""
    return list(active_runs.values())


# ── WebSocket Endpoint ───────────────────────────────────────


@app.websocket("/ws/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    """
    WebSocket endpoint for real-time agent updates.
    Clients connect here after starting a run.
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for run {run_id}")

    # Register connection
    if run_id not in ws_connections:
        ws_connections[run_id] = []
    ws_connections[run_id].append(websocket)

    try:
        # Keep the connection alive until closed
        while True:
            # We don't expect messages from the client, but read to detect disconnect
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                # Send a ping to keep alive
                try:
                    await websocket.send_json({"event_type": "ping"})
                except Exception:
                    break
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for run {run_id}")
    finally:
        if run_id in ws_connections:
            ws_connections[run_id] = [
                ws for ws in ws_connections[run_id] if ws != websocket
            ]


# ── Background Agent Execution ───────────────────────────────


async def _execute_run(run_id: str, request: RunRequest):
    """Execute the agent run and broadcast events via WebSocket."""
    agent = Agent()

    async def emit_event(event: AgentEvent):
        """Broadcast event to all WebSocket clients for this run."""
        event_dict = event.model_dump()
        
        # Ensure 'phase' is a string for JSON serialization
        if event_dict.get("phase"):
            p = event_dict["phase"]
            if hasattr(p, "value"):
                event_dict["phase"] = p.value
            else:
                event_dict["phase"] = str(p)

        clients = ws_connections.get(run_id, [])
        disconnected = []
        for ws in clients:
            try:
                await ws.send_json(event_dict)
            except Exception:
                disconnected.append(ws)

        # Clean up disconnected clients
        for ws in disconnected:
            if run_id in ws_connections:
                ws_connections[run_id] = [
                    c for c in ws_connections[run_id] if c != ws
                ]

    try:
        active_runs[run_id]["status"] = "running"
        summary = await agent.run(request, emit=emit_event)
        active_runs[run_id]["status"] = "completed"
        active_runs[run_id]["summary"] = summary.model_dump()
    except Exception as e:
        logger.exception(f"Run {run_id} failed")
        active_runs[run_id]["status"] = "failed"
        active_runs[run_id]["error"] = str(e)

        # Notify clients of failure
        error_event = AgentEvent(
            event_type="error",
            phase=RunPhase.FAILED,
            message=f"Agent run failed: {str(e)}",
        )
        await emit_event(error_event)


# ── Run with Uvicorn ─────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
