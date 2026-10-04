"""Pruebas del validador x402 y del contrato actual de /report/{wallet}.

El reporte premium con pago x402 y despliegue de contrato ya no existe: hoy
/report/{wallet} es un análisis gratuito de solo lectura sobre la wallet
objetivo. Pruebo ese contrato y conservo las pruebas del validador, que sigue
en services/servicio_x402.py.
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from services.servicio_x402 import ValidadorX402

# ─────────────────────────────────────────────────────────────────────────────
# Validador x402
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
# Contrato actual de /report/{wallet_address}: gratuito y de solo lectura
# ─────────────────────────────────────────────────────────────────────────────

WALLET_TEST = "0x1234567890123456789012345678901234567890"

REPORTE_SINTETICO = {
    "wallet": WALLET_TEST.lower(),
    "decision": "MONITOR",
    "scores": {"risk": 10, "activity": 40},
}


@pytest.fixture
def cliente_api(organizacion):
    # Desde E02 /report exige sesión.
    from tests.ayudantes_identidad import iniciar_sesion

    with iniciar_sesion(organizacion[1]) as cliente:
        yield cliente


def test_report_no_exige_pago(cliente_api):
    with patch("api.main._agent_service.run_pipeline_core", new=AsyncMock(return_value=dict(REPORTE_SINTETICO))):
        response = cliente_api.get(f"/report/{WALLET_TEST}")

    assert response.status_code == 200
    assert "payment_required" not in response.json()


def test_report_declara_wallet_objetivo_como_solo_lectura(cliente_api):
    wallet_mixta = "0xABCDEF0000000000000000000000000000000001"
    with patch("api.main._agent_service.run_pipeline_core", new=AsyncMock(return_value=dict(REPORTE_SINTETICO))) as pipeline:
        response = cliente_api.get(f"/report/{wallet_mixta}")

    assert response.status_code == 200
    datos = response.json()
    pipeline.assert_awaited_once_with(wallet_mixta)
    assert datos["decision"] == "MONITOR"
    assert datos["target_wallet"] == wallet_mixta.lower()
    assert datos["action_scope"]["target_wallet"] == "read_only"
    assert datos["decision_context"]["what_was_analyzed"] == wallet_mixta.lower()
    assert datos["action_scope"]["agent_wallet"] == "disabled"
    assert datos["agent_wallet"] is None
    assert datos["decision_context"]["who_executes"] is None


def test_report_ignora_header_de_pago(cliente_api):
    with patch("api.main._agent_service.run_pipeline_core", new=AsyncMock(return_value=dict(REPORTE_SINTETICO))):
        response = cliente_api.get(f"/report/{WALLET_TEST}", headers={"X-Payment": "0x" + "d" * 64})

    assert response.status_code == 200
    assert "x402_payment" not in response.json()


def test_report_devuelve_500_si_falla_el_pipeline(cliente_api):
    with patch("api.main._agent_service.run_pipeline_core", new=AsyncMock(side_effect=RuntimeError("proveedor caído"))):
        response = cliente_api.get(f"/report/{WALLET_TEST}")

    assert response.status_code == 500
    assert response.json()["error"] == "internal_server_error"
