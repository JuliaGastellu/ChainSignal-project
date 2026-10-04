import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator, Any

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from loguru import logger
from web3 import Web3

from api.rutas_org import auth, demo, invitaciones, orgs
from api.sesion import requiere_sesion, respuesta_de_error
from identidad.servicio import ErrorIdentidad
from infra.config import settings
from infra.red import REDES, red_del_producto
from services.agent_service import AgentService, READ_ONLY_SCOPE

# Runtime comercial de solo lectura (E01) con identidad por organización (E02).
# Esta API no importa ni construye WalletAgent, ServicioWDK, ExecutionRunner,
# AgentExecutor ni el loop Guardian: ninguna ruta puede firmar, transferir,
# hacer swap ni desplegar. Las rutas económicas heredadas responden 403 y las
# rutas globales sin organización responden 410. Todo recurso privado vive bajo
# /orgs/{org_id}/ y exige sesión, membresía y rol (api/rutas_org.py).

_agent_service = AgentService()
# Cliente RPC de lectura para el análisis de bloques, en la red del producto.
_red = red_del_producto()
_rpc_lectura = Web3(Web3.HTTPProvider(settings.ETHEREUM_RPC_URL)) if settings.ETHEREUM_RPC_URL else None


def _network_name(chain_id: int | None) -> str:
    red = REDES.get(chain_id) if chain_id is not None else None
    return red.nombre if red else "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """No arranco loops en el lifespan: con varios workers HTTP se multiplicaban
    y uno de ellos podía ejecutar (A22). El monitoreo corre en worker_lectura.py."""
    logger.info("Starting ChainSignal API in {} mode (no background loops).", settings.CHAINSIGNAL_MODE)
    from infra.db import engine, init_db

    # Registro solo la ruta local para diagnosticar permisos, nunca credenciales.
    if engine.dialect.name == "sqlite":
        from pathlib import Path
        import os

        ruta_base = Path(engine.url.database).resolve()
        logger.warning(
            "Uso SQLite temporal: ruta={}, directorio_existe={}, directorio_escribible={}",
            ruta_base, ruta_base.parent.exists(), os.access(ruta_base.parent, os.W_OK),
        )

    # Con DB_AUTO_MIGRATE migro (desarrollo); sin él solo verifico que el
    # esquema esté en head y, si no, no arranco (E08).
    init_db(engine)
    yield
    logger.info("Shutting down ChainSignal API...")


ECONOMIC_ROUTES_DISABLED = {
    "error": "economic_route_disabled",
    "message": "This ChainSignal runtime is read-only: funding, execution, signing and agent-loop routes are disabled.",
}

LEGACY_GLOBAL_ROUTE_GONE = {
    "error": "legacy_route_gone",
    "message": "This route exposed data without an organization. Use /orgs/{org_id}/... with a session.",
}


async def _economic_route_disabled():
    """Respondo 403 sin tocar presupuesto, WDK ni loops, con o sin sesión."""
    return JSONResponse(status_code=403, content={**ECONOMIC_ROUTES_DISABLED, "mode": settings.CHAINSIGNAL_MODE})


async def _legacy_global_route_gone():
    """Respondo 410 sin leer estado: estas rutas mezclaban datos de todas las organizaciones."""
    return JSONResponse(status_code=410, content=LEGACY_GLOBAL_ROUTE_GONE)


app = FastAPI(
    title="ChainSignal API",
    version="0.3.0",
    description="Read-only on-chain analysis and monitoring API with organization-scoped access.",
    lifespan=lifespan,
)
app.state.agent_service = _agent_service

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "Last-Event-ID"],
)


@app.exception_handler(ErrorIdentidad)
async def _error_de_identidad(request: Request, error: ErrorIdentidad):
    return JSONResponse(status_code=error.estado, content=respuesta_de_error(error))


@app.exception_handler(Exception)
async def _error_interno(request: Request, error: Exception):
    # Registro el detalle en el servidor y nunca lo devuelvo al cliente.
    logger.exception("Unhandled error on {} {}", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "internal_error", "message": "Internal error."})


from api.rutas_comerciales import comercial  # noqa: E402

app.include_router(comercial)
app.include_router(auth)
app.include_router(invitaciones)
app.include_router(demo)
app.include_router(orgs)


@app.get("/health", summary="Service health check")
def health():
    """Health público y mínimo: no expone métricas, presupuestos, historial ni configuración."""
    return {"status": "ok", "service": "ChainSignal API", "version": "0.3.0", "mode": settings.CHAINSIGNAL_MODE}


@app.get("/ready", summary="Readiness check", include_in_schema=False)
def ready():
    """Listo para recibir tráfico: la base responde y el esquema está en head.

    /health es la liveness (el proceso responde); /ready decide si el balanceador
    me manda requests. No expongo el detalle del error.
    """
    from sqlalchemy import text

    from infra.db import engine, revision_actual, revision_head

    try:
        with engine.connect() as conexion:
            conexion.execute(text("SELECT 1"))
        if revision_actual(engine) != revision_head():
            return JSONResponse(status_code=503, content={"status": "not_ready", "reason": "schema"})
    except Exception as error:
        logger.warning("Readiness check failed: {}", type(error).__name__)
        return JSONResponse(status_code=503, content={"status": "not_ready", "reason": "database"})
    return {"status": "ready"}


@app.get("/metrics", include_in_schema=False)
def metricas(request: Request):
    """Métricas operativas en formato Prometheus. Sin METRICS_TOKEN la ruta no existe."""
    from fastapi.responses import PlainTextResponse

    from identidad.seguridad import tokens_iguales
    from operacion.metricas import a_prometheus, medir

    esperado = settings.METRICS_TOKEN
    recibido = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()
    if not esperado:
        return JSONResponse(status_code=404, content={"error": "not_found", "message": "Not found."})
    if not recibido or not tokens_iguales(recibido, esperado):
        return JSONResponse(status_code=401, content={"error": "not_authenticated", "message": "Metrics token required."})
    return PlainTextResponse(a_prometheus(medir()), media_type="text/plain; version=0.0.4")


def _reporte_de_lectura(report: dict, wallet_address: str) -> dict:
    report["target_wallet"] = wallet_address.lower()
    report["agent_wallet"] = None
    report["action_scope"] = dict(READ_ONLY_SCOPE)
    report["decision_context"] = {
        "what_was_analyzed": wallet_address.lower(),
        "who_executes": None,
        "funds_source": None,
    }
    return report


@app.get("/report/{wallet_address}", summary="Full free analysis report", dependencies=[Depends(requiere_sesion)])
async def get_report(wallet_address: str):
    try:
        return _reporte_de_lectura(await _agent_service.run_pipeline_core(wallet_address), wallet_address)
    except Exception as e:
        logger.error("Error generating analysis report: {}", e)
        return JSONResponse(status_code=500, content={"error": "internal_server_error", "message": "Could not generate analysis report."})


@app.get("/analyze/wallet/{wallet_address}", summary="Wallet-level strategic analysis", dependencies=[Depends(requiere_sesion)])
async def analyze_wallet(wallet_address: str):
    try:
        return _reporte_de_lectura(await _agent_service.run_pipeline_core(wallet_address), wallet_address)
    except Exception as e:
        logger.error("Wallet analysis error: {}", e)
        return JSONResponse(status_code=500, content={"error": "wallet_analysis_failed", "message": "Could not analyze wallet."})


@app.get("/analyze/block/{block_number}", summary="Block-level strategic analysis", dependencies=[Depends(requiere_sesion)])
async def analyze_block(block_number: int, window: int = Query(12, ge=3, le=60)):
    if not _rpc_lectura or not _rpc_lectura.is_connected():
        return JSONResponse(status_code=503, content={"error": "rpc_unavailable", "message": "RPC unavailable for block analysis."})
    try:
        latest_block = await asyncio.to_thread(lambda: _rpc_lectura.eth.block_number)
        chain_id = await asyncio.to_thread(lambda: _rpc_lectura.eth.chain_id)
        if chain_id != _red.chain_id:
            # No mezclo redes: si el RPC apunta a otra cadena, no respondo con sus datos.
            return JSONResponse(status_code=503, content={"error": "wrong_network", "expected_chain_id": _red.chain_id, "chain_id": chain_id})
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
            return _rpc_lectura.eth.get_block(n, full_transactions=True)

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
            values_eth.append(float(_rpc_lectura.from_wei(value_wei, "ether")))
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
                "who_executes": None,
                "funds_source": None,
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
            "agent_wallet": None,
            "action_scope": dict(READ_ONLY_SCOPE),
            "chain_id": chain_id,
            "network": network_name,
        }
    except Exception as e:
        logger.error("Block analysis error: {}", e)
        try:
            latest_block = await asyncio.to_thread(lambda: _rpc_lectura.eth.block_number)
            chain_id = await asyncio.to_thread(lambda: _rpc_lectura.eth.chain_id)
        except Exception:
            latest_block = None
            chain_id = None
        msg = str(e)
        if "not found" in msg.lower():
            return JSONResponse(
                status_code=404,
                content={
                    "error": "block_not_found",
                    "message": "Block analysis failed.",
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
                "message": "Block analysis failed.",
                "network_latest_block": latest_block,
                "chain_id": chain_id,
                "network": _network_name(chain_id),
                "hint": "Try a recent block on the configured network and ensure the RPC is healthy.",
            },
        )


for _ruta, _metodo in (
    ("/agent/budget", "POST"), ("/fund-agent", "POST"), ("/agent/execute", "POST"),
    ("/agent/start", "POST"), ("/agent/stop", "POST"), ("/agent/address", "GET"),
):
    app.add_api_route(_ruta, _economic_route_disabled, methods=[_metodo], include_in_schema=False)

for _ruta, _metodo in (
    ("/track-wallet", "POST"), ("/agent/watch", "GET"), ("/agent/watch", "POST"), ("/agent/watch/{address}", "DELETE"),
    ("/agent/radar", "GET"), ("/agent/history", "GET"), ("/agent/actions", "GET"), ("/agent-activity", "GET"),
    ("/agent/state", "GET"), ("/agent/state/{wallet}", "GET"), ("/agent/budget/{wallet}", "GET"),
    ("/agent-budget/{wallet}", "GET"), ("/agent/learning", "GET"), ("/agent/status", "GET"), ("/agent/stream", "GET"),
):
    app.add_api_route(_ruta, _legacy_global_route_gone, methods=[_metodo], include_in_schema=False)


@app.get("/run-agent/{wallet}", summary="Run agent analysis stream", dependencies=[Depends(requiere_sesion)])
@app.get("/ejecutar-agente/{wallet}", include_in_schema=False, dependencies=[Depends(requiere_sesion)])
async def run_agent_stream(wallet: str):
    """
    Analizo la wallet y emito eventos SSE en tiempo real. Es solo lectura: abrir,
    repetir o reconectar este stream nunca ejecuta acciones on-chain.
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
                    "detalle": "Analysis failed.",
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


@app.get("/events/sse/{wallet}", summary="SSE stream alias for wallet analysis", dependencies=[Depends(requiere_sesion)])
async def events_sse_wallet(wallet: str):
    return await run_agent_stream(wallet)


@app.get("/events/sse", summary="SSE stream by query parameter", dependencies=[Depends(requiere_sesion)])
async def events_sse(wallet: str = Query(...)):
    return await run_agent_stream(wallet)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
