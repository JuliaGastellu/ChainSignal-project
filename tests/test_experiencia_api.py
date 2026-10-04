"""Backend de la experiencia comercial (E06): alta, demo aislada, resumen y evaluación."""

import pytest

from tests.ayudantes_identidad import CONTRASENA_PRUEBA, cliente_anonimo, crear_organizacion, email_unico, iniciar_sesion


@pytest.fixture(autouse=True)
def limites_limpios():
    import api.rutas_org as rutas

    rutas._limite_alta.reiniciar()
    rutas._limite_demo.reiniciar()
    yield


def _alta(cliente, email=None):
    return cliente.post("/auth/signup", json={"email": email or email_unico("alta"), "password": CONTRASENA_PRUEBA,
                                               "organization_name": "Mi equipo"})


def test_alta_apagada_por_defecto():
    assert _alta(cliente_anonimo()).status_code == 404


def test_alta_crea_organizacion_y_sesion(monkeypatch):
    from infra.config import settings

    monkeypatch.setattr(settings, "SIGNUP_ENABLED", True)
    cliente = cliente_anonimo()
    email = email_unico("alta")
    respuesta = _alta(cliente, email)
    assert respuesta.status_code == 201
    datos = respuesta.json()
    assert datos["memberships"][0]["role"] == "owner" and datos["memberships"][0]["organization_name"] == "Mi equipo"
    assert cliente.get("/auth/session").status_code == 200
    assert _alta(cliente_anonimo(), email).status_code == 409


def test_alta_con_limite_por_ip(monkeypatch):
    from infra.config import settings

    monkeypatch.setattr(settings, "SIGNUP_ENABLED", True)
    estados = [_alta(cliente_anonimo()).status_code for _ in range(6)]
    assert estados[:5] == [201] * 5 and estados[5] == 429


@pytest.fixture
def demo():
    cliente = cliente_anonimo()
    respuesta = cliente.post("/demo")
    assert respuesta.status_code == 201
    cliente.headers["X-CSRF-Token"] = cliente.cookies.get("cs_csrf")
    return cliente, respuesta.json()["organization_id"]


def test_demo_completa_con_datos_sinteticos(demo):
    cliente, org_id = demo
    resumen = cliente.get(f"/orgs/{org_id}/summary").json()
    assert resumen["organization"]["is_demo"] is True and resumen["organization"]["expires_at"] is not None
    assert resumen["checklist"] == {"account_added": True, "first_snapshot": True, "policy_created": True,
                                    "channel_verified": True, "incident_reviewed": False}
    assert resumen["active_incidents"] == 1

    cuenta = cliente.get(f"/orgs/{org_id}/accounts").json()["accounts"][0]
    posicion = cliente.get(f"/orgs/{org_id}/accounts/{cuenta['id']}/positions/aave-v3/latest").json()
    assert posicion["synthetic"] is True and posicion["health_factor"].startswith("1.37")
    incidente = cliente.get(f"/orgs/{org_id}/incidents").json()["incidents"][0]
    assert cliente.post(f"/orgs/{org_id}/incidents/{incidente['id']}/acknowledge").status_code == 200
    assert cliente.get(f"/orgs/{org_id}/summary").json()["checklist"]["incident_reviewed"] is True


def test_demo_aislada_de_organizaciones_reales(demo, cliente_owner, organizacion):
    from monitoreo.demo import DIRECCION_DEMO

    cliente, demo_org = demo
    real_org = organizacion[0]
    assert cliente.get(f"/orgs/{real_org}/accounts").status_code == 403
    assert cliente_owner.get(f"/orgs/{demo_org}/accounts").status_code == 403

    # Una organización real que observa la misma dirección no ve los snapshots sintéticos.
    cuenta = cliente_owner.post(f"/orgs/{real_org}/accounts", json={"address": DIRECCION_DEMO}).json()
    assert cliente_owner.get(f"/orgs/{real_org}/accounts/{cuenta['id']}/positions/aave-v3/latest").status_code == 404
    assert cliente_owner.get(f"/orgs/{real_org}/accounts/{cuenta['id']}/positions/aave-v3/snapshots").json()["snapshots"] == []


def test_worker_no_programa_demos(demo):
    from sqlalchemy import select

    from infra.db import get_session_factory, engine
    from infra.db_models import JobRecord
    from monitoreo.worker import WorkerMonitoreo

    _, org_id = demo
    WorkerMonitoreo(lambda: None).programar()
    with get_session_factory(engine)() as s:
        pendientes = s.execute(select(JobRecord).where(JobRecord.organization_id == org_id, JobRecord.status == "pending")).scalars().all()
    assert pendientes == []


def test_demo_vencida_no_da_acceso(demo, monkeypatch):
    import time as reloj

    cliente, org_id = demo
    ahora = reloj.time()
    monkeypatch.setattr("identidad.servicio.time.time", lambda: ahora + 25 * 3600)
    assert cliente.get(f"/orgs/{org_id}/summary").status_code in (401, 403)


def test_evaluar_ahora(cliente_owner, organizacion, demo):
    org_id = organizacion[0]
    cuenta = cliente_owner.post(f"/orgs/{org_id}/accounts", json={"address": "0x" + "5" * 40}).json()
    primera = cliente_owner.post(f"/orgs/{org_id}/accounts/{cuenta['id']}/evaluate").json()
    segunda = cliente_owner.post(f"/orgs/{org_id}/accounts/{cuenta['id']}/evaluate").json()
    assert (primera["status"], segunda["status"]) == ("queued", "already_queued")

    cliente, demo_org = demo
    cuenta_demo = cliente.get(f"/orgs/{demo_org}/accounts").json()["accounts"][0]
    assert cliente.post(f"/orgs/{demo_org}/accounts/{cuenta_demo['id']}/evaluate").json() == {"queued": False, "status": "done"}


def test_resumen_requiere_membresia(cliente_owner, organizacion):
    otra, email = crear_organizacion("Otra")
    assert iniciar_sesion(email).get(f"/orgs/{organizacion[0]}/summary").status_code == 403


def test_replay_prohibido_en_produccion():
    from infra.config import Settings

    with pytest.raises(RuntimeError):
        Settings(APP_ENV="production", AAVE_REPLAY_FIXTURE="tests/datos/x.json").validate()
