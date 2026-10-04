"""Garantías del monitoreo (E05) certificadas contra PostgreSQL.

Corro los mismos escenarios que en SQLite y además concurrencia real: dos
workers sobre las mismas cuentas, dos schedulers a la vez, dos despachadores
sobre el mismo outbox, el trigger que vuelve inmutable la evidencia y el índice
único parcial que impide dos episodios abiertos.
"""

import threading
import time

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, InternalError

from infra.db import get_session_factory, init_db, make_engine
from infra.db_models import AlertRecord, IncidentEvidenceRecord, IncidentRecord, JobRecord, OutboxRecord
from tests import escenarios_monitoreo as escenarios
from tests.monitoreo_ayudantes import Entorno, escenario_hf
from tests.test_identidad_postgres import pg_url  # noqa: F401  (base desechable por prueba)

pytestmark = pytest.mark.postgres


@pytest.fixture
def pg(pg_url):  # noqa: F811
    engine = make_engine(pg_url)
    init_db(engine)
    yield engine
    engine.dispose()


@pytest.mark.parametrize("escenario", [
    escenarios.abre_una_vez_y_no_repite_alertas,
    escenarios.cierra_con_histeresis,
    escenarios.escala_si_nadie_reconoce,
    escenarios.reintenta_429_y_luego_marca_dato_atrasado,
    escenarios.recupera_lease_vencido_sin_duplicar,
    escenarios.crash_despues_del_commit_y_replay,
    escenarios.entrega_at_least_once_con_misma_clave,
    escenarios.reintenta_entregas_con_backoff,
    escenarios.corrige_evidencia_ante_reorg,
    escenarios.canal_sandbox_queda_verificado,
], ids=lambda f: f.__name__)
def test_escenario_en_postgres(pg, escenario):
    escenario(pg)


def _contar(engine, modelo, **filtros):
    with get_session_factory(engine)() as s:
        consulta = select(func.count()).select_from(modelo)
        for campo, valor in filtros.items():
            consulta = consulta.where(getattr(modelo, campo) == valor)
        return s.execute(consulta).scalar_one()


def test_dos_workers_no_duplican_episodios_ni_evaluaciones(pg, pg_url):  # noqa: F811
    cuentas = 8
    e = Entorno(pg, escenarios.REGLA_HF, cuentas=cuentas)
    e.adaptador.poner(escenario_hf("1.375", cuentas=cuentas))
    # Cada worker con su propio engine (pool de conexiones), como dos procesos.
    workers = [e.worker(f"w{i}", engine=make_engine(pg_url)) for i in range(2)]
    barrera = threading.Barrier(2)
    errores = []

    def correr(w):
        try:
            barrera.wait()
            for _ in range(3):
                w.paso()
        except Exception as error:  # pragma: no cover - lo informo en el assert
            errores.append(repr(error))

    hilos = [threading.Thread(target=correr, args=(w,)) for w in workers]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert errores == []
    assert _contar(pg, IncidentRecord, organization_id=e.org_id) == cuentas
    assert _contar(pg, AlertRecord, organization_id=e.org_id) == cuentas
    assert _contar(pg, OutboxRecord, organization_id=e.org_id) == cuentas
    with get_session_factory(pg)() as s:
        jobs = s.execute(select(JobRecord.status, JobRecord.attempts).where(JobRecord.organization_id == e.org_id)).all()
    assert sorted(jobs) == [("done", 1)] * cuentas  # cada cuenta evaluada una vez, sin reintentos
    assert e.adaptador.lecturas == cuentas
    claves = [x["idempotency_key"] for x in e.transporte.enviados]
    assert len(claves) == cuentas and len(set(claves)) == cuentas


def test_dos_schedulers_simultaneos_crean_un_job_por_cuenta(pg):
    cuentas = 6
    e = Entorno(pg, escenarios.REGLA_HF, cuentas=cuentas)
    workers = [e.worker(f"s{i}") for i in range(4)]
    barrera = threading.Barrier(len(workers))
    creados = []

    def programar(w):
        barrera.wait()
        creados.append(w.programar())

    hilos = [threading.Thread(target=programar, args=(w,)) for w in workers]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sum(creados) == cuentas
    assert _contar(pg, JobRecord, organization_id=e.org_id, status="pending") == cuentas


def test_dos_despachadores_entregan_cada_fila_una_vez(pg):
    from monitoreo.notificaciones import ServicioNotificaciones

    e = Entorno(pg, escenarios.REGLA_HF)
    servicio = ServicioNotificaciones(pg, e.reloj, e.transportes)
    for _ in range(20):
        servicio.probar_canal(e.ctx, e.canal["id"])

    # Ensancho la ventana entre leer la fila y tomarla, para que dos despachadores
    # sin bloqueo de fila elijan la misma.
    from sqlalchemy import event

    def pausar(conn, cursor, sentencia, parametros, contexto, many):
        if sentencia.lstrip().upper().startswith("SELECT") and "FROM outbox" in sentencia:
            time.sleep(0.05)

    event.listen(pg, "after_cursor_execute", pausar)
    barrera = threading.Barrier(2)

    def despachar(nombre):
        barrera.wait()
        e.worker(nombre).entregar_disponibles()

    hilos = [threading.Thread(target=despachar, args=(n,)) for n in ("d1", "d2")]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    claves = [x["idempotency_key"] for x in e.transporte.enviados]
    assert len(claves) == 20 and len(set(claves)) == 20
    assert _contar(pg, OutboxRecord, organization_id=e.org_id, status="sent") == 20


def test_evidencia_es_inmutable_en_postgres(pg):
    e = escenarios.abre_una_vez_y_no_repite_alertas(pg)
    with pg.connect() as c:
        for sentencia in ("UPDATE incident_evidence SET note = 'editada'", "DELETE FROM incident_evidence"):
            with pytest.raises(InternalError):
                with c.begin():
                    c.execute(text(sentencia))
    assert _contar(pg, IncidentEvidenceRecord, organization_id=e.org_id) == 1


def test_indice_impide_dos_episodios_abiertos(pg):
    e = escenarios.abre_una_vez_y_no_repite_alertas(pg)
    with get_session_factory(pg)() as s:
        abierto = s.execute(select(IncidentRecord)).scalars().one()
        s.add(IncidentRecord(id="x" * 32, organization_id=abierto.organization_id, account_id=abierto.account_id,
                             policy_id=abierto.policy_id, policy_version=1, rule_type="health_factor_below",
                             status="open", severity="high", escalation_level=0, data_quality="FRESH",
                             opened_at=time.time(), last_evaluated_at=time.time(), last_observed={}))
        with pytest.raises(IntegrityError):
            s.commit()
