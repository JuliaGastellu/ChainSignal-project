"""Modelos de dominio para contratos inteligentes generados por el agente."""

from dataclasses import dataclass, field



@dataclass
class InsightContrato:
    """Contexto de análisis que dispara la generación de un contrato."""

    tipo: str
    wallet_analizada: str
    score_riesgo: int
    score_actividad: int = 0
    accion_recomendada: str = "monitorear"

    def __post_init__(self):
        tipos_validos = {"risk_guard", "signal_lock", "treasury_manager"}
        if self.tipo not in tipos_validos:
            raise ValueError(
                f"Tipo de contrato no soportado: '{self.tipo}'. "
                f"Válidos: {tipos_validos}"
            )


@dataclass
class ContratoCompilado:
    """Resultado de la compilación de un contrato Solidity."""

    nombre: str
    abi: list[dict]
    bytecode: str
    codigo_fuente: str = ""


@dataclass
class ContratoDeplegado:
    """Registro de un contrato desplegado en blockchain."""

    nombre: str
    direccion: str
    transaction_hash: str
    abi: list[dict] = field(default_factory=list)
    red: str = "sepolia"
