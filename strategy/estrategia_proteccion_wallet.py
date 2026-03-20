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
        acciones = []
        requiere_contrato = False
        requiere_fondos = False
        requiere_ejecucion = False
        requiere_swap = False
        token_in = ""
        token_out = ""
        detalle = "Sin acciones requeridas."

        # Estrategia 1: Riesgo Alto -> Risk Guard Contract + SWAP USD₮
        if insight.score_riesgo >= self.umbral_riesgo:
            requiere_contrato = True
            requiere_ejecucion = True
            acciones.append("Deploy RiskGuard contract")
            acciones.append("Execute actualizarPausa() to mitigate risk")
            detalle = "High risk detected. Active on-chain protection required."
            
            # Preventive swap to USD₮ for high risk
            if insight.score_riesgo >= 80:
                requiere_swap = True
                token_in = "ETH"
                token_out = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
                acciones.append("Execute preventive swap to USD₮ to protect capital")

            # Critical risk: suggest moving funds to safe wallet
            if insight.score_riesgo >= 90:
                requiere_fondos = True
                acciones.append(f"Transfer {self.cantidad_transferencia_wei} wei for rescue test to secure wallet")
                detalle = "Critical risk. Preparing preventive rescue, USD₮ swap, and on-chain lock."

        # Strategy 2: High activity -> Treasury Manager
        elif insight.score_actividad >= self.umbral_actividad_alta:
            requiere_contrato = True
            requiere_fondos = False
            requiere_ejecucion = False
            acciones.append("Deploy TreasuryManager contract")
            detalle = "Highly active wallet. On-chain treasury infrastructure required."
            
        # Strategy 3: Lower risk but suspicious -> Signal Lock
        elif insight.score_riesgo >= 30:
            requiere_contrato = True
            requiere_fondos = False
            requiere_ejecucion = False
            acciones.append("Deploy SignalLock contract")
            detalle = "Medium risk detected. Deploying temporary passive lock."

        return DecisionEstrategia(
            requiere_contrato=requiere_contrato,
            requiere_movimiento_fondos=requiere_fondos,
            requiere_ejecucion=requiere_ejecucion,
            requiere_swap=requiere_swap,
            token_in=token_in,
            token_out=token_out,
            acciones=acciones,
            detalle=detalle,
        )
