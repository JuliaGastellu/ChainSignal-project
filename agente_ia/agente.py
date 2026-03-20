"""Agente de análisis determinista para ChainSignal.

Genera insights estructurados de tipo InsightContrato y gestiona la orquestación
con OpenClaw cuando está disponible.
"""

import os
from loguru import logger
from typing import Any

from domain.modelos_contrato import InsightContrato


class AgenteAnalisis:
    """Agente determinista que transforma features en un InsightContrato."""

    def __init__(self):
        self.modo_openclaw = os.getenv("OPENCLAW_ENABLED", "true").lower() in ("1", "true", "yes")
        self.openclaw_disponible = False
        try:
            from openclaw import OpenClaw
            self.openclaw_disponible = True
            self.OpenClaw = OpenClaw
            logger.info("OpenClaw disponible para orquestación de herramientas.")
        except Exception:
            self.openclaw_disponible = False
            self.OpenClaw = None
            logger.info("OpenClaw no disponible; usando agente determinista local.")

    def analizar(self, metrics: Any, perfil: Any) -> InsightContrato:
        """Genera un InsightContrato estructurado sin llamadas HTTP externas."""
        risk = self._calcular_score_riesgo(metrics)
        activity = self._calcular_score_actividad(metrics)
        tipo = self._decidir_tipo_contrato(risk, activity, perfil)
        accion = self._determinar_accion(risk, activity, perfil)

        insight = InsightContrato(
            tipo=tipo,
            wallet_analizada=getattr(perfil, "wallet", getattr(perfil, "dirección", "desconocida")) if perfil is not None else "desconocida",
            score_riesgo=risk,
            score_actividad=activity,
        )

        insight.accion_recomendada = accion

        if self.modo_openclaw and self.openclaw_disponible:
            self._orquestar_con_openclaw(insight, metrics, perfil)

        return insight

    def _calcular_score_riesgo(self, metrics: Any) -> int:
        """Heurística de riesgo basada en métricas on-chain."""
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
        """Heurística de actividad basada en frecuencia, volumen y transacciones."""
        frecuencia = getattr(metrics, "frecuencia_transacciones_por_dia", 0)
        total = getattr(metrics, "total_transacciones", 0)
        score = 10
        score += min(40, int(frecuencia * 5))
        score += min(50, int(total / 10))
        return max(0, min(100, score))

    def _resolver_tipo_contrato(self, risk: int, actividad: int, perfil: Any, decision: str | None = None) -> str | None:
        """Reglas deterministas de asignación de tipo de contrato."""
        # Regla 1: Si no hay decisión confiable, no hay contrato.
        if decision == "DATOS_INSUFICIENTES":
            return None

        # Regla 2: Actividad muy baja no justifica despliegue.
        if actividad < 20:
            return None

        # Regla 4: Riesgo alto exige mitigación de protección.
        if risk > 70:
            return "risk_guard"

        # Regla 3: Treasury Manager solo con actividad alta.
        if actividad >= 80:
            return "treasury_manager"

        # Regla general: señal pasiva para riesgo moderado.
        if 40 <= risk <= 70:
            return "signal_lock"

        return None

    def _decidir_tipo_contrato(self, risk: int, actividad: int, perfil: Any) -> str | None:
        """Decide qué tipo de contrato se debe generar en el insight."""
        return self._resolver_tipo_contrato(risk, actividad, perfil)

    def _determinar_accion(self, risk: int, actividad: int, perfil: Any) -> str:
        """Sugerencia de acción principal para reportar en el insight."""
        tipo = self._resolver_tipo_contrato(risk, actividad, perfil)
        if tipo == "risk_guard":
            return "proteger"
        if tipo == "treasury_manager":
            return "optimizar"
        if tipo == "signal_lock":
            return "proteger"
        return "monitorear"

    def _orquestar_con_openclaw(self, insight: InsightContrato, metrics: Any, perfil: Any) -> None:
        """Log opcional de orquestación. No bloquea el flujo determinista."""
        try:
            client = self.OpenClaw()
            logger.info("OpenClaw no-op: herramienta disponible para orquestación, no se ejecuta modelo externo.")
            # Aquí se podría registrar tool wrappers si se desea extender el flujo.
        except Exception as e:
            logger.warning("No se pudo iniciar OpenClaw: {}", e)
