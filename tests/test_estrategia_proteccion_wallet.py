"""Pruebas de regresión de strategy/estrategia_proteccion_wallet.py.

Una wallet segura o de bajo riesgo debe poder producir una DecisionEstrategia
con todas las banderas requires_* en False. Antes la rama por defecto ponía
siempre requires_contract=True, así que toda wallet tenía una "estrategia
accionable" sin importar su riesgo real.
"""

from domain.modelos_contrato import InsightContrato
from strategy.estrategia_proteccion_wallet import EstrategiaProteccionWallet


def test_safe_wallet_requires_nothing():
    estrategia = EstrategiaProteccionWallet()
    insight = InsightContrato(type=None, analyzed_wallet="0xabc", risk_score=5, activity_score=10)

    decision = estrategia.evaluar(insight)

    assert decision.requires_contract is False
    assert decision.requires_funds_movement is False
    assert decision.requires_execution is False
    assert decision.requires_swap is False
    assert decision.actions == []


def test_high_risk_wallet_still_requires_contract():
    """Una detección real de riesgo alto todavía puede disparar una acción
    protectora: solo quité la rama por defecto que siempre era verdadera."""
    estrategia = EstrategiaProteccionWallet()
    insight = InsightContrato(type="risk_guard", analyzed_wallet="0xabc", risk_score=75, activity_score=10)

    decision = estrategia.evaluar(insight)

    assert decision.requires_contract is True
    assert decision.requires_execution is True


def test_critical_risk_wallet_requires_funds_movement():
    estrategia = EstrategiaProteccionWallet()
    insight = InsightContrato(type="risk_guard", analyzed_wallet="0xabc", risk_score=95, activity_score=10)

    decision = estrategia.evaluar(insight)

    assert decision.requires_funds_movement is True
    assert decision.requires_swap is True


def test_medium_risk_wallet_requires_contract_only():
    estrategia = EstrategiaProteccionWallet()
    insight = InsightContrato(type="signal_lock", analyzed_wallet="0xabc", risk_score=40, activity_score=10)

    decision = estrategia.evaluar(insight)

    assert decision.requires_contract is True
    assert decision.requires_funds_movement is False
    assert decision.requires_swap is False
