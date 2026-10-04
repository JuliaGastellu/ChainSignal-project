"""Canales de notificación y despacho del outbox.

Entrega at-least-once, nunca exactly-once: si un worker envía y muere antes de
marcar la fila como enviada, otro worker la reenvía tras vencer el lease. Cada
envío lleva la misma idempotency_key para que el receptor pueda descartar
duplicados; no prometo que lo haga.

Canales:
- sandbox: guarda la entrega en notification_deliveries. Nunca sale del sistema;
  sirve para probar el circuito completo en la demo y en las pruebas.
- webhook: POST HTTPS firmado, con header Idempotency-Key y protección contra
  SSRF (monitoreo/webhook_seguro.py). Está deshabilitado salvo
  NOTIFICATIONS_WEBHOOKS_ENABLED=true; si está apagado, crear o probar un
  webhook falla con un motivo claro: nunca lo reemplazo en silencio por el sandbox.

Qué puedo afirmar de una entrega:
- sandbox: registré una simulación; no salió nada del sistema;
- webhook: el destino aceptó la solicitud (HTTP 2xx). No sé si una persona la
  leyó: eso no lo puedo afirmar sin una confirmación aparte.

Las pruebas inyectan un TransporteFalso que registra envíos y simula fallas.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from sqlalchemy import select, update
from sqlalchemy.engine import Engine

from identidad import seguridad
from identidad.servicio import ContextoOrg, ErrorIdentidad, NoEncontrado, SolicitudInvalida, registrar_evento
from infra.config import settings
from infra.db import engine as engine_por_defecto
from infra.db import get_session_factory, init_db
from infra.db_models import NotificationChannelRecord, NotificationDeliveryRecord, OutboxRecord

TIPOS_CANAL = ("sandbox", "webhook")


class WebhooksDeshabilitados(ErrorIdentidad):
    estado = 409
    codigo = "webhooks_disabled"


class DestinoInvalido(SolicitudInvalida):
    codigo = "webhook_destination_invalid"


def resultado_de_entrega(tipo: str, estado: str) -> str:
    """Lo que puedo afirmar de una entrega, según el canal y su estado."""
    if estado == "sent":
        return "simulated" if tipo == "sandbox" else "accepted_by_destination"
    if estado in ("failed", "dead"):
        return "failed"
    return "pending"


class ErrorEntrega(Exception):
    def __init__(self, motivo: str, reintentable: bool):
        super().__init__(motivo)
        self.motivo = motivo
        self.reintentable = reintentable


@dataclass
class TransporteFalso:
    """Transporte de prueba: registra cada envío y puede fallar a demanda."""

    enviados: List[Dict[str, Any]] = field(default_factory=list)
    fallas: List[ErrorEntrega] = field(default_factory=list)

    def enviar(self, canal: NotificationChannelRecord, payload: Dict[str, Any], clave: str) -> None:
        if self.fallas:
            raise self.fallas.pop(0)
        self.enviados.append({"channel_id": canal.id, "idempotency_key": clave, "payload": payload})


class EntregaSandbox:
    def __init__(self, session_factory, reloj):
        self._Session = session_factory
        self.reloj = reloj

    def enviar(self, canal: NotificationChannelRecord, payload: Dict[str, Any], clave: str) -> None:
        with self._Session() as s:
            s.add(NotificationDeliveryRecord(organization_id=canal.organization_id, channel_id=canal.id,
                                             idempotency_key=clave, payload=payload, delivered_at=self.reloj()))
            s.commit()


class TransporteWebhook:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def enviar(self, canal: NotificationChannelRecord, payload: Dict[str, Any], clave: str) -> None:
        if not settings.NOTIFICATIONS_WEBHOOKS_ENABLED:
            raise ErrorEntrega("webhooks_disabled", reintentable=False)
        from monitoreo.webhook_seguro import DestinoNoPermitido, ErrorDeRed, enviar

        try:
            codigo = enviar(canal.config["url"], payload, clave, canal.config.get("signing_secret", ""), self.timeout)
        except DestinoNoPermitido as error:
            raise ErrorEntrega(str(error), reintentable=False)
        except ErrorDeRed as error:
            raise ErrorEntrega(str(error), reintentable=str(error) != "tls_error")
        if 300 <= codigo < 400:
            raise ErrorEntrega(f"redirect_not_followed_{codigo}", reintentable=False)
        if codigo == 429 or codigo >= 500:
            raise ErrorEntrega(f"http_{codigo}", reintentable=True)
        if codigo >= 400:
            raise ErrorEntrega(f"http_{codigo}", reintentable=False)


def _canal_a_dict(c: NotificationChannelRecord) -> Dict[str, Any]:
    config = dict(c.config)
    if "url" in config:
        # Muestro solo el host: la URL puede contener tokens. El secreto de firma no sale nunca.
        config = {"host": urlparse(config["url"]).hostname}
    return {"id": c.id, "kind": c.kind, "name": c.name, "config": config, "enabled": c.enabled,
            "verified_at": c.verified_at, "created_at": c.created_at}


class ServicioNotificaciones:
    def __init__(self, engine_: Optional[Engine] = None, reloj: Callable[[], float] = time.time,
                 transportes: Optional[Dict[str, Any]] = None, lease_segundos: float = 60.0):
        self._engine = engine_ or engine_por_defecto
        init_db(self._engine)
        self._Session = get_session_factory(self._engine)
        self.reloj = reloj
        self.lease_segundos = lease_segundos
        self.transportes = transportes or {"sandbox": EntregaSandbox(self._Session, reloj), "webhook": TransporteWebhook()}

    # --- canales ----------------------------------------------------------------------

    def crear_canal(self, ctx: ContextoOrg, tipo: str, nombre: str, config: Dict[str, Any]) -> Dict[str, Any]:
        ctx.exigir_rol("owner")
        if tipo not in TIPOS_CANAL:
            raise SolicitudInvalida("kind must be sandbox or webhook.")
        nombre = (nombre or "").strip()
        if not nombre or len(nombre) > 200:
            raise SolicitudInvalida("name is required (max 200 characters).")
        secreto = None
        if tipo == "webhook":
            if not settings.NOTIFICATIONS_WEBHOOKS_ENABLED:
                raise WebhooksDeshabilitados("External webhooks are disabled in this environment.")
            from monitoreo.webhook_seguro import DestinoNoPermitido, resolver

            url = str((config or {}).get("url", ""))
            try:
                resolver(url)
            except DestinoNoPermitido as error:
                raise DestinoInvalido(str(error))
            secreto = seguridad.nuevo_token()
            config = {"url": url, "signing_secret": secreto}
        else:
            config = {}
        canal = NotificationChannelRecord(id=seguridad.nuevo_id(), organization_id=ctx.organization_id, kind=tipo,
                                          name=nombre, config=config, enabled=True, created_at=self.reloj())
        with self._Session() as s:
            s.add(canal)
            registrar_evento(s, ctx.organization_id, "channel.created", {"channel_id": canal.id, "kind": tipo}, ctx.user_id)
            s.commit()
            resultado = _canal_a_dict(canal)
        if secreto:
            # El secreto de firma se muestra una sola vez, para configurarlo en el destino.
            resultado["signing_secret"] = secreto
        return resultado

    def listar_canales(self, ctx: ContextoOrg) -> List[Dict[str, Any]]:
        with self._Session() as s:
            canales = s.execute(select(NotificationChannelRecord).where(
                NotificationChannelRecord.organization_id == ctx.organization_id).order_by(NotificationChannelRecord.created_at)).scalars().all()
            resultado = []
            for c in canales:
                prueba = s.execute(select(OutboxRecord).where(
                    OutboxRecord.channel_id == c.id, OutboxRecord.organization_id == ctx.organization_id,
                    OutboxRecord.alert_id.is_(None)).order_by(OutboxRecord.id.desc()).limit(1)).scalar_one_or_none()
                datos = _canal_a_dict(c)
                datos["last_test"] = None if prueba is None else {
                    "status": prueba.status, "outcome": resultado_de_entrega(c.kind, prueba.status),
                    "error": prueba.last_error, "at": prueba.sent_at or prueba.created_at}
                resultado.append(datos)
            return resultado

    def _canal(self, s, ctx: ContextoOrg, channel_id: str) -> NotificationChannelRecord:
        canal = s.execute(select(NotificationChannelRecord).where(
            NotificationChannelRecord.id == channel_id, NotificationChannelRecord.organization_id == ctx.organization_id,
        )).scalar_one_or_none()
        if canal is None:
            raise NoEncontrado("Channel not found.")
        return canal

    def probar_canal(self, ctx: ContextoOrg, channel_id: str) -> Dict[str, Any]:
        """Encolo un mensaje de prueba; el despachador lo entrega y marca el canal como verificado."""
        ctx.exigir_rol("operator")
        ahora = self.reloj()
        with self._Session() as s:
            canal = self._canal(s, ctx, channel_id)
            if canal.kind == "webhook" and not settings.NOTIFICATIONS_WEBHOOKS_ENABLED:
                raise WebhooksDeshabilitados("External webhooks are disabled in this environment.")
            # Una prueba es un solo intento: quiero el resultado ahora, no reintentos en segundo plano.
            fila = OutboxRecord(organization_id=ctx.organization_id, channel_id=canal.id, alert_id=None,
                                idempotency_key=f"test:{canal.id}:{seguridad.nuevo_id()}",
                                payload={"type": "channel.test", "channel_id": canal.id, "message": "ChainSignal test notification."},
                                status="pending", attempts=0, max_attempts=1, available_at=ahora, created_at=ahora)
            s.add(fila)
            registrar_evento(s, ctx.organization_id, "channel.test_requested", {"channel_id": canal.id}, ctx.user_id)
            s.commit()
            outbox_id, tipo = fila.id, canal.kind
        # Entrego la prueba en el momento para que tenga resultado inmediato.
        estado = self.entregar_uno(f"api:{ctx.user_id}"[:64], outbox_id) or "pending"
        with self._Session() as s:
            fila = s.get(OutboxRecord, outbox_id)
            error = fila.last_error if fila is not None else None
        if estado == "sent":
            from comercial.analitica import registrar

            registrar(self._engine, ctx.organization_id, "channel_tested", {"channel_kind": tipo})
        return {"outbox_id": outbox_id, "status": estado, "kind": tipo, "outcome": resultado_de_entrega(tipo, estado), "error": error}

    def entregas(self, ctx: ContextoOrg, channel_id: str, limite: int = 50) -> List[Dict[str, Any]]:
        with self._Session() as s:
            canal = self._canal(s, ctx, channel_id)
            filas = s.execute(select(OutboxRecord).where(
                OutboxRecord.channel_id == channel_id, OutboxRecord.organization_id == ctx.organization_id,
            ).order_by(OutboxRecord.id.desc()).limit(min(max(limite, 1), 200))).scalars().all()
            return [{"id": o.id, "status": o.status, "outcome": resultado_de_entrega(canal.kind, o.status), "attempts": o.attempts,
                     "payload_type": o.payload.get("type"),
                     "created_at": o.created_at, "sent_at": o.sent_at, "last_error": o.last_error} for o in filas]

    # --- despacho -------------------------------------------------------------------------

    def tomar(self, worker_id: str, outbox_id: Optional[int] = None) -> Optional[OutboxRecord]:
        ahora = self.reloj()
        with self._Session() as s:
            disponible = (((OutboxRecord.status == "pending") & (OutboxRecord.available_at <= ahora))
                          | ((OutboxRecord.status == "sending") & (OutboxRecord.lease_expires_at < ahora)))
            if outbox_id is not None:
                disponible = disponible & (OutboxRecord.id == outbox_id)
            fila = s.execute(
                select(OutboxRecord)
                .where(disponible)
                .order_by(OutboxRecord.available_at, OutboxRecord.id).limit(1).with_for_update(skip_locked=True)
            ).scalars().first()
            if fila is None:
                return None
            fila.status, fila.attempts = "sending", fila.attempts + 1
            fila.lease_owner, fila.lease_expires_at = worker_id, ahora + self.lease_segundos
            s.commit()
            s.refresh(fila)
            s.expunge(fila)
            return fila

    def _cerrar(self, fila: OutboxRecord, worker_id: str, valores: Dict[str, Any]) -> bool:
        with self._Session() as s:
            resultado = s.execute(update(OutboxRecord).where(
                OutboxRecord.id == fila.id, OutboxRecord.status == "sending",
                OutboxRecord.lease_owner == worker_id, OutboxRecord.attempts == fila.attempts,
            ).values(lease_owner=None, lease_expires_at=None, **valores))
            if resultado.rowcount != 1:
                s.rollback()
                return False  # otro worker la retomó; no piso su estado
            if valores.get("status") == "sent" and fila.payload.get("type") == "channel.test":
                s.execute(update(NotificationChannelRecord).where(NotificationChannelRecord.id == fila.channel_id)
                          .values(verified_at=self.reloj()))
            s.commit()
            return True

    def entregar_uno(self, worker_id: str, outbox_id: Optional[int] = None) -> Optional[str]:
        """Tomo una fila, la envío y registro el resultado. Devuelvo el estado final o None si no había nada."""
        fila = self.tomar(worker_id, outbox_id)
        if fila is None:
            return None
        with self._Session() as s:
            canal = s.get(NotificationChannelRecord, fila.channel_id)
            s.expunge(canal)
        ahora = self.reloj()
        try:
            if not canal.enabled:
                raise ErrorEntrega("channel disabled", reintentable=False)
            self.transportes[canal.kind].enviar(canal, fila.payload, fila.idempotency_key)
        except ErrorEntrega as error:
            if error.reintentable and fila.attempts < fila.max_attempts:
                espera = min(600.0, 5.0 * 2 ** (fila.attempts - 1))
                estado = "pending"
                valores = dict(status=estado, available_at=ahora + espera, last_error=error.motivo[:300])
            else:
                estado = "dead" if error.reintentable else "failed"
                valores = dict(status=estado, last_error=error.motivo[:300])
            self._cerrar(fila, worker_id, valores)
            return estado
        self._cerrar(fila, worker_id, dict(status="sent", sent_at=ahora, last_error=None))
        return "sent"
