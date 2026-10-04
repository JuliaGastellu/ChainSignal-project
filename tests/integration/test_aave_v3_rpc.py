"""Integración manual: leo una posición Aave V3 real y la verifico de forma independiente.

Necesita un RPC de Ethereum mainnet de solo lectura y una cuenta con posición:
    CHAINSIGNAL_RUN_INTEGRATION=1 ETHEREUM_RPC_URL=https://... AAVE_TEST_USER=0x... pytest -m integration tests/integration/test_aave_v3_rpc.py
Sin archive, solo puedo leer bloques recientes: uso cabeza - 12 confirmaciones.
"""

import os

import pytest

pytestmark = pytest.mark.integration


def test_posicion_real_reconcilia_y_coincide_con_balanceof():
    from infra.red import ETHEREUM
    from ingestion_onchain.proveedores import RpcLectura
    from protocolos.aave_v3 import AdaptadorAaveV3
    from protocolos.replay import verificar_independiente

    url, usuario = os.getenv("ETHEREUM_RPC_URL"), os.getenv("AAVE_TEST_USER")
    if not url or not usuario:
        pytest.skip("Definí ETHEREUM_RPC_URL y AAVE_TEST_USER")
    lector = RpcLectura(ETHEREUM, url)
    snapshot = AdaptadorAaveV3(lector).leer_posicion(usuario)

    assert snapshot.bloque is not None, snapshot.presentar()["data_quality"]
    assert snapshot.conciliacion["reconciled"], snapshot.conciliacion
    assert verificar_independiente(lector, snapshot)["matches"]
