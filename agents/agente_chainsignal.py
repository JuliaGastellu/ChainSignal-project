"""Agente central de ChainSignal: planifica y ejecuta operaciones on-chain.

AgenteChainSignal es el orquestador principal del sistema. Recibe un insight
de análisis de wallet, decide si requiere infraestructura on-chain y ejecuta
el ciclo completo: generación → compilación → despliegue → interacción → lectura.

Utiliza OpenClaw como runtime de orquestación cuando está disponible.
En caso contrario, ejecuta las herramientas directamente en secuencia.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from domain.modelos_contrato import InsightContrato, ContratoCompilado, ContratoDeplegado
from domain.modelos_transaccion import ResultadoTransaccion, EstadoContrato
from domain.modelos_agente import DecisionAgente
from tools.herramienta_generar_contrato import generar_contrato
from tools.herramienta_compilar_contrato import compilar_contrato_tool
from tools.herramienta_desplegar_contrato import desplegar_contrato
from tools.herramienta_ejecutar_funcion import ejecutar_funcion
from tools.herramienta_leer_estado import leer_estado

# Umbral de score de riesgo a partir del cual se genera infraestructura on-chain.
UMBRAL_RIESGO_ACCION = int(os.getenv("UMBRAL_RIESGO_ACCION", "60"))

# Argumentos de constructor por tipo de contrato.
_ARGS_CONSTRUCTOR = {
    "risk_guard": [60],
    "signal_lock": [3600],
    "treasury_manager": [],
}

# Archivo de registro de contratos desplegados.
_REGISTRO_CONTRATOS = Path("contratos_deployados.json")

# Archivo de registro de métricas acumuladas del agente
_METRICAS_AGENTE = Path("metricas_agente.json")


class AgenteChainSignal:
    """Agente económico autónomo capaz de crear y operar infraestructura on-chain.

    Flujo de ejecución:
        1. Recibe un insight con contexto de wallet y scores.
        2. Evalúa si el score de riesgo supera el umbral configurado.
        3. Genera el código Solidity apropiado.
        4. Compila el contrato con py-solc-x.
        5. Despliega el contrato mediante el microservicio WDK.
        6. Ejecuta una función inicial de configuración.
        7. Lee el estado resultante del contrato.
        8. Registra toda la operación en disco.
    """

    def ejecutar(self, datos_insight: dict) -> dict[str, Any]:
        """Ejecuta el ciclo completo del agente para un insight dado.

        Args:
            datos_insight: Diccionario con claves 'type', 'analyzed_wallet',
                           'risk_score' y opcionalmente 'activity_score'.

        Returns:
            Diccionario con el resultado de cada fase del ciclo.
        """
        logger.info(
            "Agent starting cycle for wallet {} (risk={}, type='{}')",
            datos_insight.get("analyzed_wallet"),
            datos_insight.get("risk_score"),
            datos_insight.get("type"),
        )

        resultado: dict[str, Any] = {
            "analyzed_wallet": datos_insight.get("analyzed_wallet"),
            "contract_type": datos_insight.get("type"),
            "risk_score": datos_insight.get("risk_score"),
            "requires_action": False,
            "agent_decision": None,
            "evaluated_strategy": None,
            "solidity_code": None,
            "compiled_contract": None,
            "deployed_contract": None,
            "executed_function": None,
            "contract_state": None,
            "financial_operation": None,
            "swap_performed": None,
            "executed_skills": None,
            "timestamp": datetime.now().isoformat(),
        }

        # Step 1: Build the domain insight model.
        try:
            insight = InsightContrato(
                type=datos_insight["type"],
                analyzed_wallet=datos_insight["analyzed_wallet"],
                risk_score=datos_insight.get("risk_score", 0),
                activity_score=datos_insight.get("activity_score", 0),
            )
        except (KeyError, ValueError) as error:
            logger.error("Invalid insight: {}", error)
            resultado["error"] = str(error)
            return resultado

        # Critical guard: if no type, do not deploy.
        if insight.type is None:
            logger.info("No contract to deploy (type=None). Monitoring only.")
            resultado["no_action_reason"] = "No contract to deploy due to lack of data or criteria."
            return resultado

        # Step 2: Protection Strategy Evaluation.
        from strategy.estrategia_proteccion_wallet import EstrategiaProteccionWallet
        estrategia = EstrategiaProteccionWallet()
        decision_estrategia = estrategia.evaluar(insight)

        es_simulacion = os.getenv("APP_ENV", "local") != "production"

        decision_agente = DecisionAgente(
            contexto_analizado=f"Risk Score: {insight.risk_score}, Activity: {insight.activity_score}",
            evaluated_strategy=estrategia.__class__.__name__,
            chosen_actions=decision_estrategia.actions,
            reason=decision_estrategia.detail,
            requires_swap=decision_estrategia.requires_swap,
            is_simulation=es_simulacion,
        )

        resultado["agent_decision"] = decision_agente.__dict__
        resultado["evaluated_strategy"] = {
            "requires_contract": decision_estrategia.requires_contract,
            "requires_funds_movement": decision_estrategia.requires_funds_movement,
            "requires_swap": decision_estrategia.requires_swap,
            "actions": decision_estrategia.actions,
            "detail": decision_estrategia.detail,
        }

        if not decision_estrategia.requires_contract and not decision_estrategia.requires_funds_movement and not decision_estrategia.requires_swap:
            logger.info("Strategy determined no actions required.")
            resultado["no_action_reason"] = decision_estrategia.detail
            return resultado

        resultado["requires_action"] = True

        # Paso 3: Operaciones Económicas Preventivas
        # Se instancia ServicioWDK antes de los bloques condicionales para evitar
        # que wdk sea usado antes de ser asignado si sólo se ejecuta movimiento de fondos.
        from services.servicio_wdk import ServicioWDK
        wdk = ServicioWDK()

        if decision_estrategia.requires_funds_movement:
            logger.info("Strategy requires funds movement. Checking own balance...")
            balance = wdk.consultar_balance()

            # Secure destination wallet for rescue tests
            wallet_segura = "0x000000000000000000000000000000000000dEaD"

            if balance and balance > 0:
                # Use AA if risk is critical for fast/gasless execution
                use_aa = insight.risk_score >= 90
                tx_financiera = wdk.transferir_activo(wallet_segura, estrategia.cantidad_transferencia_wei, use_aa=use_aa)
                resultado["financial_operation"] = {
                    "type": "transfer",
                    "destination": wallet_segura,
                    "success": tx_financiera.exitoso,
                    "hash": tx_financiera.transaction_hash,
                }
            else:
                logger.warning("Insufficient balance for preventive operation.")
                resultado["financial_operation"] = {"error": "Insufficient balance."}

        # Step 3.5: Preventive Swap (Velora WDK)
        if decision_estrategia.requires_swap:
            logger.info("Strategy requires preventive SWAP. Fetching quote...")
            # Test amount: 0.0005 ETH (in wei) for the swap
            monto_swap_wei = 500000000000000

            quote = wdk.obtener_cotizacion_swap(decision_estrategia.token_in, decision_estrategia.token_out, monto_swap_wei)

            if quote or es_simulacion:
                logger.info("Quote received. Executing on-chain swap...")
                # Use AA for emergency swaps
                use_aa = insight.risk_score >= 80
                tx_swap = wdk.ejecutar_swap(decision_estrategia.token_in, decision_estrategia.token_out, monto_swap_wei, use_aa=use_aa)
                resultado["swap_performed"] = {
                    "token_in": decision_estrategia.token_in,
                    "token_out": decision_estrategia.token_out,
                    "success": tx_swap.exitoso,
                    "hash": tx_swap.transaction_hash,
                }
            else:
                logger.warning("Could not fetch swap quote.")
                resultado["swap_performed"] = {"error": "Quote fetch failed."}

        # Steps 4 to 8: On-Chain Infrastructure
        if decision_estrategia.requires_contract:
            # Step 4: Contract generation.
            try:
                codigo = generar_contrato(insight)
                resultado["solidity_code"] = codigo
            except Exception as error:
                logger.error("Contract generation failed: {}", error)
                resultado["error"] = f"Generation: {error}"
                return resultado

            # Step 5: Compilation.
            try:
                compilado: ContratoCompilado = compilar_contrato_tool(codigo)
                resultado["compiled_contract"] = {
                    "name": compilado.name,
                    "abi_entries": len(compilado.abi),
                    "bytecode_length": len(compilado.bytecode),
                }
            except Exception as error:
                logger.error("Compilation failed: {}", error)
                resultado["error"] = f"Compilation: {error}"
                return resultado

            # Step 6: Blockchain deployment.
            args_constructor = _ARGS_CONSTRUCTOR.get(insight.type, [])
            desplegado: ContratoDeplegado | None = desplegar_contrato(
                compilado, args_constructor=args_constructor
            )

            if desplegado is None:
                logger.warning(
                    "Deployment skipped (WDK not available). "
                    "The contract was generated and compiled correctly."
                )
                resultado["notice"] = "WDK not available. Deployment pending."
                return resultado

            resultado["deployed_contract"] = {
                "address": desplegado.address,
                "transaction_hash": desplegado.transaction_hash,
            }

            # Step 7: Initial function execution based on contract type.
            if decision_estrategia.requires_execution:
                funcion_inicial, args_fn = self._funcion_inicial(insight.type, insight.risk_score)
                if funcion_inicial:
                    tx: ResultadoTransaccion = ejecutar_funcion(
                        desplegado, funcion_inicial, args=args_fn
                    )
                    resultado["executed_function"] = {
                        "function": funcion_inicial,
                        "success": tx.exitoso,
                        "transaction_hash": tx.transaction_hash,
                    }

            # Step 8: Reading resulting state.
            state_field = self._state_field(insight.type)
            if state_field:
                state: EstadoContrato = leer_estado(desplegado, state_field)
                resultado["contract_state"] = {
                    "field": state.campo,
                    "value": state.valor,
                    "success": state.exitoso,
                }

        # Step 9: Agent Skills Layer (EXECUTE_ADVANCED)
        # Skills are invoked as an optional additional layer — they do not replace
        # any existing logic; they enrich the result with extra data.
        resultado["executed_skills"] = self._invoke_skills(insight, wdk)

        # Step 10: Persistent record of the operation.
        self._record_operation(resultado)

        logger.info("AgenteChainSignal cycle completed successfully.")
        return resultado


    def _funcion_inicial(
        self, type_val: str, risk_score: int
    ) -> tuple[str | None, list]:
        """Returns the initial function and its arguments based on the contract type."""
        if type_val == "risk_guard":
            return "actualizarPausa", [risk_score]
        return None, []

    def _state_field(self, type_val: str) -> str | None:
        """Returns the state field to read based on the contract type."""
        fields = {
            "risk_guard": "pausado",
            "signal_lock": "desbloqueoTimestamp",
            "treasury_manager": "scoreActividadInicial",
        }
        return fields.get(type_val)

    def _invoke_skills(
        self, insight: "InsightContrato", wdk: "ServicioWDK"
    ) -> dict[str, Any]:
        """Invokes WDK Agent Skills as an additional layer of intelligence.

        This layer is activated when the risk score exceeds the threshold and the
        system has already evaluated its main strategy. Skills enrich the
        result with real-time data (balance, quote) without mutating
        the classification logic or the decision engine.

        If the WDK is not available, it returns simulated data via ServicioWDK.

        Args:
            insight: The analysis context of the wallet.
            wdk: Already initialized instance of ServicioWDK.

        Returns:
            Dictionary with the results of each invoked skill.
        """
        summary: dict[str, Any] = {}
        logger.info("Invoking Agent Skills for wallet {}", insight.analyzed_wallet)

        # Skill 1: Balance of the analyzed wallet
        try:
            balance_data = wdk.skill_obtener_balance(insight.analyzed_wallet)
            summary["analyzed_wallet_balance"] = balance_data
        except Exception as error:
            logger.warning("Skill obtener_balance failed: {}", error)
            summary["analyzed_wallet_balance"] = {"error": str(error)}

        # Skill 2: Preventive swap quote if high risk
        if insight.risk_score >= 80:
            token_out = "0xdAC17F958D2ee523a2206206994597C13D831ec7"  # USD₮
            monto_wei = 500_000_000_000_000  # 0.0005 ETH
            try:
                quote = wdk.skill_obtener_cotizacion("ETH", token_out, monto_wei)
                summary["preventive_swap_quote"] = quote
            except Exception as error:
                logger.warning("Skill obtener_cotizacion failed: {}", error)
                summary["preventive_swap_quote"] = {"error": str(error)}

        logger.info("Agent Skills completed: {} data points obtained", len(summary))
        return summary

    def _record_operation(self, result: dict) -> None:
        """Persists the cycle result to the registry file and updates metrics."""
        # 1. Contract Registry (append)
        try:
            existing_data: dict = {"contracts": []}
            if _REGISTRO_CONTRATOS.exists():
                with _REGISTRO_CONTRATOS.open("r", encoding="utf-8") as file:
                    existing_data = json.load(file)

            existing_data["contracts"].append({
                "timestamp": result["timestamp"],
                "analyzed_wallet": result["analyzed_wallet"],
                "type": result["contract_type"],
                "address": result.get("deployed_contract", {}).get("address"),
                "transaction_hash": result.get("deployed_contract", {}).get(
                    "transaction_hash"
                ),
            })

            with _REGISTRO_CONTRATOS.open("w", encoding="utf-8") as file:
                json.dump(existing_data, file, indent=2, ensure_ascii=False)

        except Exception as error:
            logger.warning("Could not record operation on disk: {}", error)

        # 2. Update accumulated economic metrics
        try:
            metrics_dict = {
                "protected_value_eth": 0.0,
                "transactions_performed": 0,
                "contracts_created": 0
            }
            if _METRICAS_AGENTE.exists():
                with _METRICAS_AGENTE.open("r", encoding="utf-8") as file:
                    metrics_dict = json.load(file)

            if result.get("deployed_contract"):
                metrics_dict["contracts_created"] += 1
                metrics_dict["transactions_performed"] += 1 # deploy tx

            if result.get("executed_function"):
                metrics_dict["transactions_performed"] += 1 # call tx

            if result.get("financial_operation", {}).get("success"):
                metrics_dict["transactions_performed"] += 1 # transfer tx
                metrics_dict["protected_value_eth"] += 0.001

            if result.get("swap_performed", {}).get("success"):
                metrics_dict["transactions_performed"] += 1 # swap tx
                metrics_dict["protected_value_eth"] += 0.0005 # The swap amount

            with _METRICAS_AGENTE.open("w", encoding="utf-8") as file:
                json.dump(metrics_dict, file, indent=2, ensure_ascii=False)

        except Exception as error:
            logger.warning("Could not record agent metrics: {}", error)
