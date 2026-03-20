"""Pruebas unitarias del AgenteChainSignal."""

from unittest.mock import patch

from agents.agente_chainsignal import AgenteChainSignal
from domain.modelos_contrato import ContratoCompilado, ContratoDeplegado


# Insight mínimo que supera el umbral de riesgo por defecto (60).
INSIGHT_RIESGO_ALTO = {
    "type": "risk_guard",
    "analyzed_wallet": "0x1234567890123456789012345678901234567890",
    "risk_score": 85,
    "activity_score": 30,
}

INSIGHT_RIESGO_BAJO = {
    "type": "risk_guard",
    "analyzed_wallet": "0x1234567890123456789012345678901234567890",
    "risk_score": 20,
    "activity_score": 10,
}


def test_agente_no_actua_con_riesgo_bajo():
    """El agente no debe iniciar el ciclo on-chain si el score es bajo."""
    agente = AgenteChainSignal()
    resultado = agente.ejecutar(INSIGHT_RIESGO_BAJO)

    assert resultado["requires_action"] is False
    assert "no_action_reason" in resultado


def test_agente_no_actua_si_tipo_none():
    """El agente no debe ejecutar ciclo on-chain cuando insight.type es None."""
    agente = AgenteChainSignal()
    resultado = agente.ejecutar({
        "type": None,
        "analyzed_wallet": "0x123",
        "risk_score": 10,
        "activity_score": 10,
    })

    assert resultado["requires_action"] is False
    assert "no_action_reason" in resultado


@patch("agents.agente_chainsignal.generar_contrato")
@patch("agents.agente_chainsignal.compilar_contrato_tool")
@patch("agents.agente_chainsignal.desplegar_contrato")
@patch("agents.agente_chainsignal.ejecutar_funcion")
@patch("agents.agente_chainsignal.leer_estado")
def test_agente_ciclo_completo_con_wdk(
    mock_leer,
    mock_ejecutar,
    mock_desplegar,
    mock_compilar,
    mock_generar,
):
    """El agente ejecuta el ciclo completo cuando el WDK está disponible."""
    mock_generar.return_value = "// código solidity"
    mock_compilar.return_value = ContratoCompilado(
        name="RiskGuard",
        abi=[{"name": "actualizarPausa"}],
        bytecode="0xabc",
    )
    desplegado = ContratoDeplegado(
        name="RiskGuard",
        address="0xDEADBEEF",
        transaction_hash="0xHASH",
        abi=[{"name": "actualizarPausa"}],
    )
    mock_desplegar.return_value = desplegado

    from domain.modelos_transaccion import ResultadoTransaccion, EstadoContrato

    mock_ejecutar.return_value = ResultadoTransaccion(
        transaction_hash="0xFUNHASH",
        contrato_direccion="0xDEADBEEF",
        funcion="actualizarPausa",
        exitoso=True,
    )
    mock_leer.return_value = EstadoContrato(
        contrato_direccion="0xDEADBEEF",
        campo="pausado",
        valor=True,
        exitoso=True,
    )

    agente = AgenteChainSignal()
    resultado = agente.ejecutar(INSIGHT_RIESGO_ALTO)

    assert resultado["requires_action"] is True
    assert resultado["deployed_contract"]["address"] == "0xDEADBEEF"
    assert resultado["executed_function"]["exitoso"] is True
    assert resultado["contract_state"]["valor"] is True

    mock_generar.assert_called_once()
    mock_compilar.assert_called_once()
    mock_desplegar.assert_called_once()


@patch("agents.agente_chainsignal.generar_contrato")
@patch("agents.agente_chainsignal.compilar_contrato_tool")
@patch("agents.agente_chainsignal.desplegar_contrato", return_value=None)
def test_agente_sin_wdk_informa_aviso(mock_desplegar, mock_compilar, mock_generar):
    """Cuando el WDK no está disponible, el agente informa el aviso correctamente."""
    mock_generar.return_value = "// código solidity"
    mock_compilar.return_value = ContratoCompilado(
        nombre="RiskGuard",
        abi=[],
        bytecode="0xabc",
    )

    agente = AgenteChainSignal()
    resultado = agente.ejecutar(INSIGHT_RIESGO_ALTO)

    assert resultado["requiere_accion"] is True
    assert "aviso" in resultado
    assert resultado["contrato_desplegado"] is None


def test_insight_tipo_invalido_retorna_error():
    """El agente debe retornar un error claro si el tipo de contrato no existe."""
    agente = AgenteChainSignal()
    resultado = agente.ejecutar({
        "tipo": "tipo_inexistente",
        "wallet_analizada": "0xABCD",
        "score_riesgo": 90,
    })
    assert "error" in resultado
