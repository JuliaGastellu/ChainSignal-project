"""Pruebas de sesión, CSRF y superficie pública de la API (E02).

La clave global X-API-Key ya no existe: el navegador usa una cookie de sesión
HttpOnly/Secure/SameSite=Lax y las mutaciones exigen el token CSRF atado a esa
sesión. Las rutas globales heredadas responden 410 y las económicas 403.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from tests.ayudantes_identidad import CONTRASENA_PRUEBA, iniciar_sesion

WALLET = "0x00000000000000000000000000000000000000aa"


@pytest.fixture
def anonimo():
    return TestClient(app, base_url="https://testserver")


def test_health_es_publico_y_minimo(anonimo):
    respuesta = anonimo.get("/health")
    assert respuesta.status_code == 200
    assert set(respuesta.json()) == {"status", "service", "version", "mode"}


def test_login_emite_cookie_httponly_secure_samesite(organizacion, anonimo):
    respuesta = anonimo.post("/auth/login", json={"email": organizacion[1], "password": CONTRASENA_PRUEBA})

    assert respuesta.status_code == 200
    cookies = respuesta.headers.get_list("set-cookie")
    sesion = next(c for c in cookies if c.startswith("cs_session="))
    csrf = next(c for c in cookies if c.startswith("cs_csrf="))
    assert "HttpOnly" in sesion and "Secure" in sesion and "SameSite=lax" in sesion
    assert "HttpOnly" not in csrf and "Secure" in csrf
    # El token de sesión nunca vuelve en el cuerpo.
    assert sesion.split(";")[0].split("=", 1)[1] not in respuesta.text


@pytest.mark.parametrize("email,password", [
    ("desconocido@ejemplo.test", CONTRASENA_PRUEBA),
    (None, "contrasena-equivocada-larga"),
    ("no-es-un-email", CONTRASENA_PRUEBA),
])
def test_login_fallido_responde_igual_sin_revelar_la_causa(organizacion, anonimo, email, password):
    respuesta = anonimo.post("/auth/login", json={"email": email or organizacion[1], "password": password})
    assert respuesta.status_code == 401
    assert respuesta.json() == {"error": "not_authenticated", "message": "Invalid email or password."}
    assert "set-cookie" not in respuesta.headers


def test_sin_sesion_las_rutas_privadas_responden_401(organizacion, anonimo):
    org_id = organizacion[0]
    for metodo, ruta in [("GET", "/auth/session"), ("GET", f"/orgs/{org_id}/accounts"),
                         ("GET", f"/orgs/{org_id}/events"), ("GET", f"/report/{WALLET}"),
                         ("GET", f"/run-agent/{WALLET}"), ("POST", f"/orgs/{org_id}/policies")]:
        assert anonimo.request(metodo, ruta, json={} if metodo == "POST" else None).status_code == 401, ruta


def test_cookie_de_sesion_falsificada_responde_401(organizacion):
    cliente = TestClient(app, base_url="https://testserver", cookies={"cs_session": "inventada"})
    assert cliente.get("/auth/session").status_code == 401


def test_mutacion_sin_csrf_o_con_csrf_ajeno_responde_403(cliente_owner, organizacion):
    org_id = organizacion[0]
    cuerpo = {"address": WALLET, "chain_id": 1}

    sin_header = cliente_owner.post(f"/orgs/{org_id}/accounts", json=cuerpo, headers={"X-CSRF-Token": ""})
    assert sin_header.status_code == 403 and sin_header.json()["error"] == "csrf_failed"

    otro = iniciar_sesion(organizacion[1])  # otra sesión del mismo usuario
    ajeno = cliente_owner.post(f"/orgs/{org_id}/accounts", json=cuerpo, headers={"X-CSRF-Token": otro.cookies.get("cs_csrf")})
    assert ajeno.status_code == 403

    valido = cliente_owner.post(f"/orgs/{org_id}/accounts", json=cuerpo)
    assert valido.status_code == 201


def test_mutacion_desde_origen_no_permitido_responde_403(cliente_owner, organizacion):
    respuesta = cliente_owner.post(f"/orgs/{organizacion[0]}/accounts", json={"address": WALLET},
                                   headers={"Origin": "https://atacante.example"})
    assert respuesta.status_code == 403
    assert respuesta.json()["error"] == "origin_not_allowed"


def test_cors_solo_acepta_origenes_configurados(anonimo):
    permitido = anonimo.options("/auth/session", headers={"Origin": "http://localhost:8081", "Access-Control-Request-Method": "GET"})
    ajeno = anonimo.options("/auth/session", headers={"Origin": "https://atacante.example", "Access-Control-Request-Method": "GET"})
    assert permitido.headers.get("access-control-allow-origin") == "http://localhost:8081"
    assert permitido.headers.get("access-control-allow-credentials") == "true"
    assert "access-control-allow-origin" not in ajeno.headers


def test_logout_revoca_la_sesion_aunque_se_reutilice_la_cookie(organizacion):
    cliente = iniciar_sesion(organizacion[1])
    token = cliente.cookies.get("cs_session")
    assert cliente.post("/auth/logout").status_code == 200

    reutilizada = TestClient(app, base_url="https://testserver", cookies={"cs_session": token})
    assert reutilizada.get("/auth/session").status_code == 401
    assert reutilizada.get(f"/orgs/{organizacion[0]}/accounts").status_code == 401


def test_logout_all_revoca_todas_las_sesiones(organizacion):
    a, b = iniciar_sesion(organizacion[1]), iniciar_sesion(organizacion[1])
    assert a.post("/auth/logout-all").json()["revoked_sessions"] == 2
    assert b.get("/auth/session").status_code == 401


def test_sesion_vencida_responde_401(organizacion, monkeypatch):
    import time as reloj

    cliente = iniciar_sesion(organizacion[1])
    ahora = reloj.time()
    monkeypatch.setattr("identidad.servicio.time.time", lambda: ahora + 13 * 3600)
    assert cliente.get("/auth/session").status_code == 401


def test_errores_internos_no_filtran_detalles(cliente_owner, organizacion, monkeypatch):
    from api.sesion import servicio_recursos

    def explotar(*args, **kwargs):
        raise RuntimeError("detalle-secreto postgresql://usuario:clave@host/db")

    monkeypatch.setattr(servicio_recursos(), "listar_cuentas", explotar)
    cliente = TestClient(app, base_url="https://testserver", raise_server_exceptions=False, cookies=cliente_owner.cookies)
    respuesta = cliente.get(f"/orgs/{organizacion[0]}/accounts")
    assert respuesta.status_code == 500
    assert respuesta.json() == {"error": "internal_error", "message": "Internal error."}
    assert "detalle-secreto" not in respuesta.text


@pytest.mark.parametrize("metodo,ruta", [
    ("POST", "/track-wallet"), ("GET", "/agent/watch"), ("POST", "/agent/watch"), ("DELETE", f"/agent/watch/{WALLET}"),
    ("GET", "/agent/radar"), ("GET", "/agent/history"), ("GET", "/agent/actions"), ("GET", "/agent-activity"),
    ("GET", "/agent/state"), ("GET", f"/agent/state/{WALLET}"), ("GET", f"/agent/budget/{WALLET}"),
    ("GET", f"/agent-budget/{WALLET}"), ("GET", "/agent/learning"), ("GET", "/agent/status"), ("GET", "/agent/stream"),
])
def test_rutas_globales_heredadas_responden_410_incluso_con_sesion(cliente_owner, metodo, ruta):
    respuesta = cliente_owner.request(metodo, ruta, json={"wallet": WALLET, "address": WALLET} if metodo == "POST" else None)
    assert respuesta.status_code == 410
    assert respuesta.json()["error"] == "legacy_route_gone"


@pytest.mark.parametrize("ruta", ["/agent/budget", "/fund-agent", "/agent/execute", "/agent/start", "/agent/stop"])
def test_rutas_economicas_siguen_en_403_con_sesion(cliente_owner, ruta):
    respuesta = cliente_owner.post(ruta, json={"wallet": WALLET, "tx_hash": "0x" + "a" * 64})
    assert respuesta.status_code == 403
    assert respuesta.json()["error"] == "economic_route_disabled"
