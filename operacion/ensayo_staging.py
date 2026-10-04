"""Ensayo del piloto en un staging local aislado (E08).

    python -m operacion.ensayo_staging [--conservar]

Levanto deploy/compose.piloto.yml + deploy/compose.ensayo.yml con dos réplicas
de la API y pruebo, contra la topología real:

1. migración como paso aparte y arranque con el esquema verificado;
2. flujo de producto a través de TLS y nginx (alta, cuenta, política, canal, incidente);
   después, HTTPS: cookies Secure/HttpOnly/SameSite y HSTS, y una entrega de
   webhook a un receptor HTTPS controlado dentro de la red del compose, con la
   firma presente y sin el secreto en los logs;
3. varias réplicas de la API sirviendo la misma sesión;
4. reinicio de API y worker, y worker matado con un job tomado (lease);
5. proveedor caído: el dato queda UNAVAILABLE, la API sigue lista y el
   incidente no se cierra por falta de datos;
6. respaldo, pérdida total del volumen de la base y restauración, con
   comparación de huellas y login posterior.

Uso secretos aleatorios de un solo uso que no imprimo, certificados
autofirmados de un día, ningún RPC real y ninguna red externa salvo la descarga
de imágenes y paquetes del build. Al
final bajo todo y borro los volúmenes, salvo con --conservar.
"""

import argparse
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

import requests

from operacion import respaldo
from operacion.receptor_prueba import generar_certificado

RAIZ = Path(__file__).resolve().parents[1]
PROYECTO = "chainsignal-ensayo"
ARCHIVOS = [str(RAIZ / "deploy" / "compose.piloto.yml"), str(RAIZ / "deploy" / "compose.ensayo.yml")]
WEB = "https://localhost:8443"
DIRECCION_FIXTURE = "0x4246c44B2171F4f6cB6626bc19e5B977a6Be8C3F"
RESULTADO = RAIZ / "docs" / "ensayos" / "ensayo-piloto.json"


class Ensayo:
    def __init__(self) -> None:
        self.certs = Path(tempfile.mkdtemp(prefix="chainsignal-certs-"))
        tls = generar_certificado(self.certs, "localhost", "tls")
        if tls is None or generar_certificado(self.certs, "receptor", "receptor") is None:
            raise SystemExit("El ensayo necesita openssl para generar los certificados de prueba.")
        self.ca_tls = str(tls[0])
        self.env = {**os.environ, "PILOTO_DB_PASSWORD": secrets.token_urlsafe(24), "METRICS_TOKEN": secrets.token_urlsafe(24),
                    "PUBLIC_ORIGIN": WEB, "APP_ENV": "staging", "CHAINSIGNAL_VERSION": "ensayo", "ENSAYO_CERTS": str(self.certs)}
        self.resultados: Dict[str, Any] = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "steps": {}}
        self.http = self.sesion_nueva()

    # --- utilidades --------------------------------------------------------------

    def dc(self, *args: str, capturar: bool = True, extra_env: Dict[str, str] | None = None) -> str:
        env = {**self.env, **(extra_env or {})}
        salida = subprocess.run(respaldo._compose(PROYECTO, ARCHIVOS) + list(args), env=env, check=True,
                                capture_output=capturar, text=True)
        return salida.stdout if capturar else ""

    def contenedores(self, servicio: str) -> List[str]:
        return [c for c in self.dc("ps", "-q", servicio).split() if c]

    def esperar(self, condicion: Callable[[], bool], segundos: float, descripcion: str) -> float:
        inicio = time.monotonic()
        while time.monotonic() - inicio < segundos:
            try:
                if condicion():
                    return round(time.monotonic() - inicio, 2)
            except (requests.RequestException, ValueError, KeyError):
                pass
            time.sleep(1)
        raise AssertionError(f"timeout esperando: {descripcion}")

    def paso(self, nombre: str, funcion: Callable[[], Dict[str, Any]]) -> None:
        inicio = time.monotonic()
        print(f"== {nombre}", flush=True)
        try:
            datos = funcion()
            self.resultados["steps"][nombre] = {"ok": True, "seconds": round(time.monotonic() - inicio, 2), **datos}
        except Exception as error:
            self.resultados["steps"][nombre] = {"ok": False, "seconds": round(time.monotonic() - inicio, 2),
                                                "error": f"{type(error).__name__}: {str(error)[:300]}"}
            raise
        print(f"   ok en {self.resultados['steps'][nombre]['seconds']} s", flush=True)

    def sesion_nueva(self) -> requests.Session:
        sesion = requests.Session()
        sesion.headers["Origin"] = WEB
        sesion.verify = self.ca_tls
        return sesion

    def csrf(self) -> Dict[str, str]:
        return {"X-CSRF-Token": self.http.cookies.get("cs_csrf", "")}

    def api(self, metodo: str, ruta: str, **kwargs) -> requests.Response:
        if metodo != "GET":
            kwargs.setdefault("headers", {}).update(self.csrf())
        return self.http.request(metodo, f"{WEB}{ruta}", timeout=30, **kwargs)

    def metricas(self) -> Dict[str, Any]:
        api = self.contenedores("api")[0]
        salida = subprocess.run(["docker", "exec", api, "python", "-m", "operacion.metricas"], check=True, capture_output=True,
                                text=True, env=self.env)
        return json.loads(salida.stdout)

    def incidentes(self, estado: str = "active") -> List[Dict[str, Any]]:
        return self.api("GET", f"/orgs/{self.org}/incidents?status={estado}").json()["incidents"]

    def cuenta_calidad(self) -> str:
        return self.api("GET", f"/orgs/{self.org}/accounts").json()["accounts"][0]["last_data_quality"]

    # --- pasos ---------------------------------------------------------------------

    def levantar(self) -> Dict[str, Any]:
        self.dc("up", "-d", "--build", "--scale", "api=2", "--wait", "--wait-timeout", "300", capturar=False)
        migrate = self.dc("ps", "-a", "--format", "{{.Service}} {{.State}} {{.ExitCode}}", "migrate").strip()
        apis = self.contenedores("api")
        assert len(apis) == 2, apis
        assert "exited 0" in migrate, migrate
        version = respaldo._psql(PROYECTO, ARCHIVOS, "SELECT version_num FROM alembic_version", self.env)
        ready = requests.get(f"{WEB}/ready", timeout=10, verify=self.ca_tls).json()
        return {"api_replicas": len(apis), "migrate": migrate, "alembic_version": version, "ready": ready}

    def flujo(self) -> Dict[str, Any]:
        self.email = f"ensayo-{secrets.token_hex(4)}@ejemplo.test"
        self.password = secrets.token_urlsafe(18)
        alta = self.api("POST", "/auth/signup", json={"email": self.email, "password": self.password, "organization_name": "Ensayo"})
        assert alta.status_code == 201, alta.status_code
        self.org = alta.json()["organization_id"]
        cuenta = self.api("POST", f"/orgs/{self.org}/accounts", json={"address": DIRECCION_FIXTURE, "label": "Fixture"}).json()
        self.cuenta = cuenta["id"]
        posicion = self.api("GET", f"/orgs/{self.org}/accounts/{self.cuenta}/positions/aave-v3").json()
        assert posicion["data_quality"]["status"] == "FRESH", posicion["data_quality"]
        assert self.api("POST", f"/orgs/{self.org}/policies", json={"name": "HF", "rule": {"type": "health_factor_below", "threshold": "1.5"}}).status_code == 201
        canal = self.api("POST", f"/orgs/{self.org}/channels", json={"kind": "sandbox", "name": "Sandbox"}).json()
        assert self.api("POST", f"/orgs/{self.org}/channels/{canal['id']}/test").json()["status"] == "sent"
        self.api("POST", f"/orgs/{self.org}/accounts/{self.cuenta}/evaluate")
        espera = self.esperar(lambda: len(self.incidentes()) == 1, 90, "incidente abierto por el worker")
        m = self.metricas()
        return {"health_factor": posicion["health_factor"], "incident_wait_seconds": espera,
                "detection_latency_seconds": m["detection_latency_seconds"], "delivery_latency_seconds": m["delivery"]["latency_seconds"],
                "coverage": m["coverage"], "workers": m["workers"]}

    def https_y_entrega_externa(self) -> Dict[str, Any]:
        # Cookies y encabezados tal como los ve un navegador detrás de TLS.
        login = self.sesion_nueva().post(f"{WEB}/auth/login", json={"email": self.email, "password": self.password}, timeout=30)
        assert login.status_code == 200, login.status_code
        cookies = {c.split("=", 1)[0]: c.lower() for c in login.raw.headers.getlist("Set-Cookie")}
        sesion, csrf = cookies["cs_session"], cookies["cs_csrf"]
        assert "secure" in sesion and "httponly" in sesion and "samesite=lax" in sesion, "cookie de sesión sin Secure/HttpOnly/SameSite"
        assert "secure" in csrf and "httponly" not in csrf, "cookie CSRF mal configurada"
        hsts = requests.get(f"{WEB}/", timeout=10, verify=self.ca_tls).headers.get("Strict-Transport-Security", "")
        assert "max-age=" in hsts, "falta HSTS"
        # Sin la CA de prueba, la conexión no se acepta.
        try:
            requests.get(f"{WEB}/health", timeout=10)
            raise AssertionError("aceptó un certificado no confiable")
        except requests.exceptions.SSLError:
            pass

        # Entrega externa controlada: aceptada, fallida y destino privado rechazado.
        canal = self.api("POST", f"/orgs/{self.org}/channels",
                         json={"kind": "webhook", "name": "Receptor de ensayo", "config": {"url": "https://receptor:9443/hooks/ensayo"}})
        assert canal.status_code == 201, canal.status_code
        secreto = canal.json()["signing_secret"]
        prueba = self.api("POST", f"/orgs/{self.org}/channels/{canal.json()['id']}/test").json()
        assert prueba["outcome"] == "accepted_by_destination", prueba
        falla = self.api("POST", f"/orgs/{self.org}/channels",
                         json={"kind": "webhook", "name": "Receptor que falla", "config": {"url": "https://receptor:9443/hooks/falla"}}).json()
        prueba_falla = self.api("POST", f"/orgs/{self.org}/channels/{falla['id']}/test").json()
        assert prueba_falla["outcome"] == "failed" and prueba_falla["error"] == "http_500", prueba_falla
        privado = self.api("POST", f"/orgs/{self.org}/channels",
                           json={"kind": "webhook", "name": "Privado", "config": {"url": "https://db/x"}})
        assert privado.status_code == 422, privado.status_code
        llegadas = [json.loads(l) for l in self.dc("exec", "-T", "receptor", "cat", "/tmp/llegadas.jsonl").splitlines() if l.strip()]
        aceptadas = [l for l in llegadas if l["path"] == "/hooks/ensayo"]
        assert aceptadas and aceptadas[-1]["signature"], llegadas
        firma = dict(p.split("=", 1) for p in aceptadas[-1]["signature"].split(","))
        assert set(firma) == {"t", "v1"} and len(firma["v1"]) == 64, firma
        assert secreto not in self.dc("logs", "--no-color", "api", "worker"), "el secreto de firma apareció en los logs"
        return {"cookie_session": "Secure; HttpOnly; SameSite=Lax", "cookie_csrf": "Secure; SameSite=Lax", "hsts": hsts,
                "untrusted_certificate_rejected": True, "webhook_test_outcome": prueba["outcome"],
                "webhook_failure_error": prueba_falla["error"], "private_destination_rejected": True,
                "receiver_arrivals": len(llegadas), "signature_header_present": True, "secret_absent_from_logs": True}

    def replicas(self) -> Dict[str, Any]:
        antes = {c: self._requests_atendidos(c) for c in self.contenedores("api")}
        for _ in range(40):
            assert self.api("GET", f"/orgs/{self.org}/summary").status_code == 200
        despues = {c: self._requests_atendidos(c) for c in self.contenedores("api")}
        atendidos = {c[:12]: despues[c] - antes[c] for c in despues}
        assert all(n > 0 for n in atendidos.values()), atendidos
        return {"requests_per_replica": atendidos}

    def _requests_atendidos(self, contenedor: str) -> int:
        logs = subprocess.run(["docker", "logs", contenedor], capture_output=True, text=True, env=self.env)
        return (logs.stdout + logs.stderr).count("/summary HTTP/1.1\" 200")

    def reinicio(self) -> Dict[str, Any]:
        self.dc("restart", "api", "worker", capturar=False)
        espera_api = self.esperar(lambda: requests.get(f"{WEB}/ready", timeout=5, verify=self.ca_tls).status_code == 200, 120, "API lista tras reinicio")
        assert self.api("GET", "/auth/session").status_code == 200  # la sesión vive en la base
        # Crash con un job tomado: con el worker detenido dejo un job "running" de un worker
        # muerto, con lease vigente (WORKER_LEASE_SECONDS=15). Al volver, el worker no debe
        # tomarlo antes de que venza el lease, y después tiene que completarlo una sola vez.
        self.dc("kill", "worker", capturar=False)
        self.api("POST", f"/orgs/{self.org}/accounts/{self.cuenta}/evaluate")
        respaldo._psql(PROYECTO, ARCHIVOS, "UPDATE jobs SET status='running', attempts=attempts+1, lease_owner='worker-muerto', "
                                           "lease_expires_at=extract(epoch from now()) + 15 WHERE status='pending'", self.env)
        tomado_en = time.monotonic()
        self.dc("up", "-d", "--no-deps", "worker", capturar=False)
        espera_jobs = self.esperar(lambda: respaldo._psql(PROYECTO, ARCHIVOS, "SELECT count(*) FROM jobs WHERE status IN ('pending','running')",
                                                          self.env) == "0", 120, "job recuperado tras vencer el lease")
        recuperado = round(time.monotonic() - tomado_en, 2)
        assert recuperado >= 12, f"el job se completó antes de vencer el lease ({recuperado} s)"
        dueno = respaldo._psql(PROYECTO, ARCHIVOS, "SELECT lease_owner IS NULL AND status = 'done' FROM jobs ORDER BY id DESC LIMIT 1", self.env)
        activos = self.incidentes()
        assert len(activos) == 1, len(activos)  # sin duplicados
        return {"api_ready_after_restart_seconds": espera_api, "lease_seconds": 15,
                "job_recovered_after_seconds": recuperado, "last_job_done": dueno == "t",
                "active_incidents": len(activos), "jobs": self.metricas()["jobs"]["by_status"]}

    def proveedor_caido(self) -> Dict[str, Any]:
        caido = {"ENSAYO_FIXTURE": "", "ENSAYO_RPC_URL": "http://127.0.0.1:9"}
        self.dc("up", "-d", "--no-deps", "--force-recreate", "worker", capturar=False, extra_env=caido)
        self.api("POST", f"/orgs/{self.org}/accounts/{self.cuenta}/evaluate")
        espera = self.esperar(lambda: self.cuenta_calidad() == "UNAVAILABLE", 120, "dato UNAVAILABLE con el proveedor caído")
        m = self.metricas()
        assert requests.get(f"{WEB}/ready", timeout=5, verify=self.ca_tls).status_code == 200
        activos = self.incidentes()
        assert len(activos) == 1 and activos[0]["status"] == "open", activos  # no se cierra por falta de datos
        self.dc("up", "-d", "--no-deps", "--force-recreate", "worker", capturar=False)
        self.api("POST", f"/orgs/{self.org}/accounts/{self.cuenta}/evaluate")
        recuperado = self.esperar(lambda: self.cuenta_calidad() == "FRESH", 120, "dato FRESH tras volver el proveedor")
        return {"unavailable_after_seconds": espera, "recovered_after_seconds": recuperado,
                "provider_not_fresh_24h": m["provider"]["not_fresh_24h"], "job_errors_24h": m["jobs"]["errors_24h"],
                "api_ready_during_outage": True, "incident_still_open": True}

    def respaldo_y_restauracion(self) -> Dict[str, Any]:
        destino = Path(tempfile.mkdtemp(prefix="chainsignal-respaldo-")) / "piloto.dump"
        antes = respaldo.huella(PROYECTO, ARCHIVOS, self.env)
        copia = respaldo.respaldar(PROYECTO, ARCHIVOS, destino, self.env)
        inicio = time.monotonic()
        # Desastre: pierdo el contenedor y el volumen de la base.
        self.dc("stop", "api", "worker", "web", capturar=False)
        self.dc("rm", "-sf", "db", capturar=False)
        subprocess.run(["docker", "volume", "rm", f"{PROYECTO}_piloto_pgdata"], check=True, capture_output=True, env=self.env)
        self.dc("up", "-d", "--wait", "db", capturar=False)
        restaurada = respaldo.restaurar(PROYECTO, ARCHIVOS, destino, self.env)
        self.dc("up", "-d", "--scale", "api=2", "--wait", "--wait-timeout", "300", capturar=False)
        rto = round(time.monotonic() - inicio, 2)
        despues = respaldo.huella(PROYECTO, ARCHIVOS, self.env)
        assert antes == despues, {k: (antes[k], despues.get(k)) for k in antes if antes[k] != despues.get(k)}
        self.http = self.sesion_nueva()
        login = self.api("POST", "/auth/login", json={"email": self.email, "password": self.password})
        assert login.status_code == 200, login.status_code
        assert len(self.incidentes()) == 1
        return {"dump": {"seconds": copia["seconds"], "bytes": copia["bytes"]}, "restore_seconds": restaurada["seconds"],
                "recovery_seconds_measured": rto, "fingerprint_equal": True, "tables_compared": len(antes) - 1,
                "alembic_version": despues["alembic_version"], "login_after_restore": True}

    def bajar(self, conservar: bool) -> None:
        if not conservar:
            self.dc("down", "-v", "--remove-orphans", capturar=False)

    def correr(self, conservar: bool) -> int:
        codigo = 0
        try:
            for nombre, funcion in (("levantar", self.levantar), ("flujo", self.flujo),
                                    ("https_y_entrega_externa", self.https_y_entrega_externa), ("replicas", self.replicas),
                                    ("reinicio", self.reinicio), ("proveedor_caido", self.proveedor_caido),
                                    ("respaldo_y_restauracion", self.respaldo_y_restauracion)):
                self.paso(nombre, funcion)
        except Exception as error:
            print(f"   FALLÓ: {type(error).__name__}: {str(error)[:300]}", flush=True)
            codigo = 1
        finally:
            self.resultados["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            RESULTADO.parent.mkdir(parents=True, exist_ok=True)
            RESULTADO.write_text(json.dumps(self.resultados, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            self.bajar(conservar)
        return codigo


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--conservar", action="store_true", help="no bajo el entorno al terminar")
    return Ensayo().correr(parser.parse_args().conservar)


if __name__ == "__main__":
    sys.exit(main())
