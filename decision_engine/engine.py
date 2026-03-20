"""Deterministic decision engine for the AI agent."""
from loguru import logger

class DecisionEngine:
    """Makes deterministic decisions using behavior and risk scores."""

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
            reasoning = f"activity ({tx_count} txs) insufficient to build a profile."
            tipo_contrato = None
            accion_recomendada = "monitor"
            ejecucion = False
        elif risk > 60:
            decision = "BLOCK"
            action_allowed = "NONE"
            reasoning = "high-risk behavior detected in wallet activity."
            tipo_contrato = None
            accion_recomendada = "protect"
            ejecucion = False
        elif confidence > 0.80 and activity > 70 and defi > 50:
            decision = "EXECUTE_ADVANCED"
            action_allowed = "ALL"
            reasoning = "high-confidence advanced profile; advanced operations allowed."
            ejecucion = True

            # Deterministic contract type selection
            if risk > 70:
                tipo_contrato = "risk_guard"
                accion_recomendada = "protect"
            elif activity > 80:
                tipo_contrato = "treasury_manager"
                accion_recomendada = "optimize"
            else:
                tipo_contrato = "signal_lock"
                accion_recomendada = "protect"

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
            reasoning = "stable profile; standard transfers and interactions allowed."
            tipo_contrato = None
            accion_recomendada = "monitor"
            ejecucion = True
        else:
            decision = "MONITOR"
            action_allowed = "NONE"
            reasoning = "insufficient confidence for auto-execution."
            tipo_contrato = None
            accion_recomendada = "monitor"
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
