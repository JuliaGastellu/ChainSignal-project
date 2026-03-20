"""Deterministic analysis agent for ChainSignal.

Generates structured InsightContrato and optionally orchestrates with OpenClaw.
"""

import os
from loguru import logger
from typing import Any

from domain.modelos_contrato import InsightContrato


class AgenteAnalisis:
    """Deterministic agent that transforms features into an InsightContrato."""

    def __init__(self):
        self.modo_openclaw = os.getenv("OPENCLAW_ENABLED", "true").lower() in ("1", "true", "yes")
        self.openclaw_disponible = False
        try:
            from openclaw import OpenClaw
            self.openclaw_disponible = True
            self.OpenClaw = OpenClaw
            logger.info("OpenClaw available for tool orchestration.")
        except Exception:
            self.openclaw_disponible = False
            self.OpenClaw = None
            logger.info("OpenClaw not available; using local deterministic agent.")

    def analizar(self, metrics: Any, perfil: Any, wallet_addr: str = "unknown", scores: dict | None = None) -> InsightContrato:
        """Generates a structured InsightContrato without external HTTP calls."""
        if scores:
            risk = scores.get("risk", self._calcular_score_riesgo(metrics))
            activity = scores.get("activity", self._calcular_score_actividad(metrics))
        else:
            risk = self._calcular_score_riesgo(metrics)
            activity = self._calcular_score_actividad(metrics)
            
        tipo = self._decidir_tipo_contrato(risk, activity, perfil)
        accion = self._determinar_accion(risk, activity, perfil)

        insight = InsightContrato(
            type=tipo,
            analyzed_wallet=wallet_addr,
            risk_score=risk,
            activity_score=activity,
        )

        insight.recommended_action = accion

        if self.modo_openclaw and self.openclaw_disponible:
            self._orquestar_con_openclaw(insight, metrics, perfil)

        return insight

    def _calcular_score_riesgo(self, metrics: Any) -> int:
        """Risk heuristic based on on-chain metrics."""
        base = getattr(metrics, "total_transacciones", 0)
        errores = getattr(metrics, "transacciones_con_error", 0)
        frecuencia = getattr(metrics, "frecuencia_transacciones_por_dia", 0)

        score = 20
        score += min(40, int(errores * 2))
        score += min(20, int(frecuencia * 2))
        if getattr(metrics, "ratio_envios_vs_recepciones", 0) > 10:
            score += 15

        if base > 1000:
            score += 15
        elif base > 200:
            score += 7

        return max(0, min(100, score))

    def _calcular_score_actividad(self, metrics: Any) -> int:
        """Activity heuristic based on frequency, volume and transactions."""
        frecuencia = getattr(metrics, "frecuencia_transacciones_por_dia", 0)
        total = getattr(metrics, "total_transacciones", 0)
        score = 10
        score += min(40, int(frecuencia * 5))
        score += min(50, int(total / 10))
        return max(0, min(100, score))

    def _resolver_tipo_contrato(self, risk: int, actividad: int, perfil: Any, decision: str | None = None) -> str | None:
        """Deterministic rules for contract type assignment."""
        # Rule 1: If decision is insufficient data, do not propose contract.
        if decision == "INSUFFICIENT_DATA":
            return None

        # Rule 2: Very low activity does not justify deployment.
        if actividad < 20:
            return None

        # Rule 4: High risk requires risk mitigation contract.
        if risk > 70:
            return "risk_guard"

        # Rule 3: Treasury manager only at high activity.
        if actividad >= 80:
            return "treasury_manager"

        # Default: passive signal contract for moderate risk.
        if 40 <= risk <= 70:
            return "signal_lock"

        return None

    def _decidir_tipo_contrato(self, risk: int, actividad: int, perfil: Any) -> str | None:
        """Decides which contract type should be generated in the insight."""
        return self._resolver_tipo_contrato(risk, actividad, perfil)

    def _determinar_accion(self, risk: int, actividad: int, perfil: Any) -> str:
        """Main action suggestion for reporting in the insight."""
        tipo = self._resolver_tipo_contrato(risk, actividad, perfil)
        if tipo == "risk_guard":
            return "protect"
        if tipo == "treasury_manager":
            return "optimize"
        if tipo == "signal_lock":
            return "protect"
        return "monitor"

    def _orquestar_con_openclaw(self, insight: InsightContrato, metrics: Any, perfil: Any) -> None:
        """Optional orchestration log. Does not block deterministic flow."""
        try:
            client = self.OpenClaw()
            logger.info("OpenClaw no-op: tool available for orchestration, no external model executed.")
            # Here you could register tool wrappers if you want to extend the flow.
        except Exception as e:
            logger.warning("Could not start OpenClaw: {}", e)
