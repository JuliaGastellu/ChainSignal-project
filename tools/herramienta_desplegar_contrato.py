"""Herramienta del agente para desplegar contratos compilados en blockchain."""

from loguru import logger

from services.servicio_wdk import ServicioWDK
from domain.modelos_contrato import ContratoCompilado, ContratoDeplegado


def desplegar_contrato(
    contrato: ContratoCompilado,
    args_constructor: list | None = None,
) -> ContratoDeplegado | None:
    """Despliega un contrato compilado en la red configurada mediante el WDK.

    Si el microservicio WDK no está disponible, retorna None y registra la causa.

    Args:
        contrato: Contrato con ABI y bytecode listos para despliegue.
        args_constructor: Argumentos para el constructor del contrato.

    Returns:
        ContratoDeplegado con dirección y hash de transacción, o None.
    """
    servicio = ServicioWDK()

    if not servicio.activo:
        logger.warning(
            "Microservicio WDK no disponible. Despliegue de '{}' cancelado.",
            contrato.name,
        )
        return None

    return servicio.desplegar_contrato(contrato, args_constructor=args_constructor)
