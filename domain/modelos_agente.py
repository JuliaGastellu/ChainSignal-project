"""Módulos de datos para representar el estado económico y las decisiones del agente."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class DecisionAgente:
    """Documenta el razonamiento táctico detrás de una acción del agente."""

    contexto_analizado: str
    evaluated_strategy: str
    chosen_actions: List[str] = field(default_factory=list)
    reason: str = ""
    requires_swap: bool = False
    is_simulation: bool = False


@dataclass
class MetricasAgente:
    """Acumulador del impacto económico global del agente en la red."""

    protected_value_eth: float = 0.0
    transactions_performed: int = 0
    contracts_created: int = 0
