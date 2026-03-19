"""Herramienta para consultar el balance de una wallet."""

from loguru import logger

from services.servicio_wdk import ServicioWDK


def consultar_balance(direccion: str | None = None) -> float:
    """Consulta el balance en ETH de una wallet.

    Si no se proporciona una dirección, consulta el balance de la wallet
    gestionada por el agente.

    Args:
        direccion: Dirección Ethereum a consultar. Opcional.

    Returns:
        Balance en ETH. Si el WDK no está disponible o hay un error, retorna 0.0.
    """
    logger.info("Herramienta activa: Consultando balance de {}", direccion or "agente")

    servicio = ServicioWDK()
    balance = servicio.consultar_balance(direccion)
    
    if balance is None:
        logger.warning(
            "WDK no retornó balance para {}, asumiendo 0.0 ETH",
            direccion or "agente",
        )
        return 0.0

    return balance
