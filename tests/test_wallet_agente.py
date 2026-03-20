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
    insight = InsightContrato(type="risk_guard", analyzed_wallet="0x11", risk_score=95)
    estrategia = EstrategiaProteccionWallet()

    decision = estrategia.evaluar(insight)

    assert decision.requires_contract is True
    assert decision.requires_funds_movement is True
    assert decision.requires_execution is True
    assert len(decision.actions) == 4


def test_estrategia_riesgo_medio():
    """Verifica la estrategia para un riesgo detectable pero no crítico."""
    insight = InsightContrato(type="signal_lock", analyzed_wallet="0x11", risk_score=50)
    estrategia = EstrategiaProteccionWallet()

    decision = estrategia.evaluar(insight)

    assert decision.requires_contract is True
    assert decision.requires_funds_movement is False
    assert decision.requires_execution is False


def test_estrategia_actividad_alta():
    """Verifica la estrategia para actividad alta sin riesgo."""
    insight = InsightContrato(
        type="treasury_manager", analyzed_wallet="0x11", risk_score=10, activity_score=90
    )
    estrategia = EstrategiaProteccionWallet()

    decision = estrategia.evaluar(insight)

    assert decision.requires_contract is True
    assert decision.requires_funds_movement is False
    assert decision.requires_execution is False


def test_decision_engine_datos_insuficientes_tipo_nulo():
    """INSUFFICIENT_DATA debe retornar tipo null y acción monitorear."""
    from decision_engine.engine import DecisionEngine

    engine = DecisionEngine()
    resultado = engine.evaluate({"activity": 5, "risk": 10, "defi_engagement": 0}, metrics={"transaction_count": 3})

    assert resultado["decision"] == "INSUFFICIENT_DATA"
    assert resultado["contract_type"] is None
    assert resultado["recommended_action"] == "monitor"
    assert resultado["execution"] is False


def test_agente_analisis_tipo_none_por_actividad_baja():
    """Con actividad muy baja el insight no debe proponer contrato."""
    from agente_ia.agente import AgenteAnalisis
    from types import SimpleNamespace

    agente = AgenteAnalisis()
    metrics = SimpleNamespace(total_transacciones=1, transacciones_con_error=0, frecuencia_transacciones_por_dia=1, ratio_envios_vs_recepciones=0)
    perfil = SimpleNamespace(wallet="0xTEST")

    insight = agente.analizar(metrics, perfil)
    assert insight.type is None
    assert insight.recommended_action == "monitor"

def test_decision_engine_execute_advanced_ejecucion_true():
    from decision_engine.engine import DecisionEngine

    engine = DecisionEngine()
    resultado = engine.evaluate({"activity": 80, "risk": 30, "defi_engagement": 60}, metrics={"transaction_count": 20})
    assert resultado["decision"] in ["EXECUTE_ADVANCED", "EXECUTE_BASIC"]
    assert resultado["execution"] is True

