"""Pruebas de regresión de services/strategy_engine.py.

El motor debe poder devolver NO_ACTION y el fallback EXPLORE_TRIGGER nunca
autoriza mover capital: force_execute es False cuando no se disparó ninguna
señal real.
"""

from services.strategy_engine import StrategyEngine, NO_ACTION


def _wallet_intel(risk=10, confidence=0.6):
    return {"risk": risk, "confidence": confidence}


def test_no_signals_returns_no_action_and_never_forces_execution():
    engine = StrategyEngine()
    pick = engine.select(signals=[], decision={}, wallet_intel=_wallet_intel())

    assert pick["strategy"] == NO_ACTION
    assert pick["force_execute"] is False


def test_explore_trigger_only_returns_no_action_and_never_forces_execution():
    engine = StrategyEngine()
    signals = [{"type": "EXPLORE_TRIGGER", "severity": "low", "confidence": 0.55}]
    pick = engine.select(signals=signals, decision={}, wallet_intel=_wallet_intel())

    assert pick["strategy"] == NO_ACTION
    assert pick["force_execute"] is False


def test_explore_trigger_never_forces_execution_even_with_demo_mode_true():
    """AGENT_DEMO_MODE (passed as demo_mode=True) must not change the outcome."""
    engine = StrategyEngine()
    signals = [{"type": "EXPLORE_TRIGGER", "severity": "low", "confidence": 0.55}]
    pick = engine.select(signals=signals, decision={}, wallet_intel=_wallet_intel(), demo_mode=True)

    assert pick["strategy"] == NO_ACTION
    assert pick["force_execute"] is False


def test_real_signal_without_matching_strategy_returns_no_action():
    engine = StrategyEngine()
    signals = [{"type": "HIGH_VALUE_TRANSFER", "severity": "low", "confidence": 0.62}]
    pick = engine.select(signals=signals, decision={}, wallet_intel=_wallet_intel())

    assert pick["strategy"] == NO_ACTION
    assert pick["force_execute"] is False


def test_suspicious_pattern_still_selects_risk_shield():
    """Señales reales de severidad alta todavía pueden elegir una estrategia
    accionable: solo quité el fallback que siempre era verdadero."""
    engine = StrategyEngine()
    signals = [{"type": "SUSPICIOUS_PATTERN", "severity": "high", "confidence": 0.74}]
    pick = engine.select(signals=signals, decision={}, wallet_intel=_wallet_intel(risk=80))

    assert pick["strategy"] == "RISK_SHIELD"
    assert pick["force_execute"] is True


def test_whale_accumulation_with_confidence_selects_copy_trade():
    engine = StrategyEngine()
    signals = [{"type": "WHALE_ACCUMULATION", "severity": "high", "confidence": 0.78}]
    pick = engine.select(signals=signals, decision={}, wallet_intel=_wallet_intel(confidence=0.6))

    assert pick["strategy"] == "COPY_TRADE"
    assert pick["force_execute"] is True
