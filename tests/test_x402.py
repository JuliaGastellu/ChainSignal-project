"""Tests del módulo x402 — Versión Premium.

Valida la nueva estructura enriquecida del reporte x402, incluyendo
señales de comportamiento, interpretaciones de scores y datos de contrato.
"""
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from services.servicio_x402 import ValidadorX402, GatewayX402

# ─────────────────────────────────────────────────────────────────────────────
# Tests del módulo servicio_x402 (sin cambios significativos)
# ─────────────────────────────────────────────────────────────────────────────

def test_validador_extrae_hash_de_header():
    v = ValidadorX402()
    hash_valido = "0x" + "a" * 64
    assert v.extraer_hash_pago({"x-payment": hash_valido}) == hash_valido

def test_validador_acepta_hash_valido():
    with patch("services.servicio_x402.settings") as mock_settings:
        mock_settings.is_production = False
        v = ValidadorX402()
        v._hashes_usados.clear()
        hash_valido = "0x" + "b" * 64
        valido, _ = v.validar(hash_valido)
        assert valido is True

# ─────────────────────────────────────────────────────────────────────────────
# Tests del endpoint /report/{wallet_address} Premium
# ─────────────────────────────────────────────────────────────────────────────

WALLET_TEST = "0x1234567890123456789012345678901234567890"

@pytest.fixture
def cliente_api():
    from api.main import app
    with TestClient(app, raise_server_exceptions=False) as cliente:
        yield cliente

def test_report_premium_sin_pago_retorna_402(cliente_api):
    response = cliente_api.get(f"/report/{WALLET_TEST}")
    assert response.status_code == 402
    assert response.json()["payment_required"] is True

def test_report_premium_con_pago_valido_retorna_json_detallado(cliente_api):
    hash_pago = "0x" + "d" * 64
    
    with (
        patch("api.main.GatewayX402.verificar_acceso", return_value=(True, "OK")),
        patch("api.main._cliente.obtener_datos_wallet", return_value=MagicMock()),
        patch("api.main._extractor.extraer") as mock_extractor,
        patch("api.main._clasificador.clasificar") as mock_clasificador,
        patch("api.main.BehavioralScorer.calcular_scores") as mock_scorer,
        patch("api.main.DecisionEngine.evaluate") as mock_engine,
    ):
        # Mocks para datos de retorno
        metrics = MagicMock()
        metrics.total_transacciones = 100
        metrics.balance_eth_actual = 1.5
        metrics.dias_activo = 365
        metrics.frecuencia_transacciones_por_dia = 0.5
        metrics.porcentaje_interacciones_contratos = 40.0
        mock_extractor.return_value = metrics
        
        perfil = MagicMock()
        perfil.type = "active_trader"
        perfil.confidence = "high"
        perfil.description = "Test description"
        perfil.signals = ["Signal A", "Signal B"]
        mock_clasificador.return_value = perfil
        
        scores = MagicMock()
        scores.risk_score = MagicMock(value=10, interpretation="Low Risk")
        scores.activity_score = MagicMock(value=80, interpretation="High Activity")
        scores.defi_engagement = MagicMock(value=50, interpretation="Medium DeFi")
        scores.web3_activity_index = MagicMock(value=70, interpretation="High Web3")
        mock_scorer.return_value = scores
        
        mock_engine.return_value = {
            "decision": "EXECUTE_BASIC",
            "reasoning": "Stable profile",
            "recommended_action": "monitor"
        }
        
        response = cliente_api.get(
            f"/report/{WALLET_TEST}",
            headers={"X-Payment": hash_pago},
        )

    assert response.status_code == 200
    datos = response.json()
    
    # Validar estructura Premium
    assert datos["wallet"] == WALLET_TEST.lower()
    assert datos["profile"]["type"] == "active_trader"
    assert datos["profile"]["confidence"] == "high"
    assert len(datos["profile"]["signals"]) == 2
    
    assert datos["scores"]["risk"]["value"] == 10
    assert "Low Risk" in datos["scores"]["risk"]["interpretation"]
    assert "web3_index" in datos["scores"]
    
    assert datos["metrics"]["total_transactions"] == 100
    assert datos["agent_decision"]["decision"] == "EXECUTE_BASIC"
    assert datos["x402_payment"] == "validated"

def test_report_premium_con_contrato_execute_advanced(cliente_api):
    hash_pago = "0x" + "e" * 64
    
    with (
        patch("api.main.GatewayX402.verificar_acceso", return_value=(True, "OK")),
        patch("api.main._cliente.obtener_datos_wallet", return_value=MagicMock()),
        patch("api.main._extractor.extraer", return_value=MagicMock(total_transacciones=200)),
        patch("api.main._clasificador.clasificar", return_value=MagicMock(type="defi_power_user", signals=[])),
        patch("api.main.BehavioralScorer.calcular_scores", return_value=MagicMock()),
        patch("api.main.DecisionEngine.evaluate") as mock_engine,
        patch("api.main.generar_contrato", return_value="pragma solidity ..."),
        patch("api.main.compilar_contrato_tool") as mock_compile,
        patch("api.main.BackgroundTasks.add_task") as mock_bg,
    ):
        mock_engine.return_value = {
            "decision": "EXECUTE_ADVANCED",
            "contract_type": "risk_guard",
            "reasoning": "Advanced profile detected",
            "recommended_action": "protect"
        }
        
        mock_compile.return_value = MagicMock(abi=[], bytecode="0x123")
        
        response = cliente_api.get(
            f"/report/{WALLET_TEST}",
            headers={"X-Payment": hash_pago},
        )

    assert response.status_code == 200
    datos = response.json()
    
    # Validar presencia de contrato
    assert datos["contract"] is not None
    assert datos["contract"]["type"] == "risk_guard"
    assert datos["contract"]["source_code"] == "pragma solidity ..."
    assert datos["contract"]["status"] == "compiled_and_deploying"
    
    # Validar que se lanzó la tarea en segundo plano
    mock_bg.assert_called_once()
