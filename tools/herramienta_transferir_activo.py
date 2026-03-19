"""Herramienta para transferir ETH desde la wallet del agente."""

from loguru import logger

from services.servicio_wdk import ServicioWDK
from domain.modelos_transaccion import ResultadoTransaccion


def transferir_activo(direccion_destino: str, cantidad_wei: int) -> ResultadoTransaccion:
    """Transfiere ETH (en wei) desde la wallet del agente hacia un destino.

    Args:
        direccion_destino: Dirección Ethereum que recibirá los fondos.
        cantidad_wei: Cantidad exacta de wei a enviar.

    Returns:
        ResultadoTransaccion indicando el éxito y el hash de la transacción.
    """
    logger.info(
        "Herramienta activa: Transfiriendo {} wei a {}",
        cantidad_wei,
        direccion_destino,
    )

    servicio = ServicioWDK()

    if not servicio.activo:
        logger.warning(
            "WDK inactivo. Simulando fallo de transferencia a {}", direccion_destino
        )
        return ResultadoTransaccion(
            transaction_hash="",
            contrato_direccion="",
            funcion="transferencia_nativa",
            exitoso=False,
            detalle="Microservicio WDK no está disponible para transferir.",
        )

    resultado = servicio.transferir_activo(direccion_destino, cantidad_wei)
    return resultado
