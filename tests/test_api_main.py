from fastapi.testclient import TestClient

from api.main import app


def test_ejecutar_agente_wallet_nula_retorna_datos_insuficientes():
    client = TestClient(app)
    response = client.get("/ejecutar-agente/0x0000000000000000000000000000000000000000")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "no_execution_due_to_invalid_wallet" in body
    assert "DATOS_INSUFICIENTES" in body
    assert "tipo_contrato" in body
    assert "null" in body
