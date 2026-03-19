"""Módulos de datos para representar el estado económico y las decisiones del agente."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class DecisionAgente:
    """Documenta el razonamiento táctico detrás de una acción del agente."""

    contexto_analizado: str
    estrategia_evaluada: str
    acciones_elegidas: List[str] = field(default_factory=list)
    motivo: str = ""
    requiere_swap: bool = False
    es_simulacion: bool = False


@dataclass
class MetricasAgente:
    """Acumulador del impacto económico global del agente en la red."""

    valor_protegido_eth: float = 0.0
    transacciones_realizadas: int = 0
    contratos_creados: int = 0
