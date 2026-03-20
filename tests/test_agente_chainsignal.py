"""Pruebas unitarias del AgenteChainSignal."""

from unittest.mock import patch

from agents.agente_chainsignal import AgenteChainSignal
from domain.modelos_contrato import ContratoCompilado, ContratoDeplegado


# Insight mínimo que supera el umbral de riesgo por defecto (60).
INSIGHT_RIESGO_ALTO = {
    "tipo": "risk_guard",
    "wallet_analizada": "0x1234567890123456789012345678901234567890",
    "score_riesgo": 85,
    "score_actividad": 30,
}

INSIGHT_RIESGO_BAJO = {
    "tipo": "risk_guard",
    "wallet_analizada": "0x1234567890123456789012345678901234567890",
    "score_riesgo": 20,
    "score_actividad": 10,
}


def test_agente_no_actua_con_riesgo_bajo():
    """El agente no debe iniciar el ciclo on-chain si el score es bajo."""
    agente = AgenteChainSignal()
    resultado = agente.ejecutar(INSIGHT_RIESGO_BAJO)

    assert resultado["requiere_accion"] is False
    assert "motivo_sin_accion" in resultado


def test_agente_no_actua_si_tipo_none():
    """El agente no debe ejecutar ciclo on-chain cuando insight.tipo es None."""
    agente = AgenteChainSignal()
    resultado = agente.ejecutar({
        "tipo": None,
        "wallet_analizada": "0x123",
        "score_riesgo": 10,
        "score_actividad": 10,
    })

    assert resultado["requiere_accion"] is False
    assert "motivo_sin_accion" in resultado


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
        nombre="RiskGuard",
        abi=[{"name": "actualizarPausa"}],
        bytecode="0xabc",
    )
    desplegado = ContratoDeplegado(
        nombre="RiskGuard",
        direccion="0xDEADBEEF",
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

    assert resultado["requiere_accion"] is True
    assert resultado["contrato_desplegado"]["direccion"] == "0xDEADBEEF"
    assert resultado["funcion_ejecutada"]["exitoso"] is True
    assert resultado["estado_contrato"]["valor"] is True

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
