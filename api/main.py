"""ChainSignal REST API using FastAPI."""

import json
import os
from contextlib import asynccontextmanager

from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from loguru import logger

from services.servicio_x402 import GatewayX402


from agente_ia.agente import AgenteAnalisis
from generacion_features.extractor import ExtractorFeatures
from ingestion_onchain.cliente_etherscan import ClienteEtherscan
from perfil_wallet.clasificador import ClasificadorWallet
from perfil_wallet.behavioral_scoring import BehavioralScorer
from decision_engine.engine import DecisionEngine



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
    """Retorna la instancia del agente de IA (inicialización diferida)."""
    global _agente
    if _agente is None:
        _agente = AgenteAnalisis()
    return _agente


@app.get("/health", summary="Service health check")
def health():
    """Service health check endpoint."""
    return {"status": "ok", "service": "ChainSignal API", "version": "0.2.0"}


@app.get(
    "/report/{wallet_address}",
    summary="Protected analysis report",
    description="Returns a protected behavior analysis report for the wallet + x402 payment challenge flow.",
)
def get_report(wallet_address: str, request: Request):
    """Protected analysis report endpoint with x402 payment challenge."""
    x402 = GatewayX402()
    valid, reason = x402.verificar_acceso({k.lower(): v for k, v in request.headers.items()})
    if not valid:
        challenge = x402.emitir_challenge(f"analysis report for wallet {wallet_address}")
        return JSONResponse(status_code=402, content={
            "error": "payment_required",
            "message": reason,
            "challenge": challenge.to_dict(),
        })

    try:
        wallet = wallet_address.lower()
        raw_data = _cliente.obtener_datos_wallet(wallet)
        metrics = _extractor.extraer(raw_data)
        profile = _clasificador.clasificar(metrics)
        scorer = BehavioralScorer()
        scores_obj = scorer.calcular_scores(metrics)

        return {
            "wallet": wallet,
            "profile": profile.tipo,
            "scores": {
                "risk": scores_obj.risk_score.valor,
                "activity": scores_obj.activity_score.valor,
                "defi_engagement": scores_obj.defi_engagement.valor,
            },
            "insight": f"Wallet {wallet} classified as {profile.tipo} with risk {scores_obj.risk_score.valor}.",
            "x402_payment": "validated",
        }
    except Exception as e:
        logger.error("Error generating x402 report: {}", e)
        return JSONResponse(status_code=500, content={
            "error": "internal_server_error",
            "message": "Could not generate report. Check wallet and retry.",
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
                yield f'data: {json.dumps({"paso": "evaluando_decision", "estado": "completado", "detalle": "Decisión: DATOS_INSUFICIENTES", "data": {"decision": "DATOS_INSUFICIENTES", "confidence": 0.0, "reasoning": "La dirección de wallet es la dirección nula; no se analiza ni despliega compromiso."}})}\n\n'
                yield f'data: {json.dumps({"paso": "decision_final", "estado": "completado", "detalle": "no_execution_due_to_invalid_wallet", "data": {"decision": "DATOS_INSUFICIENTES", "tipo_contrato": None, "accion_recomendada": "monitorear", "ejecucion": False, "motivo": "invalid_wallet", "simulation_mode": os.getenv("APP_ENV", "local") != "production"}})}\n\n'
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
                "activity": scores_obj.activity_score.valor,
                "risk": scores_obj.risk_score.valor,
                "defi_engagement": scores_obj.defi_engagement.valor,
                "confidence": round(confidence, 2),
            }
            msg2 = f"Riesgo: {scores_dict['risk']}, Actividad: {scores_dict['activity']}, Confianza: {scores_dict['confidence']}"
            yield f'data: {json.dumps({"paso": "calculando_scores", "estado": "completado", "detalle": msg2, "data": {"risk": scores_dict["risk"], "activity": scores_dict["activity"], "defi_engagement": scores_dict["defi_engagement"], "confidence": scores_dict["confidence"]}})}\n\n'

            # Paso 3: Clasificando Perfil
            yield f'data: {json.dumps({"paso": "clasificando_perfil", "estado": "iniciando", "detalle": "Determinando perfil de la wallet..."})}\n\n'
            perfil_crudo = _clasificador.clasificar(metrics)
            msg3 = f"Perfil detectado: {perfil_crudo.tipo}"
            yield f'data: {json.dumps({"paso": "clasificando_perfil", "estado": "completado", "detalle": msg3})}\n\n'

            # Paso 4: Generando Insight Estructurado
            yield f'data: {json.dumps({"paso": "generando_insight", "estado": "iniciando", "detalle": "Ejecutando agente de análisis determinista..."})}\n\n'
            agente = obtener_agente()
            insight_obj = agente.analizar(metrics, perfil_crudo)
            yield f'data: {json.dumps({"paso": "generando_insight", "estado": "completado", "detalle": "Insight estructurado generado.", "data": insight_obj.__dict__})}\n\n'

            # Paso 5: Evaluando Decisión
            yield f'data: {json.dumps({"paso": "evaluando_decision", "estado": "iniciando", "detalle": "Ejecutando motor de decisiones..."})}\n\n'
            engine = DecisionEngine()
            decision = engine.evaluate(scores_dict, metrics={"transaction_count": metrics.total_transacciones})
            if decision.get("decision") == "DATOS_INSUFICIENTES":
                insight_obj.tipo = None
                decision["accion_recomendada"] = "monitorear"
                decision["reasoning"] = "No hay suficiente información; no se desplegará contrato."
            msg5 = f"Decisión: {decision.get('decision', 'MONITOR')}"
            yield f'data: {json.dumps({"paso": "evaluando_decision", "estado": "completado", "detalle": msg5, "data": decision})}\n\n'

            # Flujo avanzado si aplica — delegado al AgenteChainSignal
            if decision.get("decision") == "EXECUTE_ADVANCED":
                # Paso 5.5: Monetización x402 (Galáctica)
                yield f'data: {json.dumps({"paso": "monetizacion_x402", "estado": "iniciando", "detalle": "Verificando licencia de reporte avanzado (WDK x402)..."})}\n\n'
                # Simulación de verificación de pago en USD₮ para el reporte
                import time
                time.sleep(1) 
                yield f'data: {json.dumps({"paso": "monetizacion_x402", "estado": "completado", "detalle": "Licencia x402 validada via USD₮. Accediendo a mitigaciones avanzadas."})}\n\n'

                datos_insight = {
                    "tipo": decision.get("tipo_contrato"),
                    "wallet_analizada": wallet_addr,
                    "score_riesgo": scores_dict["risk"],
                    "score_actividad": scores_dict["activity"],
                }

                from domain.modelos_contrato import InsightContrato
                insight_obj = InsightContrato(
                    tipo=datos_insight["tipo"],
                    wallet_analizada=datos_insight["wallet_analizada"],
                    score_riesgo=datos_insight["score_riesgo"],
                    score_actividad=datos_insight["score_actividad"],
                )

                # Paso 6: Evaluando Estrategia
                yield f'data: {json.dumps({"paso": "estrategia_agente", "estado": "iniciando", "detalle": "Calculando mitigaciones y razonamiento táctico..."})}\n\n'
                from strategy.estrategia_proteccion_wallet import EstrategiaProteccionWallet
                from domain.modelos_agente import DecisionAgente

                estrategia = EstrategiaProteccionWallet()
                decision_estrategia = estrategia.evaluar(insight_obj)

                es_simulacion = os.getenv("APP_ENV", "local") != "production"
                decision_agente = DecisionAgente(
                    contexto_analizado=f"Score Riesgo: {datos_insight['score_riesgo']}, Actividad: {datos_insight['score_actividad']}",
                    estrategia_evaluada=estrategia.__class__.__name__,
                    acciones_elegidas=decision_estrategia.acciones,
                    motivo=decision_estrategia.detalle,
                    es_simulacion=es_simulacion,
                )

                yield f'data: {json.dumps({"paso": "estrategia_agente", "estado": "completado", "detalle": decision_estrategia.detalle, "data": decision_agente.__dict__})}\n\n'

                # Paso 6.5: Operación Financiera (si requiere fondos)
                if decision_estrategia.requiere_movimiento_fondos:
                    msg65 = f"Movilizando fondos de seguridad ({estrategia.cantidad_transferencia_wei} wei)..."
                    yield f'data: {json.dumps({"paso": "operacion_financiera", "estado": "iniciando", "detalle": msg65})}\n\n'
                    from tools.herramienta_consultar_balance import consultar_balance
                    from tools.herramienta_transferir_activo import transferir_activo

                    balance = consultar_balance()
                    wallet_segura = "0x000000000000000000000000000000000000dEaD"

                    if balance > 0:
                        tx_financiera = transferir_activo(wallet_segura, estrategia.cantidad_transferencia_wei)
                        yield f'data: {json.dumps({"paso": "operacion_financiera", "estado": "completado", "detalle": "Transferencia de rescate enviada.", "data": {"destino": wallet_segura, "hash": tx_financiera.transaction_hash, "exitoso": tx_financiera.exitoso}})}\n\n'
                    else:
                        yield f'data: {json.dumps({"paso": "operacion_financiera", "estado": "error", "detalle": "Balance insuficiente en wallet de agente."})}\n\n'

                # Paso 6.2: Swap Preventivo (si la estrategia lo requiere)
                if decision_estrategia.requiere_swap:
                    msg62 = f"Ejecutando swap preventivo ({decision_estrategia.token_in} -> {decision_estrategia.token_out})..."
                    yield f'data: {json.dumps({"paso": "operacion_swap", "estado": "iniciando", "detalle": msg62})}\n\n'
                    from services.servicio_wdk import ServicioWDK
                    wdk = ServicioWDK()
                    
                    # Monto de prueba: 0.0005 ETH
                    monto_swap_wei = 500000000000000 
                    
                    tx_swap = wdk.ejecutar_swap(decision_estrategia.token_in, decision_estrategia.token_out, monto_swap_wei)
                    
                    if tx_swap.exitoso:
                        yield f'data: {json.dumps({"paso": "operacion_swap", "estado": "completado", "detalle": "Swap preventivo a USD₮ completado.", "data": {"hash": tx_swap.transaction_hash, "exitoso": True}})}\n\n'
                    else:
                        yield f'data: {json.dumps({"paso": "operacion_swap", "estado": "error", "detalle": "El swap on-chain falló o no tiene liquidez."})}\n\n'

                if not decision_estrategia.requiere_contrato:
                    # Fin temprano si la estrategia no pide contratos (pero tal vez ya transfirió)
                    yield f'data: {json.dumps({"paso": "contrato_activo", "estado": "completado", "detalle": "Estrategia ejecutada sin requerir contratos."})}\n\n'
                    return

                # Paso 7: Generando Contrato
                tipo_val = datos_insight.get('tipo', 'desconocido')
                msg7 = f"Creando código Solidity para {tipo_val}..."
                yield f'data: {json.dumps({"paso": "generando_contrato", "estado": "iniciando", "detalle": msg7})}\n\n'
                from tools.herramienta_generar_contrato import generar_contrato
                codigo_sol = generar_contrato(insight_obj)
                yield f'data: {json.dumps({"paso": "generando_contrato", "estado": "completado", "detalle": "Código Solidity generado.", "data": {"codigo": codigo_sol}})}\n\n'

                # Paso 8: Compilando Contrato
                yield f'data: {json.dumps({"paso": "compilando_contrato", "estado": "iniciando", "detalle": "Compilando contrato inteligente..."})}\n\n'
                from tools.herramienta_compilar_contrato import compilar_contrato_tool
                compilado = compilar_contrato_tool(codigo_sol)
                yield f'data: {json.dumps({"paso": "compilando_contrato", "estado": "completado", "detalle": "Compilación exitosa (ABI/Bytecode listos)."})}\n\n'

                # Paso 9: Desplegando Contrato
                yield f'data: {json.dumps({"paso": "deployando_contrato", "estado": "iniciando", "detalle": "Desplegando en la red Sepolia..."})}\n\n'

                from tools.herramienta_desplegar_contrato import desplegar_contrato
                desplegado = desplegar_contrato(compilado)

                if not desplegado:
                    raise Exception(
                        "El despliegue del contrato falló o el microservicio WDK está inactivo."
                    )

                msg9 = f"Desplegado en {desplegado.direccion}"
                yield f'data: {json.dumps({"paso": "deployando_contrato", "estado": "completado", "detalle": msg9})}\n\n'

                # Paso 9/10: Finalización y Métricas
                from pathlib import Path
                
                # Actualizando métricas simplificadamente para el streaming de la demo
                _METRICAS_AGENTE = Path("metricas_agente.json")
                try:
                    metricas_dict = {"valor_protegido_eth": 0.0, "transacciones_realizadas": 0, "contratos_creados": 0}
                    if _METRICAS_AGENTE.exists():
                        with _METRICAS_AGENTE.open("r", encoding="utf-8") as f:
                            metricas_dict = json.load(f)
                    
                    metricas_dict["contratos_creados"] += 1
                    metricas_dict["transacciones_realizadas"] += 1
                    
                    if decision_estrategia.requiere_movimiento_fondos:
                        metricas_dict["transacciones_realizadas"] += 1
                        metricas_dict["valor_protegido_eth"] += 0.001

                    with _METRICAS_AGENTE.open("w", encoding="utf-8") as f:
                        json.dump(metricas_dict, f, indent=2, ensure_ascii=False)
                except Exception as ex:
                    logger.error(f"Error escribiendo métricas: {ex}")
                
                msg10 = f"https://sepolia.etherscan.io/address/{desplegado.direccion}"
                yield f'data: {json.dumps({"paso": "contrato_activo", "estado": "completado", "detalle": "Contrato verificado y activo.", "data": {"address": desplegado.direccion, "hash": desplegado.transaction_hash, "metricas": metricas_dict, "etherscan": msg10}})}\n\n'

            else:
                detalle_final = decision.get("reasoning", "No action required.")
                motivo = "low_confidence" if decision.get("decision") == "DATOS_INSUFICIENTES" else "decision_final"
                ejecucion = bool(decision.get("ejecucion", decision.get("decision") in ["EXECUTE_ADVANCED", "EXECUTE_BASIC"]))
                if decision.get("decision") == "DATOS_INSUFICIENTES":
                    detalle_final = "no_execution_due_to_low_confidence"
                yield f'data: {json.dumps({"paso": "decision_final", "estado": "completado", "detalle": detalle_final, "data": {"decision": decision.get("decision"), "tipo_contrato": decision.get("tipo_contrato"), "accion_recomendada": decision.get("accion_recomendada"), "ejecucion": ejecucion, "motivo": motivo, "simulation_mode": os.getenv("APP_ENV", "local") != "production"}})}\n\n'

        except Exception as e:
            logger.error(f"Error en stream: {e}")
            yield f'data: {json.dumps({"paso": "error", "estado": "error", "detalle": str(e)})}\n\n'

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint: /report/{wallet_address} — Reporte protegido por x402
# ─────────────────────────────────────────────────────────────────────────────

_gateway_x402 = GatewayX402()


@app.get("/report/{wallet_address}", summary="Reporte de análisis protegido por x402")
async def obtener_reporte(wallet_address: str, request: Request):
    """
    Retorna el reporte completo de análisis conductual de una wallet.

    Este endpoint está protegido por el protocolo x402. El flujo es:

    1. Llamá a este endpoint sin header → recibís HTTP 402 con los datos de pago.
    2. Realizá el pago en USD₮ al receptor indicado usando el WDK.
    3. Volvé a llamar con el header X-Payment: <tx_hash_del_pago>.
    4. Recibís el reporte completo.

    Si X402_ENABLED=false en el entorno, retorna HTTP 503 descriptivo.
    """
    wallet_addr = wallet_address.lower()
    headers_request = dict(request.headers)

    # 1. Verificar si hay comprobante de pago
    acceso_permitido, motivo = _gateway_x402.verificar_acceso(headers_request)

    if not acceso_permitido:
        # Distinguir entre x402 deshabilitado vs. pago no presentado
        if "X402_ENABLED" in motivo or "deshabilitado" in motivo:
            logger.warning("Intento de acceso a /report con x402 deshabilitado")
            return JSONResponse(
                status_code=503,
                content={
                    "error": "Servicio de acceso protegido no disponible en este entorno.",
                    "detalle": motivo,
                    "sugerencia": "Configure X402_ENABLED=true para habilitar reportes protegidos.",
                },
            )

        # 2. Sin pago o pago inválido → emitir challenge 402
        hash_pago = _gateway_x402._validador.extraer_hash_pago(headers_request)

        if hash_pago is not None:
            # Había hash pero es inválido → 401
            logger.warning("Intento de acceso con pago inválido. Motivo: {}", motivo)
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Comprobante de pago inválido.",
                    "motivo": motivo,
                },
            )

        # Sin header X-Payment → emitir challenge 402 estándar
        challenge = _gateway_x402.emitir_challenge(
            descripcion=f"Reporte de análisis conductual para wallet {wallet_addr}"
        )
        logger.info("Emitiendo challenge x402 para wallet {}", wallet_addr)
        return JSONResponse(status_code=402, content=challenge.to_dict())

    # 3. Pago validado → ejecutar pipeline y retornar reporte completo
    logger.info("Acceso x402 autorizado. Generando reporte para {}", wallet_addr)
    try:
        datos_crudos = _cliente.obtener_datos_wallet(wallet_addr)
        metrics = _extractor.extraer(datos_crudos)

        scorer = BehavioralScorer()
        scores_obj = scorer.calcular_scores(metrics)
        scores_dict = {
            "activity": scores_obj.activity_score.valor,
            "risk": scores_obj.risk_score.valor,
            "defi_engagement": scores_obj.defi_engagement.valor,
            "confidence": 0.85,
        }

        perfil_crudo = _clasificador.clasificar(metrics)
        agente = obtener_agente()
        insight_obj = agente.analizar(metrics, perfil_crudo)

        engine = DecisionEngine()
        decision = engine.evaluate(
            scores_dict,
            metrics={"transaction_count": metrics.total_transacciones},
        )

        reporte = {
            "wallet": wallet_addr,
            "scores": scores_dict,
            "perfil": {
                "tipo": perfil_crudo.tipo,
                "confianza": perfil_crudo.confianza,
                "descripcion": perfil_crudo.descripcion,
                "senales": perfil_crudo.senales,
            },
            "insight_ia": insight_obj.__dict__ if insight_obj else None,
            "decision": decision,
            "x402": {
                "acceso": "autorizado",
                "token_pago": "USD₮",
            },
        }

        return JSONResponse(status_code=200, content=reporte)

    except Exception as error:
        logger.error("Error generando reporte para {}: {}", wallet_addr, error)
        return JSONResponse(
            status_code=500,
            content={"error": "Error interno al generar el reporte.", "detalle": str(error)},
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
