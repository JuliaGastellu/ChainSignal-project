"""Motor de decisiones determinista para el agente AI."""
from loguru import logger

class DecisionEngine:
    """Toma decisiones financieras basadas en scores conductuales."""

    def evaluate(self, scores: dict, metrics: dict = None):
        """
        Evalúa si se debe ejecutar una acción financiera (transferencia o contrato).
        La confianza es proporcional a la cantidad de datos y la calidad del perfil.
        """
        if not scores:
            return {
                "decision": "DATOS_INSUFICIENTES",
                "confidence": 0,
                "reasoning": "el sistema no cuenta con informacion para realizar un analisis."
            }
            
        activity = scores.get("activity", 0)
        risk = scores.get("risk", 15)
        defi = scores.get("defi_engagement", 0)
        tx_count = metrics.get("transaction_count", 0) if metrics else 0
        
        logger.info(f"Evaluando decisión: Actividad={activity}, Riesgo={risk}, DeFi={defi}, Txs={tx_count}")
        
        # 1. Cálculo de Confianza Proporcional
        if tx_count <= 10:
            confidence = 0.20 + (tx_count * 0.02)
        elif tx_count <= 50:
            confidence = 0.41 + ((tx_count - 10) * 0.01)
        else:
            confidence = min(0.98, 0.81 + ((tx_count - 50) * 0.001))
            
        # 3. Límites dinámicos (Simulación/Seguridad)
        max_amount_eth = round(confidence * 0.5, 3) 
        gas_limit = 500000 if activity > 70 else 250000

        if tx_count < 5:
            decision = "DATOS_INSUFICIENTES"
            action_allowed = "NONE"
            reasoning = f"actividad ({tx_count} txs) insuficiente para establecer perfil."
            tipo_contrato = None
            accion_recomendada = "monitorear"
            ejecucion = False
        elif risk > 60:
            decision = "BLOCK"
            action_allowed = "NONE"
            reasoning = "riesgo elevado detectado en el comportamiento de la wallet."
            tipo_contrato = None
            accion_recomendada = "proteger"
            ejecucion = False
        elif confidence > 0.80 and activity > 70 and defi > 50:
            decision = "EXECUTE_ADVANCED"
            action_allowed = "ALL"
            reasoning = "perfil experto con alta confianza; se permiten operaciones avanzadas."
            ejecucion = True

            # Selección de tipo de contrato determinista
            if risk > 70:
                tipo_contrato = "risk_guard"
                accion_recomendada = "proteger"
            elif activity > 80:
                tipo_contrato = "treasury_manager"
                accion_recomendada = "optimizar"
            else:
                tipo_contrato = "signal_lock"
                accion_recomendada = "proteger"

            return {
                "decision": decision,
                "action_allowed": action_allowed,
                "confidence": round(confidence, 2),
                "reasoning": reasoning,
                "tipo_contrato": tipo_contrato,
                "accion_recomendada": accion_recomendada,
                "ejecucion": ejecucion,
                "limits": {
                    "max_eth": max_amount_eth,
                    "gas_limit": gas_limit
                },
                "tx_count": tx_count
            }
        elif confidence > 0.50:
            decision = "EXECUTE_BASIC"
            action_allowed = "TRANSFER_CALL"
            reasoning = "perfil estable; se permiten transferencias e interacciones estándar."
            tipo_contrato = None
            accion_recomendada = "monitorear"
            ejecucion = True
        else:
            decision = "MONITOR"
            action_allowed = "NONE"
            reasoning = "confianza insuficiente para ejecutar operaciones automáticas."
            tipo_contrato = None
            accion_recomendada = "monitorear"
            ejecucion = False

        return {
            "decision": decision,
            "action_allowed": action_allowed,
            "confidence": round(confidence, 2),
            "reasoning": reasoning,
            "tipo_contrato": tipo_contrato,
            "accion_recomendada": accion_recomendada,
            "ejecucion": ejecucion,
            "limits": {
                "max_eth": max_amount_eth,
                "gas_limit": gas_limit
            },
            "tx_count": tx_count
        }
