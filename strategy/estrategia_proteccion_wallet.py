"""Estrategia para determinar si una wallet analizada requiere protección."""

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
        """Evalúa el insight y determina la estrategia de protección.

        Args:
            insight: El contexto analizado de la wallet externa.

        Returns:
            DecisionEstrategia con las acciones requeridas.
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
            acciones.append("Desplegar contrato RiskGuard")
            acciones.append("Ejecutar actualizarPausa() para mitigar riesgo")
            detalle = "Riesgo alto detectado. Se requiere protección on-chain activa."
            
            # Galáctica: Swap preventivo a USD₮ si el riesgo es alto
            if insight.score_riesgo >= 80:
                requiere_swap = True
                token_in = "ETH" # Vende ETH
                token_out = "0xdAC17F958D2ee523a2206206994597C13D831ec7" # Compra USD₮
                acciones.append("Ejecutar SWAP preventivo a USD₮ para proteger capital")

            # Si además hay riesgo crítico, sugerir mover fondos preventivamente
            if insight.score_riesgo >= 90:
                requiere_fondos = True
                acciones.append(f"Transferir {self.cantidad_transferencia_wei} wei para test de rescate a wallet segura")
                detalle = "Riesgo crítico. Preparando rescate de fondos preventivo, swap a USD₮ y bloqueo on-chain."

        # Estrategia 2: Actividad muy alta -> Treasury Manager
        elif insight.score_actividad >= self.umbral_actividad_alta:
            requiere_contrato = True
            requiere_fondos = False
            requiere_ejecucion = False
            acciones.append("Desplegar contrato TreasuryManager")
            detalle = "Wallet altamente activa. Se requiere infraestructura de tesorería on-chain."
            
        # Estrategia 3: Risk Guard bajo pero sospechoso -> Signal Lock
        elif insight.score_riesgo >= 30:
            requiere_contrato = True
            requiere_fondos = False
            requiere_ejecucion = False
            acciones.append("Desplegar contrato SignalLock")
            detalle = "Riesgo medio detectado. Desplegando bloqueo temporal pasivo."

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
