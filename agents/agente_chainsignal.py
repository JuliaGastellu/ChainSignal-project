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
            datos_insight: Diccionario con claves 'tipo', 'wallet_analizada',
                           'score_riesgo' y opcionalmente 'score_actividad'.

        Returns:
            Diccionario con el resultado de cada fase del ciclo.
        """
        logger.info(
            "Agente iniciando ciclo para wallet {} (riesgo={}, tipo='{}')",
            datos_insight.get("wallet_analizada"),
            datos_insight.get("score_riesgo"),
            datos_insight.get("tipo"),
        )

        resultado: dict[str, Any] = {
            "wallet_analizada": datos_insight.get("wallet_analizada"),
            "tipo_contrato": datos_insight.get("tipo"),
            "score_riesgo": datos_insight.get("score_riesgo"),
            "requiere_accion": False,
            "decision_agente": None,
            "estrategia_evaluada": None,
            "codigo_solidity": None,
            "contrato_compilado": None,
            "contrato_desplegado": None,
            "funcion_ejecutada": None,
            "estado_contrato": None,
            "operacion_financiera": None,
            "swap_realizado": None,
            "skills_ejecutados": None,
            "timestamp": datetime.now().isoformat(),
        }

        # Paso 1: Construir el modelo de insight del dominio.
        try:
            insight = InsightContrato(
                tipo=datos_insight["tipo"],
                wallet_analizada=datos_insight["wallet_analizada"],
                score_riesgo=datos_insight.get("score_riesgo", 0),
                score_actividad=datos_insight.get("score_actividad", 0),
            )
        except (KeyError, ValueError) as error:
            logger.error("Insight inválido: {}", error)
            resultado["error"] = str(error)
            return resultado

        # Guardia crítica: cuando no hay tipo, no se despliega.
        if insight.tipo is None:
            logger.info("Sin contrato a desplegar (tipo=None). Solo monitoreo.")
            resultado["motivo_sin_accion"] = "Sin contrato a desplegar por falta de datos o criterio."
            return resultado

        # Paso 2: Evaluación de Estrategia de Protección.
        from strategy.estrategia_proteccion_wallet import EstrategiaProteccionWallet
        estrategia = EstrategiaProteccionWallet()
        decision_estrategia = estrategia.evaluar(insight)

        es_simulacion = os.getenv("APP_ENV", "local") != "production"

        decision_agente = DecisionAgente(
            contexto_analizado=f"Score Riesgo: {insight.score_riesgo}, Actividad: {insight.score_actividad}",
            estrategia_evaluada=estrategia.__class__.__name__,
            acciones_elegidas=decision_estrategia.acciones,
            motivo=decision_estrategia.detalle,
            requiere_swap=decision_estrategia.requiere_swap,
            es_simulacion=es_simulacion,
        )

        resultado["decision_agente"] = decision_agente.__dict__
        resultado["estrategia_evaluada"] = {
            "requiere_contrato": decision_estrategia.requiere_contrato,
            "requiere_movimiento_fondos": decision_estrategia.requiere_movimiento_fondos,
            "requiere_swap": decision_estrategia.requiere_swap,
            "acciones": decision_estrategia.acciones,
            "detalle": decision_estrategia.detalle,
        }

        if not decision_estrategia.requiere_contrato and not decision_estrategia.requiere_movimiento_fondos and not decision_estrategia.requiere_swap:
            logger.info("Estrategia determinó que no hay acciones requeridas.")
            resultado["motivo_sin_accion"] = decision_estrategia.detalle
            return resultado

        resultado["requiere_accion"] = True

        # Paso 3: Operaciones Económicas Preventivas
        # Se instancia ServicioWDK antes de los bloques condicionales para evitar
        # que wdk sea usado antes de ser asignado si sólo se ejecuta movimiento de fondos.
        from services.servicio_wdk import ServicioWDK
        wdk = ServicioWDK()

        if decision_estrategia.requiere_movimiento_fondos:
            logger.info("Estrategia requiere movimiento de fondos. Consultando balance propio...")
            balance = wdk.consultar_balance()

            # Billetera segura de destino para tests de rescate
            wallet_segura = "0x000000000000000000000000000000000000dEaD"

            if balance and balance > 0:
                # Usar AA si el riesgo es crítico para asegurar ejecución rápida/gasless
                use_aa = insight.score_riesgo >= 90
                tx_financiera = wdk.transferir_activo(wallet_segura, estrategia.cantidad_transferencia_wei, use_aa=use_aa)
                resultado["operacion_financiera"] = {
                    "tipo": "transferencia",
                    "destino": wallet_segura,
                    "exitoso": tx_financiera.exitoso,
                    "hash": tx_financiera.transaction_hash,
                }
            else:
                logger.warning("No hay balance suficiente para la operación preventiva.")
                resultado["operacion_financiera"] = {"error": "Balance insuficiente."}

        # Paso 3.5: Swap Preventivo (Velora WDK)
        if decision_estrategia.requiere_swap:
            logger.info("Estrategia requiere SWAP preventivo. Consultando cotización...")
            # Monto de prueba: 0.0005 ETH (en wei) para el swap
            monto_swap_wei = 500000000000000

            quote = wdk.obtener_cotizacion_swap(decision_estrategia.token_in, decision_estrategia.token_out, monto_swap_wei)

            if quote or es_simulacion:
                logger.info("Cotización recibida. Ejecutando swap on-chain...")
                # Usar AA para swaps de emergencia
                use_aa = insight.score_riesgo >= 80
                tx_swap = wdk.ejecutar_swap(decision_estrategia.token_in, decision_estrategia.token_out, monto_swap_wei, use_aa=use_aa)
                resultado["swap_realizado"] = {
                    "token_in": decision_estrategia.token_in,
                    "token_out": decision_estrategia.token_out,
                    "exitoso": tx_swap.exitoso,
                    "hash": tx_swap.transaction_hash,
                }
            else:
                logger.warning("No se pudo obtener cotización para el swap.")
                resultado["swap_realizado"] = {"error": "Fallo en cotización."}

        # Paso 4 a 8: Infraestructura On-Chain
        if decision_estrategia.requiere_contrato:
            # Paso 4: Generación del contrato.
            try:
                codigo = generar_contrato(insight)
                resultado["codigo_solidity"] = codigo
            except Exception as error:
                logger.error("Fallo en generación de contrato: {}", error)
                resultado["error"] = f"Generación: {error}"
                return resultado

            # Paso 5: Compilación.
            try:
                compilado: ContratoCompilado = compilar_contrato_tool(codigo)
                resultado["contrato_compilado"] = {
                    "nombre": compilado.nombre,
                    "abi_entradas": len(compilado.abi),
                    "bytecode_longitud": len(compilado.bytecode),
                }
            except Exception as error:
                logger.error("Fallo en compilación: {}", error)
                resultado["error"] = f"Compilación: {error}"
                return resultado

            # Paso 6: Despliegue en blockchain.
            args_constructor = _ARGS_CONSTRUCTOR.get(insight.tipo, [])
            desplegado: ContratoDeplegado | None = desplegar_contrato(
                compilado, args_constructor=args_constructor
            )

            if desplegado is None:
                logger.warning(
                    "Despliegue omitido (WDK no disponible). "
                    "El contrato fue generado y compilado correctamente."
                )
                resultado["aviso"] = "WDK no disponible. Despliegue pendiente."
                return resultado

            resultado["contrato_desplegado"] = {
                "direccion": desplegado.direccion,
                "transaction_hash": desplegado.transaction_hash,
            }

            # Paso 7: Ejecución de función inicial según el tipo de contrato.
            if decision_estrategia.requiere_ejecucion:
                funcion_inicial, args_fn = self._funcion_inicial(insight.tipo, insight.score_riesgo)
                if funcion_inicial:
                    tx: ResultadoTransaccion = ejecutar_funcion(
                        desplegado, funcion_inicial, args=args_fn
                    )
                    resultado["funcion_ejecutada"] = {
                        "funcion": funcion_inicial,
                        "exitoso": tx.exitoso,
                        "transaction_hash": tx.transaction_hash,
                    }

            # Paso 8: Lectura del estado resultante.
            campo_estado = self._campo_estado(insight.tipo)
            if campo_estado:
                estado: EstadoContrato = leer_estado(desplegado, campo_estado)
                resultado["estado_contrato"] = {
                    "campo": estado.campo,
                    "valor": estado.valor,
                    "exitoso": estado.exitoso,
                }

        # Paso 9: Capa de Agent Skills (EXECUTE_ADVANCED)
        # Los skills se invocan como capa adicional opcional — no reemplazan
        # ninguna lógica existente; enriquecen el resultado con datos extra.
        resultado["skills_ejecutados"] = self._invocar_skills(insight, wdk)

        # Paso 10: Registro persistente de la operación.
        self._registrar_operacion(resultado)

        logger.info("Ciclo del AgenteChainSignal completado exitosamente.")
        return resultado


    def _funcion_inicial(
        self, tipo: str, score_riesgo: int
    ) -> tuple[str | None, list]:
        """Retorna la función inicial y sus argumentos según el tipo de contrato."""
        if tipo == "risk_guard":
            return "actualizarPausa", [score_riesgo]
        return None, []

    def _campo_estado(self, tipo: str) -> str | None:
        """Retorna el campo de estado a leer según el tipo de contrato."""
        campos = {
            "risk_guard": "pausado",
            "signal_lock": "desbloqueoTimestamp",
            "treasury_manager": "scoreActividadInicial",
        }
        return campos.get(tipo)

    def _invocar_skills(
        self, insight: "InsightContrato", wdk: "ServicioWDK"
    ) -> dict[str, Any]:
        """Invoca los WDK Agent Skills como capa adicional de inteligencia.

        Esta capa se activa cuando el score de riesgo supera el umbral y el
        sistema ya evaluó su estrategia principal. Los skills enriquecen el
        resultado con datos en tiempo real (balance, cotización) sin mutar
        la lógica de clasificación ni el motor de decisiones.

        Si el WDK no está disponible, retorna datos simulados vía ServicioWDK.

        Args:
            insight: El contexto de análisis de la wallet.
            wdk: Instancia ya inicializada de ServicioWDK.

        Returns:
            Diccionario con los resultados de cada skill invocado.
        """
        resumen: dict[str, Any] = {}
        logger.info("Invocando Agent Skills para wallet {}", insight.wallet_analizada)

        # Skill 1: Balance de la wallet analizada
        try:
            datos_balance = wdk.skill_obtener_balance(insight.wallet_analizada)
            resumen["balance_wallet_analizada"] = datos_balance
        except Exception as error:
            logger.warning("Skill obtener_balance falló: {}", error)
            resumen["balance_wallet_analizada"] = {"error": str(error)}

        # Skill 2: Cotización de swap preventivo si hay riesgo alto
        if insight.score_riesgo >= 80:
            token_out = "0xdAC17F958D2ee523a2206206994597C13D831ec7"  # USD₮
            monto_wei = 500_000_000_000_000  # 0.0005 ETH
            try:
                cotizacion = wdk.skill_obtener_cotizacion("ETH", token_out, monto_wei)
                resumen["cotizacion_swap_preventivo"] = cotizacion
            except Exception as error:
                logger.warning("Skill obtener_cotizacion falló: {}", error)
                resumen["cotizacion_swap_preventivo"] = {"error": str(error)}

        logger.info("Agent Skills completados: {} datos obtenidos", len(resumen))
        return resumen

    def _registrar_operacion(self, resultado: dict) -> None:
        """Persiste el resultado del ciclo en el archivo de registro y actualiza métricas."""
        # 1. Registro del contrato (append)
        try:
            datos_existentes: dict = {"contratos": []}
            if _REGISTRO_CONTRATOS.exists():
                with _REGISTRO_CONTRATOS.open("r", encoding="utf-8") as archivo:
                    datos_existentes = json.load(archivo)

            datos_existentes["contratos"].append({
                "timestamp": resultado["timestamp"],
                "wallet_analizada": resultado["wallet_analizada"],
                "tipo": resultado["tipo_contrato"],
                "direccion": resultado.get("contrato_desplegado", {}).get("direccion"),
                "transaction_hash": resultado.get("contrato_desplegado", {}).get(
                    "transaction_hash"
                ),
            })

            with _REGISTRO_CONTRATOS.open("w", encoding="utf-8") as archivo:
                json.dump(datos_existentes, archivo, indent=2, ensure_ascii=False)

        except Exception as error:
            logger.warning("No se pudo registrar la operación en disco: {}", error)

        # 2. Actualización de las métricas económicas acumuladas
        try:
            metricas_dict = {
                "valor_protegido_eth": 0.0,
                "transacciones_realizadas": 0,
                "contratos_creados": 0
            }
            if _METRICAS_AGENTE.exists():
                with _METRICAS_AGENTE.open("r", encoding="utf-8") as archivo:
                    metricas_dict = json.load(archivo)

            if resultado.get("contrato_desplegado"):
                metricas_dict["contratos_creados"] += 1
                metricas_dict["transacciones_realizadas"] += 1 # deploy tx

            if resultado.get("funcion_ejecutada"):
                metricas_dict["transacciones_realizadas"] += 1 # call tx

            if resultado.get("operacion_financiera", {}).get("exitoso"):
                metricas_dict["transacciones_realizadas"] += 1 # transfer tx
                metricas_dict["valor_protegido_eth"] += 0.001

            if resultado.get("swap_realizado", {}).get("exitoso"):
                metricas_dict["transacciones_realizadas"] += 1 # swap tx
                metricas_dict["valor_protegido_eth"] += 0.0005 # El monto del swap

            with _METRICAS_AGENTE.open("w", encoding="utf-8") as archivo:
                json.dump(metricas_dict, archivo, indent=2, ensure_ascii=False)

        except Exception as error:
            logger.warning("No se pudieron registrar las métricas del agente: {}", error)
