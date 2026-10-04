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
    # La demo es un recorrido simulado: nunca cuenta como monitoreo preparado.
    assert resumen["readiness"] == {"account_observed": True, "valid_read": True, "policy_enabled": True,
                                    "external_channel_verified": False, "ready": False, "simulated": True,
                                    "configured": False, "issues": {"valid_read": None, "policy_enabled": None,
                                                                    "external_channel_verified": "simulated_only"}}
    assert resumen["practice"] == {"incident_reviewed": False}
    assert resumen["active_incidents"] == 1 and resumen["attention"][0]["kind"] == "incident"

    cuenta = cliente.get(f"/orgs/{org_id}/accounts").json()["accounts"][0]
    posicion = cliente.get(f"/orgs/{org_id}/accounts/{cuenta['id']}/positions/aave-v3/latest").json()
    assert posicion["synthetic"] is True and posicion["health_factor"].startswith("1.37")
    incidente = cliente.get(f"/orgs/{org_id}/incidents").json()["incidents"][0]
    assert cliente.post(f"/orgs/{org_id}/incidents/{incidente['id']}/acknowledge").status_code == 200
    assert cliente.get(f"/orgs/{org_id}/summary").json()["practice"]["incident_reviewed"] is True


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


# --- preparación del monitoreo, atención y práctica ---------------------------------------------


def _webhook_verificado(engine, org_id):
    """Marco un webhook como verificado directamente: la entrega real se prueba en tests/test_webhook.py."""
    import time

    from identidad import seguridad
    from infra.db import get_session_factory
    from infra.db_models import NotificationChannelRecord

    with get_session_factory(engine)() as s:
        s.add(NotificationChannelRecord(id=seguridad.nuevo_id(), organization_id=org_id, kind="webhook", name="Alertas",
                                        config={"url": "https://hooks.ejemplo.test/x", "signing_secret": "s"}, enabled=True,
                                        verified_at=time.time(), created_at=time.time()))
        s.commit()
        return s.query(NotificationChannelRecord.id).filter_by(organization_id=org_id, kind="webhook").scalar()


@pytest.fixture
def webhooks_encendidos(monkeypatch):
    from infra.config import settings

    monkeypatch.setattr(settings, "NOTIFICATIONS_WEBHOOKS_ENABLED", True)
    return settings


def _cuenta_sana_preparada(owner_email=None):
    from infra.db import engine
    from tests import escenarios_monitoreo as escenarios
    from tests.monitoreo_ayudantes import Entorno, escenario_hf

    e = Entorno(engine, escenarios.REGLA_HF)
    e.adaptador.poner(escenario_hf("2.4"))
    e.adaptador.fixture["synthetic"] = False
    e.worker().paso()
    canal = _webhook_verificado(engine, e.org_id)
    owner = iniciar_sesion(e.email)
    assert owner.get(f"/orgs/{e.org_id}/summary").json()["readiness"]["ready"] is True
    return e, owner, canal


def test_preparacion_cae_si_el_dato_deja_de_estar_disponible_y_vuelve(webhooks_encendidos):
    from ingestion_onchain.resultados import Motivo

    e, owner, _ = _cuenta_sana_preparada()
    e.adaptador.falla = Motivo.TIMEOUT
    # El worker reintenta las fallas transitorias; agotados los intentos, la cuenta queda UNAVAILABLE.
    for _ in range(5):
        e.siguiente_ronda(700)
        e.worker().paso()
    r = owner.get(f"/orgs/{e.org_id}/summary").json()["readiness"]
    # El snapshot FRESH anterior sigue en la base, pero no afirma frescura actual.
    assert r["valid_read"] is False and r["ready"] is False
    assert r["configured"] is True and r["issues"]["valid_read"] == "unavailable"
    e.adaptador.falla = None
    e.siguiente_ronda()
    e.worker().paso()
    assert owner.get(f"/orgs/{e.org_id}/summary").json()["readiness"]["ready"] is True


def test_preparacion_cae_si_el_dato_envejece(webhooks_encendidos):
    import time

    from infra.db import engine
    from monitoreo.resumen import resumen

    e, _, _ = _cuenta_sana_preparada()
    assert resumen(e.ctx, engine)["readiness"]["ready"] is True
    # Sin evaluaciones nuevas durante más de dos intervalos (mínimo 15 min), el dato deja de ser vigente.
    r = resumen(e.ctx, engine, ahora=time.time() + 3600)["readiness"]
    assert r["valid_read"] is False and r["issues"]["valid_read"] == "outdated" and r["configured"] is True


def test_preparacion_cae_si_se_apagan_los_envios_o_el_canal(webhooks_encendidos, monkeypatch):
    from infra.db import engine, get_session_factory
    from infra.db_models import NotificationChannelRecord, OutboxRecord

    e, owner, canal = _cuenta_sana_preparada()
    resumen = lambda: owner.get(f"/orgs/{e.org_id}/summary").json()["readiness"]  # noqa: E731

    monkeypatch.setattr(webhooks_encendidos, "NOTIFICATIONS_WEBHOOKS_ENABLED", False)
    r = resumen()
    assert r["external_channel_verified"] is False and r["ready"] is False
    assert r["issues"]["external_channel_verified"] == "webhooks_disabled" and r["configured"] is True
    monkeypatch.setattr(webhooks_encendidos, "NOTIFICATIONS_WEBHOOKS_ENABLED", True)

    with get_session_factory(engine)() as s:
        s.get(NotificationChannelRecord, canal).enabled = False
        s.commit()
    assert resumen()["issues"]["external_channel_verified"] == "channel_disabled"
    with get_session_factory(engine)() as s:
        s.get(NotificationChannelRecord, canal).enabled = True
        # Una entrega posterior a la prueba aceptada falló: ya no afirmo que el circuito funciona.
        s.add(OutboxRecord(organization_id=e.org_id, channel_id=canal, idempotency_key=f"falla-{canal}", payload={"type": "alert"},
                           status="failed", attempts=1, max_attempts=1, available_at=0, created_at=0, last_error="http_503"))
        s.commit()
    r = resumen()
    assert r["ready"] is False and r["issues"]["external_channel_verified"] == "last_delivery_failed"
    with get_session_factory(engine)() as s:
        s.add(OutboxRecord(organization_id=e.org_id, channel_id=canal, idempotency_key=f"ok-{canal}", payload={"type": "channel.test"},
                           status="sent", attempts=1, max_attempts=1, available_at=0, created_at=0, sent_at=0))
        s.commit()
    assert resumen()["ready"] is True


def test_politica_pausada_se_informa(webhooks_encendidos):
    from infra.db import engine, get_session_factory
    from infra.db_models import AlertPolicyRecord

    e, owner, _ = _cuenta_sana_preparada()
    with get_session_factory(engine)() as s:
        s.get(AlertPolicyRecord, e.politica["id"]).enabled = False
        s.commit()
    r = owner.get(f"/orgs/{e.org_id}/summary").json()["readiness"]
    assert r["ready"] is False and r["issues"]["policy_enabled"] == "paused" and r["configured"] is True


def test_cuenta_sana_queda_preparada_sin_incidente(webhooks_encendidos):
    from infra.db import engine
    from tests import escenarios_monitoreo as escenarios
    from tests.monitoreo_ayudantes import Entorno, escenario_hf

    e = Entorno(engine, escenarios.REGLA_HF)
    e.adaptador.poner(escenario_hf("2.4"))  # sana: por encima del umbral
    # Una organización real solo cuenta lecturas reales: marco la fixture como tal en esta prueba.
    e.adaptador.fixture["synthetic"] = False
    e.worker().paso()
    owner = iniciar_sesion(e.email)
    antes = owner.get(f"/orgs/{e.org_id}/summary").json()
    # El sandbox probado no alcanza: hace falta un canal externo verificado.
    assert antes["readiness"]["valid_read"] and antes["readiness"]["policy_enabled"], antes["readiness"]
    assert antes["readiness"]["external_channel_verified"] is False and antes["readiness"]["ready"] is False
    _webhook_verificado(engine, e.org_id)
    despues = owner.get(f"/orgs/{e.org_id}/summary").json()
    assert despues["readiness"]["ready"] is True and despues["active_incidents"] == 0 and despues["attention"] == []
    assert despues["practice"]["incident_reviewed"] is False


def test_atencion_por_severidad_y_datos_no_disponibles():
    from infra.db import engine
    from ingestion_onchain.resultados import Motivo
    from tests import escenarios_monitoreo as escenarios
    from tests.monitoreo_ayudantes import Entorno, escenario_hf

    e = Entorno(engine, escenarios.REGLA_HF, cuentas=2)
    e.adaptador.poner(escenario_hf("1.2", cuentas=2))
    e.worker().paso()
    owner = iniciar_sesion(e.email)
    resumen = owner.get(f"/orgs/{e.org_id}/summary").json()
    incidentes = [a for a in resumen["attention"] if a["kind"] == "incident"]
    assert len(incidentes) == 2 and all(a["observed"]["threshold"] == "1.5" for a in incidentes)

    e.adaptador.falla = Motivo.TIMEOUT  # el proveedor deja de responder
    e.siguiente_ronda()
    for _ in range(4):
        e.siguiente_ronda(700)
        e.worker().paso()
    resumen = owner.get(f"/orgs/{e.org_id}/summary").json()
    # Las cuentas con incidente siguen apareciendo por el incidente, no se duplican como "dato".
    assert {a["kind"] for a in resumen["attention"]} == {"incident"}
    assert resumen["accounts_by_data_quality"].get("UNAVAILABLE") == 2


def test_practica_aislada_no_cuenta_como_preparacion(cliente_owner, organizacion):
    from infra.db import engine
    from infra.db_models import ProductEventRecord
    from sqlalchemy import select
    from infra.db import get_session_factory

    org_real = organizacion[0]
    practica = cliente_owner.post("/practice")
    assert practica.status_code == 201 and practica.json()["created"] is True
    org_practica = practica.json()["organization_id"]
    assert cliente_owner.post("/practice").json() == {**practica.json(), "created": False}  # reutiliza la vigente
    # La misma sesión ve las dos organizaciones; la práctica es simulada y no está preparada.
    membresias = {m["organization_id"] for m in cliente_owner.get("/auth/session").json()["memberships"]}
    assert {org_real, org_practica} <= membresias
    resumen = cliente_owner.get(f"/orgs/{org_practica}/summary").json()
    assert resumen["readiness"]["simulated"] is True and resumen["readiness"]["ready"] is False
    # La organización real no recibe nada de la práctica.
    assert cliente_owner.get(f"/orgs/{org_real}/incidents").json()["incidents"] == []
    with get_session_factory(engine)() as s:
        eventos = s.execute(select(ProductEventRecord).where(ProductEventRecord.organization_id == org_practica)).scalars().all()
    assert eventos and all(ev.is_demo for ev in eventos)  # fuera de la analítica comercial


def test_practica_exige_sesion_y_csrf():
    assert cliente_anonimo().post("/practice").status_code == 401
