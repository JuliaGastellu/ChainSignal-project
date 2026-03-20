"""Strategy to determine if an analyzed wallet requires protection."""

from strategy.modelos_estrategia import DecisionEstrategia
from domain.modelos_contrato import InsightContrato


class EstrategiaProteccionWallet:
    """Implementa la lógica para decidir la protección de una wallet."""

    def __init__(self, umbral_riesgo: int = 60, umbral_actividad_alta: int = 80, cantidad_transferencia_wei: int = 1000000000000000):
        # 1000000000000000 wei = 0.001 ETH
        self.umbral_riesgo = umbral_riesgo
        self.umbral_actividad_alta = umbral_actividad_alta
        self.cantidad_transferencia_wei = cantidad_transferencia_wei

    def evaluar(self, insight: InsightContrato) -> DecisionEstrategia:
        """Evaluates the insight and determines protection strategy.

        Args:
            insight: The analyzed context of the external wallet.

        Returns:
            DecisionEstrategia with required actions.
        """
        actions = []
        requires_contract = False
        requires_funds = False
        requires_execution = False
        requires_swap = False
        token_in = ""
        token_out = ""
        detail = "No actions required."

        # Strategy 1: High Risk -> Risk Guard Contract + USDT SWAP
        if insight.risk_score >= self.umbral_riesgo:
            requires_contract = True
            requires_execution = True
            actions.append("Deploy RiskGuard contract")
            actions.append("Execute actualizarPausa() to mitigate risk")
            detail = "High risk detected. Active on-chain protection required."
            
            # Preventive swap to USDC for high risk
            if insight.risk_score >= 80:
                requires_swap = True
                token_in = "ETH"
                token_out = settings.USDC_ADDRESS_SEPOLIA
                actions.append("Execute preventive swap to USDC to protect capital")

            # Critical risk: suggest moving funds to safe wallet
            if insight.risk_score >= 90:
                requires_funds = True
                actions.append(f"Transfer {self.cantidad_transferencia_wei} wei for rescue test to secure wallet")
                detail = "Critical risk. Preparing preventive rescue, USDT swap, and on-chain lock."

        # Strategy 2: High activity -> Treasury Manager
        elif insight.activity_score >= self.umbral_actividad_alta:
            requires_contract = True
            requires_funds = False
            requires_execution = False
            actions.append("Deploy TreasuryManager contract")
            detail = "Highly active wallet. On-chain treasury infrastructure required."
            
        # Strategy 3: Lower risk but suspicious -> Signal Lock
        elif insight.risk_score >= 30:
            requires_contract = True
            requires_funds = False
            requires_execution = False
            actions.append("Deploy SignalLock contract")
            detail = "Medium risk detected. Deploying temporary passive lock."

        return DecisionEstrategia(
            requires_contract=requires_contract,
            requires_funds_movement=requires_funds,
            requires_execution=requires_execution,
            requires_swap=requires_swap,
            token_in=token_in,
            token_out=token_out,
            actions=actions,
            detail=detail,
        )
