from tests.ayudantes_identidad import iniciar_sesion


def test_ejecutar_agente_wallet_nula_retorna_datos_insuficientes(organizacion):
    client = iniciar_sesion(organizacion[1])
    response = client.get("/ejecutar-agente/0x0000000000000000000000000000000000000000")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert "no_execution_due_to_invalid_wallet" in body
    assert "INSUFFICIENT_DATA" in body
    assert "contract_type" in body
    assert "null" in body
