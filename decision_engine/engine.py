"""Deterministic decision engine for the AI agent."""
from loguru import logger

class DecisionEngine:
    """Makes deterministic decisions using behavior and risk scores."""

    def evaluate(self, scores: dict, metrics: dict = None):
        """
        Evaluates whether a financial action (transfer or contract) should be executed.
        Confidence is proportional to data volume and profile quality.
        """
        if not scores:
            return {
                "decision": "INSUFFICIENT_DATA",
                "confidence": 0,
                "reasoning": "system lacks information to perform an analysis."
            }
            
        activity = scores.get("activity", 0)
        risk = scores.get("risk", 15)
        defi = scores.get("defi_engagement", 0)
        tx_count = metrics.get("transaction_count", 0) if metrics else 0
        
        logger.info(f"Evaluating decision: Activity={activity}, Risk={risk}, DeFi={defi}, Txs={tx_count}")
        
        # 1. Proportional Confidence Calculation
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
            decision = "INSUFFICIENT_DATA"
            action_allowed = "NONE"
            reasoning = f"activity ({tx_count} txs) insufficient to build a profile."
            contract_type = None
            recommended_action = "monitor"
            execution = False
        elif risk > 60:
            decision = "BLOCK"
            action_allowed = "NONE"
            reasoning = "high-risk behavior detected in wallet activity."
            contract_type = None
            recommended_action = "protect"
            execution = False
        elif confidence > 0.80 and activity > 70 and defi > 50:
            decision = "EXECUTE_ADVANCED"
            action_allowed = "ALL"
            reasoning = "high-confidence advanced profile; advanced operations allowed."
            execution = True

            # Deterministic contract type selection
            if risk > 70:
                contract_type = "risk_guard"
                recommended_action = "protect"
            elif activity > 80:
                contract_type = "treasury_manager"
                recommended_action = "optimize"
            else:
                contract_type = "signal_lock"
                recommended_action = "protect"

            return {
                "decision": decision,
                "action_allowed": action_allowed,
                "confidence": round(confidence, 2),
                "reasoning": reasoning,
                "contract_type": contract_type,
                "recommended_action": recommended_action,
                "execution": execution,
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
            contract_type = None
            recommended_action = "monitor"
            execution = True
        else:
            decision = "MONITOR"
            action_allowed = "NONE"
            reasoning = "insufficient confidence for auto-execution."
            contract_type = None
            recommended_action = "monitor"
            execution = False

        return {
            "decision": decision,
            "action_allowed": action_allowed,
            "confidence": round(confidence, 2),
            "reasoning": reasoning,
            "contract_type": contract_type,
            "recommended_action": recommended_action,
            "execution": execution,
            "limits": {
                "max_eth": max_amount_eth,
                "gas_limit": gas_limit
            },
            "tx_count": tx_count
        }
