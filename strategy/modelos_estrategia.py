"""Módulo de estrategias de alto nivel para el Agente Económico."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class DecisionEstrategia:
    """Representa la decisión estructurada de alto nivel del agente."""

    requires_contract: bool
    requires_funds_movement: bool
    requires_execution: bool
    requires_swap: bool = False
    token_in: str = ""
    token_out: str = ""
    actions: List[str] = field(default_factory=list)
    detail: str = ""
