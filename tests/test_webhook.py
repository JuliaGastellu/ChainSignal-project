"""Webhook externo con protección contra SSRF, firma y entrega controlada.

La entrega real la valido contra un receptor HTTPS local con un certificado
generado en el momento (openssl). No salgo a internet ni envío datos de clientes.
"""

import hashlib
import hmac
import http.server
import json
import shutil
import socket
import ssl
import subprocess
import threading

import pytest

from monitoreo import webhook_seguro as w


def _resolvedor(*ips):
    def resolver(host, puerto, type=None):
        return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, puerto)) for ip in ips]
    return resolver


# --- validación de la URL y SSRF -----------------------------------------------------


@pytest.mark.parametrize("url, codigo", [
    ("http://hooks.ejemplo.test/x", "https_required"),
    ("https://usuario:clave@hooks.ejemplo.test/x", "credentials_in_url"),
    ("https://hooks.ejemplo.test:8443/x", "port_not_allowed"),
    ("https:///sin-host", "invalid_url"),
    ("https://" + "a" * 600 + ".test/", "invalid_url"),
    ("ftp://hooks.ejemplo.test/", "https_required"),
])
def test_url_invalida(url, codigo):
    with pytest.raises(w.DestinoNoPermitido) as error:
        w.validar_url(url)
    assert str(error.value) == codigo


@pytest.mark.parametrize("ips", [
    ("127.0.0.1",), ("10.0.0.5",), ("192.168.1.10",), ("172.16.0.1",), ("169.254.169.254",), ("::1",),
    ("fd00::1",), ("0.0.0.0",), ("100.64.0.1",), ("224.0.0.1",), ("::ffff:10.0.0.1",),
    ("93.184.216.34", "10.0.0.5"),  # una pública y una privada: rechazo todo
])
def test_destinos_no_publicos_se_rechazan(ips):
    with pytest.raises(w.DestinoNoPermitido) as error:
        w.resolver("https://hooks.ejemplo.test/x", _resolvedor(*ips))
    assert str(error.value) == "destination_not_public"


def test_destino_publico_se_acepta_y_dns_fallido_es_error_claro():
    destino = w.resolver("https://hooks.ejemplo.test/ruta?x=1", _resolvedor("93.184.216.34"))
    assert destino.ips == ("93.184.216.34",) and destino.ruta == "/ruta?x=1" and not destino.de_prueba

    def falla(*args, **kwargs):
        raise socket.gaierror("no existe")

    with pytest.raises(w.DestinoNoPermitido) as error:
        w.resolver("https://no-existe.ejemplo.test/x", falla)
    assert str(error.value) == "dns_error"


def test_destinos_de_prueba_solo_si_se_configuran(monkeypatch):
    from infra.config import Settings, settings

    with pytest.raises(w.DestinoNoPermitido):
        w.resolver("https://localhost:9443/x", _resolvedor("127.0.0.1"))
    monkeypatch.setattr(settings, "WEBHOOK_TEST_ALLOWED_TARGETS", "localhost:9443")
    assert w.resolver("https://localhost:9443/x", _resolvedor("127.0.0.1")).de_prueba
    with pytest.raises(RuntimeError):
        Settings(APP_ENV="production", DATABASE_URL="postgresql+psycopg2://u:p@db/cs", DB_AUTO_MIGRATE=False,
                 CORS_ALLOWED_ORIGINS="https://app.ejemplo.test", SAFE_WALLET_ADDRESS="", WDK_SERVICE_TOKEN="",
                 WEBHOOK_TEST_ALLOWED_TARGETS="localhost:9443").validate()


# --- entrega real contra un receptor HTTPS local ------------------------------------------


@pytest.fixture
def receptor(tmp_path, monkeypatch):
    if shutil.which("openssl") is None:
        pytest.skip("openssl no está disponible para generar el certificado de prueba")
    cert, clave = tmp_path / "cert.pem", tmp_path / "clave.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=localhost",
                    "-addext", "subjectAltName=DNS:localhost", "-keyout", str(clave), "-out", str(cert)],
                   check=True, capture_output=True)
    recibidos = []
    respuesta = {"codigo": 200, "ubicacion": None}

    class Manejador(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            cuerpo = self.rfile.read(int(self.headers["Content-Length"]))
            recibidos.append({"ruta": self.path, "cabeceras": dict(self.headers), "cuerpo": cuerpo})
            self.send_response(respuesta["codigo"])
            if respuesta["ubicacion"]:
                self.send_header("Location", respuesta["ubicacion"])
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            pass

    servidor = http.server.HTTPServer(("127.0.0.1", 0), Manejador)
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.load_cert_chain(str(cert), str(clave))
    servidor.socket = contexto.wrap_socket(servidor.socket, server_side=True)
    puerto = servidor.server_address[1]
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    from infra.config import settings

    monkeypatch.setattr(settings, "WEBHOOK_TEST_ALLOWED_TARGETS", f"localhost:{puerto}")
    monkeypatch.setattr(settings, "WEBHOOK_CA_BUNDLE", str(cert))
    yield {"url": f"https://localhost:{puerto}/hooks/TOKEN-SECRETO", "recibidos": recibidos, "respuesta": respuesta}
    servidor.shutdown()


def test_entrega_firmada_al_receptor(receptor):
    codigo = w.enviar(receptor["url"], {"type": "channel.test"}, "clave-1", "secreto-del-canal", timeout=5)
    assert codigo == 200
    llegada = receptor["recibidos"][0]
    assert llegada["ruta"] == "/hooks/TOKEN-SECRETO" and llegada["cabeceras"]["Idempotency-Key"] == "clave-1"
    firma = dict(p.split("=", 1) for p in llegada["cabeceras"]["X-ChainSignal-Signature"].split(","))
    esperada = hmac.new(b"secreto-del-canal", f"{firma['t']}.".encode() + llegada["cuerpo"], hashlib.sha256).hexdigest()
    assert hmac.compare_digest(firma["v1"], esperada)
    assert json.loads(llegada["cuerpo"]) == {"type": "channel.test"}


def test_redireccion_no_se_sigue_y_errores_por_codigo(receptor):
    from infra.db_models import NotificationChannelRecord
    from infra.config import settings
    from monitoreo.notificaciones import ErrorEntrega, TransporteWebhook

    canal = NotificationChannelRecord(id="c1", organization_id="o1", kind="webhook", name="w",
                                      config={"url": receptor["url"], "signing_secret": "s"}, enabled=True, created_at=0)
    transporte = TransporteWebhook(timeout=5)
    settings_previo = settings.NOTIFICATIONS_WEBHOOKS_ENABLED
    settings.NOTIFICATIONS_WEBHOOKS_ENABLED = True
    try:
        receptor["respuesta"].update(codigo=302, ubicacion="https://169.254.169.254/latest/meta-data")
        with pytest.raises(ErrorEntrega) as error:
            transporte.enviar(canal, {"type": "x"}, "k")
        assert str(error.value) == "redirect_not_followed_302" and not error.value.reintentable
        assert len(receptor["recibidos"]) == 1  # no siguió la redirección
        receptor["respuesta"].update(codigo=503, ubicacion=None)
        with pytest.raises(ErrorEntrega) as error:
            transporte.enviar(canal, {"type": "x"}, "k")
        assert str(error.value) == "http_503" and error.value.reintentable
        receptor["respuesta"]["codigo"] = 404
        with pytest.raises(ErrorEntrega) as error:
            transporte.enviar(canal, {"type": "x"}, "k")
        assert str(error.value) == "http_404" and not error.value.reintentable
    finally:
        settings.NOTIFICATIONS_WEBHOOKS_ENABLED = settings_previo


def test_certificado_no_confiable_es_tls_error(receptor, monkeypatch):
    from infra.config import settings

    monkeypatch.setattr(settings, "WEBHOOK_CA_BUNDLE", "")  # sin la CA de prueba, el certificado no es confiable
    with pytest.raises(w.ErrorDeRed) as error:
        w.enviar(receptor["url"], {"type": "x"}, "k", "s", timeout=5)
    assert str(error.value) == "tls_error" and "TOKEN-SECRETO" not in str(error.value)


# --- API: roles, flag, secreto y organización -----------------------------------------------


def test_api_webhook_apagado_explica_y_no_cambia_a_sandbox(cliente_owner, organizacion):
    org = organizacion[0]
    listado = cliente_owner.get(f"/orgs/{org}/channels").json()
    assert listado["webhooks_enabled"] is False
    respuesta = cliente_owner.post(f"/orgs/{org}/channels", json={"kind": "webhook", "name": "w", "config": {"url": "https://hooks.ejemplo.test/x"}})
    assert respuesta.status_code == 409 and respuesta.json()["error"] == "webhooks_disabled"
    assert cliente_owner.get(f"/orgs/{org}/channels").json()["channels"] == []  # no creó un sandbox en su lugar


def test_api_webhook_habilitado_con_roles_y_secreto_una_vez(cliente_owner, organizacion, monkeypatch, receptor, caplog):
    from infra.config import settings
    from tests.ayudantes_identidad import crear_organizacion, iniciar_sesion, sumar_miembro

    monkeypatch.setattr(settings, "NOTIFICATIONS_WEBHOOKS_ENABLED", True)
    org = organizacion[0]
    operador, _ = sumar_miembro(org, cliente_owner, "operator")
    lector, _ = sumar_miembro(org, cliente_owner, "viewer")
    cuerpo = {"kind": "webhook", "name": "Alertas", "config": {"url": receptor["url"]}}
    assert operador.post(f"/orgs/{org}/channels", json=cuerpo).status_code == 403
    malo = cliente_owner.post(f"/orgs/{org}/channels", json={**cuerpo, "config": {"url": "https://127.0.0.1/x"}})
    assert malo.status_code == 422 and malo.json()["error"] == "webhook_destination_invalid"

    creado = cliente_owner.post(f"/orgs/{org}/channels", json=cuerpo)
    assert creado.status_code == 201 and len(creado.json()["signing_secret"]) >= 32
    listado = json.dumps(cliente_owner.get(f"/orgs/{org}/channels").json())
    assert "signing_secret" not in listado and "TOKEN-SECRETO" not in listado

    canal = creado.json()["id"]
    assert lector.post(f"/orgs/{org}/channels/{canal}/test").status_code == 403
    prueba = operador.post(f"/orgs/{org}/channels/{canal}/test").json()
    assert (prueba["kind"], prueba["outcome"]) == ("webhook", "accepted_by_destination")
    # El destino recibió la prueba firmada con el secreto que se mostró una vez.
    llegada = receptor["recibidos"][-1]
    firma = dict(p.split("=", 1) for p in llegada["cabeceras"]["X-ChainSignal-Signature"].split(","))
    assert hmac.compare_digest(firma["v1"], hmac.new(creado.json()["signing_secret"].encode(),
                                                     f"{firma['t']}.".encode() + llegada["cuerpo"], hashlib.sha256).hexdigest())

    # Falla del destino: resultado y error útiles, sin la URL en el registro.
    receptor["respuesta"]["codigo"] = 500
    fallida = operador.post(f"/orgs/{org}/channels/{canal}/test").json()
    assert (fallida["outcome"], fallida["error"]) == ("failed", "http_500")
    assert "TOKEN-SECRETO" not in caplog.text

    _, email = crear_organizacion("Otra")
    ajeno = iniciar_sesion(email)
    assert ajeno.post(f"/orgs/{org}/channels/{canal}/test").status_code == 403


def test_sandbox_dice_que_simulo(cliente_owner, organizacion):
    org = organizacion[0]
    canal = cliente_owner.post(f"/orgs/{org}/channels", json={"kind": "sandbox", "name": "Prueba"}).json()
    prueba = cliente_owner.post(f"/orgs/{org}/channels/{canal['id']}/test").json()
    assert (prueba["kind"], prueba["outcome"]) == ("sandbox", "simulated")
    canales = cliente_owner.get(f"/orgs/{org}/channels").json()["channels"]
    assert canales[0]["last_test"]["outcome"] == "simulated"
