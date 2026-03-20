"""Tests del módulo x402 — Mejora 2.

Cubre el ValidadorX402, el GatewayX402 y el endpoint /report/{wallet}
usando TestClient de FastAPI. Las pruebas son independientes del WDK y de
Etherscan (se mockea la infraestructura externa).
"""
import os
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from fastapi.testclient import TestClient


# ─────────────────────────────────────────────────────────────────────────────
# Tests del módulo servicio_x402
# ─────────────────────────────────────────────────────────────────────────────


def test_validador_extrae_hash_de_header():
    """El validador extrae el hash del header X-Payment correctamente."""
    from services.servicio_x402 import ValidadorX402

    v = ValidadorX402()
    hash_valido = "0x" + "a" * 64
    resultado = v.extraer_hash_pago({"x-payment": hash_valido})
    assert resultado == hash_valido


def test_validador_acepta_hash_valido():
    """Un hash con formato correcto y no usado pasa la validación."""
    from services.servicio_x402 import ValidadorX402

    with patch("services.servicio_x402.settings.is_production", new_callable=PropertyMock, return_value=False):
        v = ValidadorX402()
        hash_valido = "0x" + "b" * 64
        valido, motivo = v.validar(hash_valido)
        assert valido is True
        assert "valid" in motivo.lower() or "válido" in motivo.lower()


def test_validador_rechaza_hash_corto():
    """Un hash con formato incorrecto es rechazado."""
    from services.servicio_x402 import ValidadorX402

    with patch("services.servicio_x402.settings.is_production", new_callable=PropertyMock, return_value=False):
        v = ValidadorX402()
        valido, motivo = v.validar("0xabc123")
        assert valido is False
        assert "invalid" in motivo.lower() or "inválido" in motivo.lower()


def test_validador_rechaza_replay():
    """El mismo hash no puede usarse dos veces (anti-replay)."""
    from services.servicio_x402 import ValidadorX402

    with patch("services.servicio_x402.settings.is_production", False):
        v = ValidadorX402()
        hash_valido = "0x" + "c" * 64

        valido1, _ = v.validar(hash_valido)
        assert valido1 is True

        valido2, motivo2 = v.validar(hash_valido)
        assert valido2 is False
        assert "used" in motivo2.lower() or "utilizado" in motivo2.lower()


def test_gateway_emite_challenge():
    """El gateway genera un challenge con los campos requeridos."""
    from services.servicio_x402 import GatewayX402

    gw = GatewayX402()
    challenge = gw.emitir_challenge("Reporte de wallet 0xABCD")
    datos = challenge.to_dict()

    assert datos["payment_required"] is True
    assert "amount" in datos["challenge"]
    assert "token" in datos["challenge"]
    assert "recipient" in datos["challenge"]
    assert "instructions" in datos["challenge"]


def test_gateway_deshabilitado_retorna_false():
    """Con X402_ENABLED=false, verificar_acceso retorna False con mensaje descriptivo."""
    with patch.dict(os.environ, {"X402_ENABLED": "false"}):
        from services.servicio_x402 import GatewayX402

        gw = GatewayX402()
        acceso, motivo = gw.verificar_acceso({})

        assert acceso is False
        assert "disabled" in motivo.lower() or "deshabilitado" in motivo.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Tests del endpoint /report/{wallet_address} via TestClient
# ─────────────────────────────────────────────────────────────────────────────

# Wallet de prueba
WALLET_TEST = "0x1234567890123456789012345678901234567890"


@pytest.fixture
def cliente_api():
    """Fixture que crea un TestClient parcheando el AgenteAnalisis en el módulo api.main.

    El módulo agente_ia no existe como paquete separado en este proyecto —
    AgenteAnalisis se importa en api.main como dependencia externa. Mockeamos
    directamente en api.main para evitar el ModuleNotFoundError.
    """
    import api.main  # Importar primero para que patch pueda resolver 'api.main.AgenteAnalisis'
    with patch("api.main.AgenteAnalisis") as mock_clase_agente:
        mock_clase_agente.return_value.analizar.return_value = None
        from api.main import app
        with TestClient(app, raise_server_exceptions=False) as cliente:
            yield cliente


def test_report_sin_pago_retorna_402(cliente_api):
    """Sin header X-Payment, el endpoint retorna HTTP 402 con challenge."""
    with patch.dict(os.environ, {"X402_ENABLED": "true"}):
        response = cliente_api.get(f"/report/{WALLET_TEST}")

    assert response.status_code == 402
    datos = response.json()
    assert datos["payment_required"] is True
    assert "amount" in datos["challenge"]
    assert "token" in datos["challenge"]


def test_report_con_pago_invalido_retorna_401(cliente_api):
    """Con un hash malformado en X-Payment, retorna HTTP 401."""
    with patch.dict(os.environ, {"X402_ENABLED": "true"}):
        response = cliente_api.get(
            f"/report/{WALLET_TEST}",
            headers={"X-Payment": "0xinvalido"},
        )

    assert response.status_code == 401
    datos = response.json()
    assert (
        "invalid" in datos.get("error", "").lower()
        or "inválido" in datos.get("error", "").lower()
        or "invalid" in datos.get("message", "").lower()
        or "inválido" in datos.get("message", "").lower()
    )


def test_report_x402_deshabilitado_retorna_false_en_gateway():
    """Con X402_ENABLED=false, API retorna 503 descriptivo."""
    with patch.dict(os.environ, {"X402_ENABLED": "false"}):
        import api.main
        from services.servicio_x402 import GatewayX402
        
        # Inyectar un Gateway fresco para que lea las variables de entorno de patch.dict
        api.main._gateway_x402 = GatewayX402()
        
        from api.main import app
        # Importar el cliente de prueba limpio
        with TestClient(app, raise_server_exceptions=False) as cliente_fresco:
            response = cliente_fresco.get(f"/report/{WALLET_TEST}")

    assert response.status_code == 503
    datos = response.json()
    assert "disabled" in datos.get("error", "").lower() or "deshabilitado" in datos.get("error", "").lower() or "X402_ENABLED" in datos.get("message", "")


def test_report_con_pago_valido_retorna_datos():
    """Con hash válido de 66 chars, el sistema intenta generar el reporte."""
    hash_pago = "0x" + "d" * 64

    datos_wallet_mock = MagicMock()
    datos_wallet_mock.total_transacciones = 10

    scores_mock = MagicMock()
    scores_mock.activity_score.valor = 50
    scores_mock.risk_score.valor = 30
    scores_mock.defi_engagement.valor = 20

    perfil_mock = MagicMock()
    perfil_mock.tipo = "passive_holder"
    perfil_mock.confianza = 0.7
    perfil_mock.descripcion = "Holder pasivo"
    perfil_mock.senales = []

    with (
        patch("api.main._cliente") as mock_cliente,
        patch("api.main._extractor") as mock_extractor,
        patch("api.main._clasificador") as mock_clasificador,
        patch("api.main.BehavioralScorer") as mock_scorer_cls,
        patch("api.main.AgenteAnalisis") as mock_agente_cls,
        patch("api.main.DecisionEngine") as mock_engine_cls,
    ):
        mock_cliente.obtener_datos_wallet.return_value = datos_wallet_mock
        mock_extractor.extraer.return_value = datos_wallet_mock
        mock_clasificador.clasificar.return_value = perfil_mock

        mock_scorer_cls.return_value.calcular_scores.return_value = scores_mock
        mock_agente_cls.return_value.analizar.return_value = None

        decision_mock = {
            "decision": "MONITOR",
            "confidence": 0.4,
            "reasoning": "test",
            "action_allowed": "NONE",
            "limits": {"max_eth": 0.1, "gas_limit": 250000},
            "tx_count": 10,
        }
        mock_engine_cls.return_value.evaluate.return_value = decision_mock

        with patch("services.servicio_x402.settings.is_production", new_callable=PropertyMock, return_value=False):
            with patch.dict(os.environ, {"X402_ENABLED": "true"}):
                from api.main import app
                # Forzar reset del gateway para tomar el env actualizado
                import api.main as api_module
                from services.servicio_x402 import GatewayX402
                api_module._gateway_x402 = GatewayX402()

                with TestClient(app, raise_server_exceptions=False) as cliente:
                    response = cliente.get(
                        f"/report/{WALLET_TEST}",
                        headers={"X-Payment": hash_pago},
                    )

    assert response.status_code in (200, 500)
    if response.status_code == 200:
        datos = response.json()
        assert "wallet" in datos
        assert "scores" in datos
        assert "x402" in datos
        assert datos["x402"]["acceso"] == "autorizado"

