"""ChainSignal REST API using FastAPI."""

import json
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from loguru import logger
from pydantic import BaseModel

from services.agent_service import AgentService
from services.agent_budget_service import AgentBudgetService
from infra.config import settings
from agent_loop import AutonomousAgentLoop
from execution_guard.persistence import PersistenceManager

# Instanciamos el servicio centralizado
_agent_service = AgentService()
# Instanciamos el loop autónomo
_agent_loop = AutonomousAgentLoop(_agent_service)
_budget_service = AgentBudgetService()
_persistence = PersistenceManager()
_TRACKING_FILE = Path("tracking.json")


class FundAgentRequest(BaseModel):
    wallet: str
    tx_hash: str


class TrackWalletRequest(BaseModel):
    wallet: str
    priority: str = "medium"
    interval_seconds: int = 300

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and clean up resources during API lifespan."""
    logger.info("Starting ChainSignal API and Autonomous Agent Loop...")
    
    # Iniciar el loop autónomo en background
    await _agent_loop.start()
    
    yield
    
    # Detener el loop de forma segura
    await _agent_loop.stop()
    logger.info("Shutting down ChainSignal API...")


app = FastAPI(
    title="ChainSignal API",
    version="0.2.2",
    description="Autonomous On-Chain Agent with WDK, ESL and Priority Monitoring Loop.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", summary="Service health check")
def health():
    """Service health check endpoint."""
    return {
        "status": "ok", 
        "service": "ChainSignal API", 
        "version": "0.2.2",
        "agent_loop": "active" if _agent_loop.is_running else "inactive",
        "global_metrics": _agent_service.metrics.to_dict()
    }


@app.get("/report/{wallet_address}", summary="Deprecated premium report endpoint")
async def get_report(wallet_address: str, request: Request):
    return JSONResponse(
        status_code=410,
        content={
            "deprecated": True,
            "message": "Premium report was removed. Use /run-agent/{wallet} for full analysis stream.",
            "wallet": wallet_address,
        },
    )


@app.post("/fund-agent", summary="Associate MetaMask funding tx with an agent budget")
async def fund_agent(payload: FundAgentRequest):
    result = _budget_service.verify_and_fund(payload.wallet, payload.tx_hash)
    if not result.get("ok"):
        return JSONResponse(status_code=400, content=result)
    return result


@app.get("/agent-budget/{wallet}", summary="Get current agent budget for wallet")
async def get_agent_budget(wallet: str):
    budget = _budget_service.get_budget(wallet)
    budget["simulation_only"] = float(budget.get("balance_eth", 0.0)) <= 0
    return budget


@app.post("/track-wallet", summary="Add or update tracked wallet for autonomous loop")
async def track_wallet(payload: TrackWalletRequest):
    wallet = payload.wallet.lower()
    if not _TRACKING_FILE.exists():
        data = {}
    else:
        try:
            with _TRACKING_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    data[wallet] = {
        "priority": payload.priority if payload.priority in {"high", "medium", "low"} else "medium",
        "last_evaluation": data.get(wallet, {}).get("last_evaluation"),
        "last_risk_score": data.get(wallet, {}).get("last_risk_score", 0),
        "interval_seconds": max(30, int(payload.interval_seconds)),
    }
    with _TRACKING_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    return {"status": "ok", "wallet": wallet, "tracking": data[wallet]}


@app.get("/agent-activity", summary="Recent autonomous agent actions")
async def agent_activity(limit: int = 25):
    plans = _persistence.get_all_plans()
    plans_sorted = sorted(plans, key=lambda p: p.get("created_at", 0), reverse=True)
    recent_actions = []
    total_value_moved_eth = 0.0

    for plan in plans_sorted:
        context = plan.get("context", {}) or {}
        reason = context.get("reason", "")
        created_at = plan.get("created_at")
        for action in plan.get("actions", []) or []:
            status = action.get("status")
            if status not in {"SUCCESS", "FAILED"}:
                continue
            params = action.get("params", {}) or {}
            moved_wei = 0
            if action.get("type") == "TRANSFER":
                moved_wei = int(params.get("value_wei") or 0)
            elif action.get("type") == "SWAP":
                moved_wei = int(params.get("amount_wei") or 0)
            moved_eth = float(moved_wei / 1e18) if moved_wei > 0 else 0.0
            total_value_moved_eth += moved_eth
            tx_hash = action.get("tx_hash")
            explorer = f"https://sepolia.etherscan.io/tx/{tx_hash}" if tx_hash else None
            recent_actions.append(
                {
                    "wallet": plan.get("wallet"),
                    "timestamp": created_at,
                    "type": action.get("type"),
                    "status": status,
                    "tx_hash": tx_hash,
                    "value_moved_eth": moved_eth,
                    "reason": reason,
                    "explorer": explorer,
                }
            )
            if len(recent_actions) >= limit:
                break
        if len(recent_actions) >= limit:
            break

    return {
        "recent_actions": recent_actions,
        "stats": {
            "total_executions": len([a for a in recent_actions if a.get("status") == "SUCCESS"]),
            "total_value_moved": round(total_value_moved_eth, 8),
        },
    }


@app.get("/run-agent/{wallet}", summary="Run agent analysis stream")
@app.get("/ejecutar-agente/{wallet}", include_in_schema=False)
async def run_agent_stream(wallet: str):
    """
    Runs the full agent pipeline with real-time SSE event streaming via AgentService.
    """
    def _format_sse(payload: dict) -> str:
        return f"data: {json.dumps(payload)}\n\n"

    async def event_generator() -> AsyncGenerator[str, Any]:
        sent_final = False
        last_paso = None

        try:
            async for chunk in _agent_service.run_pipeline_stream(wallet):
                if isinstance(chunk, str) and chunk.startswith("data: "):
                    try:
                        data_raw = chunk[6:].strip()
                        if data_raw:
                            payload = json.loads(data_raw)
                            paso = str(payload.get("paso", "")).lower()
                            last_paso = paso or last_paso
                            if paso in {"decision_final", "execution_final_status"}:
                                sent_final = True
                    except Exception:
                        pass

                yield chunk

        except Exception as e:
            logger.error(f"SSE error: {e}")
            sent_final = True
            yield _format_sse(
                {
                    "paso": "decision_final",
                    "estado": "error",
                    "detalle": f"Execution failed: {str(e)}",
                    "data": {"decision": "ERROR"},
                    "source": "api",
                }
            )
        finally:
            if not sent_final:
                yield _format_sse(
                    {
                        "paso": "decision_final",
                        "estado": "completed",
                        "detalle": "Stream completed.",
                        "data": {"decision": "COMPLETED"},
                        "source": "api",
                    }
                )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
