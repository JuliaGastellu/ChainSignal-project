"""Herramienta del agente para ejecutar funciones de escritura en contratos."""

from loguru import logger

from services.servicio_wdk import ServicioWDK
from domain.modelos_contrato import ContratoDeplegado
from domain.modelos_transaccion import ResultadoTransaccion


def ejecutar_funcion(
    contrato: ContratoDeplegado,
    funcion: str,
    args: list | None = None,
    valor_wei: int = 0,
) -> ResultadoTransaccion:
    """Ejecuta una función de escritura en un contrato desplegado.

    Si el WDK no está disponible, retorna un ResultadoTransaccion con exitoso=False.

    Args:
        contrato: Contrato desplegado con dirección y ABI.
        funcion: Nombre del método a invocar.
        args: Argumentos de la función.
        valor_wei: ETH a enviar adjunto a la transacción (en wei).

    Returns:
        ResultadoTransaccion con hash y estado de la operación.
    """
    servicio = ServicioWDK()

    if not servicio.activo:
        logger.warning(
            "Microservicio WDK no disponible. Ejecución de {}() cancelada.",
            funcion,
        )
        return ResultadoTransaccion(
            transaction_hash="",
            contract_address=contrato.address,
            function=funcion,
            success=False,
            detail="Microservicio WDK no disponible.",
        )

    return servicio.ejecutar_funcion(contrato, funcion, args=args, valor_wei=valor_wei)
