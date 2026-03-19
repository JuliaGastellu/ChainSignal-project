"""Útiles generales para gestionar transacciones y representaciones de valores."""

def ether_a_wei(ether_valor: float) -> int:
    """Convierte un valor de Ether a Wei (1 ETH = 10^18 Wei)."""
    return int(ether_valor * 10**18)

def wei_a_ether(wei_valor: int) -> float:
    """Convierte un valor de Wei a Ether."""
    return float(wei_valor) / 10**18
