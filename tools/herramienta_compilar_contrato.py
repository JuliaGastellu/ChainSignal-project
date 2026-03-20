"""Herramienta del agente para compilar código Solidity."""

import re
from loguru import logger

from contract_generator.compiler import compilar_contrato
from domain.modelos_contrato import ContratoCompilado


def _extraer_nombre_contrato(codigo_solidity: str) -> str:
    """Extrae el nombre del primer contrato declarado en el código fuente.

    Args:
        codigo_solidity: Código fuente Solidity completo.

    Returns:
        Nombre del contrato encontrado, o 'Contrato' como fallback.
    """
    patron = re.compile(r"^\s*contract\s+(\w+)", re.MULTILINE)
    coincidencia = patron.search(codigo_solidity)
    return coincidencia.group(1) if coincidencia else "Contrato"


def compilar_contrato_tool(
    codigo_solidity: str,
    nombre_contrato: str | None = None,
) -> ContratoCompilado:
    """Compila código Solidity y retorna ABI y bytecode en un modelo de dominio.

    Si no se indica el nombre del contrato, se extrae automáticamente del código.

    Args:
        codigo_solidity: Código fuente Solidity a compilar.
        nombre_contrato: Nombre del contrato (opcional; se detecta si se omite).

    Returns:
        ContratoCompilado con ABI, bytecode y código fuente.

    Raises:
        Exception: Si la compilación falla.
    """
    if not nombre_contrato:
        nombre_contrato = _extraer_nombre_contrato(codigo_solidity)

    logger.info("Compilando contrato '{}'...", nombre_contrato)

    resultado = compilar_contrato(codigo_solidity, nombre_contrato)

    compilado = ContratoCompilado(
        name=resultado["nombre"],
        abi=resultado["abi"],
        bytecode=resultado["bytecode"],
        source_code=codigo_solidity,
    )

    logger.info(
        "Compilación exitosa: '{}', ABI={} entradas, bytecode={} bytes",
        compilado.name,
        len(compilado.abi),
        len(compilado.bytecode),
    )
    return compilado
