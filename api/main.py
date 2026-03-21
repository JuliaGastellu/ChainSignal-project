"""ChainSignal REST API using FastAPI."""

import json
import os
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any

from fastapi import FastAPI, Request, Query
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


class ExecuteAgentRequest(BaseModel):
    wallet: str

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
        "global_metrics": _agent_service.metrics.to_dict(),
        "agent_budget": _budget_service.get_global_state(),
    }


@app.get("/report/{wallet_address}", summary="Full free analysis report")
async def get_report(wallet_address: str, request: Request):
    try:
        report = await _agent_service.run_pipeline_core(wallet_address)
        report["target_wallet"] = wallet_address.lower()
        report["agent_wallet"] = settings.X402_PAYMENT_RECIPIENT
        report["action_scope"] = {"target_wallet": "read_only", "agent_wallet": "execution_enabled"}
        report["decision_context"] = {
            "what_was_analyzed": wallet_address.lower(),
            "who_executes": settings.X402_PAYMENT_RECIPIENT,
            "funds_source": "agent_budget",
        }
        return report
    except Exception as e:
        logger.error("Error generating analysis report: {}", e)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": f"Could not generate analysis report: {str(e)}",
            },
        )


@app.get("/analyze/wallet/{wallet_address}", summary="Wallet-level strategic analysis")
async def analyze_wallet(wallet_address: str):
    try:
        report = await _agent_service.run_pipeline_core(wallet_address)
        report["target_wallet"] = wallet_address.lower()
        report["agent_wallet"] = settings.X402_PAYMENT_RECIPIENT
        report["action_scope"] = {"target_wallet": "read_only", "agent_wallet": "execution_enabled"}
        report["decision_context"] = {
            "what_was_analyzed": wallet_address.lower(),
            "who_executes": settings.X402_PAYMENT_RECIPIENT,
            "funds_source": "agent_budget",
        }
        return report
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "wallet_analysis_failed", "message": str(e)})


@app.get("/analyze/block/{block_number}", summary="Block-level strategic analysis")
async def analyze_block(block_number: int):
    if not _budget_service.w3 or not _budget_service.w3.is_connected():
        return JSONResponse(status_code=503, content={"error": "rpc_unavailable", "message": "RPC unavailable for block analysis."})
    try:
        block = _budget_service.w3.eth.get_block(block_number, full_transactions=True)
        txs = block.get("transactions", []) or []
        tx_count = len(txs)
        total_value_wei = sum(int((tx.get("value") or 0)) for tx in txs)
        total_value_eth = float(_budget_service.w3.from_wei(total_value_wei, "ether"))
        avg_gas_price = int(sum(int((tx.get("gasPrice") or 0)) for tx in txs) / tx_count) if tx_count > 0 else 0
        high_value_txs = sum(1 for tx in txs if int((tx.get("value") or 0)) >= 10**18)
        suggested_action = "monitor"
        if high_value_txs > 15:
            suggested_action = "protect"
        elif tx_count > 200:
            suggested_action = "rebalance"

        return {
            "block_number": block_number,
            "decision_context": {
                "what_was_analyzed": f"block:{block_number}",
                "who_executes": settings.X402_PAYMENT_RECIPIENT,
                "funds_source": "agent_budget",
            },
            "metrics": {
                "tx_count": tx_count,
                "total_value_eth": round(total_value_eth, 8),
                "avg_gas_price_wei": avg_gas_price,
                "high_value_transactions": high_value_txs,
            },
            "reasoning": "Block-level flow analyzed for abnormal activity and value density.",
            "recommended_action": suggested_action,
            "agent_wallet": settings.X402_PAYMENT_RECIPIENT,
            "action_scope": {"target_wallet": "read_only", "agent_wallet": "execution_enabled"},
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "block_analysis_failed", "message": str(e)})


@app.post("/agent/budget", summary="Assign budget to agent wallet from verified MetaMask tx")
@app.post("/fund-agent", include_in_schema=False)
async def fund_agent(payload: FundAgentRequest):
    result = _budget_service.verify_and_fund(payload.wallet, payload.tx_hash)
    if not result.get("ok"):
        return JSONResponse(status_code=400, content=result)
    return result


@app.get("/agent/budget/{wallet}", summary="Get current agent budget for target wallet")
@app.get("/agent-budget/{wallet}", include_in_schema=False)
@app.get("/agent/state/{wallet}", include_in_schema=False)
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


@app.get("/agent/actions", summary="Recent autonomous agent actions")
@app.get("/agent-activity", include_in_schema=False)
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


@app.get("/agent/state", summary="Global autonomous agent state")
async def agent_state():
    actions = await agent_activity(limit=50)
    last_action = actions["recent_actions"][0] if actions["recent_actions"] else None
    return {
        "status": "active" if _agent_loop.is_running else "inactive",
        "agent_wallet": settings.X402_PAYMENT_RECIPIENT,
        "metrics": _agent_service.metrics.to_dict(),
        "budget": _budget_service.get_global_state(),
        "stats": actions["stats"],
        "last_action": last_action,
    }


@app.post("/agent/execute", summary="Execute autonomous decision for a target wallet")
async def execute_agent(payload: ExecuteAgentRequest):
    result = await _agent_service.run_pipeline_loop(payload.wallet)
    return {
        "target_wallet": payload.wallet.lower(),
        "agent_wallet": settings.X402_PAYMENT_RECIPIENT,
        "result": result,
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


@app.get("/events/sse/{wallet}", summary="SSE stream alias for wallet analysis")
async def events_sse_wallet(wallet: str):
    return await run_agent_stream(wallet)


@app.get("/events/sse", summary="SSE stream by query parameter")
async def events_sse(wallet: str = Query(...)):
    return await run_agent_stream(wallet)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
