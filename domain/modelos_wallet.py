"""Módulos de datos para representar la wallet del agente."""

from dataclasses import dataclass


@dataclass
class WalletAgente:
    """Representa la identidad on-chain y balance del agente económico."""

    direccion: str
    balance_eth: float
    red: str = "sepolia"

    def tiene_balance_suficiente(self, costo_estimado_eth: float) -> bool:
        """Verifica si la wallet tiene fondos suficientes para una operación."""
        return self.balance_eth >= costo_estimado_eth
