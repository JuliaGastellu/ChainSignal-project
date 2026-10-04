"""El historial cuenta; no decide (E07)."""

import inspect

from services.historial_evaluaciones import HistorialEvaluaciones
from services.strategy_engine import NO_ACTION, StrategyEngine


def test_resumen_no_trata_aceptacion_como_exito_por_estrategia(tmp_path):
    historial = HistorialEvaluaciones(str(tmp_path / "historial.json"))
    for _ in range(50):
        historial.registrar_resultado("0xabc", "success", "COPY_TRADE", 0.01, "0xhash")
    historial.registrar_resultado("0xabc", "failed", "RISK_SHIELD", 0.0)
    resumen = historial.resumen()
    assert resumen["accepted_transactions"] == 50
    assert resumen["outcome_status"] == {"success": 50, "failed": 1}
    assert "strategy_success" not in resumen and "success_count" not in resumen


def test_la_seleccion_no_depende_del_historial():
    # Ya no existe el parámetro que traía el resumen del historial.
    assert "learning_summary" not in inspect.signature(StrategyEngine.select).parameters
    motor = StrategyEngine()
    senales = [{"type": "HIGH_VALUE_TRANSFER", "severity": "low", "confidence": 0.9}]
    eleccion = motor.select(senales, {}, {"risk": 10, "confidence": 0.9})
    # Antes, con muchas transacciones aceptadas de COPY_TRADE, esta señal forzaba COPY_TRADE.
    assert eleccion["strategy"] == NO_ACTION and eleccion["force_execute"] is False
