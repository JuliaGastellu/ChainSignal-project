"""Operación del piloto (E08): readiness, métricas, latido y migraciones separadas del arranque."""

import pytest
from fastapi.testclient import TestClient

from infra.db import EsquemaDesactualizado, init_db, make_engine, revision_actual, revision_head
from tests import escenarios_monitoreo as escenarios


@pytest.fixture
def engine(tmp_path):
    return make_engine(f"sqlite:///{(tmp_path / 'operacion.db').as_posix()}")


@pytest.fixture
def cliente():
    from api.main import app

    with TestClient(app) as c:  # corre el lifespan: prepara la base
        yield c


def test_liveness_y_readiness(cliente):
    assert cliente.get("/health").json()["status"] == "ok"
    assert cliente.get("/ready").json() == {"status": "ready"}


def test_readiness_falla_si_el_esquema_no_esta_en_head(cliente, monkeypatch):
    import infra.db

    monkeypatch.setattr(infra.db, "revision_head", lambda: "9999")
    respuesta = cliente.get("/ready")
    assert respuesta.status_code == 503 and respuesta.json() == {"status": "not_ready", "reason": "schema"}


def test_readiness_falla_sin_base(cliente, monkeypatch):
    import infra.db

    def caida(*args, **kwargs):
        raise ConnectionError("db down")

    monkeypatch.setattr(infra.db.engine, "connect", caida)
    respuesta = cliente.get("/ready")
    assert respuesta.status_code == 503 and respuesta.json()["reason"] == "database" and "db down" not in respuesta.text


def test_metricas_exigen_token(cliente, monkeypatch):
    from infra.config import settings

    monkeypatch.setattr(settings, "METRICS_TOKEN", "")
    assert cliente.get("/metrics").status_code == 404
    monkeypatch.setattr(settings, "METRICS_TOKEN", "token-de-metricas")
    assert cliente.get("/metrics").status_code == 401
    assert cliente.get("/metrics", headers={"Authorization": "Bearer otro"}).status_code == 401
    respuesta = cliente.get("/metrics", headers={"Authorization": "Bearer token-de-metricas"})
    assert respuesta.status_code == 200 and "chainsignal_workers_alive" in respuesta.text


def test_sin_auto_migracion_verifica_el_esquema(engine, monkeypatch):
    from infra.config import settings

    monkeypatch.setattr(settings, "DB_AUTO_MIGRATE", False)
    with pytest.raises(EsquemaDesactualizado):
        init_db(engine)
    assert revision_actual(engine) is None  # no migró

    monkeypatch.setattr(settings, "DB_AUTO_MIGRATE", True)
    otro = make_engine(str(engine.url))
    init_db(otro)  # el paso de migración, aparte
    monkeypatch.setattr(settings, "DB_AUTO_MIGRATE", False)
    tercero = make_engine(str(engine.url))
    init_db(tercero)  # ahora verifica y pasa
    assert revision_actual(tercero) == revision_head()


def test_migraciones_ida_y_vuelta(engine):
    from alembic import command

    from infra.db import _config_alembic

    init_db(engine)
    config = _config_alembic()
    with engine.begin() as conexion:
        config.attributes["connection"] = conexion
        command.downgrade(config, "0006")
    assert revision_actual(engine) == "0006"
    with engine.begin() as conexion:
        config.attributes["connection"] = conexion
        command.upgrade(config, "head")
    assert revision_actual(engine) == revision_head() == "0009"


def test_el_worker_late_y_las_metricas_miden(engine):
    from operacion.metricas import a_prometheus, medir

    e = escenarios.abre_una_vez_y_no_repite_alertas(engine)
    e.worker("w-metricas").paso()
    m = medir(engine, ahora=e.reloj())
    assert m["workers"]["alive"] >= 1
    assert m["coverage"]["accounts"] == 1 and m["coverage"]["ratio"] == 1.0
    assert m["detection_latency_seconds"]["count"] == 0  # los snapshots del escenario son sintéticos: no cuentan
    assert m["delivery"]["by_status"].get("sent", 0) >= 1
    assert m["targets"]["internal_only"] is True and m["cost"]["rpc_usd"].startswith("pending")
    texto = a_prometheus(m)
    assert "chainsignal_coverage_ratio 1.0" in texto and "chainsignal_workers_alive" in texto


def test_cobertura_baja_si_los_datos_se_atrasan(engine):
    from operacion.metricas import medir

    e = escenarios.abre_una_vez_y_no_repite_alertas(engine)
    e.siguiente_ronda(3600)
    m = medir(engine, ahora=e.reloj())
    assert m["coverage"]["ratio"] == 0.0 and m["targets"]["coverage_met"] is False


def test_init_db_no_confunde_engines_que_reutilizan_direccion(tmp_path):
    """Un engine nuevo nunca hereda el estado 'migrado' de otro ya liberado."""
    import gc

    from infra import db

    gc.collect()
    antes = len(db._migrados)
    for i in range(30):
        motor = make_engine(f"sqlite:///{(tmp_path / f'base-{i}.db').as_posix()}")
        init_db(motor)
        assert revision_actual(motor) == revision_head()
        motor.dispose()
        del motor
        gc.collect()
    assert len(db._migrados) <= antes  # no retengo engines liberados
