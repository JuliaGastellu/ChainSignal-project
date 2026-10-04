"""Servicio de análisis de wallets: solo lectura.

Recorro ingestión, features, perfil, scores, señales, estrategia y decisión, y
devuelvo una recomendación. Este servicio no firma, no transfiere, no hace swap,
no despliega contratos ni consume presupuesto: no tiene referencias a WDK,
WalletAgent, ejecutores ni presupuesto. La ejecución heredada vive en
experiments/testnet_ejecucion.py y solo corre en el experimento testnet.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from loguru import logger

from agente_ia.agente import AgenteAnalisis
from decision_engine.engine import DecisionEngine
from generacion_features.extractor import ExtractorFeatures
from infra.config import settings
from ingestion_onchain.resultados import CalidadDatos
from perfil_wallet.behavioral_scoring import BehavioralScorer
from perfil_wallet.clasificador import ClasificadorWallet
from services.intelligence_layer import WalletIntelService, BlockIntelService, ProtocolIntelService
from services.signal_detector import SignalDetector
from services.strategy_engine import StrategyEngine
from services.historial_evaluaciones import HistorialEvaluaciones
from strategy.estrategia_proteccion_wallet import EstrategiaProteccionWallet


# Estos tres códigos de decisión son TERMINALES. Ninguna señal de estrategia,
# sesgo de historial, fallback ni modo demo puede volverlos ejecutables. Los
# consulto en _apply_strategy_overlay, _run_stream y _run_loop como defensa en
# profundidad.
TERMINAL_DECISIONS = {"INSUFFICIENT_DATA", "MONITOR", "BLOCK"}
ACTIONABLE_DECISIONS = {"EXECUTE_ADVANCED", "EXECUTE_BASIC"}

# Alcance que declaro en cada respuesta de análisis: observo la wallet objetivo
# y no existe una wallet ejecutora en el runtime comercial.
READ_ONLY_SCOPE = {"target_wallet": "read_only", "agent_wallet": "disabled"}


class AgentMetrics:
    def __init__(self):
        self.total_runs = 0
        self.executions_triggered = 0
        self.executions_blocked = 0
        self.last_execution_time: Optional[datetime] = None

    def record_run(self):
        self.total_runs += 1

    def record_execution_triggered(self):
        self.executions_triggered += 1
        self.last_execution_time = datetime.now()

    def record_execution_blocked(self):
        self.executions_blocked += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_runs": self.total_runs,
            "executions_triggered": self.executions_triggered,
            "executions_blocked": self.executions_blocked,
            "last_execution_time": self.last_execution_time.isoformat() if self.last_execution_time else None,
        }


class DatosNoDisponibles(Exception):
    """No tengo datos utilizables de la wallet: nunca la trato como cuenta sana."""

    def __init__(self, calidad: CalidadDatos):
        super().__init__(calidad.motivo.value)
        self.calidad = calidad


def _calidad_de(metrics: Any) -> Optional[CalidadDatos]:
    return getattr(metrics, "calidad_datos", None)


class AgentService:
    def __init__(self):
        self._ingesta = None
        self.extractor = ExtractorFeatures()
        self.clasificador = ClasificadorWallet()
        self.scorer = BehavioralScorer()
        self.engine = DecisionEngine()
        self.wallet_intel = WalletIntelService()
        self.block_intel = BlockIntelService()
        self.protocol_intel = ProtocolIntelService()
        self.signal_detector = SignalDetector()
        self.strategy_engine = StrategyEngine()
        self.historial = HistorialEvaluaciones()
        self.metrics = AgentMetrics()
        self._semaphore = asyncio.Semaphore(3)
        self._active_stream_wallets: set[str] = set()
        self._active_stream_wallets_lock = asyncio.Lock()
        self._agente_ia: Optional[AgenteAnalisis] = None

    @property
    def ingesta(self):
        """Construyo la ingesta al primer uso: la red y los proveedores salen de infra/red.py."""
        if self._ingesta is None:
            from ingestion_onchain.ingesta import construir_servicio_ingesta

            self._ingesta = construir_servicio_ingesta()
        return self._ingesta

    @staticmethod
    def _aplicar_calidad(decision: Dict[str, Any], metrics: Any) -> Dict[str, Any]:
        """Sin datos FRESH y completos para la ventana, no queda ninguna decisión accionable."""
        calidad = _calidad_de(metrics)
        if decision.get("decision") in ACTIONABLE_DECISIONS and (calidad is None or not calidad.permite_recomendacion_accionable):
            estado = calidad.calidad.value if calidad is not None else "UNKNOWN"
            decision["decision"] = "MONITOR"
            decision["recommended_action"] = "monitor"
            decision["reasoning"] = f"Data quality is {estado}; no actionable recommendation without fresh, complete data."
            decision["data_quality_gate"] = estado
        return decision

    def _reporte_no_disponible(self, wallet_addr: str, calidad: CalidadDatos) -> Dict[str, Any]:
        return {
            "wallet": wallet_addr,
            "timestamp": datetime.now().isoformat(),
            "data_quality": calidad.a_dict(),
            "executive_summary": None,
            "profile": None,
            "scores": None,
            "metrics": None,
            "agent_decision": {
                "decision": "DATA_UNAVAILABLE",
                "reasoning": f"On-chain data unavailable ({calidad.motivo.value}). This is not evidence that the account is healthy.",
                "recommended_action": "retry_later",
            },
            "agent_metrics": self.metrics.to_dict(),
        }

    async def _acquire_semaphore(self, timeout_s: float = 3.0) -> bool:
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout_s)
            return True
        except TimeoutError:
            return False

    def _obtener_agente_ia(self) -> AgenteAnalisis:
        if self._agente_ia is None:
            self._agente_ia = AgenteAnalisis()
        return self._agente_ia

    async def run_pipeline_stream(self, wallet: str) -> AsyncGenerator[str, None]:
        context_payload = {
            "agent_wallet": None,
            "action_scope": dict(READ_ONLY_SCOPE),
            "decision_context": {
                "target_wallet": wallet.lower(),
                "executor_wallet": None,
                "funds_source": None,
            },
        }
        async for event in self._run_stream(wallet, source="api"):
            event["agent_wallet"] = None
            event["action_scope"] = context_payload["action_scope"]
            if isinstance(event.get("data"), dict):
                event["data"] = {**context_payload, **event["data"]}
            else:
                event["data"] = context_payload
            yield f"data: {json.dumps(event)}\n\n"

    async def run_pipeline_core(self, wallet: str) -> Dict[str, Any]:
        return await self._run_report(wallet)

    async def _run_stream(self, wallet: str, source: str) -> AsyncGenerator[Dict[str, Any], None]:
        wallet_addr = wallet.lower()
        self.metrics.record_run()

        try:
            sem_acquired = await self._acquire_semaphore(timeout_s=3.0)
            if not sem_acquired:
                yield {
                    "paso": "decision_final",
                    "estado": "completed",
                    "detalle": "System busy, retry shortly",
                    "data": {"decision": "SYSTEM_BUSY", "recommended_action": "retry"},
                    "source": source,
                }
                return

            already_running = False
            async with self._active_stream_wallets_lock:
                if wallet_addr in self._active_stream_wallets:
                    already_running = True
                else:
                    self._active_stream_wallets.add(wallet_addr)

            if already_running:
                # Libero el semáforo: antes este camino lo retenía y tres
                # consultas duplicadas dejaban el servicio ocupado para siempre.
                self._semaphore.release()
                yield {
                    "paso": "decision_final",
                    "estado": "completed",
                    "detalle": "Pipeline already running for this wallet.",
                    "data": {"decision": "ALREADY_RUNNING"},
                    "source": source,
                }
                return

            try:
                if wallet_addr == "0x0000000000000000000000000000000000000000":
                    yield {
                        "paso": "evaluating_decision",
                        "estado": "completed",
                        "detalle": "Decision: INSUFFICIENT_DATA",
                        "data": {
                            "decision": "INSUFFICIENT_DATA",
                            "confidence": 0.0,
                            "reasoning": "Null address; no analysis or deployment executed.",
                        },
                        "source": source,
                    }
                    yield {
                        "paso": "decision_final",
                        "estado": "completed",
                        "detalle": "no_execution_due_to_invalid_wallet",
                        "data": {
                            "decision": "INSUFFICIENT_DATA",
                            "contract_type": None,
                            "recommended_action": "monitor",
                            "execution": False,
                            "motivo": "invalid_wallet",
                            "read_only": True,
                        },
                        "source": source,
                    }
                    return

                yield {"paso": "analyzing_wallet", "estado": "starting", "detalle": "Fetching on-chain data...", "source": source}
                try:
                    metrics, profile, scores_obj, scores_dict, risk_breakdown, insight_obj = await self._analyze(wallet_addr)
                except DatosNoDisponibles as error:
                    calidad = error.calidad.a_dict()
                    yield {"paso": "analyzing_wallet", "estado": "error",
                           "detalle": f"On-chain data unavailable: {error.calidad.motivo.value}", "data": {"data_quality": calidad}, "source": source}
                    yield {
                        "paso": "decision_final",
                        "estado": "completed",
                        "detalle": "No recommendation: on-chain data is unavailable. This is not evidence of a healthy account.",
                        "data": {"decision": "DATA_UNAVAILABLE", "recommended_action": "retry_later", "execution": False,
                                 "motivo": "data_unavailable", "read_only": True, "data_quality": calidad},
                        "source": source,
                    }
                    return
                calidad_actual = _calidad_de(metrics)
                yield {
                    "paso": "analyzing_wallet",
                    "estado": "completed",
                    "detalle": f"Analyzed {metrics.total_transacciones} transactions.",
                    "data": {"data_quality": calidad_actual.a_dict() if calidad_actual else None},
                    "source": source,
                }

                yield {"paso": "calculating_scores", "estado": "starting", "detalle": "Running behavioral scoring...", "source": source}
                yield {
                    "paso": "calculating_scores",
                    "estado": "completed",
                    "detalle": f"Risk: {scores_dict['risk']}, Activity: {scores_dict['activity']}, Confidence: {scores_dict['confidence']}",
                    "data": {
                        "risk": scores_dict["risk"],
                        "activity": scores_dict["activity"],
                        "defi_engagement": scores_dict["defi_engagement"],
                        "confidence": scores_dict["confidence"],
                    },
                    "source": source,
                }

                yield {"paso": "classifying_profile", "estado": "starting", "detalle": "Determining wallet profile...", "source": source}
                yield {"paso": "classifying_profile", "estado": "completed", "detalle": f"Profile detected: {profile.type}", "source": source}

                yield {"paso": "generating_insight", "estado": "starting", "detalle": "Running deterministic analysis agent...", "source": source}
                yield {
                    "paso": "generating_insight",
                    "estado": "completed",
                    "detalle": "Structured insight generated.",
                    "data": {
                        "type": insight_obj.type,
                        "analyzed_wallet": insight_obj.analyzed_wallet,
                        "risk_score": insight_obj.risk_score,
                        "activity_score": insight_obj.activity_score,
                        "recommended_action": insight_obj.recommended_action,
                    },
                    "source": source,
                }

                wallet_intel = self.wallet_intel.analyze(wallet_addr, metrics, profile, scores_dict)
                protocol_intel = self.protocol_intel.analyze(metrics, profile)
                signals = self.signal_detector.detect(wallet_intel, protocol_intel)
                strategy_pick = self.strategy_engine.select(
                    signals,
                    {},
                    wallet_intel,
                    demo_mode=settings.AGENT_DEMO_MODE,
                )
                self.historial.registrar_senales(wallet_addr, signals, strategy_pick["strategy"])
                yield {
                    "paso": "signal_detected",
                    "estado": "completed",
                    "detalle": f"{len(signals)} signals detected",
                    "data": {"signals": signals},
                    "source": source,
                }
                yield {
                    "paso": "strategy_selected",
                    "estado": "completed",
                    "detalle": strategy_pick["strategy"],
                    "data": strategy_pick,
                    "source": source,
                }

                yield {"paso": "evaluating_decision", "estado": "starting", "detalle": "Executing decision engine...", "source": source}
                decision, decision_estrategia = await self._decide(insight_obj, scores_dict, metrics)
                decision, decision_estrategia = self._apply_strategy_overlay(decision, decision_estrategia, strategy_pick, insight_obj)
                decision = self._aplicar_calidad(decision, metrics)
                report_snapshot = self._build_report(wallet_addr, profile, scores_obj, scores_dict, risk_breakdown, metrics, decision, decision_estrategia)
                decision_code = str(decision.get("decision") or "MONITOR")
                has_actionable_strategy = bool(
                    decision_estrategia.requires_funds_movement
                    or decision_estrategia.requires_swap
                    or decision_estrategia.requires_contract
                )
                # Quité la salida `low_confidence_defensive_execution`, que
                # permitía ejecutar con INSUFFICIENT_DATA. TERMINAL_DECISIONS lo
                # impide sin importar las banderas de decision_estrategia.
                # should_execute solo describe si la decisión sería accionable;
                # este servicio nunca la ejecuta.
                should_execute = (
                    decision_code not in TERMINAL_DECISIONS
                    and decision_code in ACTIONABLE_DECISIONS
                    and has_actionable_strategy
                )

                agent_intent = "No action required"
                if should_execute:
                    agent_intent = "Recommend protective review due to elevated on-chain risk indicators (no automatic execution)"
                elif decision_code in {"EXECUTE_ADVANCED", "EXECUTE_BASIC"} and not has_actionable_strategy:
                    agent_intent = "Monitoring only: strategy found no actionable on-chain mitigation."
                elif decision_code == "INSUFFICIENT_DATA":
                    agent_intent = "Monitoring only: low-confidence profile without defensive trigger."

                yield {
                    "paso": "evaluating_decision",
                    "estado": "completed",
                    "detalle": f"Decision: {decision.get('decision', 'MONITOR')}",
                    "data": {
                        **decision,
                        "agent_intent": agent_intent,
                        "confidence": scores_dict.get("confidence"),
                        "reasoning": decision.get("reasoning") or decision_estrategia.detail,
                        "metrics": report_snapshot.get("metrics"),
                        "features": {
                            "profile_type": profile.type,
                            "profile_signals": profile.signals,
                            "days_observed": metrics.dias_observados,
                            "complete_history": metrics.historial_completo,
                            "contract_interactions_pct": metrics.porcentaje_interacciones_contratos,
                        },
                        "risk_factors": risk_breakdown if isinstance(risk_breakdown, list) else [risk_breakdown],
                    },
                    "source": source,
                }
                yield {"paso": "analysis_snapshot", "estado": "completed", "detalle": "Full analysis snapshot ready.", "data": report_snapshot, "source": source}

                # Nunca ejecuto desde aquí. Si la decisión habría sido accionable,
                # lo informo como recomendación sin efecto on-chain.
                detalle_final = decision.get("reasoning", "No action required.")
                motivo = "low_confidence" if decision_code == "INSUFFICIENT_DATA" else "decision_final"
                if decision_code == "INSUFFICIENT_DATA":
                    detalle_final = "no_execution_due_to_low_confidence"
                if decision_code in ACTIONABLE_DECISIONS and not has_actionable_strategy:
                    detalle_final = "No autonomous execution: strategy did not require transfer/swap/deploy."
                    motivo = "no_actionable_strategy"
                if should_execute:
                    detalle_final = "Recommendation only: this runtime is read-only and never executes on-chain actions."
                    motivo = "read_only_runtime"
                yield {
                    "paso": "decision_final",
                    "estado": "completed",
                    "detalle": detalle_final,
                    "data": {
                        "decision": decision_code,
                        "contract_type": decision.get("contract_type"),
                        "recommended_action": decision.get("recommended_action"),
                        "execution": False,
                        "motivo": motivo,
                        "read_only": True,
                        "suggested_actions": list(decision_estrategia.actions) if should_execute else [],
                    },
                    "source": source,
                }
            finally:
                async with self._active_stream_wallets_lock:
                    self._active_stream_wallets.discard(wallet_addr)
                self._semaphore.release()
        except Exception as e:
            logger.error(f"Pipeline stream error: {e}")
            yield {"paso": "error", "estado": "error", "detalle": str(e), "source": source}

    async def _run_report(self, wallet: str) -> Dict[str, Any]:
        wallet_addr = wallet.lower()
        self.metrics.record_run()

        acquired = await self._acquire_semaphore(timeout_s=3.0)
        if not acquired:
            raise RuntimeError("System busy, retrying...")
        try:
            if wallet_addr == "0x0000000000000000000000000000000000000000":
                now = datetime.now().isoformat()
                return {
                    "wallet": wallet_addr,
                    "timestamp": now,
                    "executive_summary": {
                        "profile_title": "Invalid Wallet",
                        "security_rating": "D",
                        "activity_level": "Low",
                        "main_recommendation": "Invalid wallet address; no execution performed.",
                    },
                    "profile": {"type": "invalid", "confidence": 1.0, "description": "Null/burn address.", "signals": []},
                    "scores": {
                        "risk": {"value": 100, "interpretation": "Invalid wallet", "breakdown": {}},
                        "activity": {"value": 0, "interpretation": "No activity"},
                        "defi": {"value": 0, "interpretation": "No engagement"},
                        "web3_index": {"value": 0, "interpretation": "N/A"},
                    },
                    "metrics": {"total_transactions": 0, "eth_balance": None, "days_observed": 0, "tx_per_day": 0.0, "contract_interactions_pct": 0.0},
                    "data_quality": None,
                    "agent_decision": {"decision": "INSUFFICIENT_DATA", "reasoning": "invalid_wallet", "recommended_action": "monitor"},
                    "agent_metrics": self.metrics.to_dict(),
                        }

            try:
                metrics, profile, scores_obj, scores_dict, risk_breakdown, insight_obj = await self._analyze(wallet_addr)
            except DatosNoDisponibles as error:
                return self._reporte_no_disponible(wallet_addr, error.calidad)
            decision, decision_estrategia = await self._decide(insight_obj, scores_dict, metrics)
            wallet_intel = self.wallet_intel.analyze(wallet_addr, metrics, profile, scores_dict)
            protocol_intel = self.protocol_intel.analyze(metrics, profile)
            signals = self.signal_detector.detect(wallet_intel, protocol_intel)
            strategy_pick = self.strategy_engine.select(
                signals,
                decision,
                wallet_intel,
                demo_mode=settings.AGENT_DEMO_MODE,
            )
            decision, decision_estrategia = self._apply_strategy_overlay(decision, decision_estrategia, strategy_pick, insight_obj)
            decision = self._aplicar_calidad(decision, metrics)
            decision["signals"] = signals
            return self._build_report(wallet_addr, profile, scores_obj, scores_dict, risk_breakdown, metrics, decision, decision_estrategia)
        finally:
            self._semaphore.release()

    async def _analyze(self, wallet_addr: str) -> Tuple[Any, Any, Any, Dict[str, Any], Dict[str, Any], Any]:
        datos_crudos = await asyncio.to_thread(self.ingesta.obtener_datos_wallet, wallet_addr)
        if datos_crudos.calidad is None or not datos_crudos.calidad.utilizable:
            raise DatosNoDisponibles(datos_crudos.calidad)
        metrics = await asyncio.to_thread(self.extractor.extraer, datos_crudos)
        profile = self.clasificador.clasificar(metrics)
        scores_obj = self.scorer.calcular_scores(metrics)
        risk_breakdown = self.scorer.get_risk_breakdown(metrics)

        tx_count = metrics.total_transacciones if hasattr(metrics, "total_transacciones") else 0
        confidence = min(1.0, tx_count / 100)
        scores_dict = {
            "activity": scores_obj.activity_score.value,
            "risk": scores_obj.risk_score.value,
            "defi_engagement": scores_obj.defi_engagement.value,
            "confidence": round(confidence, 2),
        }

        agente = self._obtener_agente_ia()
        insight_obj = await asyncio.to_thread(agente.analizar, metrics, profile, wallet_addr=wallet_addr, scores=scores_dict)
        return metrics, profile, scores_obj, scores_dict, risk_breakdown, insight_obj

    async def _decide(self, insight_obj: Any, scores_dict: Dict[str, Any], metrics: Any) -> Tuple[Dict[str, Any], Any]:
        decision = self.engine.evaluate(scores_dict, metrics={"transaction_count": metrics.total_transacciones})
        if decision.get("decision") == "INSUFFICIENT_DATA":
            insight_obj.type = None
            decision["recommended_action"] = "monitor"
            decision["reasoning"] = "Insufficient information; no contract will be deployed."
        estrategia = EstrategiaProteccionWallet()
        decision_estrategia = estrategia.evaluar(insight_obj)
        return decision, decision_estrategia

    def _apply_strategy_overlay(self, decision: Dict[str, Any], decision_estrategia: Any, strategy_pick: Dict[str, Any], insight_obj: Any):
        """Attaches strategy metadata to a decision.

        Antes este método podía convertir BLOCK/MONITOR/INSUFFICIENT_DATA en una
        transferencia real EXECUTE_BASIC cuando había `force_execute`, y todas
        las ramas de estrategia lo activaban. Quité ese override: aquí solo
        anoto una decisión o, como máximo, bajo a MONITOR una decisión
        "accionable" sin respaldo. Nunca subo una decisión a ejecutable.
        """
        strategy_name = str(strategy_pick.get("strategy", "NO_ACTION"))
        decision["strategy"] = strategy_name
        decision["strategy_reason"] = strategy_pick.get("reason")
        decision["strategy_confidence"] = float(strategy_pick.get("confidence", 0.55) or 0.55)
        decision["trigger_signals"] = list(strategy_pick.get("trigger_signals") or ["EXPLORE_TRIGGER"])

        # TERMINAL: BLOCK / MONITOR / INSUFFICIENT_DATA can never become executable
        # here, regardless of strategy_pick.force_execute or AGENT_DEMO_MODE.
        if decision.get("decision") in TERMINAL_DECISIONS:
            return decision, decision_estrategia

        has_actionable = bool(
            getattr(decision_estrategia, "requires_funds_movement", False)
            or getattr(decision_estrategia, "requires_swap", False)
            or getattr(decision_estrategia, "requires_contract", False)
        )
        if decision.get("decision") in {"EXECUTE_BASIC", "EXECUTE_ADVANCED"} and not has_actionable:
            # El motor juzgó accionable la wallet, pero la estrategia no encontró
            # nada concreto. No invento una acción: bajo a MONITOR en lugar de
            # forzar una transferencia.
            decision["decision"] = "MONITOR"
            decision["recommended_action"] = "monitor"
            decision["reasoning"] = (
                f"No concrete protective action available for strategy '{strategy_name}'. "
                "Downgraded to MONITOR rather than forcing an action."
            )
        return decision, decision_estrategia

    def _build_report(
        self,
        wallet_addr: str,
        profile: Any,
        scores_obj: Any,
        scores_dict: Dict[str, Any],
        risk_breakdown: Dict[str, Any],
        metrics: Any,
        decision: Dict[str, Any],
        decision_estrategia: Any,
    ) -> Dict[str, Any]:
        return {
            "wallet": wallet_addr,
            "timestamp": datetime.now().isoformat(),
            "executive_summary": {
                "profile_title": profile.type.replace("_", " ").title(),
                "security_rating": "A" if scores_dict["risk"] < 20 else "B" if scores_dict["risk"] < 40 else "C" if scores_dict["risk"] < 60 else "D",
                "activity_level": "High" if scores_dict["activity"] > 70 else "Medium" if scores_dict["activity"] > 30 else "Low",
                "main_recommendation": decision_estrategia.detail,
            },
            "profile": {"type": profile.type, "confidence": profile.confidence, "description": profile.description, "signals": profile.signals},
            "scores": {
                "risk": {"value": scores_dict["risk"], "interpretation": scores_obj.risk_score.interpretation, "breakdown": risk_breakdown},
                "activity": {"value": scores_dict["activity"], "interpretation": scores_obj.activity_score.interpretation},
                "defi": {"value": scores_dict["defi_engagement"], "interpretation": scores_obj.defi_engagement.interpretation},
                "web3_index": {"value": scores_obj.web3_activity_index.value, "interpretation": scores_obj.web3_activity_index.interpretation},
            },
            "metrics": {
                "total_transactions": metrics.total_transacciones,
                "eth_balance": metrics.balance_eth_actual,
                "days_observed": metrics.dias_observados,
                "first_observed_activity": metrics.primera_actividad_observada_timestamp or None,
                "complete_history": metrics.historial_completo,
                "tx_per_day": metrics.frecuencia_transacciones_por_dia,
                "contract_interactions_pct": metrics.porcentaje_interacciones_contratos,
            },
            "agent_decision": {"decision": decision.get("decision"), "reasoning": decision_estrategia.detail, "recommended_action": decision.get("recommended_action")},
            "strategy": {"name": decision.get("strategy"), "reason": decision.get("strategy_reason"), "confidence": decision.get("strategy_confidence"), "trigger_signals": decision.get("trigger_signals", [])},
            "signals": decision.get("signals", []),
            "agent_metrics": self.metrics.to_dict(),
            "data_quality": _calidad_de(metrics).a_dict() if _calidad_de(metrics) is not None else None,
        }
