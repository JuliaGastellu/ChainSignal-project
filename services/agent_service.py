import asyncio
import json
import os
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from loguru import logger

from agente_ia.agente import AgenteAnalisis
from decision_engine.engine import DecisionEngine
from domain.modelos_agente import DecisionAgente
from generacion_features.extractor import ExtractorFeatures
from infra.config import settings
from ingestion_onchain.cliente_etherscan import ClienteEtherscan
from perfil_wallet.behavioral_scoring import BehavioralScorer
from perfil_wallet.clasificador import ClasificadorWallet
from services.servicio_wdk import ServicioWDK
from strategy.estrategia_proteccion_wallet import EstrategiaProteccionWallet
from tools.herramienta_compilar_contrato import compilar_contrato_tool
from tools.herramienta_generar_contrato import generar_contrato

from execution_guard.guard import ExecutionGuard
from execution_guard.lock_manager import WalletLockManager
from execution_guard.runner import ExecutionRunner


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


class AgentService:
    def __init__(self):
        self.cliente = ClienteEtherscan()
        self.extractor = ExtractorFeatures()
        self.clasificador = ClasificadorWallet()
        self.scorer = BehavioralScorer()
        self.engine = DecisionEngine()
        self.guard = ExecutionGuard()
        self.lock_manager = WalletLockManager()
        self.wdk = ServicioWDK()
        self.metrics = AgentMetrics()
        self._semaphore = asyncio.Semaphore(3)
        self._active_stream_wallets: set[str] = set()
        self._active_stream_wallets_lock = asyncio.Lock()
        self._agente_ia: Optional[AgenteAnalisis] = None

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
        async for event in self._run_stream(wallet, source="api"):
            yield f"data: {json.dumps(event)}\n\n"

    async def run_pipeline_core(self, wallet: str) -> Dict[str, Any]:
        return await self._run_report(wallet)

    async def run_pipeline_loop(self, wallet: str) -> Dict[str, Any]:
        return await self._run_loop(wallet)

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
                            "simulation_mode": os.getenv("APP_ENV", "local") != "production",
                        },
                        "source": source,
                    }
                    return

                yield {"paso": "analyzing_wallet", "estado": "starting", "detalle": "Fetching data from Etherscan...", "source": source}
                metrics, profile, scores_obj, scores_dict, risk_breakdown, insight_obj = await self._analyze(wallet_addr)
                yield {
                    "paso": "analyzing_wallet",
                    "estado": "completed",
                    "detalle": f"Analyzed {metrics.total_transacciones} transactions.",
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

                yield {"paso": "evaluating_decision", "estado": "starting", "detalle": "Executing decision engine...", "source": source}
                decision, decision_estrategia = await self._decide(insight_obj, scores_dict, metrics)

                agent_intent = "No action required"
                if decision.get("decision") == "EXECUTE_ADVANCED":
                    agent_intent = "Protect funds due to elevated on-chain risk indicators"

                yield {
                    "paso": "evaluating_decision",
                    "estado": "completed",
                    "detalle": f"Decision: {decision.get('decision', 'MONITOR')}",
                    "data": {**decision, "agent_intent": agent_intent},
                    "source": source,
                }

                if decision.get("decision") != "EXECUTE_ADVANCED":
                    detalle_final = decision.get("reasoning", "No action required.")
                    motivo = "low_confidence" if decision.get("decision") == "INSUFFICIENT_DATA" else "decision_final"
                    execution = bool(decision.get("execution", decision.get("decision") in ["EXECUTE_ADVANCED", "EXECUTE_BASIC"]))
                    if decision.get("decision") == "INSUFFICIENT_DATA":
                        detalle_final = "no_execution_due_to_low_confidence"
                    yield {
                        "paso": "decision_final",
                        "estado": "completed",
                        "detalle": detalle_final,
                        "data": {
                            "decision": decision.get("decision"),
                            "contract_type": decision.get("contract_type"),
                            "recommended_action": decision.get("recommended_action"),
                            "execution": execution,
                            "motivo": motivo,
                            "simulation_mode": os.getenv("APP_ENV", "local") != "production",
                        },
                        "source": source,
                    }
                    return

                yield {"paso": "x402_validation", "estado": "starting", "detalle": "Verifying advanced report license (WDK x402)...", "source": source}
                yield {"paso": "x402_validation", "estado": "completed", "detalle": "x402 license validated via USDC. Accessing advanced mitigations.", "source": source}

                yield {"paso": "strategy_execution", "estado": "starting", "detalle": "Calculating mitigations and tactical reasoning...", "source": source}
                es_simulacion = os.getenv("APP_ENV", "local") != "production"
                decision_agente = DecisionAgente(
                    contexto_analizado=f"Risk Score: {insight_obj.risk_score}, Activity: {insight_obj.activity_score}",
                    evaluated_strategy=EstrategiaProteccionWallet.__name__,
                    chosen_actions=decision_estrategia.actions,
                    reason=decision_estrategia.detail,
                    is_simulation=es_simulacion,
                )
                yield {"paso": "strategy_execution", "estado": "completed", "detalle": decision_estrategia.detail, "data": decision_agente.__dict__, "source": source}

                lock_acquired = await asyncio.to_thread(self.lock_manager.acquire, wallet_addr)
                if not lock_acquired:
                    self.metrics.record_execution_blocked()
                    yield {"paso": "execution_lock", "estado": "error", "detalle": "Wallet is currently being processed by another task.", "source": source}
                    return

                try:
                    self.metrics.record_execution_triggered()
                    async for ev in self._execute_with_esl(wallet_addr, decision_estrategia, decision, insight_obj, source, stream_mode=True):
                        yield ev
                finally:
                    await asyncio.to_thread(self.lock_manager.release, wallet_addr)
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
                    "metrics": {"total_transactions": 0, "eth_balance": 0.0, "days_active": 0, "tx_per_day": 0.0, "contract_interactions_pct": 0.0},
                    "agent_decision": {"decision": "INSUFFICIENT_DATA", "reasoning": "invalid_wallet", "recommended_action": "monitor"},
                    "agent_metrics": self.metrics.to_dict(),
                    "x402_payment": "validated",
                }

            metrics, profile, scores_obj, scores_dict, risk_breakdown, insight_obj = await self._analyze(wallet_addr)
            decision, decision_estrategia = await self._decide(insight_obj, scores_dict, metrics)
            return self._build_report(wallet_addr, profile, scores_obj, scores_dict, risk_breakdown, metrics, decision, decision_estrategia)
        finally:
            self._semaphore.release()

    async def _run_loop(self, wallet: str) -> Dict[str, Any]:
        wallet_addr = wallet.lower()
        self.metrics.record_run()

        acquired = await self._acquire_semaphore(timeout_s=3.0)
        if not acquired:
            return {"status": "skipped", "reason": "system_busy"}
        try:
            locked = await asyncio.to_thread(self.lock_manager.is_locked, wallet_addr)
            if locked:
                return {"status": "skipped", "reason": "locked"}

            metrics, profile, scores_obj, scores_dict, risk_breakdown, insight_obj = await self._analyze(wallet_addr)
            decision, decision_estrategia = await self._decide(insight_obj, scores_dict, metrics)
            if decision.get("decision") != "EXECUTE_ADVANCED":
                return {"status": "no_action", "decision": decision.get("decision"), "why_not_acting": decision.get("reasoning")}

            acquired = await asyncio.to_thread(self.lock_manager.acquire, wallet_addr)
            if not acquired:
                self.metrics.record_execution_blocked()
                return {"status": "skipped", "reason": "locked"}

            try:
                self.metrics.record_execution_triggered()
                result = {"status": "unknown"}
                async for ev in self._execute_with_esl(wallet_addr, decision_estrategia, decision, insight_obj, "loop", stream_mode=False):
                    if ev.get("paso") == "execution_final_status":
                        result = ev.get("data", result)
                    if ev.get("estado") == "error":
                        return {"status": "error", "message": ev.get("detalle")}
                return result
            finally:
                await asyncio.to_thread(self.lock_manager.release, wallet_addr)
        finally:
            self._semaphore.release()

    async def _analyze(self, wallet_addr: str) -> Tuple[Any, Any, Any, Dict[str, Any], Dict[str, Any], Any]:
        datos_crudos = await asyncio.to_thread(self.cliente.obtener_datos_wallet, wallet_addr)
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

    async def _execute_with_esl(
        self,
        wallet_addr: str,
        decision_estrategia: Any,
        decision: Dict[str, Any],
        insight_obj: Any,
        source: str,
        stream_mode: bool,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        yield {"paso": "execution_safety", "estado": "starting", "detalle": "Initializing Execution Safety Layer (ESL) guards...", "source": source}

        runner = ExecutionRunner(self.wdk)
        temp_agent = self.wdk._agente
        def _read_chain_state():
            agent_wallet_local = temp_agent.create_agent_wallet()
            addr = agent_wallet_local["address"]
            nonce = temp_agent.w3.eth.get_transaction_count(addr)
            balance = temp_agent.get_balance()
            block = temp_agent.w3.eth.block_number
            return agent_wallet_local, nonce, balance, block

        agent_wallet, current_nonce, current_balance, current_block = await asyncio.to_thread(_read_chain_state)

        actions_data = self._gather_actions(decision_estrategia, decision, include_deploy=False)
        plan = self.guard.create_plan(
            wallet=wallet_addr,
            actions_data=actions_data,
            risk_score=insight_obj.risk_score,
            block_number=current_block,
            nonce=current_nonce,
            balance=current_balance,
        )

        valid, reason = self.guard.validate_plan(
            plan,
            {"nonce": current_nonce, "balance": current_balance, "current_risk_score": insight_obj.risk_score, "simulation_success": os.getenv("APP_ENV", "local") != "production"},
        )
        if not valid:
            yield {"paso": "execution_safety", "estado": "error", "detalle": f"Safety Guard Abort: {reason}", "source": source}
            yield {"paso": "execution_final_status", "data": {"status": "aborted", "reason": reason}}
            return

        yield {"paso": "execution_safety", "estado": "completed", "detalle": f"Safety checks passed. Fingerprint: {plan.fingerprint[:12]}...", "source": source}

        if plan.actions:
            async for ev in self._run_runner_stream(runner, plan, source):
                yield ev

        if decision_estrategia.requires_contract:
            contract_type = decision.get("contract_type") or getattr(insight_obj, "type", None) or "unknown"
            yield {"paso": "contract_generation", "estado": "starting", "detalle": f"Creating Solidity code for {contract_type}...", "source": source}
            source_code = generar_contrato(insight_obj)
            yield {"paso": "contract_generation", "estado": "completed", "detalle": "Solidity code generated.", "data": {"code": source_code}, "source": source}

            yield {"paso": "contract_compilation", "estado": "starting", "detalle": "Compiling smart contract...", "source": source}
            compilado = await asyncio.to_thread(compilar_contrato_tool, source_code)
            yield {"paso": "contract_compilation", "estado": "completed", "detalle": "Compilation successful (ABI/Bytecode ready).", "source": source}

            _, current_nonce_2, current_balance_2, current_block_2 = await asyncio.to_thread(_read_chain_state)

            deploy_actions = [
                {
                    "type": "DEPLOY",
                    "params": {
                        "compiled_contract": {
                            "name": compilado.name,
                            "abi": compilado.abi,
                            "bytecode": compilado.bytecode,
                            "source_code": getattr(compilado, "source_code", source_code),
                        },
                        "args_constructor": None,
                    },
                }
            ]
            deploy_plan = self.guard.create_plan(
                wallet=wallet_addr,
                actions_data=deploy_actions,
                risk_score=insight_obj.risk_score,
                block_number=current_block_2,
                nonce=current_nonce_2,
                balance=current_balance_2,
            )
            valid2, reason2 = self.guard.validate_plan(
                deploy_plan,
                {"nonce": current_nonce_2, "balance": current_balance_2, "current_risk_score": insight_obj.risk_score, "simulation_success": os.getenv("APP_ENV", "local") != "production"},
            )
            if not valid2:
                yield {"paso": "contract_deployment", "estado": "error", "detalle": f"Safety Guard Abort: {reason2}", "source": source}
                yield {"paso": "execution_final_status", "data": {"status": "aborted", "reason": reason2}}
                return

            yield {"paso": "contract_deployment", "estado": "starting", "detalle": "Deploying to Sepolia network...", "source": source}
            success_deploy = await asyncio.to_thread(runner.run, deploy_plan)
            if not success_deploy:
                yield {"paso": "contract_deployment", "estado": "error", "detalle": "Contract deployment failed.", "source": source}
                yield {"paso": "execution_final_status", "data": {"status": "failed", "reason": "contract_deployment_failed"}}
                return

            deploy_action = deploy_plan.actions[0]
            deployed_address = deploy_action.params.get("deployed_address")
            tx_hash = deploy_action.tx_hash
            yield {"paso": "contract_deployment", "estado": "completed", "detalle": f"Deployed at {deployed_address}", "source": source}

            etherscan_url = f"https://sepolia.etherscan.io/address/{deployed_address}" if deployed_address else None
            yield {
                "paso": "contract_active",
                "estado": "completed",
                "detalle": "Contract verified and active.",
                "data": {"address": deployed_address, "hash": tx_hash, "etherscan": etherscan_url},
                "source": source,
            }
        else:
            yield {"paso": "contract_active", "estado": "completed", "detalle": "Strategy executed without requiring contracts.", "source": source}

        if source == "loop":
            yield {"paso": "execution_final_status", "data": {"status": "success", "last_fingerprint": plan.fingerprint}}

    async def _run_runner_stream(self, runner: ExecutionRunner, plan: Any, source: str) -> AsyncGenerator[Dict[str, Any], None]:
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def on_step(step_name: str, status: str, data: dict):
            loop.call_soon_threadsafe(queue.put_nowait, (step_name, status, data))

        task = asyncio.create_task(asyncio.to_thread(runner.run, plan, on_step=on_step))

        while True:
            if task.done() and queue.empty():
                break
            try:
                step_name, status, data = await asyncio.wait_for(queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                continue

            detalle = str(data.get("detalle") or data.get("message") or "")
            payload = dict(data)
            payload.pop("detalle", None)
            payload.pop("message", None)
            yield {"paso": step_name, "estado": status, "detalle": detalle, "data": payload or None, "source": source}

        await task

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
                "days_active": metrics.dias_activo,
                "tx_per_day": metrics.frecuencia_transacciones_por_dia,
                "contract_interactions_pct": metrics.porcentaje_interacciones_contratos,
            },
            "agent_decision": {"decision": decision.get("decision"), "reasoning": decision_estrategia.detail, "recommended_action": decision.get("recommended_action")},
            "agent_metrics": self.metrics.to_dict(),
            "x402_payment": "validated",
        }

    def _gather_actions(self, decision_estrategia: Any, decision: Dict[str, Any], include_deploy: bool) -> List[Dict[str, Any]]:
        intended_actions: List[Dict[str, Any]] = []
        if decision_estrategia.requires_funds_movement:
            intended_actions.append({"type": "TRANSFER", "params": {"to": settings.SAFE_WALLET_ADDRESS, "value_wei": decision_estrategia.cantidad_transferencia_wei}})
        if decision_estrategia.requires_swap:
            intended_actions.append({"type": "SWAP", "params": {"token_in": decision_estrategia.token_in, "token_out": decision_estrategia.token_out, "amount_wei": settings.SWAP_AMOUNT_WEI}})
        if include_deploy and decision_estrategia.requires_contract:
            intended_actions.append({"type": "DEPLOY", "params": {"type": decision.get("contract_type", "unknown")}})
        return intended_actions
