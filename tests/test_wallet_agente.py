"""Pruebas unitarias para los modelos de wallet y la estrategia."""

from domain.modelos_wallet import WalletAgente
from domain.modelos_contrato import InsightContrato
from strategy.estrategia_proteccion_wallet import EstrategiaProteccionWallet


def test_wallet_agente_modelo():
    """Verifica la lógica básica del modelo WalletAgente."""
    wallet = WalletAgente(direccion="0x123", balance_eth=1.5, red="sepolia")

    assert wallet.direccion == "0x123"
    assert wallet.balance_eth == 1.5
    assert wallet.tiene_balance_suficiente(1.0) is True
    assert wallet.tiene_balance_suficiente(2.0) is False


def test_estrategia_riesgo_critico():
    """Verifica la estrategia para un caso de riesgo crítico."""
    insight = InsightContrato(tipo="risk_guard", wallet_analizada="0x11", score_riesgo=95)
    estrategia = EstrategiaProteccionWallet()

    decision = estrategia.evaluar(insight)

    assert decision.requiere_contrato is True
    assert decision.requiere_movimiento_fondos is True
    assert decision.requiere_ejecucion is True
    assert len(decision.acciones) == 4


def test_estrategia_riesgo_medio():
    """Verifica la estrategia para un riesgo detectable pero no crítico."""
    insight = InsightContrato(tipo="signal_lock", wallet_analizada="0x11", score_riesgo=50)
    estrategia = EstrategiaProteccionWallet()

    decision = estrategia.evaluar(insight)

    assert decision.requiere_contrato is True
    assert decision.requiere_movimiento_fondos is False
    assert decision.requiere_ejecucion is False


def test_estrategia_actividad_alta():
    """Verifica la estrategia para actividad alta sin riesgo."""
    insight = InsightContrato(
        tipo="treasury_manager", wallet_analizada="0x11", score_riesgo=10, score_actividad=90
    )
    estrategia = EstrategiaProteccionWallet()

    decision = estrategia.evaluar(insight)

    assert decision.requiere_contrato is True
    assert decision.requiere_movimiento_fondos is False
    assert decision.requiere_ejecucion is False
