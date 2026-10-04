"""Aislamiento entre organizaciones y autorización por rol (E02).

Armo dos organizaciones con cuentas, políticas y eventos, y pruebo IDs y
filtros manipulados, cuerpos con organization_id, cursores SSE ajenos, cambios
de rol, sesiones revocadas, viewers que intentan mutar y el worker que procesa
cuentas de ambas. La autorización tiene que cumplirse también en servicios,
jobs y eventos, no solo en las rutas.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from identidad.servicio import ContextoOrg, Prohibido
from tests.ayudantes_identidad import crear_organizacion, iniciar_sesion, sumar_miembro

DIR_A = "0x00000000000000000000000000000000000000a1"
DIR_B = "0x00000000000000000000000000000000000000b1"
REGLA = {"metric": "health_factor", "operator": "lt", "threshold": 1.2}


@pytest.fixture
def dos_orgs():
    """Organización A y B, cada una con su owner, una cuenta y una política."""
    datos = {}
    for nombre, direccion in (("a", DIR_A), ("b", DIR_B)):
        org_id, email = crear_organizacion(f"Org {nombre}")
        owner = iniciar_sesion(email)
        cuenta = owner.post(f"/orgs/{org_id}/accounts", json={"address": direccion, "chain_id": 1}).json()
        politica = owner.post(f"/orgs/{org_id}/policies", json={"name": "HF bajo", "rule": REGLA, "account_id": cuenta["id"]}).json()
        datos[nombre] = {"org": org_id, "owner": owner, "email": email, "cuenta": cuenta["id"], "politica": politica["id"]}
    return datos


# --- IDs y filtros manipulados ------------------------------------------------


def test_no_miembro_recibe_403_en_toda_ruta_de_otra_org(dos_orgs):
    a, b = dos_orgs["a"]["owner"], dos_orgs["b"]
    for metodo, ruta in [
        ("GET", f"/orgs/{b['org']}/accounts"), ("GET", f"/orgs/{b['org']}/accounts/{b['cuenta']}"),
        ("GET", f"/orgs/{b['org']}/policies"), ("GET", f"/orgs/{b['org']}/members"),
        ("GET", f"/orgs/{b['org']}/events"), ("GET", f"/orgs/{b['org']}/events/stream"),
        ("GET", f"/orgs/{b['org']}/accounts/{b['cuenta']}/analysis"),
        ("PATCH", f"/orgs/{b['org']}/policies/{b['politica']}"), ("DELETE", f"/orgs/{b['org']}/accounts/{b['cuenta']}"),
        ("POST", f"/orgs/{b['org']}/invitations"),
    ]:
        respuesta = a.request(metodo, ruta, json={"name": "x"} if metodo in {"PATCH", "POST"} else None)
        assert respuesta.status_code == 403, (metodo, ruta, respuesta.status_code)


def test_id_de_recurso_ajeno_bajo_mi_org_responde_404_y_no_lo_modifica(dos_orgs):
    a, b = dos_orgs["a"], dos_orgs["b"]
    cliente = a["owner"]
    assert cliente.get(f"/orgs/{a['org']}/accounts/{b['cuenta']}").status_code == 404
    assert cliente.patch(f"/orgs/{a['org']}/accounts/{b['cuenta']}", json={"label": "robada"}).status_code == 404
    assert cliente.delete(f"/orgs/{a['org']}/accounts/{b['cuenta']}").status_code == 404
    assert cliente.patch(f"/orgs/{a['org']}/policies/{b['politica']}", json={"enabled": False}).status_code == 404
    assert cliente.delete(f"/orgs/{a['org']}/policies/{b['politica']}").status_code == 404
    assert cliente.get(f"/orgs/{a['org']}/accounts/{b['cuenta']}/analysis").status_code == 404

    # B sigue intacta.
    propia = b["owner"].get(f"/orgs/{b['org']}/accounts/{b['cuenta']}").json()
    assert propia["label"] is None
    assert b["owner"].get(f"/orgs/{b['org']}/policies").json()["policies"][0]["enabled"] is True


def test_filtros_manipulados_en_query_no_amplian_el_alcance(dos_orgs):
    a, b = dos_orgs["a"], dos_orgs["b"]
    respuesta = a["owner"].get(f"/orgs/{a['org']}/accounts", params={"organization_id": b["org"], "org_id": b["org"]})
    direcciones = [c["address"] for c in respuesta.json()["accounts"]]
    assert direcciones == [DIR_A]
    politicas = a["owner"].get(f"/orgs/{a['org']}/policies", params={"organization_id": b["org"]}).json()["policies"]
    assert [p["id"] for p in politicas] == [a["politica"]]


def test_organization_id_en_el_cuerpo_se_rechaza_con_422(dos_orgs):
    a, b = dos_orgs["a"], dos_orgs["b"]
    cuerpo = {"address": "0x" + "c" * 40, "organization_id": b["org"]}
    assert a["owner"].post(f"/orgs/{a['org']}/accounts", json=cuerpo).status_code == 422
    assert a["owner"].post(f"/orgs/{a['org']}/policies", json={"name": "x", "rule": REGLA, "organization_id": b["org"]}).status_code == 422


def test_politica_no_puede_referenciar_cuenta_de_otra_org(dos_orgs):
    a, b = dos_orgs["a"], dos_orgs["b"]
    creada = a["owner"].post(f"/orgs/{a['org']}/policies", json={"name": "cruzada", "rule": REGLA, "account_id": b["cuenta"]})
    assert creada.status_code == 404
    reasignada = a["owner"].patch(f"/orgs/{a['org']}/policies/{a['politica']}", json={"account_id": b["cuenta"]})
    assert reasignada.status_code == 404


# --- Roles --------------------------------------------------------------------


def test_viewer_lee_pero_no_puede_mutar_politicas_ni_cuentas(dos_orgs):
    a = dos_orgs["a"]
    viewer, _ = sumar_miembro(a["org"], a["owner"], "viewer")

    assert viewer.get(f"/orgs/{a['org']}/policies").status_code == 200
    assert viewer.get(f"/orgs/{a['org']}/accounts").status_code == 200
    for metodo, ruta, cuerpo in [
        ("POST", f"/orgs/{a['org']}/policies", {"name": "x", "rule": REGLA}),
        ("PATCH", f"/orgs/{a['org']}/policies/{a['politica']}", {"enabled": False}),
        ("DELETE", f"/orgs/{a['org']}/policies/{a['politica']}", None),
        ("POST", f"/orgs/{a['org']}/accounts", {"address": "0x" + "d" * 40}),
        ("DELETE", f"/orgs/{a['org']}/accounts/{a['cuenta']}", None),
        ("POST", f"/orgs/{a['org']}/invitations", {"email": "x@ejemplo.test", "role": "owner"}),
        ("GET", f"/orgs/{a['org']}/invitations", None),
    ]:
        respuesta = viewer.request(metodo, ruta, json=cuerpo)
        assert respuesta.status_code == 403, (metodo, ruta)
    assert a["owner"].get(f"/orgs/{a['org']}/policies").json()["policies"][0]["enabled"] is True


def test_operator_muta_recursos_pero_no_administra_miembros(dos_orgs):
    a = dos_orgs["a"]
    operator, _ = sumar_miembro(a["org"], a["owner"], "operator")
    assert operator.patch(f"/orgs/{a['org']}/policies/{a['politica']}", json={"enabled": False}).status_code == 200
    assert operator.post(f"/orgs/{a['org']}/invitations", json={"email": "y@ejemplo.test", "role": "viewer"}).status_code == 403
    miembros = operator.get(f"/orgs/{a['org']}/members").json()["members"]
    owner = next(m for m in miembros if m["role"] == "owner")
    assert operator.patch(f"/orgs/{a['org']}/members/{owner['membership_id']}", json={"role": "viewer"}).status_code == 403


def test_cambio_de_rol_aplica_a_la_sesion_ya_abierta(dos_orgs):
    a = dos_orgs["a"]
    operator, email = sumar_miembro(a["org"], a["owner"], "operator")
    assert operator.post(f"/orgs/{a['org']}/accounts", json={"address": "0x" + "e" * 40}).status_code == 201

    miembro = next(m for m in a["owner"].get(f"/orgs/{a['org']}/members").json()["members"] if m["email"] == email)
    assert a["owner"].patch(f"/orgs/{a['org']}/members/{miembro['membership_id']}", json={"role": "viewer"}).status_code == 200
    assert operator.post(f"/orgs/{a['org']}/accounts", json={"address": "0x" + "f" * 40}).status_code == 403

    assert a["owner"].delete(f"/orgs/{a['org']}/members/{miembro['membership_id']}").status_code == 204
    assert operator.get(f"/orgs/{a['org']}/accounts").status_code == 403


def test_la_org_siempre_conserva_un_owner(dos_orgs):
    a = dos_orgs["a"]
    miembros = a["owner"].get(f"/orgs/{a['org']}/members").json()["members"]
    unico = miembros[0]
    assert a["owner"].patch(f"/orgs/{a['org']}/members/{unico['membership_id']}", json={"role": "viewer"}).status_code == 409
    assert a["owner"].delete(f"/orgs/{a['org']}/members/{unico['membership_id']}").status_code == 409


def test_membresia_de_otra_org_no_se_puede_tocar_desde_la_mia(dos_orgs):
    a, b = dos_orgs["a"], dos_orgs["b"]
    owner_b = b["owner"].get(f"/orgs/{b['org']}/members").json()["members"][0]
    assert a["owner"].patch(f"/orgs/{a['org']}/members/{owner_b['membership_id']}", json={"role": "viewer"}).status_code == 404
    assert a["owner"].delete(f"/orgs/{a['org']}/members/{owner_b['membership_id']}").status_code == 404


def test_servicio_exige_rol_aunque_lo_llame_sin_ruta(dos_orgs):
    """La autorización no depende solo de la ruta: el servicio también verifica."""
    from api.sesion import servicio_recursos

    a = dos_orgs["a"]
    ctx_viewer = ContextoOrg(a["org"], "usuario-cualquiera", "viewer", "m")
    with pytest.raises(Prohibido):
        servicio_recursos().crear_politica(ctx_viewer, "x", REGLA)
    with pytest.raises(Prohibido):
        servicio_recursos().eliminar_cuenta(ctx_viewer, a["cuenta"])


# --- Invitaciones ---------------------------------------------------------------


def test_invitacion_es_de_un_solo_uso_y_no_se_vuelve_a_mostrar(dos_orgs):
    from tests.ayudantes_identidad import CONTRASENA_PRUEBA, cliente_anonimo, email_unico

    a = dos_orgs["a"]
    invitacion = a["owner"].post(f"/orgs/{a['org']}/invitations", json={"email": email_unico("inv"), "role": "viewer"}).json()
    token = invitacion["token"]
    listado = a["owner"].get(f"/orgs/{a['org']}/invitations")
    assert token not in listado.text

    assert cliente_anonimo().post("/invitations/accept", json={"token": token, "password": CONTRASENA_PRUEBA}).status_code == 200
    assert cliente_anonimo().post("/invitations/accept", json={"token": token, "password": CONTRASENA_PRUEBA}).status_code == 404


def test_invitacion_revocada_o_vencida_no_se_acepta(dos_orgs, monkeypatch):
    import time as reloj

    from tests.ayudantes_identidad import CONTRASENA_PRUEBA, cliente_anonimo, email_unico

    a = dos_orgs["a"]
    revocada = a["owner"].post(f"/orgs/{a['org']}/invitations", json={"email": email_unico("rev"), "role": "viewer"}).json()
    assert a["owner"].delete(f"/orgs/{a['org']}/invitations/{revocada['id']}").status_code == 204
    assert cliente_anonimo().post("/invitations/accept", json={"token": revocada["token"], "password": CONTRASENA_PRUEBA}).status_code == 404

    vencida = a["owner"].post(f"/orgs/{a['org']}/invitations", json={"email": email_unico("ven"), "role": "viewer"}).json()
    ahora = reloj.time()
    monkeypatch.setattr("identidad.servicio.time.time", lambda: ahora + 73 * 3600)
    assert cliente_anonimo().post("/invitations/accept", json={"token": vencida["token"], "password": CONTRASENA_PRUEBA}).status_code == 404


def test_invitacion_para_otro_email_no_la_acepta_una_sesion_distinta(dos_orgs):
    a, b = dos_orgs["a"], dos_orgs["b"]
    invitacion = a["owner"].post(f"/orgs/{a['org']}/invitations", json={"email": "otra-persona@ejemplo.test", "role": "owner"}).json()
    respuesta = b["owner"].post("/invitations/accept", json={"token": invitacion["token"]})
    assert respuesta.status_code == 403
    assert b["owner"].get(f"/orgs/{a['org']}/accounts").status_code == 403


def test_invitacion_a_email_existente_exige_iniciar_sesion(dos_orgs):
    from tests.ayudantes_identidad import CONTRASENA_PRUEBA, cliente_anonimo

    a, b = dos_orgs["a"], dos_orgs["b"]
    invitacion = a["owner"].post(f"/orgs/{a['org']}/invitations", json={"email": b["email"], "role": "viewer"}).json()
    # Sin sesión no puedo tomar la identidad de una persona ya registrada.
    assert cliente_anonimo().post("/invitations/accept", json={"token": invitacion["token"], "password": CONTRASENA_PRUEBA}).status_code == 401
    # Con su propia sesión, sí.
    assert b["owner"].post("/invitations/accept", json={"token": invitacion["token"]}).status_code == 200
    assert b["owner"].get(f"/orgs/{a['org']}/accounts").status_code == 200


# --- Eventos y SSE --------------------------------------------------------------


def test_eventos_solo_de_mi_org_y_cursor_ajeno_responde_404(dos_orgs):
    a, b = dos_orgs["a"], dos_orgs["b"]
    eventos_a = a["owner"].get(f"/orgs/{a['org']}/events").json()["events"]
    eventos_b = b["owner"].get(f"/orgs/{b['org']}/events").json()["events"]
    assert eventos_a and eventos_b
    assert {e["id"] for e in eventos_a}.isdisjoint({e["id"] for e in eventos_b})
    assert all(DIR_B not in str(e["payload"]) for e in eventos_a)

    cursor_ajeno = eventos_b[-1]["id"]
    assert a["owner"].get(f"/orgs/{a['org']}/events", params={"cursor": cursor_ajeno}).status_code == 404
    assert a["owner"].get(f"/orgs/{a['org']}/events/stream", params={"cursor": cursor_ajeno}).status_code == 404
    assert a["owner"].get(f"/orgs/{a['org']}/events/stream", headers={"Last-Event-ID": str(cursor_ajeno)}).status_code == 404
    assert a["owner"].get(f"/orgs/{a['org']}/events", params={"cursor": 10**12}).status_code == 404

    propio = eventos_a[0]["id"]
    siguientes = a["owner"].get(f"/orgs/{a['org']}/events", params={"cursor": propio}).json()["events"]
    assert all(e["id"] > propio for e in siguientes)


def test_eventos_no_incluyen_tokens_ni_hashes(dos_orgs):
    a = dos_orgs["a"]
    invitacion = a["owner"].post(f"/orgs/{a['org']}/invitations", json={"email": "z@ejemplo.test", "role": "viewer"}).json()
    texto = a["owner"].get(f"/orgs/{a['org']}/events").text
    assert invitacion["token"] not in texto
    assert "token_hash" not in texto and "password" not in texto


def _stream(sesion, ctx, cursor):
    from api.rutas_org import generar_stream_eventos

    return generar_stream_eventos(sesion, ctx, cursor, intervalo=0)


def _sesion_y_ctx(cliente, org_id):
    from api.sesion import servicio_identidad

    sesion = servicio_identidad().sesion_por_token(cliente.cookies.get("cs_session"))
    return sesion, servicio_identidad().contexto(sesion, org_id, "viewer")


def test_stream_entrega_solo_eventos_propios_y_cierra_al_revocar_la_sesion(dos_orgs):
    from api.sesion import servicio_identidad

    a, b = dos_orgs["a"], dos_orgs["b"]
    sesion, ctx = _sesion_y_ctx(a["owner"], a["org"])

    async def escenario():
        stream = _stream(sesion, ctx, 0)
        mensajes = [await stream.__anext__() for _ in range(3)]
        b["owner"].post(f"/orgs/{b['org']}/accounts", json={"address": "0x" + "9" * 40})
        servicio_identidad().revocar_sesion(sesion.session_id)
        resto = [m async for m in stream]
        return mensajes, resto

    mensajes, resto = asyncio.run(escenario())
    texto = "".join(mensajes + resto)
    assert "account.created" in texto and DIR_A in texto
    assert DIR_B not in texto and "0x" + "9" * 40 not in texto
    assert resto[-1].startswith("event: session_ended")


def test_stream_cierra_si_me_quitan_de_la_org(dos_orgs):
    a = dos_orgs["a"]
    viewer, email = sumar_miembro(a["org"], a["owner"], "viewer")
    sesion, ctx = _sesion_y_ctx(viewer, a["org"])
    miembro = next(m for m in a["owner"].get(f"/orgs/{a['org']}/members").json()["members"] if m["email"] == email)

    async def escenario():
        stream = _stream(sesion, ctx, 0)
        await stream.__anext__()
        a["owner"].delete(f"/orgs/{a['org']}/members/{miembro['membership_id']}")
        return [m async for m in stream]

    resto = asyncio.run(escenario())
    assert resto[-1].startswith("event: session_ended")


# --- Worker y análisis por cuenta -------------------------------------------------


def test_worker_escribe_cada_resultado_en_su_org(dos_orgs):
    from agent_loop import AutonomousAgentLoop
    from api.sesion import servicio_recursos

    a, b = dos_orgs["a"], dos_orgs["b"]
    servicio = AsyncMock()
    servicio.run_pipeline_core.side_effect = lambda direccion: {
        "agent_decision": {"decision": "MONITOR"}, "scores": {"risk": {"value": 11 if direccion == DIR_A else 22}},
    }
    monitor = AutonomousAgentLoop(servicio, servicio_recursos())
    resultados = asyncio.run(monitor.run_once())

    assert resultados[a["cuenta"]]["risk_score"] == 11 and resultados[b["cuenta"]]["risk_score"] == 22
    assert a["owner"].get(f"/orgs/{a['org']}/accounts/{a['cuenta']}").json()["last_risk_score"] == 11
    assert b["owner"].get(f"/orgs/{b['org']}/accounts/{b['cuenta']}").json()["last_risk_score"] == 22
    eventos_a = [e for e in a["owner"].get(f"/orgs/{a['org']}/events").json()["events"] if e["type"] == "account.analyzed"]
    assert [e["payload"]["account_id"] for e in eventos_a] == [a["cuenta"]]


def test_job_no_escribe_si_la_cuenta_no_es_de_esa_org(dos_orgs):
    from api.sesion import servicio_recursos

    a, b = dos_orgs["a"], dos_orgs["b"]
    assert servicio_recursos().registrar_evaluacion(a["org"], b["cuenta"], "BLOCK", 99, "analyzed") is False
    assert b["owner"].get(f"/orgs/{b['org']}/accounts/{b['cuenta']}").json()["last_risk_score"] is None


def test_analisis_por_cuenta_usa_la_direccion_de_mi_org(dos_orgs, monkeypatch):
    import api.main as api_main

    a = dos_orgs["a"]
    pipeline = AsyncMock(return_value={"agent_decision": {"decision": "MONITOR"}})
    monkeypatch.setattr(api_main._agent_service, "run_pipeline_core", pipeline)
    respuesta = a["owner"].get(f"/orgs/{a['org']}/accounts/{a['cuenta']}/analysis")
    assert respuesta.status_code == 200
    pipeline.assert_awaited_once_with(DIR_A)
    assert respuesta.json()["read_only"] is True
