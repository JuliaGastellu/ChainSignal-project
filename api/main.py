"""ChainSignal REST API using FastAPI."""

import json
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from loguru import logger

from services.agent_service import AgentService
from services.servicio_x402 import GatewayX402
from infra.config import settings
from agent_loop import AutonomousAgentLoop

# Instanciamos el servicio centralizado
_agent_service = AgentService()
# Instanciamos el loop autónomo
_agent_loop = AutonomousAgentLoop(_agent_service)

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


@app.get("/report/{wallet_address}", summary="Protected analysis report")
async def get_report(wallet_address: str, request: Request):
    """Protected analysis report endpoint with x402 payment challenge."""
    x402 = GatewayX402()
    headers_lower = {k.lower(): v for k, v in request.headers.items()}
    valid, reason = x402.verificar_acceso(headers_lower)
    
    if not valid:
        challenge = x402.emitir_challenge(f"analysis report for wallet {wallet_address}")
        challenge_dict = challenge.to_dict()
        challenge_dict["message"] = reason
        challenge_dict["simulation_mode"] = not settings.is_production
        return JSONResponse(status_code=402, content=challenge_dict)

    try:
        report = await _agent_service.run_pipeline_core(wallet_address)
        return report
    except Exception as e:
        logger.error("Error generating advanced x402 report: {}", e)
        return JSONResponse(status_code=500, content={
            "error": "internal_server_error",
            "message": f"Could not generate advanced report: {str(e)}",
        })


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
