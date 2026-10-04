"""Envío de webhooks a destinos externos con protección contra SSRF.

Un webhook lo configura una persona de la organización: la URL es un dato no
confiable que hace que mi servidor salga a la red. Por eso:

- solo acepto https al puerto 443, sin usuario ni contraseña en la URL;
- resuelvo el nombre y exijo que todas las direcciones sean públicas (nada de
  loopback, redes privadas, link-local, metadatos de nube, multicast ni reservadas);
- me conecto a la IP que validé, con verificación TLS contra el nombre
  original: un cambio de DNS entre la validación y la conexión no me lleva a
  otra dirección (DNS rebinding);
- no sigo redirecciones: una respuesta 3xx cuenta como error;
- firmo el cuerpo con HMAC-SHA256 y un secreto propio del canal, para que el
  destino pueda comprobar que el mensaje es mío;
- nunca escribo la URL ni el secreto en logs ni en errores: los errores son
  códigos (`timeout`, `tls_error`, `http_404`...).

Solo fuera de producción admito destinos de prueba explícitos
(WEBHOOK_TEST_ALLOWED_TARGETS) y una CA propia (WEBHOOK_CA_BUNDLE) para
validar entregas en un entorno controlado.
"""

import hashlib
import hmac
import ipaddress
import json
import socket
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

PUERTO_PERMITIDO = 443
LARGO_MAXIMO_URL = 500


class DestinoNoPermitido(ValueError):
    """La URL o su resolución no son un destino externo aceptable. El mensaje es un código."""


@dataclass(frozen=True)
class Destino:
    host: str
    puerto: int
    ruta: str
    ips: Tuple[str, ...]
    de_prueba: bool


def _objetivos_de_prueba() -> set:
    from infra.config import settings

    return {o.strip().lower() for o in (settings.WEBHOOK_TEST_ALLOWED_TARGETS or "").split(",") if o.strip()}


def validar_url(url: str) -> Tuple[str, int, str]:
    """Valido la forma de la URL sin resolverla. Devuelvo (host, puerto, ruta con query)."""
    if not isinstance(url, str) or len(url) > LARGO_MAXIMO_URL:
        raise DestinoNoPermitido("invalid_url")
    partes = urlparse(url)
    if partes.scheme != "https":
        raise DestinoNoPermitido("https_required")
    if partes.username or partes.password:
        raise DestinoNoPermitido("credentials_in_url")
    if not partes.hostname:
        raise DestinoNoPermitido("invalid_url")
    try:
        puerto = partes.port or PUERTO_PERMITIDO
    except ValueError:
        raise DestinoNoPermitido("invalid_url")
    host = partes.hostname.lower()
    if puerto != PUERTO_PERMITIDO and f"{host}:{puerto}" not in _objetivos_de_prueba():
        raise DestinoNoPermitido("port_not_allowed")
    ruta = (partes.path or "/") + (f"?{partes.query}" if partes.query else "")
    return host, puerto, ruta


def _es_publica(ip: str) -> bool:
    direccion = ipaddress.ip_address(ip)
    if isinstance(direccion, ipaddress.IPv6Address) and direccion.ipv4_mapped:
        direccion = direccion.ipv4_mapped
    return direccion.is_global and not direccion.is_multicast


def resolver(url: str, resolvedor: Optional[Callable[..., List]] = None) -> Destino:
    host, puerto, ruta = validar_url(url)
    resolvedor = resolvedor or socket.getaddrinfo
    de_prueba = f"{host}:{puerto}" in _objetivos_de_prueba()
    try:
        ips = tuple(sorted({info[4][0] for info in resolvedor(host, puerto, type=socket.SOCK_STREAM)}))
    except (socket.gaierror, UnicodeError):
        raise DestinoNoPermitido("dns_error")
    if not ips:
        raise DestinoNoPermitido("dns_error")
    if not de_prueba and not all(_es_publica(ip) for ip in ips):
        # Si alguna dirección no es pública rechazo todo: no elijo la "buena".
        raise DestinoNoPermitido("destination_not_public")
    return Destino(host, puerto, ruta, ips, de_prueba)


def firmar(secreto: str, cuerpo: bytes, momento: int) -> str:
    mac = hmac.new(secreto.encode(), f"{momento}.".encode() + cuerpo, hashlib.sha256).hexdigest()
    return f"t={momento},v1={mac}"


def enviar(url: str, payload: Dict, clave_idempotencia: str, secreto: str, timeout: float = 10.0,
           resolvedor: Optional[Callable[..., List]] = None) -> int:
    """Hago el POST y devuelvo el código HTTP. Lanzo DestinoNoPermitido o ErrorDeRed con un código."""
    import certifi
    import urllib3

    from infra.config import settings

    destino = resolver(url, resolvedor)
    cuerpo = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    cabeceras = {
        "Content-Type": "application/json",
        "User-Agent": "chainsignal-notifier/0.4",
        "Idempotency-Key": clave_idempotencia,
        "X-ChainSignal-Signature": firmar(secreto, cuerpo, int(time.time())),
        "Host": destino.host if destino.puerto == PUERTO_PERMITIDO else f"{destino.host}:{destino.puerto}",
    }
    ca = settings.WEBHOOK_CA_BUNDLE if destino.de_prueba and settings.WEBHOOK_CA_BUNDLE else certifi.where()
    pool = urllib3.HTTPSConnectionPool(
        destino.ips[0], port=destino.puerto, server_hostname=destino.host, assert_hostname=destino.host,
        cert_reqs="CERT_REQUIRED", ca_certs=ca, retries=False,
        timeout=urllib3.Timeout(connect=min(5.0, timeout), read=timeout),
    )
    try:
        respuesta = pool.urlopen("POST", destino.ruta, body=cuerpo, headers=cabeceras, redirect=False, retries=False,
                                 preload_content=False)
        respuesta.drain_conn()
        return respuesta.status
    except urllib3.exceptions.SSLError:
        raise ErrorDeRed("tls_error")
    except (urllib3.exceptions.ConnectTimeoutError, urllib3.exceptions.ReadTimeoutError):
        raise ErrorDeRed("timeout")
    except urllib3.exceptions.HTTPError:
        raise ErrorDeRed("connection_error")
    finally:
        pool.close()


class ErrorDeRed(RuntimeError):
    """Falla de red o TLS hacia el destino; el mensaje es un código, sin la URL."""
