"""ChainSignal REST API using FastAPI."""

import asyncio
import json
import os
from datetime import datetime
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
from agent_loop import AutonomousAgentLoop, GuardianAgentLoop
from agent_runtime.event_bus import AgentEventBus
from watch_queue.queue_manager import QueueManager
from wallet_controller.wallet_agent import WalletAgent
from execution_guard.persistence import PersistenceManager

# Instanciamos el servicio centralizado
_agent_service = AgentService()
# Instanciamos el bus de eventos y el loop guardián (instrumentado)
_agent_event_bus = AgentEventBus()
_guardian_loop = GuardianAgentLoop(_agent_service, _agent_event_bus)
_watch_queue = QueueManager()
_wallet_agent = WalletAgent()
_budget_service = AgentBudgetService()
_persistence = PersistenceManager()
_TRACKING_FILE = Path("tracking.json")
_EXECUTIONS_FILE = Path("executions.json")


class FundAgentRequest(BaseModel):
    wallet: str
    tx_hash: str


class TrackWalletRequest(BaseModel):
    wallet: str
    priority: str = "medium"
    interval_seconds: int = 300


class ExecuteAgentRequest(BaseModel):
    wallet: str


class WatchWalletRequest(BaseModel):
    address: str
    label: str | None = None


def _network_name(chain_id: int | None) -> str:
    if chain_id == settings.SEPOLIA_CHAIN_ID:
        return "sepolia"
    if chain_id == 1:
        return "mainnet"
    if chain_id == 137:
        return "polygon"
    return "unknown"


def _compute_activity_snapshot(limit: int = 25) -> dict:
    plans = _persistence.get_all_plans()
    plans_sorted = sorted(plans, key=lambda p: p.created_at, reverse=True)
    recent_actions = []
    total_value_moved_eth = 0.0
    total_success_executions = 0
    total_attempted_executions = 0

    for plan in plans_sorted:
        context = plan.context
        for action in plan.actions:
            recent_actions.append({
                "wallet": plan.wallet,
                "action_type": action.type,
                "status": action.status.value,
                "tx_hash": action.tx_hash,
                "created_at": plan.created_at,
                "risk_score": plan.risk_score
            })
            
            if action.status.value == "SUCCESS":
                total_success_executions += 1
            total_attempted_executions += 1

    recent_actions = recent_actions[:limit]

    return {
        "recent_actions": recent_actions,
        "total_value_moved_eth": total_value_moved_eth,
        "total_success_executions": total_success_executions,
        "total_attempted_executions": total_attempted_executions,
        "success_rate": (total_success_executions / total_attempted_executions * 100) if total_attempted_executions > 0 else 0.0
    }

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and clean up resources during API lifespan."""
    logger.info("Starting ChainSignal API and Guardian Agent Loop...")
    
    # Iniciar el loop guardián en background por defecto
    await _guardian_loop.start()
    
    yield
    
    # Detener el loop de forma segura
    await _guardian_loop.stop()
    logger.info("Shutting down ChainSignal API...")


app = FastAPI(
    title="ChainSignal API",
    version="0.2.2",
    description="Autonomous On-Chain Agent with WDK, ESL and Priority Monitoring Loop.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://chain-signal-project.vercel.app",
        "https://chainsignal-project.onrender.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", summary="Service health check")
def health():
    """Service health check endpoint."""
    activity = _compute_activity_snapshot(limit=10)
    raw_metrics = _agent_service.metrics.to_dict()
    return {
        "status": "ok", 
        "service": "ChainSignal API", 
        "version": "0.2.2",
        "agent_loop": "active" if _guardian_loop.is_running else "inactive",
        "global_metrics": {
            **raw_metrics,
            "execution_attempts": raw_metrics.get("executions_triggered", 0),
            "executions_triggered": activity["total_attempted_executions"],
            "executions_confirmed": activity["total_success_executions"],
            "total_value_moved": activity["total_value_moved_eth"],
        },
        "agent_budget": _budget_service.get_global_state(),
        "learning": _agent_service.learning.summary(),
        "activity": activity,
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
async def analyze_block(block_number: int, window: int = Query(12, ge=3, le=60)):
    if not _budget_service.w3 or not _budget_service.w3.is_connected():
        return JSONResponse(status_code=503, content={"error": "rpc_unavailable", "message": "RPC unavailable for block analysis."})
    try:
        latest_block = await asyncio.to_thread(lambda: _budget_service.w3.eth.block_number)
        chain_id = await asyncio.to_thread(lambda: _budget_service.w3.eth.chain_id)
        network_name = _network_name(chain_id)
        if block_number < 0 or block_number > latest_block:
            mismatch_hint = ""
            if network_name == "sepolia" and block_number > (latest_block * 3):
                mismatch_hint = " This block number looks like another network (possibly Ethereum mainnet)."
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_block_number",
                    "message": f"Block {block_number} is out of range for current network.",
                    "network_latest_block": latest_block,
                    "chain_id": chain_id,
                    "network": network_name,
                    "hint": f"Use a valid {network_name} block number less than or equal to network_latest_block.{mismatch_hint}",
                },
            )

        start_block = max(0, block_number - window + 1)
        block_numbers = list(range(start_block, block_number + 1))

        def _fetch_block(n: int):
            return _budget_service.w3.eth.get_block(n, full_transactions=True)

        blocks = await asyncio.gather(*[asyncio.to_thread(_fetch_block, n) for n in block_numbers])
        tx_counts = []
        values_eth = []
        gas_prices = []
        high_value_txs = 0
        for block in blocks:
            txs = block.get("transactions", []) or []
            tx_count_local = len(txs)
            tx_counts.append(tx_count_local)
            value_wei = sum(int((tx.get("value") or 0)) for tx in txs)
            values_eth.append(float(_budget_service.w3.from_wei(value_wei, "ether")))
            gas_local = int(sum(int((tx.get("gasPrice") or 0)) for tx in txs) / tx_count_local) if tx_count_local > 0 else 0
            gas_prices.append(gas_local)
            high_value_txs += sum(1 for tx in txs if int((tx.get("value") or 0)) >= 10**18)

        tx_count = int(sum(tx_counts) / len(tx_counts)) if tx_counts else 0
        total_value_eth = float(sum(values_eth))
        avg_gas_price = int(sum(gas_prices) / len(gas_prices)) if gas_prices else 0
        tx_density = round(sum(tx_counts) / max(1, len(tx_counts)), 2)
        value_spike = round(max(values_eth), 8) if values_eth else 0.0
        gas_anomaly = bool(avg_gas_price > 1_000_000_000)
        suggested_action = "monitor"
        if high_value_txs > 15 or gas_anomaly:
            suggested_action = "protect"
        elif tx_density > 200:
            suggested_action = "rebalance"

        return {
            "block_number": block_number,
            "decision_context": {
                "what_was_analyzed": f"block:{block_number}",
                "window_blocks": len(block_numbers),
                "who_executes": settings.X402_PAYMENT_RECIPIENT,
                "funds_source": "agent_budget",
            },
            "metrics": {
                "tx_count": tx_count,
                "total_value_eth": round(total_value_eth, 8),
                "avg_gas_price_wei": avg_gas_price,
                "high_value_transactions": high_value_txs,
                "tx_density": tx_density,
                "value_spike_eth": value_spike,
                "gas_anomaly": gas_anomaly,
            },
            "reasoning": "Block-window flow analyzed for tx density, value spikes and gas anomalies.",
            "recommended_action": suggested_action,
            "agent_wallet": settings.X402_PAYMENT_RECIPIENT,
            "action_scope": {"target_wallet": "read_only", "agent_wallet": "execution_enabled"},
            "chain_id": chain_id,
            "network": network_name,
        }
    except Exception as e:
        logger.error("Block analysis error: {}", e)
        try:
            latest_block = await asyncio.to_thread(lambda: _budget_service.w3.eth.block_number)
            chain_id = await asyncio.to_thread(lambda: _budget_service.w3.eth.chain_id)
        except Exception:
            latest_block = None
            chain_id = None
        msg = str(e)
        if "not found" in msg.lower():
            return JSONResponse(
                status_code=404,
                content={
                    "error": "block_not_found",
                    "message": msg,
                    "network_latest_block": latest_block,
                    "chain_id": chain_id,
                    "network": _network_name(chain_id),
                    "hint": "Block may not exist on this network or your RPC provider may not serve this historical block.",
                },
            )
        return JSONResponse(
            status_code=500,
            content={
                "error": "block_analysis_failed",
                "message": msg,
                "network_latest_block": latest_block,
                "chain_id": chain_id,
                "network": _network_name(chain_id),
                "hint": "Try a recent Sepolia block and ensure RPC is healthy.",
            },
        )


@app.post("/agent/budget", summary="Assign budget to agent wallet from verified MetaMask tx")
@app.post("/fund-agent", include_in_schema=False)
async def fund_agent(payload: FundAgentRequest):
    result = _budget_service.verify_and_fund(payload.wallet, payload.tx_hash)
    if not result.get("ok"):
        return JSONResponse(status_code=400, content=result)
    if settings.AGENT_DEMO_MODE:
        activity = _compute_activity_snapshot(limit=10)
        effective_balance = _budget_service.get_effective_balance_eth(payload.wallet)
        if effective_balance > 0 and int(activity["stats"].get("total_executions", 0)) == 0:
            bootstrap_result = await _agent_service.run_pipeline_loop(payload.wallet)
            result["bootstrap_execution"] = bootstrap_result
    return result


@app.get("/agent/budget/{wallet}", summary="Get current agent budget for target wallet")
@app.get("/agent-budget/{wallet}", include_in_schema=False)
@app.get("/agent/state/{wallet}", include_in_schema=False)
async def get_agent_budget(wallet: str):
    budget = _budget_service.get_budget(wallet)
    effective_balance = _budget_service.get_effective_balance_eth(wallet)
    budget["effective_balance_eth"] = effective_balance
    budget["simulation_only"] = effective_balance <= 0
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
    return _compute_activity_snapshot(limit=limit)


@app.get("/agent/state", summary="Global autonomous agent state")
async def agent_state():
    actions = _compute_activity_snapshot(limit=50)
    last_action = actions["recent_actions"][0] if actions["recent_actions"] else None
    learning = _agent_service.learning.summary()
    budget_state = _budget_service.get_global_state()
    pnl = round(float(actions["stats"].get("total_value_moved", 0.0)) - float(budget_state.get("total_spent_eth", 0.0)), 8)
    return {
        "status": "active" if _guardian_loop.is_running else "inactive",
        "agent_wallet": settings.X402_PAYMENT_RECIPIENT,
        "metrics": _agent_service.metrics.to_dict(),
        "budget": budget_state,
        "positions": {"open_positions": 0, "closed_positions": int(actions["stats"].get("total_executions", 0))},
        "pnl": {"estimated_eth": pnl},
        "stats": actions["stats"],
        "learning": learning,
        "last_action": last_action,
    }


@app.get("/agent/learning", summary="Learning store summary and latest signal/outcome")
async def agent_learning():
    return _agent_service.learning.summary()


@app.get("/agent/radar", summary="Tracked wallets radar with priority and freshness")
async def agent_radar(limit: int = 12):
    if not _TRACKING_FILE.exists():
        return {"wallets": []}
    try:
        with _TRACKING_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    wallets = []
    for wallet, cfg in data.items():
        risk_score = cfg.get("last_risk_score", 0)
        reason = "Scheduled autonomous monitoring"
        if risk_score >= 70:
            reason = "High transaction risk profile from recent evaluations"
        elif risk_score >= 35:
            reason = "Moderate behavioral risk requires frequent checks"
        elif cfg.get("priority", "medium") == "high":
            reason = "High priority wallet in monitoring queue"
        wallets.append(
            {
                "wallet": wallet,
                "priority": cfg.get("priority", "medium"),
                "last_evaluation": cfg.get("last_evaluation"),
                "last_risk_score": risk_score,
                "interval_seconds": cfg.get("interval_seconds", 300),
                "reason": reason,
            }
        )
    wallets_sorted = sorted(wallets, key=lambda w: ({"high": 0, "medium": 1, "low": 2}.get(w["priority"], 3), -int(w.get("last_risk_score", 0))))
    return {"wallets": wallets_sorted[:limit]}


def _load_execution_history() -> list[dict]:
    if not _EXECUTIONS_FILE.exists():
        return []
    try:
        with _EXECUTIONS_FILE.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    return sorted(raw, key=lambda x: str(x.get("timestamp", "")), reverse=True)


@app.post("/agent/start", summary="Start guardian watch loop")
async def start_guardian_agent():
    return await _guardian_loop.start()


@app.post("/agent/stop", summary="Request guardian watch loop stop")
async def stop_guardian_agent():
    return await _guardian_loop.stop()


@app.get("/agent/status", summary="Guardian loop status")
async def guardian_status():
    state = _compute_activity_snapshot(limit=10)
    history = _load_execution_history()
    budget = _budget_service.get_global_state()
    
    # Get agent wallet from the wallet agent
    agent_wallet = None
    try:
        agent_wallet = _wallet_agent.get_agent_wallet_address()
    except Exception:
        pass
    
    return {
        "running": _guardian_loop.is_running,
        "stop_requested": _guardian_loop.stop_requested,
        "cycles_completed": _guardian_loop.cycles_completed,
        "wallets_watched": len(_watch_queue.list_wallets()),
        "agent_wallet": agent_wallet,
        "agent_balance_eth": budget.get("total_balance_eth", 0.0),
        "total_eth_moved": state.get("total_value_moved_eth", 0.0),
        "last_action": history[0] if history else None,
    }


@app.get("/agent/history", summary="Execution history")
async def guardian_history():
    return {"executions": _load_execution_history()}


@app.get("/agent/address", summary="Agent wallet address")
async def guardian_address():
    wallet_data = _wallet_agent.create_agent_wallet()
    return {"agent_wallet": wallet_data.get("address")}


@app.post("/agent/watch", summary="Add wallet to watch queue")
async def add_watch_wallet(payload: WatchWalletRequest):
    item = _watch_queue.add_wallet(payload.address, payload.label)
    return {"status": "ok", "wallet": item}


@app.delete("/agent/watch/{address}", summary="Remove wallet from watch queue")
async def delete_watch_wallet(address: str):
    removed = _watch_queue.remove_wallet(address)
    return {"status": "ok" if removed else "not_found", "address": address.lower()}


@app.get("/agent/watch", summary="List watch queue")
async def get_watch_wallets():
    return {"wallets": _watch_queue.list_wallets()}


@app.get("/agent/stream", summary="Guardian loop SSE stream")
async def guardian_stream():
    def _format_sse(payload: dict) -> str:
        return f"data: {json.dumps(payload)}\n\n"

    async def event_generator() -> AsyncGenerator[str, Any]:
        queue = await _guardian_loop.event_bus.subscribe()
        try:
            # Send initial status if agent is not running
            if not _guardian_loop.is_running:
                yield _format_sse({
                    "type": "agent_status",
                    "running": False,
                    "timestamp": datetime.now().isoformat()
                })
            
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield _format_sse(event)
                except asyncio.TimeoutError:
                    # Send heartbeat every 15 seconds
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            return
        finally:
            await _guardian_loop.event_bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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
    uvicorn.run(app, host="0.0.0.0", port=8001)
