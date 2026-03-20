"""Tests del módulo x402 — Mejora 2.

Cubre el ValidadorX402, el GatewayX402 y el endpoint /report/{wallet}
usando TestClient de FastAPI. Las pruebas son independientes del WDK y de
Etherscan (se mockea la infraestructura externa).
"""
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from services.servicio_x402 import ValidadorX402, GatewayX402

# ─────────────────────────────────────────────────────────────────────────────
# Tests del módulo servicio_x402
# ─────────────────────────────────────────────────────────────────────────────

def test_validador_extrae_hash_de_header():
    """El validador extrae el hash del header X-Payment correctamente."""
    v = ValidadorX402()
    hash_valido = "0x" + "a" * 64
    resultado = v.extraer_hash_pago({"x-payment": hash_valido})
    assert resultado == hash_valido

def test_validador_acepta_hash_valido():
    """Un hash con formato correcto y no usado pasa la validación."""
    with patch("services.servicio_x402.settings") as mock_settings:
        mock_settings.is_production = False
        v = ValidadorX402()
        v._hashes_usados.clear() # Limpiar para evitar colisión con persistencia
        hash_valido = "0x" + "b" * 64
        valido, motivo = v.validar(hash_valido)
        assert valido is True
        assert "valid" in motive.lower() if 'motive' in locals() else "valid" in motivo.lower()

def test_validador_rechaza_hash_corto():
    """Un hash con formato incorrecto es rechazado."""
    with patch("services.servicio_x402.settings") as mock_settings:
        mock_settings.is_production = False
        v = ValidadorX402()
        valido, motivo = v.validar("0xabc123")
        assert valido is False
        assert "invalid" in motivo.lower()

def test_validador_rechaza_replay():
    """El mismo hash no puede usarse dos veces (anti-replay)."""
    with patch("services.servicio_x402.settings") as mock_settings:
        mock_settings.is_production = False
        v = ValidadorX402()
        hash_valido = "0x" + "c" * 64
        v._hashes_usados.clear()
        
        valido1, _ = v.validar(hash_valido)
        assert valido1 is True
        valido2, motivo2 = v.validar(hash_valido)
        assert valido2 is False
        assert "used" in motivo2.lower()

def test_gateway_emite_challenge():
    """El gateway genera un challenge con los campos requeridos."""
    gw = GatewayX402()
    challenge = gw.emitir_challenge("Reporte de wallet 0xABCD")
    datos = challenge.to_dict()
    assert datos["payment_required"] is True
    assert "amount" in datos["challenge"]
    assert "token" in datos["challenge"]
    assert "recipient" in datos["challenge"]
    assert "instructions" in datos["challenge"]

def test_gateway_deshabilitado_retorna_true():
    """Con X402_ENABLED=false, verificar_acceso retorna True (acceso permitido)."""
    with patch("services.servicio_x402.ValidadorX402.esta_habilitado", return_value=False):
        gw = GatewayX402()
        acceso, motivo = gw.verificar_acceso({})
        assert acceso is True
        assert "disabled" in motivo.lower()

# ─────────────────────────────────────────────────────────────────────────────
# Tests del endpoint /report/{wallet_address} via TestClient
# ─────────────────────────────────────────────────────────────────────────────

WALLET_TEST = "0x1234567890123456789012345678901234567890"

@pytest.fixture
def cliente_api():
    """Fixture que crea un TestClient."""
    with patch("api.main.AgenteAnalisis") as mock_clase_agente:
        mock_clase_agente.return_value.analizar.return_value = None
        from api.main import app
        with TestClient(app, raise_server_exceptions=False) as cliente:
            yield cliente

def test_report_sin_pago_retorna_402(cliente_api):
    """Sin header X-Payment, el endpoint retorna HTTP 402 con challenge."""
    with patch("api.main.GatewayX402") as mock_gw_cls:
        mock_gw_cls.return_value.verificar_acceso.return_value = (False, "Payment Required")
        mock_gw_cls.return_value.emitir_challenge.return_value.to_dict.return_value = {
            "payment_required": True,
            "challenge": {"amount": "1000000", "token": "USDC"}
        }
        response = cliente_api.get(f"/report/{WALLET_TEST}")
        assert response.status_code == 402
        datos = response.json()
        assert datos["payment_required"] is True

def test_report_con_pago_valido_retorna_datos(cliente_api):
    """Con hash válido, el sistema intenta generar el reporte."""
    hash_pago = "0x" + "d" * 64
    
    # Mock Gateway to allow access
    with patch("api.main.GatewayX402") as mock_gw_cls:
        mock_gw_cls.return_value.verificar_acceso.return_value = (True, "Access granted")
        
        # Mock dependencies in report generation
        with (
            patch("api.main._cliente") as mock_cliente,
            patch("api.main._extractor") as mock_extractor,
            patch("api.main._clasificador") as mock_clasificador,
            patch("api.main.BehavioralScorer") as mock_scorer_cls,
        ):
            mock_cliente.obtener_datos_wallet.return_value = {}
            mock_extractor.extraer.return_value = MagicMock()
            
            perfil = MagicMock()
            perfil.type = "passive_holder"
            mock_clasificador.clasificar.return_value = perfil
            
            scores = MagicMock()
            scores.risk_score.value = 10
            scores.activity_score.value = 20
            scores.defi_engagement.value = 30
            mock_scorer_cls.return_value.calcular_scores.return_value = scores
            
            response = cliente_api.get(
                f"/report/{WALLET_TEST}",
                headers={"X-Payment": hash_pago},
            )

    assert response.status_code == 200
    datos = response.json()
    assert datos["wallet"] == WALLET_TEST.lower()
    assert datos["profile"] == "passive_holder"
    assert "scores" in datos
    assert datos["x402_payment"] == "validated"
