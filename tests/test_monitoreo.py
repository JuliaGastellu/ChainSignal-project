"""Monitoreo durable (E05) sobre SQLite: reglas, incidentes, jobs y outbox.

Las garantías de concurrencia las certifico en tests/test_monitoreo_postgres.py;
aquí pruebo la lógica con un solo proceso.
"""

from decimal import Decimal

import pytest

from infra.db import make_engine
from monitoreo.reglas import Observacion, ReglaInvalida, evaluar, normalizar_regla
from tests import escenarios_monitoreo as escenarios


@pytest.fixture
def engine(tmp_path):
    return make_engine(f"sqlite:///{(tmp_path / 'monitoreo.db').as_posix()}")


# --- reglas ---------------------------------------------------------------------


def test_regla_heredada_se_convierte_y_las_invalidas_se_rechazan():
    regla = normalizar_regla({"metric": "health_factor", "operator": "lt", "threshold": 1.2})
    assert regla["type"] == "health_factor_below" and Decimal(regla["clear_above"]) == Decimal("1.26")
    for invalida in ({"type": "ganancia"}, {"type": "health_factor_below", "threshold": "1.5", "clear_above": "1.2"},
                     {"type": "stale_data", "max_age_seconds": 5}, {"type": "debt_change", "change_pct": "10", "extra": 1},
                     {"type": "health_factor_below", "threshold": True}):
        with pytest.raises(ReglaInvalida):
            normalizar_regla(invalida)


def test_ninguna_regla_devuelve_probabilidad():
    regla = normalizar_regla(escenarios.REGLA_HF)
    veredicto = evaluar(regla, Observacion("FRESH", Decimal("1.2"), False, 10, None, 0), None)
    assert veredicto.condicion is True
    assert not any("prob" in clave or "confidence" in clave for clave in veredicto.valores)


@pytest.mark.parametrize("calidad", ["STALE", "PARTIAL", "UNAVAILABLE"])
def test_health_factor_no_se_evalua_sin_datos_frescos(calidad):
    regla = normalizar_regla(escenarios.REGLA_HF)
    assert evaluar(regla, Observacion(calidad, Decimal("1.0"), False, 10, None, 0), None).condicion is None


def test_sin_deuda_despeja_y_banda_de_histeresis_no():
    regla = normalizar_regla(escenarios.REGLA_HF)
    sin_deuda = evaluar(regla, Observacion("FRESH", None, True, 0, None, 0), None)
    banda = evaluar(regla, Observacion("FRESH", Decimal("1.55"), False, 1, None, 0), None)
    assert sin_deuda.condicion is False and sin_deuda.despejada is True
    assert banda.condicion is False and banda.despejada is False


def test_cambio_de_deuda_contra_linea_base():
    regla = normalizar_regla({"type": "debt_change", "change_pct": "20"})
    obs = lambda deuda: Observacion("FRESH", Decimal("2"), False, deuda, None, 0)  # noqa: E731
    assert evaluar(regla, obs(100), None).condicion is False  # sin línea base todavía
    assert evaluar(regla, obs(119), 100).condicion is False
    assert evaluar(regla, obs(120), 100).condicion is True
    assert evaluar(regla, obs(79), 100).condicion is True
    assert evaluar(regla, obs(1), 0).condicion is True


def test_dato_atrasado():
    regla = normalizar_regla({"type": "stale_data", "max_age_seconds": 120})
    assert evaluar(regla, Observacion("FRESH", None, None, None, 1_000, 1_100), None).condicion is False
    atrasado = evaluar(regla, Observacion("UNAVAILABLE", None, None, None, 1_000, 1_200), None)
    assert atrasado.condicion is True and atrasado.valores["age_seconds"] == 200


# --- escenarios -------------------------------------------------------------------


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
def test_escenario(engine, escenario):
    escenario(engine)


def test_version_de_politica_queda_en_el_incidente(engine):
    from infra.db_models import IncidentRecord

    e = escenarios.abre_una_vez_y_no_repite_alertas(engine)
    actualizada = e.recursos.actualizar_politica(e.ctx, e.politica["id"], {"rule": {**escenarios.REGLA_HF, "threshold": "1.4"}})
    assert actualizada["version"] == 2
    assert [v["version"] for v in e.recursos.versiones_politica(e.ctx, e.politica["id"])] == [1, 2]
    assert e.tabla(IncidentRecord, organization_id=e.org_id)[0].policy_version == 1


# --- reclamo de jobs ----------------------------------------------------------------


def test_reclamo_condicional_no_toma_un_job_que_otro_proceso_tomo(engine):
    """Entre elegir el candidato y reclamarlo, otro proceso lo toma: no lo tomo yo también.

    En SQLite no hay SKIP LOCKED; el compare-and-set sobre estado e intentos es la
    única defensa. Simulo la carrera escribiendo desde otra conexión justo antes
    del UPDATE de reclamo.
    """
    from sqlalchemy import event, text

    from monitoreo.trabajos import ColaTrabajos

    e = escenarios.Entorno(engine, escenarios.REGLA_HF)
    cola = ColaTrabajos(engine)
    assert cola.encolar("evaluate_account", e.org_id, e.cuentas[0], "evaluate:carrera")
    disparado = []

    def otro_proceso_lo_toma(conn, cursor, sentencia, parametros, contexto, executemany):
        if sentencia.lstrip().upper().startswith("UPDATE JOBS") and not disparado:
            disparado.append(True)
            with engine.connect() as otra:
                otra.execute(text("UPDATE jobs SET status='running', attempts=attempts+1, lease_owner='otro', "
                                  "lease_expires_at=:hasta WHERE dedupe_key='evaluate:carrera'"), {"hasta": 10**12})
                otra.commit()

    event.listen(engine, "before_cursor_execute", otro_proceso_lo_toma)
    try:
        assert cola.tomar("yo", dedupe_key="evaluate:carrera") is None
    finally:
        event.remove(engine, "before_cursor_execute", otro_proceso_lo_toma)
    assert disparado
    from infra.db_models import JobRecord

    job = e.tabla(JobRecord, dedupe_key="evaluate:carrera")[0]
    assert (job.lease_owner, job.attempts) == ("otro", 1)


def test_el_worker_no_toma_jobs_de_demos(engine):
    from sqlalchemy import update

    from infra.db import get_session_factory
    from infra.db_models import JobRecord, OrganizationRecord
    from monitoreo.trabajos import ColaTrabajos

    e = escenarios.Entorno(engine, escenarios.REGLA_HF)
    with get_session_factory(engine)() as s:
        s.execute(update(OrganizationRecord).where(OrganizationRecord.id == e.org_id).values(is_demo=True))
        s.commit()
    cola = ColaTrabajos(engine, e.reloj)
    assert cola.encolar("evaluate_account", e.org_id, e.cuentas[0], f"evaluate:{e.cuentas[0]}")
    assert e.worker().evaluar_disponibles() == {}
    assert e.adaptador.lecturas == 0
    assert e.tabla(JobRecord, organization_id=e.org_id)[0].status == "pending"
    # La evaluación en línea de la demo sí lo toma.
    assert cola.tomar("inline", dedupe_key=f"evaluate:{e.cuentas[0]}") is not None
