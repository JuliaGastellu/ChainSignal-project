"""Rutas de sesión, organizaciones y recursos privados (E02).

Todas las rutas /orgs/{org_id}/... pasan por contexto_org: sesión válida,
CSRF en mutaciones, membresía confirmada en la base y rol mínimo. Los cuerpos
rechazan campos desconocidos (incluido organization_id) con 422.
"""

import asyncio
import json
import threading
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from api.limites import LimiteSimple
from api.sesion import (
    borrar_cookies_de_sesion,
    contexto_org,
    escribir_cookies_de_sesion,
    requiere_sesion,
    servicio_identidad,
    servicio_recursos,
    sesion_opcional,
    verificar_origen,
)
from identidad.servicio import ContextoOrg, ErrorIdentidad, SesionActiva
from infra.config import settings


class _Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AltaBody(_Estricto):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)
    organization_name: str = Field(min_length=1, max_length=200)


class LoginBody(_Estricto):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


class AceptarInvitacionBody(_Estricto):
    token: str = Field(max_length=256)
    password: Optional[str] = Field(default=None, max_length=1024)


class InvitacionBody(_Estricto):
    email: str = Field(max_length=320)
    role: str


class RolBody(_Estricto):
    role: str


class CuentaBody(_Estricto):
    address: str = Field(max_length=64)
    chain_id: int = 1
    label: Optional[str] = Field(default=None, max_length=200)
    priority: str = "medium"
    interval_seconds: int = Field(default=300, ge=30, le=86400)


class CuentaCambiosBody(_Estricto):
    label: Optional[str] = Field(default=None, max_length=200)
    priority: Optional[str] = None
    interval_seconds: Optional[int] = Field(default=None, ge=30, le=86400)


class PoliticaBody(_Estricto):
    name: str = Field(max_length=200)
    # Regla tipada (monitoreo/reglas.py); el servicio la valida y normaliza.
    rule: Dict[str, Any]
    account_id: Optional[str] = Field(default=None, max_length=32)
    enabled: bool = True


class PoliticaCambiosBody(_Estricto):
    name: Optional[str] = Field(default=None, max_length=200)
    rule: Optional[Dict[str, Any]] = None
    account_id: Optional[str] = Field(default=None, max_length=32)
    enabled: Optional[bool] = None


def _cambios(body: BaseModel) -> Dict[str, Any]:
    return body.model_dump(exclude_unset=True)


# --- sesión -------------------------------------------------------------------

auth = APIRouter(prefix="/auth", tags=["auth"])


def _sesion_publica(sesion: SesionActiva, csrf: Optional[str] = None) -> Dict[str, Any]:
    datos = {
        "user": {"id": sesion.user_id, "email": sesion.email},
        "expires_at": sesion.expires_at,
        "memberships": servicio_identidad().membresias(sesion.user_id),
    }
    if csrf is not None:
        datos["csrf_token"] = csrf
    return datos


@auth.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    verificar_origen(request)
    identidad = servicio_identidad()
    user_id = identidad.autenticar(body.email, body.password)
    token, csrf, sesion = identidad.crear_sesion(user_id)
    escribir_cookies_de_sesion(response, token, csrf)
    return _sesion_publica(sesion, csrf)


_limite_alta = LimiteSimple(maximo=5, ventana_segundos=3600)
_limite_demo = LimiteSimple(maximo=20, ventana_segundos=3600)


class LimiteExcedido(ErrorIdentidad):
    estado = 429
    codigo = "rate_limited"


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


@auth.post("/signup", status_code=201)
def alta(body: AltaBody, request: Request, response: Response):
    """Alta autoservicio: persona nueva y su organización. Apagada salvo SIGNUP_ENABLED."""
    if not settings.SIGNUP_ENABLED:
        raise NoEncontradoRuta("Sign-up is not enabled.")
    verificar_origen(request)
    if not _limite_alta.permitir(_ip(request)):
        raise LimiteExcedido("Too many sign-ups from this address; try again later.")
    identidad = servicio_identidad()
    org_id, user_id = identidad.registrar(body.email, body.password, body.organization_name)
    token, csrf, sesion = identidad.crear_sesion(user_id)
    escribir_cookies_de_sesion(response, token, csrf)
    return {**_sesion_publica(sesion, csrf), "organization_id": org_id}


@auth.get("/session")
def sesion_actual(sesion: SesionActiva = Depends(requiere_sesion)):
    return _sesion_publica(sesion)


@auth.post("/logout")
def logout(response: Response, sesion: SesionActiva = Depends(requiere_sesion)):
    servicio_identidad().revocar_sesion(sesion.session_id)
    borrar_cookies_de_sesion(response)
    return {"status": "logged_out"}


@auth.post("/logout-all")
def logout_todas(response: Response, sesion: SesionActiva = Depends(requiere_sesion)):
    revocadas = servicio_identidad().revocar_sesiones_de_usuario(sesion.user_id)
    borrar_cookies_de_sesion(response)
    return {"status": "logged_out", "revoked_sessions": revocadas}


class NoEncontradoRuta(ErrorIdentidad):
    estado = 404
    codigo = "not_found"


demo = APIRouter(tags=["demo"])


@demo.post("/demo", status_code=201)
def crear_demo(request: Request, response: Response):
    """Demo aislada con datos sintéticos: organización propia que vence, sin lecturas reales."""
    if not settings.DEMO_ENABLED:
        raise NoEncontradoRuta("Demo is not enabled.")
    verificar_origen(request)
    if not _limite_demo.permitir(_ip(request)):
        raise LimiteExcedido("Too many demos from this address; try again later.")
    from monitoreo.demo import crear_demo as crear

    datos = crear()
    escribir_cookies_de_sesion(response, datos["token"], datos["csrf"])
    return {"organization_id": datos["organization_id"], "expires_at": datos["expires_at"], "csrf_token": datos["csrf"]}


invitaciones = APIRouter(tags=["invitations"])


@invitaciones.post("/invitations/accept")
def aceptar_invitacion(body: AceptarInvitacionBody, request: Request, response: Response):
    verificar_origen(request)
    sesion = sesion_opcional(request)
    if sesion is not None:
        # Con sesión iniciada, aceptar es una mutación más: exijo CSRF.
        from api.sesion import verificar_csrf

        verificar_csrf(request, sesion)
    identidad = servicio_identidad()
    user_id, org_id, nuevo = identidad.aceptar_invitacion(body.token, sesion, body.password)
    if nuevo:
        token, csrf, _ = identidad.crear_sesion(user_id)
        escribir_cookies_de_sesion(response, token, csrf)
    return {"organization_id": org_id, "user_id": user_id, "new_user": nuevo}


# --- organizaciones -------------------------------------------------------------

orgs = APIRouter(prefix="/orgs/{org_id}", tags=["organizations"])


@orgs.get("/members")
def listar_miembros(ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    return {"members": servicio_identidad().listar_miembros(ctx)}


@orgs.patch("/members/{membership_id}")
def cambiar_rol(membership_id: str, body: RolBody, ctx: ContextoOrg = Depends(contexto_org("owner"))):
    return servicio_identidad().cambiar_rol(ctx, membership_id, body.role)


@orgs.delete("/members/{membership_id}", status_code=204)
def quitar_miembro(membership_id: str, ctx: ContextoOrg = Depends(contexto_org("owner"))):
    servicio_identidad().quitar_miembro(ctx, membership_id)
    return Response(status_code=204)


@orgs.post("/invitations", status_code=201)
def invitar(body: InvitacionBody, ctx: ContextoOrg = Depends(contexto_org("owner"))):
    invitacion, token = servicio_identidad().invitar(ctx, body.email, body.role)
    # El token se muestra una sola vez; lo comparto por un canal propio.
    return {**invitacion, "token": token}


@orgs.get("/invitations")
def listar_invitaciones(ctx: ContextoOrg = Depends(contexto_org("owner"))):
    return {"invitations": servicio_identidad().listar_invitaciones(ctx)}


@orgs.delete("/invitations/{invitation_id}", status_code=204)
def revocar_invitacion(invitation_id: str, ctx: ContextoOrg = Depends(contexto_org("owner"))):
    servicio_identidad().revocar_invitacion(ctx, invitation_id)
    return Response(status_code=204)


@orgs.get("/accounts")
def listar_cuentas(limit: int = Query(50), offset: int = Query(0), ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    return {"accounts": servicio_recursos().listar_cuentas(ctx, limit, offset), "limit": limit, "offset": offset}


@orgs.post("/accounts", status_code=201)
def crear_cuenta(body: CuentaBody, ctx: ContextoOrg = Depends(contexto_org("operator"))):
    return servicio_recursos().crear_cuenta(ctx, body.address, body.chain_id, body.label, body.priority, body.interval_seconds)


@orgs.get("/accounts/{account_id}")
def obtener_cuenta(account_id: str, ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    return servicio_recursos().obtener_cuenta(ctx, account_id)


@orgs.patch("/accounts/{account_id}")
def actualizar_cuenta(account_id: str, body: CuentaCambiosBody, ctx: ContextoOrg = Depends(contexto_org("operator"))):
    return servicio_recursos().actualizar_cuenta(ctx, account_id, _cambios(body))


@orgs.delete("/accounts/{account_id}", status_code=204)
def eliminar_cuenta(account_id: str, ctx: ContextoOrg = Depends(contexto_org("operator"))):
    servicio_recursos().eliminar_cuenta(ctx, account_id)
    return Response(status_code=204)


@orgs.get("/accounts/{account_id}/analysis")
async def analizar_cuenta(account_id: str, request: Request, ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    cuenta = servicio_recursos().obtener_cuenta(ctx, account_id)
    servicio = request.app.state.agent_service
    reporte = await servicio.run_pipeline_core(cuenta["address"])
    return {"account_id": account_id, "chain_id": cuenta["chain_id"], "read_only": True, "report": reporte}


def construir_adaptador_aave():
    """Adaptador de lectura Aave V3 sobre el RPC de mainnet configurado."""
    from protocolos.aave_v3 import construir_desde_settings

    return construir_desde_settings()


def servicio_posiciones():
    from protocolos.servicio import ServicioPosiciones

    return ServicioPosiciones()


def _es_demo(ctx: ContextoOrg) -> bool:
    return servicio_identidad().organizacion(ctx.organization_id)["is_demo"]


def _adaptador_para(ctx: ContextoOrg, direccion_cuenta: str):
    """La demo usa su escenario sintético; una organización real, el RPC configurado."""
    if _es_demo(ctx):
        from monitoreo.demo import adaptador_demo

        return adaptador_demo(direccion_cuenta)
    return construir_adaptador_aave()


def _servicio_vigente(ctx: ContextoOrg) -> None:
    """Las lecturas en vivo y las evaluaciones exigen un plan con servicio (E09). El historial no."""
    if not _es_demo(ctx):
        from comercial.suscripciones import ServicioSuscripciones

        ServicioSuscripciones().exigir_servicio(ctx.organization_id)


def _evento(ctx: ContextoOrg, nombre: str, propiedades: Optional[Dict[str, Any]] = None, recurso: Optional[str] = None) -> None:
    from comercial.analitica import registrar

    registrar(None, ctx.organization_id, nombre, propiedades or {}, recurso=recurso)


@orgs.get("/summary")
def resumen_org(ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    from monitoreo.resumen import resumen

    _evento(ctx, "data_reviewed", {"role": ctx.role})
    return resumen(ctx)


@orgs.get("/subscription")
def suscripcion(ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    from comercial.suscripciones import ServicioSuscripciones

    return ServicioSuscripciones().presentar(ctx.organization_id)


@orgs.post("/subscription/cancel")
def cancelar_suscripcion(ctx: ContextoOrg = Depends(contexto_org("owner"))):
    from comercial.suscripciones import ServicioSuscripciones

    return ServicioSuscripciones().cancelar(ctx)


@orgs.post("/subscription/resume")
def reanudar_suscripcion(ctx: ContextoOrg = Depends(contexto_org("owner"))):
    from comercial.suscripciones import ServicioSuscripciones

    return ServicioSuscripciones().reanudar(ctx)


@orgs.get("/accounts/{account_id}/positions/aave-v3")
def posicion_aave(account_id: str, block: Optional[int] = Query(None, ge=0), ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    cuenta = servicio_recursos().obtener_cuenta(ctx, account_id)
    _servicio_vigente(ctx)
    snapshot = servicio_posiciones().leer_y_guardar(_adaptador_para(ctx, cuenta["address"]), cuenta["address"], block)
    if snapshot.id is not None:
        _evento(ctx, "first_snapshot", {"source": "api"})
    return {"account_id": account_id, "read_only": True, **snapshot.presentar()}


@orgs.get("/accounts/{account_id}/positions/aave-v3/latest")
def ultima_posicion_aave(account_id: str, ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    """Último snapshot guardado, sin volver a leer la red."""
    from infra.red import ETHEREUM
    from protocolos.aave_v3 import AdaptadorAaveV3

    cuenta = servicio_recursos().obtener_cuenta(ctx, account_id)
    snapshots = servicio_posiciones().listar(ETHEREUM.chain_id, AdaptadorAaveV3.protocolo, AdaptadorAaveV3.mercado,
                                             cuenta["address"], 1, sintetico=_es_demo(ctx))
    if not snapshots:
        raise NoEncontradoRuta("No snapshot yet for this account.")
    return {"account_id": account_id, "read_only": True, **snapshots[0].presentar()}


@orgs.get("/accounts/{account_id}/positions/aave-v3/snapshots")
def snapshots_aave(account_id: str, limit: int = Query(20, ge=1, le=200), ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    from infra.red import ETHEREUM
    from protocolos.aave_v3 import AdaptadorAaveV3

    cuenta = servicio_recursos().obtener_cuenta(ctx, account_id)
    snapshots = servicio_posiciones().listar(ETHEREUM.chain_id, AdaptadorAaveV3.protocolo, AdaptadorAaveV3.mercado,
                                             cuenta["address"], limit, sintetico=_es_demo(ctx))
    return {"account_id": account_id, "snapshots": [s.presentar() for s in snapshots]}


@orgs.post("/accounts/{account_id}/evaluate", status_code=202)
def evaluar_cuenta(account_id: str, ctx: ContextoOrg = Depends(contexto_org("operator"))):
    """Pido una evaluación ahora. En una organización real la encolo para el worker;
    en la demo la ejecuto en línea con datos sintéticos."""
    cuenta = servicio_recursos().obtener_cuenta(ctx, account_id)
    _servicio_vigente(ctx)
    if _es_demo(ctx):
        from infra.db import engine
        from monitoreo.demo import adaptador_demo, evaluar_en_linea

        estado = evaluar_en_linea(engine, ctx.organization_id, account_id, cuenta["address"],
                                  lambda: adaptador_demo(cuenta["address"]))
        return {"queued": False, "status": estado}
    from monitoreo.trabajos import ColaTrabajos

    encolado = ColaTrabajos().encolar("evaluate_account", ctx.organization_id, account_id, f"evaluate:{account_id}")
    return {"queued": True, "status": "queued" if encolado else "already_queued"}


class ResolverBody(_Estricto):
    note: str = Field(min_length=1, max_length=500)


class CorreccionBody(_Estricto):
    evidence_id: int
    note: str = Field(min_length=1, max_length=500)


class CanalBody(_Estricto):
    kind: str
    name: str = Field(max_length=200)
    config: Dict[str, Any] = Field(default_factory=dict)


def servicio_incidentes():
    from monitoreo.incidentes import ServicioIncidentes

    return ServicioIncidentes()


def servicio_notificaciones():
    from monitoreo.notificaciones import ServicioNotificaciones

    return ServicioNotificaciones()


@orgs.get("/incidents")
def listar_incidentes(status: Optional[str] = Query(None), limit: int = Query(50), offset: int = Query(0),
                      ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    return {"incidents": servicio_incidentes().listar(ctx, status, limit, offset), "limit": limit, "offset": offset}


@orgs.get("/incidents/{incident_id}")
def obtener_incidente(incident_id: str, ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    detalle = servicio_incidentes().obtener(ctx, incident_id)
    _evento(ctx, "incident_reviewed", {"role": ctx.role, "severity": detalle["severity"]}, recurso=incident_id)
    return detalle


@orgs.post("/incidents/{incident_id}/acknowledge")
def reconocer_incidente(incident_id: str, ctx: ContextoOrg = Depends(contexto_org("operator"))):
    return servicio_incidentes().reconocer(ctx, incident_id)


@orgs.post("/incidents/{incident_id}/resolve")
def resolver_incidente(incident_id: str, body: ResolverBody, ctx: ContextoOrg = Depends(contexto_org("operator"))):
    return servicio_incidentes().resolver(ctx, incident_id, body.note)


@orgs.post("/incidents/{incident_id}/corrections", status_code=201)
def corregir_evidencia(incident_id: str, body: CorreccionBody, ctx: ContextoOrg = Depends(contexto_org("operator"))):
    return servicio_incidentes().corregir(ctx, incident_id, body.evidence_id, body.note)


def servicio_explicaciones():
    from explicacion.servicio import ServicioExplicaciones

    return ServicioExplicaciones()


@orgs.get("/incidents/{incident_id}/explanation")
def explicacion_incidente(incident_id: str, ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    """Última explicación guardada o la plantilla determinista, sin costo."""
    return _explicar(lambda: servicio_explicaciones().ultima(ctx, incident_id))


@orgs.post("/incidents/{incident_id}/explanation", status_code=201)
def generar_explicacion(incident_id: str, ctx: ContextoOrg = Depends(contexto_org("operator"))):
    """Genero una explicación (con modelo si está habilitado y hay presupuesto; si no, plantilla)."""
    return _explicar(lambda: servicio_explicaciones().generar(ctx, incident_id))


def _explicar(funcion):
    from explicacion.entrada import EntradaInvalida
    from identidad.servicio import SolicitudInvalida

    try:
        return funcion()
    except EntradaInvalida as error:
        raise SolicitudInvalida(str(error))


@orgs.get("/channels")
def listar_canales(ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    return {"channels": servicio_notificaciones().listar_canales(ctx)}


@orgs.post("/channels", status_code=201)
def crear_canal(body: CanalBody, ctx: ContextoOrg = Depends(contexto_org("owner"))):
    return servicio_notificaciones().crear_canal(ctx, body.kind, body.name, body.config)


@orgs.post("/channels/{channel_id}/test", status_code=202)
def probar_canal(channel_id: str, ctx: ContextoOrg = Depends(contexto_org("operator"))):
    return servicio_notificaciones().probar_canal(ctx, channel_id)


@orgs.get("/channels/{channel_id}/deliveries")
def entregas_canal(channel_id: str, limit: int = Query(50), ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    return {"deliveries": servicio_notificaciones().entregas(ctx, channel_id, limit)}


@orgs.get("/policies")
def listar_politicas(limit: int = Query(50), offset: int = Query(0), ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    return {"policies": servicio_recursos().listar_politicas(ctx, limit, offset), "limit": limit, "offset": offset}


@orgs.post("/policies", status_code=201)
def crear_politica(body: PoliticaBody, ctx: ContextoOrg = Depends(contexto_org("operator"))):
    return servicio_recursos().crear_politica(ctx, body.name, body.rule, body.account_id, body.enabled)


@orgs.patch("/policies/{policy_id}")
def actualizar_politica(policy_id: str, body: PoliticaCambiosBody, ctx: ContextoOrg = Depends(contexto_org("operator"))):
    return servicio_recursos().actualizar_politica(ctx, policy_id, _cambios(body))


@orgs.get("/policies/{policy_id}/versions")
def versiones_politica(policy_id: str, ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    return {"versions": servicio_recursos().versiones_politica(ctx, policy_id)}


@orgs.delete("/policies/{policy_id}", status_code=204)
def eliminar_politica(policy_id: str, ctx: ContextoOrg = Depends(contexto_org("operator"))):
    servicio_recursos().eliminar_politica(ctx, policy_id)
    return Response(status_code=204)


@orgs.get("/events")
def listar_eventos(cursor: int = Query(0), limit: int = Query(100), ctx: ContextoOrg = Depends(contexto_org("viewer"))):
    cursor = servicio_recursos().validar_cursor(ctx, cursor)
    eventos = servicio_recursos().eventos_desde(ctx, cursor, limit)
    return {"events": eventos, "next_cursor": eventos[-1]["id"] if eventos else cursor}


class DemasiadosStreams(ErrorIdentidad):
    estado = 429
    codigo = "too_many_streams"


# Cuento streams abiertos por organización en este proceso. No hay cola en
# memoria: cada stream lee eventos durables de la base por cursor, así que un
# corte o un cliente lento no pierde eventos; al reconectar con Last-Event-ID
# sigue desde el último que recibió.
_streams_abiertos: Dict[str, int] = {}
_lock_streams = threading.Lock()


def _reservar_stream(organization_id: str) -> bool:
    with _lock_streams:
        actuales = _streams_abiertos.get(organization_id, 0)
        if actuales >= settings.MAX_EVENT_STREAMS_PER_ORG:
            return False
        _streams_abiertos[organization_id] = actuales + 1
        return True


def _soltar_stream(organization_id: str) -> None:
    with _lock_streams:
        _streams_abiertos[organization_id] = max(0, _streams_abiertos.get(organization_id, 1) - 1)


async def _liberar_al_terminar(organization_id: str, generador):
    try:
        async for parte in generador:
            yield parte
    finally:
        _soltar_stream(organization_id)
        await generador.aclose()


async def generar_stream_eventos(sesion: SesionActiva, ctx: ContextoOrg, cursor: int,
                                 intervalo: Optional[float] = None) -> AsyncGenerator[str, None]:
    """Emito eventos de la organización desde el cursor.

    En cada vuelta vuelvo a verificar la sesión y la membresía: si la sesión
    se revocó, venció o la persona dejó la organización, cierro el stream.
    """
    identidad, recursos = servicio_identidad(), servicio_recursos()
    espera = settings.EVENT_STREAM_POLL_SECONDS if intervalo is None else intervalo
    vueltas_sin_eventos = 0
    yield ": connected\n\n"
    while True:
        try:
            ctx = await asyncio.to_thread(identidad.contexto, sesion, ctx.organization_id, "viewer")
        except ErrorIdentidad:
            yield "event: session_ended\ndata: {}\n\n"
            return
        eventos = await asyncio.to_thread(recursos.eventos_desde, ctx, cursor, 100)
        for evento in eventos:
            cursor = evento["id"]
            yield f"id: {evento['id']}\nevent: org_event\ndata: {json.dumps(evento)}\n\n"
        vueltas_sin_eventos = 0 if eventos else vueltas_sin_eventos + 1
        if vueltas_sin_eventos and vueltas_sin_eventos % 8 == 0:
            yield ": ping\n\n"
        await asyncio.sleep(espera)


@orgs.get("/events/stream")
def stream_eventos(
    request: Request,
    cursor: Optional[int] = Query(None),
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    ctx: ContextoOrg = Depends(contexto_org("viewer")),
    sesion: SesionActiva = Depends(requiere_sesion),
):
    # Valido el cursor antes de abrir el stream para responder 404 como HTTP.
    if cursor is None:
        cursor = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
    cursor = servicio_recursos().validar_cursor(ctx, cursor)
    if not _reservar_stream(ctx.organization_id):
        raise DemasiadosStreams("Too many open event streams for this organization; retry later.")
    return StreamingResponse(
        _liberar_al_terminar(ctx.organization_id, generar_stream_eventos(sesion, ctx, cursor)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
