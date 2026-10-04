"""Modelos de dominio para contratos inteligentes generados por el agente."""

from dataclasses import dataclass, field
from typing import Optional



@dataclass
class InsightContrato:
    """Contexto de análisis que dispara la generación de un contrato."""

    type: Optional[str]
    analyzed_wallet: str
    risk_score: int
    activity_score: int = 0
    recommended_action: str = "monitor"

    def __post_init__(self):
        valid_types = {None, "risk_guard", "signal_lock", "treasury_manager"}
        if self.type not in valid_types:
            raise ValueError(
                f"Unsupported contract type: '{self.type}'. "
                f"Valid: {valid_types - {None}} or null"
            )


@dataclass
class ContratoCompilado:
    """Result of a Solidity contract compilation."""

    name: str
    abi: list[dict]
    bytecode: str
    source_code: str = ""


@dataclass
class ContratoDeplegado:
    """Record of a deployed contract on the blockchain."""

    name: str
    address: str
    transaction_hash: str
    abi: list[dict] = field(default_factory=list)
    network: str = "sepolia"
