"""Herramienta del agente para generar código Solidity a partir de un insight."""

from loguru import logger

from contract_generator.contract_generator import GeneradorContratos
from domain.modelos_contrato import InsightContrato


def generar_contrato(insight: InsightContrato) -> str:
    """Genera el código fuente Solidity adecuado para el insight recibido.

    Delega la generación al módulo contract_generator existente.

    Args:
        insight: Contexto de análisis que determina el tipo de contrato.

    Returns:
        Código fuente Solidity como cadena de texto.

    Raises:
        ValueError: Si el tipo de contrato no está soportado.
    """
    logger.info(
        "Generating contract type '{}' for wallet {}",
        insight.type,
        insight.analyzed_wallet,
    )

    generador = GeneradorContratos()
    codigo = generador.generar({
        "type": insight.type,
        "analyzed_wallet": insight.analyzed_wallet,
        "risk_score": insight.risk_score,
        "activity_score": insight.activity_score,
    })

    logger.info(
        "Solidity code generated: {} characters, type '{}'",
        len(codigo),
        insight.type,
    )
    return codigo
