"""Concurrencia de la ingesta, certificada solo contra PostgreSQL (E03)."""

import threading

import pytest
from sqlalchemy import func, select

from infra.db import make_engine
from infra.db_models import ChainTransactionRecord
from infra.red import ETHEREUM
from ingestion_onchain.ingesta import ServicioIngesta
from ingestion_onchain.proveedores import ClienteEtherscan, PoliticaReintentos
from tests.proveedor_simulado import DIRECCION, CadenaSimulada, TransporteSimulado
from tests.test_identidad_postgres import pg_url  # noqa: F401  (fixture de base desechable)

pytestmark = pytest.mark.postgres


def test_dos_procesos_sincronizan_la_misma_cuenta_sin_duplicar(pg_url, monkeypatch):  # noqa: F811
    from infra.config import settings

    monkeypatch.setattr(settings, "INGESTION_PAGE_SIZE", 3)
    cadena = CadenaSimulada()
    for bloque in (100, 200, 300, 400, 500):
        cadena.agregar_tx(bloque)

    barrera = threading.Barrier(2, timeout=20)

    def construir():
        historial = ClienteEtherscan(ETHEREUM, "k", TransporteSimulado(cadena), PoliticaReintentos(dormir=lambda s: None), url="https://simulado")
        servicio = ServicioIngesta(ETHEREUM, historial, None, make_engine(pg_url))
        original = servicio._guardar

        def guardar_juntos(direccion, flujo, *args, **kwargs):
            if flujo == "transactions":
                barrera.wait()  # los dos consultaron al proveedor y escriben a la vez
            return original(direccion, flujo, *args, **kwargs)

        servicio._guardar = guardar_juntos
        return servicio

    servicios = [construir(), construir()]
    resultados = []
    hilos = [threading.Thread(target=lambda s=s: resultados.append(s.obtener_datos_wallet(DIRECCION))) for s in servicios]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert len(resultados) == 2
    assert all(sorted(t.bloque for t in r.transacciones) == [100, 200, 300, 400, 500] for r in resultados)
    engine = make_engine(pg_url)
    with engine.connect() as c:
        filas = c.execute(select(func.count()).select_from(ChainTransactionRecord).where(
            ChainTransactionRecord.address == DIRECCION, ChainTransactionRecord.stream == "transactions")).scalar_one()
    engine.dispose()
    assert filas == 5
