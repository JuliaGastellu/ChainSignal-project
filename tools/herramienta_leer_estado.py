"""Herramienta del agente para leer el estado on-chain de contratos desplegados."""

from loguru import logger

from services.servicio_wdk import ServicioWDK
from domain.modelos_contrato import ContratoDeplegado
from domain.modelos_transaccion import EstadoContrato


def leer_estado(
    contrato: ContratoDeplegado,
    campo: str,
    args: list | None = None,
) -> EstadoContrato:
    """Lee el valor de una variable o función view de un contrato desplegado.

    Si el WDK no está disponible, retorna un EstadoContrato con exitoso=False.

    Args:
        contrato: Contrato desplegado con dirección y ABI.
        campo: Nombre de la variable pública o función view a consultar.
        args: Argumentos opcionales para funciones view parametrizadas.

    Returns:
        EstadoContrato con el valor leído y el estado de la operación.
    """
    servicio = ServicioWDK()

    if not servicio.activo:
        logger.warning(
            "Microservicio WDK no disponible. Lectura de '{}' cancelada.", campo
        )
        return EstadoContrato(
            contract_address=contrato.address,
            field=campo,
            value=None,
            success=False,
            detail="Microservicio WDK no disponible.",
        )

    return servicio.leer_estado(contrato, campo, args=args)
