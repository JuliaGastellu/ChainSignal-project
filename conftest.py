"""Aislamiento común para la suite de pytest.

Este archivo se carga antes de que pytest importe cualquier módulo del
proyecto. Lo uso para que las pruebas unitarias:

- nunca lean mi .env real (CHAINSIGNAL_DISABLE_DOTENV=1);
- usen variables sintéticas, sin claves ni seeds reales;
- escriban todo estado relativo (tracking.json, watched_wallets.json,
  storage/, cache/) en un directorio temporal y no en el repositorio;
- no abran conexiones de red fuera de localhost;
- no arranquen los loops autónomos de la API al usar TestClient.

Las pruebas marcadas `integration` son manuales y piden doble opt-in:
`CHAINSIGNAL_RUN_INTEGRATION=1 pytest -m integration`. En ese modo no piso el
entorno ni bloqueo la red, porque necesitan servicios reales.
"""

import os
import socket
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import pytest

_DIRECTORIO_SESION = Path(tempfile.mkdtemp(prefix="chainsignal-tests-"))

# Valores sintéticos: ninguno es una credencial real. Piso cualquier valor que
# venga del shell para que la suite sea determinística.
_ENTORNO_SINTETICO = {
    "CHAINSIGNAL_DISABLE_DOTENV": "1",
    "APP_ENV": "test",
    "DATABASE_URL": f"sqlite:///{(_DIRECTORIO_SESION / 'sesion.db').as_posix()}",
    # Fuerzo cookies Secure: los clientes de prueba usan https://testserver.
    "SESSION_COOKIE_SECURE": "true",
    "WDK_SERVICE_TOKEN": "token-sintetico-de-prueba",
    "SAFE_WALLET_ADDRESS": "0x1111111111111111111111111111111111111111",
    # Puerto 9 (discard) en loopback: la verificación inicial del WDK falla
    # rápido y el código cae en su modo sin servicio.
    "WDK_URL": "http://127.0.0.1:9",
    "SEPOLIA_RPC_URL": "",
    "CHAIN_ID": "1",
    "ETHEREUM_RPC_URL": "",
    "ETHERSCAN_API_KEY": "",
    "OPENAI_API_KEY": "",
    "AGENT_SEED_PHRASE": "",
    "AGENT_DEMO_MODE": "false",
    "ENABLE_CACHE": "false",
}
MODO_INTEGRACION = os.getenv("CHAINSIGNAL_RUN_INTEGRATION", "") == "1"

_RAIZ = Path(__file__).resolve().parent
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

if not MODO_INTEGRACION:
    os.environ.update(_ENTORNO_SINTETICO)
    # Sin CHAINSIGNAL_MODE en el entorno, las pruebas ven el modo por defecto
    # (READ_ONLY) y no el que tenga configurado mi shell.
    os.environ.pop("CHAINSIGNAL_MODE", None)


def pytest_sessionstart(session):
    # Cambio de directorio después de que pytest resolvió testpaths y antes de
    # importar los módulos de prueba: así las rutas relativas del código
    # heredado (que escriben estado al importarse) no tocan el repositorio.
    if not MODO_INTEGRACION:
        os.chdir(_DIRECTORIO_SESION)

_HOSTS_LOCALES = {"127.0.0.1", "::1", "localhost"}
_URL_POSTGRES_PRUEBA = os.getenv("CHAINSIGNAL_TEST_POSTGRES_URL", "")
if _URL_POSTGRES_PRUEBA:
    _host_postgres = urlparse(_URL_POSTGRES_PRUEBA).hostname
    if _host_postgres:
        _HOSTS_LOCALES.add(_host_postgres)


def pytest_collection_modifyitems(config, items):
    if MODO_INTEGRACION:
        return
    omitir = pytest.mark.skip(reason="integración manual: definí CHAINSIGNAL_RUN_INTEGRATION=1")
    for item in items:
        if item.get_closest_marker("integration"):
            item.add_marker(omitir)


class RedBloqueadaEnPrueba(RuntimeError):
    """La lanzo cuando una prueba unitaria intenta salir a la red."""


def _host_de(direccion):
    if isinstance(direccion, tuple) and direccion:
        return str(direccion[0])
    return None


@pytest.fixture(autouse=True)
def _sin_red_externa(request, monkeypatch):
    if request.node.get_closest_marker("integration"):
        yield
        return

    connect_original = socket.socket.connect
    connect_ex_original = socket.socket.connect_ex
    getaddrinfo_original = socket.getaddrinfo

    def _verificar(host):
        if host is not None and host not in _HOSTS_LOCALES:
            raise RedBloqueadaEnPrueba(f"Bloqueé una conexión externa en una prueba unitaria: {host}")

    def connect(sock, direccion):
        _verificar(_host_de(direccion))
        return connect_original(sock, direccion)

    def connect_ex(sock, direccion):
        _verificar(_host_de(direccion))
        return connect_ex_original(sock, direccion)

    def getaddrinfo(host, *args, **kwargs):
        _verificar(host if isinstance(host, str) else None)
        return getaddrinfo_original(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    yield


@pytest.fixture(autouse=True)
def _directorio_por_prueba(request, tmp_path, monkeypatch):
    """Cada prueba corre en su propio directorio temporal."""
    if request.node.get_closest_marker("integration"):
        monkeypatch.chdir(_RAIZ)
    else:
        monkeypatch.chdir(tmp_path)
    yield


@pytest.fixture(autouse=True)
def _sin_loops_autonomos(monkeypatch):
    """Evito que el lifespan de la API arranque loops en segundo plano."""
    api_main = sys.modules.get("api.main")
    if api_main is None:
        yield
        return

    async def _no_iniciar():
        return None

    for nombre in ("_agent_loop", "_guardian_loop"):  # ya no existen desde E01; queda como red de seguridad
        loop = getattr(api_main, nombre, None)
        if loop is not None:
            monkeypatch.setattr(loop, "start", _no_iniciar)
    yield


@pytest.fixture
def modo_experimental(monkeypatch):
    """Habilito TESTNET_EXPERIMENT solo para una prueba (APP_ENV sigue en test)."""
    from infra.config import settings

    monkeypatch.setattr(settings, "CHAINSIGNAL_MODE", "TESTNET_EXPERIMENT")
    yield


# --- Fixtures de identidad para pruebas de API (E02) ---------------------------


@pytest.fixture
def organizacion():
    """Creo una organización con su owner y devuelvo (org_id, email_owner)."""
    from tests.ayudantes_identidad import crear_organizacion

    return crear_organizacion()


@pytest.fixture
def cliente_owner(organizacion):
    from tests.ayudantes_identidad import iniciar_sesion

    return iniciar_sesion(organizacion[1])
