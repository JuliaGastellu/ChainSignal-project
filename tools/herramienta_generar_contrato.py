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
        "Generando contrato tipo '{}' para wallet {}",
        insight.tipo,
        insight.wallet_analizada,
    )

    generador = GeneradorContratos()
    codigo = generador.generar({
        "tipo": insight.tipo,
        "wallet_analizada": insight.wallet_analizada,
        "score_riesgo": insight.score_riesgo,
        "score_actividad": insight.score_actividad,
    })

    logger.info(
        "Código Solidity generado: {} caracteres, tipo '{}'",
        len(codigo),
        insight.tipo,
    )
    return codigo
