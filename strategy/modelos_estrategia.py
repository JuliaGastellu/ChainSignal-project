"""Módulo de estrategias de alto nivel para el Agente Económico."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class DecisionEstrategia:
    """Representa la decisión de alto nivel estructurada del agente."""

    requiere_contrato: bool
    requiere_movimiento_fondos: bool
    requiere_ejecucion: bool
    requiere_swap: bool = False
    token_in: str = ""
    token_out: str = ""
    acciones: List[str] = field(default_factory=list)
    detalle: str = ""
