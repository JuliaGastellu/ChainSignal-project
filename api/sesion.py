"""Sesión de navegador, CSRF y chequeo de Origin para la API.

La sesión viaja en una cookie HttpOnly, Secure y SameSite=Lax que JavaScript
no puede leer. Las mutaciones exigen además el token CSRF por doble envío: la
cookie legible `cs_csrf` y el header `X-CSRF-Token` deben coincidir entre sí y
con el hash guardado en la sesión. Si el navegador manda Origin, tiene que ser
uno de CORS_ALLOWED_ORIGINS.
"""

from functools import lru_cache
from typing import Optional

from fastapi import Depends, Request, Response

from identidad import seguridad
from identidad.recursos import ServicioRecursos
from identidad.servicio import (
    ContextoOrg,
    ErrorIdentidad,
    NoAutenticado,
    Prohibido,
    SesionActiva,
    ServicioIdentidad,
)
from infra.config import settings

COOKIE_SESION = "cs_session"
COOKIE_CSRF = "cs_csrf"
HEADER_CSRF = "X-CSRF-Token"
METODOS_SEGUROS = {"GET", "HEAD", "OPTIONS"}


class CsrfInvalido(Prohibido):
    codigo = "csrf_failed"


class OrigenNoPermitido(Prohibido):
    codigo = "origin_not_allowed"


@lru_cache(maxsize=1)
def servicio_identidad() -> ServicioIdentidad:
    return ServicioIdentidad()


@lru_cache(maxsize=1)
def servicio_recursos() -> ServicioRecursos:
    return ServicioRecursos()


def escribir_cookies_de_sesion(respuesta: Response, token: str, csrf: str) -> None:
    max_age = int(settings.SESSION_TTL_HOURS * 3600)
    comunes = dict(secure=settings.SESSION_COOKIE_SECURE, samesite="lax", max_age=max_age, path="/")
    respuesta.set_cookie(COOKIE_SESION, token, httponly=True, **comunes)
    # El token CSRF tiene que poder leerlo el frontend para mandarlo en el header.
    respuesta.set_cookie(COOKIE_CSRF, csrf, httponly=False, **comunes)


def borrar_cookies_de_sesion(respuesta: Response) -> None:
    for nombre in (COOKIE_SESION, COOKIE_CSRF):
        respuesta.delete_cookie(nombre, path="/", secure=settings.SESSION_COOKIE_SECURE, samesite="lax")


def verificar_origen(request: Request) -> None:
    origen = request.headers.get("origin")
    if origen and origen.rstrip("/") not in settings.cors_origins:
        raise OrigenNoPermitido("Origin not allowed.")


def verificar_csrf(request: Request, sesion: SesionActiva) -> None:
    header = request.headers.get(HEADER_CSRF) or ""
    cookie = request.cookies.get(COOKIE_CSRF) or ""
    if not header or not cookie or not seguridad.tokens_iguales(header, cookie):
        raise CsrfInvalido("Missing or invalid CSRF token.")
    if not seguridad.tokens_iguales(seguridad.hashear_token(header), sesion.csrf_hash):
        raise CsrfInvalido("Missing or invalid CSRF token.")


def sesion_opcional(request: Request) -> Optional[SesionActiva]:
    try:
        return servicio_identidad().sesion_por_token(request.cookies.get(COOKIE_SESION))
    except NoAutenticado:
        return None


def requiere_sesion(request: Request) -> SesionActiva:
    sesion = servicio_identidad().sesion_por_token(request.cookies.get(COOKIE_SESION))
    if request.method not in METODOS_SEGUROS:
        verificar_origen(request)
        verificar_csrf(request, sesion)
    return sesion


def contexto_org(rol_minimo: str):
    """Dependencia que verifica sesión, CSRF (en mutaciones), membresía y rol.

    El organization_id sale del path y solo se acepta si la base confirma la
    membresía de quien llama.
    """

    def _dependencia(org_id: str, sesion: SesionActiva = Depends(requiere_sesion)) -> ContextoOrg:
        return servicio_identidad().contexto(sesion, org_id, rol_minimo)

    return _dependencia


def respuesta_de_error(error: ErrorIdentidad) -> dict:
    return {"error": error.codigo, "message": error.mensaje}
