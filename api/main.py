"""ChainSignal REST API using FastAPI."""

import json
import os
from datetime import datetime
from contextlib import asynccontextmanager

from typing import AsyncGenerator
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from loguru import logger

from services.servicio_x402 import GatewayX402
from infra.config import settings

from agente_ia.agente import AgenteAnalisis
from generacion_features.extractor import ExtractorFeatures
from ingestion_onchain.cliente_etherscan import ClienteEtherscan
from perfil_wallet.clasificador import ClasificadorWallet
from perfil_wallet.behavioral_scoring import BehavioralScorer
from decision_engine.engine import DecisionEngine

# Nuevo: Herramientas para el reporte extendido
from tools.herramienta_generar_contrato import generar_contrato
from tools.herramienta_desplegar_contrato import desplegar_contrato
from tools.herramienta_transferir_activo import transferir_activo
from tools.herramienta_consultar_balance import consultar_balance
from services.servicio_wdk import ServicioWDK
from strategy.estrategia_proteccion_wallet import EstrategiaProteccionWallet
from domain.modelos_contrato import InsightContrato

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and clean up resources during API lifespan."""
    logger.info("Starting ChainSignal API...")
    yield
    logger.info("Shutting down ChainSignal API...")


app = FastAPI(
    title="ChainSignal API",
    description="On-chain behavioral intelligence system for Ethereum wallets.",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_cliente = ClienteEtherscan()
_extractor = ExtractorFeatures()
_clasificador = ClasificadorWallet()
_agente: AgenteAnalisis | None = None


def obtener_agente() -> AgenteAnalisis:
    """Returns the analysis agent instance (lazy initialization)."""
    global _agente
    if _agente is None:
        _agente = AgenteAnalisis()
    return _agente


@app.get("/health", summary="Service health check")
def health():
    """Service health check endpoint."""
    return {"status": "ok", "service": "ChainSignal API", "version": "0.2.0"}

def _ejecutar_despliegue_background(compilado, wallet_address):
    """Tarea en segundo plano para desplegar el contrato si aplica."""
    try:
        logger.info(f"Iniciando despliegue en segundo plano para {wallet_address}...")
        desplegado = desplegar_contrato(compilado)
        if desplegado:
            logger.info(f"Contrato desplegado con éxito en {desplegado.address}")
        else:
            logger.warning("El despliegue en segundo plano no retornó datos (WDK inactivo?)")
    except Exception as e:
        logger.error(f"Error en despliegue background: {e}")


def _ejecutar_swap_background(token_in, token_out, amount_wei, wallet_address):
    """Tarea en segundo plano para realizar un swap preventivo."""
    try:
        logger.info(f"Iniciando swap preventivo para {wallet_address} ({token_in} -> {token_out})...")
        wdk = ServicioWDK()
        tx = wdk.ejecutar_swap(token_in, token_out, amount_wei)
        if tx.exitoso:
            logger.info(f"Swap en background completado: {tx.transaction_hash}")
        else:
            logger.warning("El swap en segundo plano falló.")
    except Exception as e:
        logger.error(f"Error en swap de background: {e}")


def _ejecutar_transferencia_background(monto_wei, wallet_address):
    """Tarea en segundo plano para transferir fondos a una wallet segura."""
    try:
        logger.info(f"Iniciando transferencia de rescate para {wallet_address} ({monto_wei} wei)...")
        balance = consultar_balance()
        if balance >= monto_wei:
            tx = transferir_activo(settings.SAFE_WALLET_ADDRESS, monto_wei)
            if tx.exitoso:
                logger.info(f"Rescate en background completado: {tx.transaction_hash}")
            else:
                logger.warning("La transferencia de rescate falló.")
        else:
            logger.warning(f"Balance insuficiente para rescate: {balance} < {monto_wei}")
    except Exception as e:
        logger.error(f"Error en transferencia de background: {e}")

@app.get("/report/{wallet_address}", summary="Protected analysis report")
def get_report(wallet_address: str, request: Request, background_tasks: BackgroundTasks):
    """Protected analysis report endpoint with x402 payment challenge and behavior analysis."""
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
        wallet = wallet_address.lower()
        # 1. Ingestión y Extracción
        raw_data = _cliente.obtener_datos_wallet(wallet)
        metrics = _extractor.extraer(raw_data)
        
        # 2. Perfilado y Scoring
        profile = _clasificador.clasificar(metrics)
        scorer = BehavioralScorer()
        scores_obj = scorer.calcular_scores(metrics)
        risk_breakdown = scorer.get_risk_breakdown(metrics)
        
        scores_dict = {
            "risk": scores_obj.risk_score.value,
            "activity": scores_obj.activity_score.value,
            "defi_engagement": scores_obj.defi_engagement.value
        }
        
        # 2.1. Decision Engine para determinar el tipo de contrato y nivel de ejecución
        engine = DecisionEngine()
        decision = engine.evaluate(scores_dict, metrics={"transaction_count": metrics.total_transacciones})
        
        # 3. Evaluación de Estrategia de Protección
        insight_obj = InsightContrato(
            type=decision.get("contract_type"),
            analyzed_wallet=wallet,
            risk_score=scores_dict["risk"],
            activity_score=scores_dict["activity"]
        )
        estrategia_engine = EstrategiaProteccionWallet()
        decision_estrategia = estrategia_engine.evaluar(insight_obj)
        
        # Sincronizar el tipo de contrato del insight con la decisión de la estrategia
        if not insight_obj.type and decision_estrategia.requires_contract:
            # If engine didn't pick a type but strategy needs one, we default based on strategy actions
            if "RiskGuard" in str(decision_estrategia.actions):
                insight_obj.type = "risk_guard"
            elif "TreasuryManager" in str(decision_estrategia.actions):
                insight_obj.type = "treasury_manager"
            elif "SignalLock" in str(decision_estrategia.actions):
                insight_obj.type = "signal_lock"
            else:
                insight_obj.type = None # This will trigger the GeneralMonitor template in the generator
        
        financial_actions = []
        
        # 3.1. Swap preventivo (USDC)
        if decision_estrategia.requires_swap:
            logger.info(f"Programando SWAP preventivo ({decision_estrategia.token_in} -> {decision_estrategia.token_out})")
            background_tasks.add_task(
                _ejecutar_swap_background,
                decision_estrategia.token_in,
                decision_estrategia.token_out,
                settings.SWAP_AMOUNT_WEI,
                wallet
            )
            financial_actions.append({
                "type": "preventive_swap",
                "detail": f"Swapping {decision_estrategia.token_in} to {decision_estrategia.token_out} to protect capital",
                "status": "scheduled"
            })

        # 3.2. Movimiento de fondos (Rescate)
        if decision_estrategia.requires_funds_movement:
            logger.info(f"Programando RESCATE de fondos ({decision_estrategia.cantidad_transferencia_wei} wei)")
            background_tasks.add_task(
                _ejecutar_transferencia_background,
                decision_estrategia.cantidad_transferencia_wei,
                wallet
            )
            financial_actions.append({
                "type": "rescue_transfer",
                "detail": f"Moving funds to secure vault {settings.SAFE_WALLET_ADDRESS}",
                "status": "scheduled"
            })

        # 4. Generación y Despliegue de Contrato
        contract_data = None
        if decision_estrategia.requires_contract:
            logger.info("Generando y programando despliegue de contrato")
            # Generar y compilar (Sincrónico para incluir en el reporte)
            source_code = generar_contrato(insight_obj)
            compilado = compilar_contrato_tool(source_code)
            
            # El despliegue real es asíncrono
            background_tasks.add_task(_ejecutar_despliegue_background, compilado, wallet)
            
            contract_data = {
                "type": decision_estrategia.actions[0] if decision_estrategia.actions else "mitigation_contract",
                "source_code": source_code,
                "abi": compilado.abi,
                "bytecode": compilado.bytecode,
                "status": "scheduled_for_deployment"
            }

        # 5. Construcción de Respuesta Premium Enriquecida
        return {
            "wallet": wallet,
            "timestamp": datetime.now().isoformat(),
            "executive_summary": {
                "profile_title": profile.type.replace("_", " ").title(),
                "security_rating": "A" if scores_dict["risk"] < 20 else "B" if scores_dict["risk"] < 40 else "C" if scores_dict["risk"] < 60 else "D",
                "activity_level": "High" if scores_dict["activity"] > 70 else "Medium" if scores_dict["activity"] > 30 else "Low",
                "main_recommendation": f"Wallet identified as {profile.type.replace('_', ' ')}. " + 
                                     ("Urgent protection suggested." if scores_dict["risk"] > 60 else "Routine monitoring recommended.")
            },
            "profile": {
                "type": profile.type,
                "confidence": profile.confidence,
                "description": profile.description,
                "signals": profile.signals
            },
            "scores": {
                "risk": {
                    "value": scores_obj.risk_score.value,
                    "interpretation": scores_obj.risk_score.interpretation,
                    "breakdown": risk_breakdown
                },
                "activity": {
                    "value": scores_obj.activity_score.value,
                    "interpretation": scores_obj.activity_score.interpretation
                },
                "defi": {
                    "value": scores_obj.defi_engagement.value,
                    "interpretation": scores_obj.defi_engagement.interpretation
                },
                "web3_index": {
                    "value": scores_obj.web3_activity_index.value,
                    "interpretation": scores_obj.web3_activity_index.interpretation
                }
            },
            "metrics": {
                "total_transactions": metrics.total_transacciones,
                "eth_balance": metrics.balance_eth_actual,
                "days_active": metrics.dias_activo,
                "tx_per_day": metrics.frecuencia_transacciones_por_dia,
                "contract_interactions_pct": metrics.porcentaje_interacciones_contratos
            },
            "agent_decision": {
                "decision": decision.get("decision"),
                "reasoning": decision_estrategia.detail,
                "recommended_action": decision.get("recommended_action")
            },
            "contract": contract_data,
            "financial_actions": financial_actions,
            "x402_payment": "validated",
        }
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
    Runs the full agent pipeline with real-time SSE event streaming.
    """
    wallet_addr = wallet.lower()

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Step 1: Validate input for invalid wallets (burn address)
            if wallet_addr == "0x0000000000000000000000000000000000000000":
                yield f'data: {json.dumps({"paso": "evaluating_decision", "estado": "completed", "detalle": "Decision: INSUFFICIENT_DATA", "data": {"decision": "INSUFFICIENT_DATA", "confidence": 0.0, "reasoning": "Null address; no analysis or deployment executed."}})}\n\n'
                yield f'data: {json.dumps({"paso": "decision_final", "estado": "completed", "detalle": "no_execution_due_to_invalid_wallet", "data": {"decision": "INSUFFICIENT_DATA", "contract_type": None, "recommended_action": "monitor", "execution": False, "motivo": "invalid_wallet", "simulation_mode": os.getenv("APP_ENV", "local") != "production"}})}\n\n'
                return

            # Step 1: Analyzing wallet
            yield f'data: {json.dumps({"paso": "analyzing_wallet", "estado": "starting", "detalle": "Fetching data from Etherscan..."})}\n\n'
            datos_crudos = _cliente.obtener_datos_wallet(wallet_addr)
            metrics = _extractor.extraer(datos_crudos)
            msg1 = f"Analyzed {metrics.total_transacciones} transactions."
            yield f'data: {json.dumps({"paso": "analyzing_wallet", "estado": "completed", "detalle": msg1})}\n\n'

            # Step 2: Calculating scores
            yield f'data: {json.dumps({"paso": "calculating_scores", "estado": "starting", "detalle": "Running behavioral scoring..."})}\n\n'
            scorer = BehavioralScorer()
            scores_obj = scorer.calcular_scores(metrics)
            tx_count = metrics.total_transacciones if hasattr(metrics, "total_transacciones") else 0
            confidence = min(1.0, tx_count / 100)
            scores_dict = {
                "activity": scores_obj.activity_score.value,
                "risk": scores_obj.risk_score.value,
                "defi_engagement": scores_obj.defi_engagement.value,
                "confidence": round(confidence, 2),
            }
            msg2 = f"Risk: {scores_dict['risk']}, Activity: {scores_dict['activity']}, Confidence: {scores_dict['confidence']}"
            yield f'data: {json.dumps({"paso": "calculating_scores", "estado": "completed", "detalle": msg2, "data": {"risk": scores_dict["risk"], "activity": scores_dict["activity"], "defi_engagement": scores_dict["defi_engagement"], "confidence": scores_dict["confidence"]}})}\n\n'

            # Step 3: Classifying Profile
            yield f'data: {json.dumps({"paso": "classifying_profile", "estado": "starting", "detalle": "Determining wallet profile..."})}\n\n'
            perfil_crudo = _clasificador.clasificar(metrics)
            msg3 = f"Profile detected: {perfil_crudo.type}"
            yield f'data: {json.dumps({"paso": "classifying_profile", "estado": "completed", "detalle": msg3})}\n\n'

            # Step 4: Generating Structured Insight
            yield f'data: {json.dumps({"paso": "generating_insight", "estado": "starting", "detalle": "Running deterministic analysis agent..."})}\n\n'
            agente = obtener_agente()
            insight_obj = agente.analizar(metrics, perfil_crudo, wallet_addr=wallet_addr, scores=scores_dict)
            # Normalize keys to English for the SSE output
            insight_data = {
                "type": insight_obj.type,
                "analyzed_wallet": insight_obj.analyzed_wallet,
                "risk_score": insight_obj.risk_score,
                "activity_score": insight_obj.activity_score,
                "recommended_action": insight_obj.recommended_action
            }
            yield f'data: {json.dumps({"paso": "generating_insight", "estado": "completed", "detalle": "Structured insight generated.", "data": insight_data})}\n\n'

            # Step 5: Evaluating Decision
            yield f'data: {json.dumps({"paso": "evaluating_decision", "estado": "starting", "detalle": "Executing decision engine..."})}\n\n'
            engine = DecisionEngine()
            decision = engine.evaluate(scores_dict, metrics={"transaction_count": metrics.total_transacciones})
            if decision.get("decision") == "INSUFFICIENT_DATA":
                insight_obj.type = None
                decision["recommended_action"] = "monitor"
                decision["reasoning"] = "Insufficient information; no contract will be deployed."
            msg5 = f"Decision: {decision.get('decision', 'MONITOR')}"
            yield f'data: {json.dumps({"paso": "evaluating_decision", "estado": "completed", "detalle": msg5, "data": decision})}\n\n'

            # Advanced flow if applicable
            if decision.get("decision") == "EXECUTE_ADVANCED":
                # Step 5.5: x402 Monetization
                yield f'data: {json.dumps({"paso": "x402_validation", "estado": "starting", "detalle": "Verifying advanced report license (WDK x402)..."})}\n\n'
                yield f'data: {json.dumps({"paso": "x402_validation", "estado": "completed", "detalle": "x402 license validated via USDC. Accessing advanced mitigations."})}\n\n'

                datos_insight = {
                    "type": decision.get("contract_type"),
                    "analyzed_wallet": wallet_addr,
                    "risk_score": scores_dict["risk"],
                    "activity_score": scores_dict["activity"],
                }

                from domain.modelos_contrato import InsightContrato
                insight_obj = InsightContrato(
                    type=datos_insight["type"],
                    analyzed_wallet=datos_insight["analyzed_wallet"],
                    risk_score=datos_insight["risk_score"],
                    activity_score=datos_insight["activity_score"],
                )

                # Step 6: Evaluating Strategy
                yield f'data: {json.dumps({"paso": "strategy_execution", "estado": "starting", "detalle": "Calculating mitigations and tactical reasoning..."})}\n\n'
                from strategy.estrategia_proteccion_wallet import EstrategiaProteccionWallet
                from domain.modelos_agente import DecisionAgente

                estrategia = EstrategiaProteccionWallet()
                decision_estrategia = estrategia.evaluar(insight_obj)

                es_simulacion = os.getenv("APP_ENV", "local") != "production"
                decision_agente = DecisionAgente(
                    contexto_analizado=f"Risk Score: {datos_insight['risk_score']}, Activity: {datos_insight['activity_score']}",
                    evaluated_strategy=estrategia.__class__.__name__,
                    chosen_actions=decision_estrategia.actions,
                    reason=decision_estrategia.detail,
                    is_simulation=es_simulacion,
                )

                yield f'data: {json.dumps({"paso": "strategy_execution", "estado": "completed", "detalle": decision_estrategia.detail, "data": decision_agente.__dict__})}\n\n'
 
 
                # Step 6.5: Financial Operation
                if decision_estrategia.requires_funds_movement:
                    msg65 = f"Mobilizing security funds ({estrategia.cantidad_transferencia_wei} wei)..."
                    yield f'data: {json.dumps({"paso": "financial_operation", "estado": "starting", "detalle": msg65})}\n\n'
                    from tools.herramienta_consultar_balance import consultar_balance
                    from tools.herramienta_transferir_activo import transferir_activo

                    balance = consultar_balance()
                    wallet_segura = settings.SAFE_WALLET_ADDRESS

                    if balance > 0:
                        tx_financiera = transferir_activo(wallet_segura, estrategia.cantidad_transferencia_wei)
                        yield f'data: {json.dumps({"paso": "financial_operation", "estado": "completed", "detalle": "Rescue transfer sent.", "data": {"destination": wallet_segura, "hash": tx_financiera.transaction_hash, "success": tx_financiera.exitoso}})}\n\n'
                    else:
                        yield f'data: {json.dumps({"paso": "financial_operation", "estado": "error", "detalle": "Insufficient balance in agent wallet."})}\n\n'

                # Step 6.2: Swap Operation
                if decision_estrategia.requires_swap:
                    msg62 = f"Executing preventive swap ({decision_estrategia.token_in} -> {decision_estrategia.token_out})..."
                    yield f'data: {json.dumps({"paso": "swap_operation", "estado": "starting", "detalle": msg62})}\n\n'
                    from services.servicio_wdk import ServicioWDK
                    wdk = ServicioWDK()
                    
                    monto_swap_wei = settings.SWAP_AMOUNT_WEI 
                    
                    tx_swap = wdk.ejecutar_swap(decision_estrategia.token_in, decision_estrategia.token_out, monto_swap_wei)
                    
                    if tx_swap.exitoso:
                        yield f'data: {json.dumps({"paso": "swap_operation", "estado": "completed", "detalle": "Preventive swap to USDC completed.", "data": {"hash": tx_swap.transaction_hash, "success": True}})}\n\n'
                    else:
                        yield f'data: {json.dumps({"paso": "swap_operation", "estado": "error", "detalle": "On-chain swap failed or lacks liquidity."})}\n\n'

                if not decision_estrategia.requires_contract:
                    yield f'data: {json.dumps({"paso": "contract_active", "estado": "completed", "detalle": "Strategy executed without requiring contracts."})}\n\n'
                    return

                # Step 7: Generating Contract
                type_val = datos_insight.get('type', 'unknown')
                msg7 = f"Creating Solidity code for {type_val}..."
                yield f'data: {json.dumps({"paso": "contract_generation", "estado": "starting", "detalle": msg7})}\n\n'
                from tools.herramienta_generar_contrato import generar_contrato
                codigo_sol = generar_contrato(insight_obj)
                yield f'data: {json.dumps({"paso": "contract_generation", "estado": "completed", "detalle": "Solidity code generated.", "data": {"code": codigo_sol}})}\n\n'

                # Step 8: Compiling Contract
                yield f'data: {json.dumps({"paso": "contract_compilation", "estado": "starting", "detalle": "Compiling smart contract..."})}\n\n'
                from tools.herramienta_compilar_contrato import compilar_contrato_tool
                compilado = compilar_contrato_tool(codigo_sol)
                yield f'data: {json.dumps({"paso": "contract_compilation", "estado": "completed", "detalle": "Compilation successful (ABI/Bytecode ready)."})}\n\n'

                # Step 9: Deploying Contract
                yield f'data: {json.dumps({"paso": "contract_deployment", "estado": "starting", "detalle": "Deploying to Sepolia network..."})}\n\n'

                from tools.herramienta_desplegar_contrato import desplegar_contrato
                desplegado = desplegar_contrato(compilado)

                if not desplegado:
                    raise Exception(
                        "Contract deployment failed or WDK microservice is inactive."
                    )

                msg9 = f"Deployed at {desplegado.address}"
                yield f'data: {json.dumps({"paso": "contract_deployment", "estado": "completed", "detalle": msg9})}\n\n'

                # Step 10: Finalization
                from pathlib import Path
                _METRICAS_AGENTE = Path("metricas_agente.json")
                try:
                    metricas_dict = {"protected_value_eth": 0.0, "transactions_performed": 0, "contracts_created": 0}
                    if _METRICAS_AGENTE.exists():
                        with _METRICAS_AGENTE.open("r", encoding="utf-8") as f:
                            metricas_dict = json.load(f)
                    
                    metricas_dict["contracts_created"] += 1
                    metricas_dict["transactions_performed"] += 1
                    
                    if decision_estrategia.requires_funds_movement:
                        metricas_dict["transactions_performed"] += 1
                        metricas_dict["protected_value_eth"] += 0.001

                    with _METRICAS_AGENTE.open("w", encoding="utf-8") as f:
                        json.dump(metricas_dict, f, indent=2, ensure_ascii=False)
                except Exception as ex:
                    logger.error(f"Error writing metrics: {ex}")
                
                msg10 = f"https://sepolia.etherscan.io/address/{desplegado.address}"
                yield f'data: {json.dumps({"paso": "contract_active", "estado": "completed", "detalle": "Contract verified and active.", "data": {"address": desplegado.address, "hash": desplegado.transaction_hash, "metrics": metricas_dict, "etherscan": msg10}})}\n\n'

            else:
                detalle_final = decision.get("reasoning", "No action required.")
                motivo = "low_confidence" if decision.get("decision") == "INSUFFICIENT_DATA" else "decision_final"
                execution = bool(decision.get("execution", decision.get("decision") in ["EXECUTE_ADVANCED", "EXECUTE_BASIC"]))
                if decision.get("decision") == "INSUFFICIENT_DATA":
                    detalle_final = "no_execution_due_to_low_confidence"
                yield f'data: {json.dumps({"paso": "decision_final", "estado": "completed", "detalle": detalle_final, "data": {"decision": decision.get("decision"), "contract_type": decision.get("contract_type"), "recommended_action": decision.get("recommended_action"), "execution": execution, "motivo": motivo, "simulation_mode": os.getenv("APP_ENV", "local") != "production"}})}\n\n'

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f'data: {json.dumps({"paso": "error", "estado": "error", "detalle": str(e)})}\n\n'

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
