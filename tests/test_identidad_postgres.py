"""Garantías de E02 que solo certifico contra PostgreSQL.

Cada prueba usa una base nueva creada en el servidor de
CHAINSIGNAL_TEST_POSTGRES_URL y la borra al terminar. SQLite no demuestra
bloqueos de fila ni aislamiento entre conexiones concurrentes.
"""

import os
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from identidad.recursos import ServicioRecursos
from identidad.servicio import Conflicto, ContextoOrg, NoEncontrado, ServicioIdentidad
from infra.db import init_db, make_engine
from infra.db_models import AlertPolicyRecord

pytestmark = pytest.mark.postgres

URL = os.getenv("CHAINSIGNAL_TEST_POSTGRES_URL", "")
CONTRASENA = "contrasena-sintetica-larga"


@pytest.fixture
def pg_url():
    if not URL:
        pytest.skip("Definí CHAINSIGNAL_TEST_POSTGRES_URL con un PostgreSQL desechable")
    nombre = f"cs_e02_{uuid.uuid4().hex[:12]}"
    admin = create_engine(URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'CREATE DATABASE "{nombre}"'))
    url = URL.rsplit("/", 1)[0] + "/" + nombre
    yield url
    with admin.connect() as c:
        c.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n AND pid <> pg_backend_pid()"), {"n": nombre})
        c.execute(text(f'DROP DATABASE IF EXISTS "{nombre}"'))
    admin.dispose()


@pytest.fixture
def pg_engine(pg_url):
    engine = make_engine(pg_url)
    init_db(engine)
    yield engine
    engine.dispose()


def _cabeza() -> str:
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    raiz = Path(__file__).resolve().parents[1]
    config = Config(str(raiz / "alembic.ini"))
    config.set_main_option("script_location", str(raiz / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


def _org_con_owner(identidad, nombre):
    email = f"{nombre}-{uuid.uuid4().hex[:8]}@ejemplo.test"
    org_id, user_id = identidad.crear_organizacion_con_owner(nombre, email, CONTRASENA)
    with identidad._Session() as s:
        from sqlalchemy import select

        from infra.db_models import MembershipRecord

        m = s.execute(select(MembershipRecord).where(MembershipRecord.organization_id == org_id)).scalar_one()
    return ContextoOrg(org_id, user_id, "owner", m.id), email


def test_migraciones_crean_el_esquema_y_son_idempotentes(pg_url):
    engine = make_engine(pg_url)
    init_db(engine)
    tablas = set(inspect(engine).get_table_names())
    assert {"organizations", "users", "memberships", "invitations", "sessions",
            "monitored_accounts", "alert_policies", "org_events", "execution_plans", "alembic_version",
            "chain_transactions", "ingestion_checkpoints", "position_snapshots", "position_snapshot_assets"} <= tablas
    with engine.connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == _cabeza()
    # Un segundo engine (otro proceso) no rompe nada.
    otro = make_engine(pg_url)
    init_db(otro)
    otro.dispose()
    engine.dispose()


def test_linea_base_acepta_una_base_creada_con_create_all(pg_url):
    """Bases anteriores a Alembic tenían las tablas heredadas sin alembic_version."""
    from infra.db import Base
    import infra.db_models  # noqa: F401

    engine = make_engine(pg_url)
    heredadas = [Base.metadata.tables[n] for n in ("execution_plans", "execution_plan_events", "executions",
                                                   "agent_budgets", "budget_consumptions", "processed_funding_txs")]
    Base.metadata.create_all(engine, tables=heredadas)
    with engine.begin() as c:
        c.execute(text("INSERT INTO executions (id, timestamp, cycle, wallet, status) VALUES ('x', 't', 1, '0xabc', 'failed')"))

    init_db(engine)

    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM executions")).scalar_one() == 1
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == _cabeza()
    engine.dispose()


def test_la_base_impide_politica_con_cuenta_de_otra_org(pg_engine):
    identidad, recursos = ServicioIdentidad(pg_engine), ServicioRecursos(pg_engine)
    ctx_a, _ = _org_con_owner(identidad, "a")
    ctx_b, _ = _org_con_owner(identidad, "b")
    cuenta_b = recursos.crear_cuenta(ctx_b, "0x" + "b" * 40)

    # Salteo el servicio a propósito: aun con un error de código, la clave
    # foránea compuesta rechaza la referencia cruzada.
    with identidad._Session() as s:
        s.add(AlertPolicyRecord(id=uuid.uuid4().hex, organization_id=ctx_a.organization_id, account_id=cuenta_b["id"],
                                name="cruzada", rule={"metric": "m", "operator": "lt", "threshold": 1}, enabled=True,
                                created_at=time.time(), updated_at=time.time()))
        with pytest.raises(IntegrityError):
            s.commit()


def test_degradar_dos_owners_a_la_vez_deja_al_menos_uno(pg_engine, monkeypatch):
    identidad = ServicioIdentidad(pg_engine)
    ctx_1, _ = _org_con_owner(identidad, "owners")
    invitacion, token = identidad.invitar(ctx_1, f"segundo-{uuid.uuid4().hex[:6]}@ejemplo.test", "owner")
    user_2, _, _ = identidad.aceptar_invitacion(token, None, CONTRASENA)
    miembros = {m["user_id"]: m["membership_id"] for m in identidad.listar_miembros(ctx_1)}
    ctx_2 = ContextoOrg(ctx_1.organization_id, user_2, "owner", miembros[user_2])

    # Ensancho la ventana entre leer los owners y escribir el nuevo rol, para
    # que sin bloqueo de filas ambos hilos vieran dos owners y degradaran.
    original = identidad._membresia_de_org

    def con_pausa(*args, **kwargs):
        membresia = original(*args, **kwargs)
        time.sleep(0.5)
        return membresia

    monkeypatch.setattr(identidad, "_membresia_de_org", con_pausa)

    barrera = threading.Barrier(2)
    resultados = []

    def degradar(ctx, objetivo):
        barrera.wait()
        try:
            identidad.cambiar_rol(ctx, objetivo, "viewer")
            resultados.append("ok")
        except Conflicto:
            resultados.append("conflicto")

    hilos = [threading.Thread(target=degradar, args=(ctx_1, miembros[user_2])),
             threading.Thread(target=degradar, args=(ctx_2, miembros[ctx_1.user_id]))]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert sorted(resultados) == ["conflicto", "ok"]
    assert identidad.contar_owners(ctx_1.organization_id) == 1


def test_aceptar_la_misma_invitacion_en_paralelo_crea_una_sola_membresia(pg_engine):
    identidad = ServicioIdentidad(pg_engine)
    ctx, _ = _org_con_owner(identidad, "paralelo")
    _, token = identidad.invitar(ctx, f"invitada-{uuid.uuid4().hex[:6]}@ejemplo.test", "viewer")

    barrera = threading.Barrier(4)
    resultados = []

    def aceptar():
        barrera.wait()
        try:
            identidad.aceptar_invitacion(token, None, CONTRASENA)
            resultados.append("ok")
        except (NoEncontrado, Conflicto):
            resultados.append("rechazada")

    hilos = [threading.Thread(target=aceptar) for _ in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert resultados.count("ok") == 1
    assert len(identidad.listar_miembros(ctx)) == 2
