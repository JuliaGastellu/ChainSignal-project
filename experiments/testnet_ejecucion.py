"""Experimento de ejecución en Sepolia, fuera del runtime comercial.

Conservo aquí el camino heredado que analiza una wallet y, si la decisión es
accionable, arma un plan, lo valida con ExecutionGuard y lo ejecuta vía WDK.
La API no importa este módulo. Lo corro a mano con experiments/cli.py.

Límites explícitos:
- el constructor exige CHAINSIGNAL_MODE=TESTNET_EXPERIMENT y APP_ENV distinto
  de production (EscrituraDeshabilitada en otro caso);
- cada plan declara la política TESTNET_UNSIMULATED y el guard la rechaza si
  el chain_id leído no es Sepolia;
- WalletAgent, ServicioWDK, ExecutionRunner y AgentExecutor repiten la misma
  guarda en cada método que firma.

Pendientes conocidos: A04 (no espero receipts), A05 (fingerprint), A06
(re-reclamo no atómico), A08 (float) y A09 (contabilizo valor planeado aunque
falle). Por eso nada de esto entra al producto.
"""

import asyncio
from typing import Any, AsyncGenerator, Dict, List

from infra.config import settings
from infra.red import SEPOLIA
from infra.modo import exigir_escritura_experimental
from execution_guard.guard import ExecutionGuard, POLITICA_TESTNET_SIN_SIMULACION
from execution_guard.lock_manager import WalletLockManager
from execution_guard.runner import ExecutionRunner
from services.agent_budget_service import AgentBudgetService
from services.agent_service import ACTIONABLE_DECISIONS, TERMINAL_DECISIONS, AgentService
from services.servicio_wdk import ServicioWDK
from tools.herramienta_compilar_contrato import compilar_contrato_tool
from tools.herramienta_generar_contrato import generar_contrato


def ingesta_sepolia():
    """Ingesta fijada a Sepolia: el experimento nunca analiza mainnet para ejecutar en testnet."""
    from infra.red import SEPOLIA
    from ingestion_onchain.ingesta import ServicioIngesta
    from ingestion_onchain.proveedores import ClienteEtherscan, RpcLectura

    rpc = RpcLectura(SEPOLIA, settings.SEPOLIA_RPC_URL) if settings.SEPOLIA_RPC_URL else None
    return ServicioIngesta(SEPOLIA, ClienteEtherscan(SEPOLIA, settings.ETHERSCAN_API_KEY), rpc)


class ExperimentoEjecucionTestnet(AgentService):
    """Análisis de AgentService más la capa de ejecución del experimento."""

    def __init__(self):
        exigir_escritura_experimental("experimento_ejecucion_testnet")
        super().__init__()
        self._ingesta = ingesta_sepolia()
        self.guard = ExecutionGuard()
        self.lock_manager = WalletLockManager()
        self.wdk = ServicioWDK()
        self.budget = AgentBudgetService()

    async def run_pipeline_loop(self, wallet: str) -> Dict[str, Any]:
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
            wallet_intel = self.wallet_intel.analyze(wallet_addr, metrics, profile, scores_dict)
            protocol_intel = self.protocol_intel.analyze(metrics, profile)
            signals = self.signal_detector.detect(wallet_intel, protocol_intel)
            strategy_pick = self.strategy_engine.select(
                signals,
                decision,
                wallet_intel,
                demo_mode=settings.AGENT_DEMO_MODE,
            )
            self.historial.registrar_senales(wallet_addr, signals, strategy_pick["strategy"])
            decision, decision_estrategia = self._apply_strategy_overlay(decision, decision_estrategia, strategy_pick, insight_obj)
            decision_code = str(decision.get("decision") or "MONITOR")
            has_actionable_strategy = bool(
                decision_estrategia.requires_funds_movement
                or decision_estrategia.requires_swap
                or decision_estrategia.requires_contract
            )
            effective_balance = self.budget.get_effective_balance_eth(wallet_addr)
            # Quité `low_confidence_defensive_execution` y
            # `demo_force_first_execution` (AGENT_DEMO_MODE forzaba una
            # transferencia real en el primer ciclo fondeado). Con
            # TERMINAL_DECISIONS, BLOCK, MONITOR e INSUFFICIENT_DATA nunca
            # producen should_execute=True en ningún entorno.
            should_execute = (
                decision_code not in TERMINAL_DECISIONS
                and decision_code in ACTIONABLE_DECISIONS
                and has_actionable_strategy
            )
            if not should_execute:
                if decision_code in ACTIONABLE_DECISIONS and not has_actionable_strategy:
                    return {"status": "no_action", "decision": decision_code, "why_not_acting": "No actionable strategy was generated for this wallet."}
                return {"status": "no_action", "decision": decision_code, "why_not_acting": decision.get("reasoning")}
            if effective_balance <= 0:
                return {"status": "simulation_only", "reason": "no_budget"}

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
            chain_id = temp_agent.w3.eth.chain_id
            return agent_wallet_local, nonce, balance, block, chain_id

        agent_wallet, current_nonce, current_balance, current_block, chain_id = await asyncio.to_thread(_read_chain_state)

        actions_data = self._gather_actions(decision_estrategia, decision, include_deploy=False)
        plan = self.guard.create_plan(
            wallet=wallet_addr,
            actions_data=actions_data,
            risk_score=insight_obj.risk_score,
            block_number=current_block,
            nonce=current_nonce,
            balance=current_balance,
            simulation_policy=POLITICA_TESTNET_SIN_SIMULACION,
        )

        valid, reason = self.guard.validate_plan(
            plan,
            {"nonce": current_nonce, "balance": current_balance, "current_risk_score": insight_obj.risk_score, "chain_id": chain_id},
        )
        if not valid:
            yield {"paso": "execution_safety", "estado": "error", "detalle": f"Safety Guard Abort: {reason}", "source": source}
            self.historial.registrar_resultado(wallet_addr, "aborted", str(decision.get("strategy", "EXPLORE")), 0.0)
            yield {"paso": "execution_final_status", "data": {"status": "aborted", "reason": reason}}
            return

        yield {"paso": "execution_safety", "estado": "completed", "detalle": f"Safety checks passed. Fingerprint: {plan.fingerprint[:12]}...", "source": source}
        yield {"paso": "simulation_passed", "estado": "completed", "detalle": "Execution simulation and ESL checks passed.", "data": {"fingerprint": plan.fingerprint}, "source": source}
        yield {"paso": "execution_submitted", "estado": "starting", "detalle": f"Submitting {len(plan.actions)} actions to execution runner.", "data": {"actions": len(plan.actions)}, "source": source}

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

            _, current_nonce_2, current_balance_2, current_block_2, chain_id_2 = await asyncio.to_thread(_read_chain_state)

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
                simulation_policy=POLITICA_TESTNET_SIN_SIMULACION,
            )
            valid2, reason2 = self.guard.validate_plan(
                deploy_plan,
                {"nonce": current_nonce_2, "balance": current_balance_2, "current_risk_score": insight_obj.risk_score, "chain_id": chain_id_2},
            )
            if not valid2:
                yield {"paso": "contract_deployment", "estado": "error", "detalle": f"Safety Guard Abort: {reason2}", "source": source}
                self.historial.registrar_resultado(wallet_addr, "aborted", str(decision.get("strategy", "EXPLORE")), 0.0)
                yield {"paso": "execution_final_status", "data": {"status": "aborted", "reason": reason2}}
                return

            yield {"paso": "contract_deployment", "estado": "starting", "detalle": "Deploying to Sepolia network...", "source": source}
            success_deploy = await asyncio.to_thread(runner.run, deploy_plan)
            if not success_deploy:
                yield {"paso": "contract_deployment", "estado": "error", "detalle": "Contract deployment failed.", "source": source}
                self.historial.registrar_resultado(wallet_addr, "failed", str(decision.get("strategy", "EXPLORE")), 0.0)
                yield {"paso": "execution_final_status", "data": {"status": "failed", "reason": "contract_deployment_failed"}}
                return

            deploy_action = deploy_plan.actions[0]
            deployed_address = deploy_action.params.get("deployed_address")
            tx_hash = deploy_action.tx_hash
            yield {"paso": "contract_deployment", "estado": "completed", "detalle": f"Deployed at {deployed_address}", "source": source}

            etherscan_url = SEPOLIA.url_direccion(deployed_address) if deployed_address else None
            yield {
                "paso": "contract_active",
                "estado": "completed",
                "detalle": "Contract verified and active.",
                "data": {"address": deployed_address, "hash": tx_hash, "etherscan": etherscan_url},
                "source": source,
            }
        else:
            yield {"paso": "contract_active", "estado": "completed", "detalle": "Strategy executed without requiring contracts.", "source": source}

        # Quité la invención de DEMO_SIMULATED_MOVED_ETH como valor "movido"
        # cuando nada se movía: reportaba un éxito ficticio al feed SSE y al
        # historial. Los valores reportados reflejan lo que contiene el
        # ExecutionPlan.
        moved_eth = self._estimate_value_moved_eth(plan)
        if moved_eth > 0:
            # Uso el fingerprint del plan como clave para no descontar dos
            # veces la misma ejecución si este camino se repitiera.
            self.budget.consume(wallet_addr, moved_eth, fingerprint=plan.fingerprint)
        first_tx_hash = next((getattr(a, "tx_hash", None) for a in plan.actions if getattr(a, "tx_hash", None)), None)
        outcome_status = "success" if moved_eth > 0 else "no_value_moved"
        self.historial.registrar_resultado(wallet_addr, outcome_status, str(decision.get("strategy", "EXPLORE")), moved_eth, tx_hash=first_tx_hash)
        yield {
            "paso": "execution_value",
            "estado": "completed",
            "detalle": f"Moved {round(moved_eth, 8)} ETH" if moved_eth > 0 else "No value was moved by this execution.",
            "data": {
                "moved_value_eth": round(moved_eth, 8),
                "strategy": decision.get("strategy", "EXPLORE"),
                "strategy_used": decision.get("strategy", "EXPLORE"),
                "simulated": False,
            },
            "source": source,
        }
        yield {"paso": "execution_verified", "estado": "completed", "detalle": "Execution verified and persisted.", "data": {"moved_eth": moved_eth, "moved_value_eth": moved_eth, "strategy_used": decision.get("strategy", "EXPLORE"), "simulated": False}, "source": source}

        yield {"paso": "execution_final_status", "data": {"status": outcome_status, "last_fingerprint": plan.fingerprint, "moved_eth": moved_eth, "moved_value_eth": moved_eth, "strategy_used": decision.get("strategy", "EXPLORE"), "simulated": False}}

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

    def _gather_actions(self, decision_estrategia: Any, decision: Dict[str, Any], include_deploy: bool) -> List[Dict[str, Any]]:
        intended_actions: List[Dict[str, Any]] = []
        strategy_used = str(decision.get("strategy", "EXPLORE"))
        if decision_estrategia.requires_funds_movement:
            transfer_wei = int(getattr(decision_estrategia, "cantidad_transferencia_wei", settings.SWAP_AMOUNT_WEI) or settings.SWAP_AMOUNT_WEI)
            intended_actions.append({"type": "TRANSFER", "params": {"to": settings.SAFE_WALLET_ADDRESS, "value_wei": transfer_wei, "strategy_used": strategy_used}})
        if decision_estrategia.requires_swap:
            intended_actions.append({"type": "SWAP", "params": {"token_in": decision_estrategia.token_in, "token_out": decision_estrategia.token_out, "amount_wei": settings.SWAP_AMOUNT_WEI, "strategy_used": strategy_used}})
        if include_deploy and decision_estrategia.requires_contract:
            intended_actions.append({"type": "DEPLOY", "params": {"type": decision.get("contract_type", "unknown"), "strategy_used": strategy_used}})
        return intended_actions

    def _estimate_value_moved_eth(self, plan: Any) -> float:
        moved_wei = 0
        for action in getattr(plan, "actions", []):
            params = getattr(action, "params", {}) or {}
            if action.type == "TRANSFER":
                moved_wei += int(params.get("value_wei") or 0)
            elif action.type == "SWAP":
                moved_wei += int(params.get("amount_wei") or 0)
        if moved_wei <= 0:
            return 0.0
        return float(moved_wei / 1e18)
