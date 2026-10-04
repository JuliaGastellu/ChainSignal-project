"""Límite de cuentas del plan bajo concurrencia real, en PostgreSQL (E09)."""

import threading
import time

import pytest
from sqlalchemy import event, func, select

from comercial.planes import PILOTO
from comercial.suscripciones import LimiteDelPlan
from identidad.recursos import ServicioRecursos
from identidad.servicio import ServicioIdentidad
from infra.db import get_session_factory, init_db, make_engine
from infra.db_models import MonitoredAccountRecord
from tests.ayudantes_identidad import CONTRASENA_PRUEBA
from tests.test_identidad_postgres import pg_url  # noqa: F401

pytestmark = pytest.mark.postgres


def test_dos_altas_simultaneas_no_superan_el_limite(pg_url):  # noqa: F811
    engine = make_engine(pg_url)
    init_db(engine)
    identidad = ServicioIdentidad(engine)
    org_id, user_id = identidad.crear_organizacion_con_owner("Carrera", f"carrera-{time.time_ns()}@ejemplo.test", CONTRASENA_PRUEBA)
    _, _, sesion = identidad.crear_sesion(user_id)
    ctx = identidad.contexto(sesion, org_id, "owner")
    recursos = ServicioRecursos(engine)
    for i in range(PILOTO.limites.max_cuentas - 1):
        recursos.crear_cuenta(ctx, "0x" + f"{i + 1:040x}", 1, None, "medium", 60)

    # Ensancho la carrera: cada alta espera a la otra justo después de contar
    # cuentas. Con el bloqueo de la suscripción, la segunda ni siquiera llega a
    # contar hasta que la primera confirma, y la barrera vence sola.
    barrera = threading.Barrier(2, timeout=2)

    def despues_de_contar(conn, cursor, sentencia, *args):
        if "count(*)" in sentencia.lower() and "monitored_accounts" in sentencia.lower():
            try:
                barrera.wait()
            except threading.BrokenBarrierError:
                pass

    event.listen(engine, "after_cursor_execute", despues_de_contar)
    resultados = []

    def alta(i):
        try:
            recursos.crear_cuenta(ctx, "0x" + f"{1000 + i:040x}", 1, None, "medium", 60)
            resultados.append("ok")
        except LimiteDelPlan:
            resultados.append("limite")

    hilos = [threading.Thread(target=alta, args=(i,)) for i in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    event.remove(engine, "after_cursor_execute", despues_de_contar)

    with get_session_factory(engine)() as s:
        total = s.execute(select(func.count()).select_from(MonitoredAccountRecord).where(
            MonitoredAccountRecord.organization_id == org_id)).scalar_one()
    engine.dispose()
    assert sorted(resultados) == ["limite", "ok"]
    assert total == PILOTO.limites.max_cuentas
