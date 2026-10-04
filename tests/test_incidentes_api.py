"""API de incidentes, canales y eventos (E05), con autorización por organización."""

import asyncio

import pytest

from infra.db import engine as engine_por_defecto
from infra.db_models import JobRecord
from tests import escenarios_monitoreo as escenarios
from tests.ayudantes_identidad import cliente_anonimo, crear_organizacion, iniciar_sesion, sumar_miembro


@pytest.fixture
def con_incidente():
    """Un incidente abierto en la base por defecto, visible para la API."""
    e = escenarios.abre_una_vez_y_no_repite_alertas(engine_por_defecto)
    owner = iniciar_sesion(e.email)
    incidente = owner.get(f"/orgs/{e.org_id}/incidents").json()["incidents"][0]
    return e, owner, incidente


def test_detalle_muestra_condicion_bloque_evidencia_y_entregas(con_incidente):
    e, owner, incidente = con_incidente
    detalle = owner.get(f"/orgs/{e.org_id}/incidents/{incidente['id']}").json()

    assert detalle["status"] == "open" and detalle["severity"] == "high" and detalle["policy_version"] == 1
    assert detalle["last_observed"]["threshold"] == "1.5"
    assert detalle["evidence"][0]["kind"] == "opening" and detalle["evidence"][0]["block_number"] == 20_000_000
    assert detalle["alerts"][0]["kind"] == "opened"
    assert detalle["deliveries"][0]["status"] == "sent"
    assert "probability" not in str(detalle) and "confidence" not in str(detalle)


def test_ciclo_de_vida_con_roles(con_incidente):
    e, owner, incidente = con_incidente
    base = f"/orgs/{e.org_id}/incidents/{incidente['id']}"
    viewer, _ = sumar_miembro(e.org_id, owner, "viewer")
    operator, _ = sumar_miembro(e.org_id, owner, "operator")

    assert viewer.get(base).status_code == 200
    assert viewer.post(f"{base}/acknowledge").status_code == 403
    assert viewer.post(f"{base}/resolve", json={"note": "x"}).status_code == 403

    assert operator.post(f"{base}/acknowledge").status_code == 200
    assert operator.post(f"{base}/acknowledge").status_code == 409
    assert operator.post(f"{base}/resolve", json={"note": ""}).status_code == 422
    resuelto = operator.post(f"{base}/resolve", json={"note": "Repagué parte de la deuda."})
    assert resuelto.status_code == 200 and resuelto.json()["resolution"] == "manual"
    assert operator.post(f"{base}/resolve", json={"note": "otra vez"}).status_code == 409

    detalle = owner.get(base).json()
    assert [a["kind"] for a in detalle["alerts"]] == ["opened", "resolved"]
    assert detalle["acknowledged_by_user_id"] is not None and detalle["resolution_note"] == "Repagué parte de la deuda."


def test_correccion_trazable_sin_editar_la_original(con_incidente):
    e, owner, incidente = con_incidente
    base = f"/orgs/{e.org_id}/incidents/{incidente['id']}"
    original = owner.get(base).json()["evidence"][0]

    correccion = owner.post(f"{base}/corrections", json={"evidence_id": original["id"], "note": "El umbral estaba mal cargado."})
    assert correccion.status_code == 201 and correccion.json()["corrects_evidence_id"] == original["id"]
    assert owner.post(f"{base}/corrections", json={"evidence_id": 10**9, "note": "x"}).status_code == 404
    evidencias = owner.get(base).json()["evidence"]
    assert evidencias[0] == original and len(evidencias) == 2


def test_otra_organizacion_no_ve_ni_toca_incidentes(con_incidente):
    e, owner, incidente = con_incidente
    otra_org, email = crear_organizacion("Otra")
    ajeno = iniciar_sesion(email)
    assert ajeno.get(f"/orgs/{e.org_id}/incidents").status_code == 403
    assert ajeno.get(f"/orgs/{otra_org}/incidents/{incidente['id']}").status_code == 404
    assert ajeno.post(f"/orgs/{otra_org}/incidents/{incidente['id']}/acknowledge").status_code == 404
    assert ajeno.get(f"/orgs/{otra_org}/incidents").json()["incidents"] == []


def test_canales(cliente_owner, organizacion):
    org_id = organizacion[0]
    operator, _ = sumar_miembro(org_id, cliente_owner, "operator")
    assert operator.post(f"/orgs/{org_id}/channels", json={"kind": "sandbox", "name": "x"}).status_code == 403
    assert cliente_owner.post(f"/orgs/{org_id}/channels", json={"kind": "webhook", "name": "w", "config": {"url": "http://inseguro.test/x"}}).status_code == 422
    webhook = cliente_owner.post(f"/orgs/{org_id}/channels", json={"kind": "webhook", "name": "w", "config": {"url": "https://hooks.ejemplo.test/t/SECRETO"}}).json()
    assert webhook["config"] == {"host": "hooks.ejemplo.test"} and "SECRETO" not in str(cliente_owner.get(f"/orgs/{org_id}/channels").json())

    sandbox = cliente_owner.post(f"/orgs/{org_id}/channels", json={"kind": "sandbox", "name": "Canal de prueba"}).json()
    prueba = operator.post(f"/orgs/{org_id}/channels/{sandbox['id']}/test")
    # El sandbox no sale del sistema: la prueba se entrega en el momento y verifica el canal.
    assert prueba.status_code == 202 and prueba.json()["status"] == "sent"
    entregas = cliente_owner.get(f"/orgs/{org_id}/channels/{sandbox['id']}/deliveries").json()["deliveries"]
    assert entregas[0]["status"] == "sent" and entregas[0]["payload_type"] == "channel.test"
    canales = {c["id"]: c for c in cliente_owner.get(f"/orgs/{org_id}/channels").json()["channels"]}
    assert canales[sandbox["id"]]["verified_at"] is not None and canales[webhook["id"]]["verified_at"] is None


def test_webhook_deshabilitado_no_envia(cliente_owner, organizacion):
    from monitoreo.notificaciones import ServicioNotificaciones

    org_id = organizacion[0]
    canal = cliente_owner.post(f"/orgs/{org_id}/channels", json={"kind": "webhook", "name": "w", "config": {"url": "https://hooks.ejemplo.test/x"}}).json()
    cliente_owner.post(f"/orgs/{org_id}/channels/{canal['id']}/test")
    servicio = ServicioNotificaciones()
    estados = []
    while (estado := servicio.entregar_uno("w-api")) is not None:
        estados.append(estado)
    assert "failed" in estados
    entrega = cliente_owner.get(f"/orgs/{org_id}/channels/{canal['id']}/deliveries").json()["deliveries"][0]
    assert entrega["status"] == "failed" and "disabled" in entrega["last_error"]


def test_limite_de_streams_por_organizacion(cliente_owner, organizacion, monkeypatch):
    import api.rutas_org as rutas
    from infra.config import settings

    org_id = organizacion[0]
    monkeypatch.setattr(settings, "MAX_EVENT_STREAMS_PER_ORG", 1)
    assert rutas._reservar_stream(org_id) is True  # un stream ya abierto
    try:
        respuesta = cliente_owner.get(f"/orgs/{org_id}/events/stream")
        assert respuesta.status_code == 429 and respuesta.json()["error"] == "too_many_streams"
    finally:
        rutas._soltar_stream(org_id)


def test_reanudar_sse_no_dispara_analisis_ni_escritura(con_incidente):
    from sqlalchemy import func, select

    from api.rutas_org import generar_stream_eventos
    from api.sesion import servicio_identidad
    from infra.db import get_session_factory

    e, owner, _ = con_incidente
    eventos = owner.get(f"/orgs/{e.org_id}/events").json()["events"]
    medio = eventos[len(eventos) // 2]["id"]
    sesion = servicio_identidad().sesion_por_token(owner.cookies.get("cs_session"))
    ctx = servicio_identidad().contexto(sesion, e.org_id, "viewer")
    lecturas_antes = e.adaptador.lecturas
    with get_session_factory(engine_por_defecto)() as s:
        jobs_antes = s.execute(select(func.count()).select_from(JobRecord)).scalar_one()

    async def reanudar():
        stream = generar_stream_eventos(sesion, ctx, medio, intervalo=0)
        recibidos = []
        async for parte in stream:
            if parte.startswith("id: "):
                recibidos.append(int(parte.split("\n")[0][4:]))
            if len(recibidos) == len([x for x in eventos if x["id"] > medio]):
                break
        await stream.aclose()
        return recibidos

    recibidos = asyncio.run(reanudar())
    assert recibidos == [x["id"] for x in eventos if x["id"] > medio]
    assert e.adaptador.lecturas == lecturas_antes
    with get_session_factory(engine_por_defecto)() as s:
        assert s.execute(select(func.count()).select_from(JobRecord)).scalar_one() == jobs_antes


def test_incidentes_exigen_sesion():
    assert cliente_anonimo().get("/orgs/cualquiera/incidents").status_code == 401
