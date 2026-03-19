"""Tests de WDK Agent Skills — Mejora 1.

Cubre los tres skills (balance, cotización, swap) en modo simulación
y verifica que el agente los invoca cuando la decisión es EXECUTE_ADVANCED.
"""

import os
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Tests de ServicioWDK — Métodos skill_*
# ─────────────────────────────────────────────────────────────────────────────


def test_skill_balance_modo_simulacion():
    """El skill de balance retorna datos simulados cuando APP_ENV != production."""
    with patch.dict(os.environ, {"APP_ENV": "local"}):
        from services.servicio_wdk import ServicioWDK

        wdk = ServicioWDK()
        resultado = wdk.skill_obtener_balance("0xABCD1234")

    assert "balanceEth" in resultado
    assert float(resultado["balanceEth"]) > 0
    assert resultado.get("red") == "simulacion"


def test_skill_cotizacion_modo_simulacion():
    """El skill de cotización retorna estructura correcta en modo simulación."""
    with patch.dict(os.environ, {"APP_ENV": "local"}):
        from services.servicio_wdk import ServicioWDK

        wdk = ServicioWDK()
        token_out = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
        resultado = wdk.skill_obtener_cotizacion("ETH", token_out, 500_000_000_000_000)

    assert "fee" in resultado
    assert "tokenInAmount" in resultado
    assert "tokenOutAmount" in resultado
    assert resultado["tokenIn"] == "ETH"
    assert resultado["tokenOut"] == token_out


def test_skill_swap_modo_simulacion():
    """El skill de swap retorna ResultadoTransaccion exitoso en modo simulación."""
    with patch.dict(os.environ, {"APP_ENV": "local"}):
        from services.servicio_wdk import ServicioWDK

        wdk = ServicioWDK()
        token_out = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
        resultado = wdk.skill_ejecutar_swap("ETH", token_out, 500_000_000_000_000)

    assert resultado.exitoso is True
    assert resultado.transaction_hash.startswith("0xSkillSwapSimulado")
    assert resultado.funcion == "skill_swap"


def test_skill_balance_sin_wdk_retorna_vacio():
    """Sin WDK activo y sin modo simulación, el skill de balance retorna dict vacío."""
    with patch.dict(os.environ, {"APP_ENV": "production"}):
        with patch("wallet_controller.wallet_agent.WalletAgent.__init__", return_value=None):
            from services.servicio_wdk import ServicioWDK

            wdk = ServicioWDK()
            # Forzar modo sin simulación y WDK inactivo
            wdk.modo_simulacion = False
            # Mockear httpx para simular fallo de conexión
            with patch("httpx.get", side_effect=Exception("Connection refused")):
                resultado = wdk.skill_obtener_balance("0xABCD")

    assert resultado == {}


def test_skill_cotizacion_sin_wdk_retorna_vacio():
    """Sin WDK activo, el skill de cotización retorna dict vacío sin crash."""
    with patch.dict(os.environ, {"APP_ENV": "production"}):
        with patch("wallet_controller.wallet_agent.WalletAgent.__init__", return_value=None):
            from services.servicio_wdk import ServicioWDK

            wdk = ServicioWDK()
            wdk.modo_simulacion = False
            with patch("httpx.post", side_effect=Exception("Connection refused")):
                resultado = wdk.skill_obtener_cotizacion("ETH", "0xToken", 1000)

    assert resultado == {}


# ─────────────────────────────────────────────────────────────────────────────
# Tests de AgenteChainSignal — Integración de _invocar_skills
# ─────────────────────────────────────────────────────────────────────────────


INSIGHT_RIESGO_ALTO_SKILLS = {
    "tipo": "risk_guard",
    "wallet_analizada": "0x1234567890123456789012345678901234567890",
    "score_riesgo": 85,
    "score_actividad": 30,
}


@patch("agents.agente_chainsignal.generar_contrato")
@patch("agents.agente_chainsignal.compilar_contrato_tool")
@patch("agents.agente_chainsignal.desplegar_contrato")
@patch("agents.agente_chainsignal.ejecutar_funcion")
@patch("agents.agente_chainsignal.leer_estado")
def test_skills_invocados_en_execute_advanced(
    mock_leer, mock_ejecutar, mock_desplegar, mock_compilar, mock_generar
):
    """El agente invoca los skills y los adjunta al resultado cuando hay acción requerida."""
    from domain.modelos_contrato import ContratoCompilado, ContratoDeplegado
    from domain.modelos_transaccion import ResultadoTransaccion, EstadoContrato

    mock_generar.return_value = "// solidity"
    mock_compilar.return_value = ContratoCompilado(
        nombre="RiskGuard", abi=[{"name": "actualizarPausa"}], bytecode="0xabc"
    )
    mock_desplegar.return_value = ContratoDeplegado(
        nombre="RiskGuard",
        direccion="0xDEAD",
        transaction_hash="0xHASH",
        abi=[{"name": "actualizarPausa"}],
    )
    mock_ejecutar.return_value = ResultadoTransaccion(
        transaction_hash="0xFUN",
        contrato_direccion="0xDEAD",
        funcion="actualizarPausa",
        exitoso=True,
    )
    mock_leer.return_value = EstadoContrato(
        contrato_direccion="0xDEAD", campo="pausado", valor=True, exitoso=True
    )

    with patch.dict(os.environ, {"APP_ENV": "local"}):
        from agents.agente_chainsignal import AgenteChainSignal

        agente = AgenteChainSignal()
        resultado = agente.ejecutar(INSIGHT_RIESGO_ALTO_SKILLS)

    # El resultado debe incluir la clave skills_ejecutados con al menos balance
    assert resultado["requiere_accion"] is True
    assert "skills_ejecutados" in resultado
    assert resultado["skills_ejecutados"] is not None
    assert "balance_wallet_analizada" in resultado["skills_ejecutados"]
    # Con score >= 80, también debe haber cotización
    assert "cotizacion_swap_preventivo" in resultado["skills_ejecutados"]


def test_invocar_skills_riesgo_bajo_no_cotiza():
    """Con score < 80, _invocar_skills no consulta cotización de swap."""
    from domain.modelos_contrato import InsightContrato

    with patch.dict(os.environ, {"APP_ENV": "local"}):
        from agents.agente_chainsignal import AgenteChainSignal
        from services.servicio_wdk import ServicioWDK

        agente = AgenteChainSignal()
        insight = InsightContrato(
            tipo="signal_lock",
            wallet_analizada="0xABCD",
            score_riesgo=50,
            score_actividad=40,
        )
        wdk = ServicioWDK()
        resultado = agente._invocar_skills(insight, wdk)

    assert "balance_wallet_analizada" in resultado
    # Con score_riesgo 50 (< 80) NO debe haber cotización de swap
    assert "cotizacion_swap_preventivo" not in resultado
