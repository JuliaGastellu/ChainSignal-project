"""Interfaz para un procesador de pagos futuro (E09). No integro ninguno real.

Hoy cobro de forma asistida: emito una factura fuera del sistema y, cuando el
pago está confirmado, una persona lo registra con `python -m comercial.cli
confirmar-pago`. Dejo preparado el camino automático para cuando haya
renovaciones:

- **firma:** `X-Billing-Signature: t=<epoch>,v1=<hex>`, con
  HMAC-SHA256(BILLING_WEBHOOK_SECRET, "<t>.<cuerpo>") y comparación en tiempo constante;
- **replay:** rechazo firmas con más de 5 minutos de diferencia con mi reloj y
  registro cada `event_id` una sola vez (`billing_events`); un reenvío
  devuelve `duplicate` sin volver a aplicar efectos;
- **entitlement:** `payment.succeeded` registra un pago confirmado y extiende
  el período; `payment.failed` pasa a `past_due` con gracia de 7 días;
  `subscription.canceled` deja de renovar al fin del período.

Sin BILLING_WEBHOOK_SECRET la ruta no existe (404). Nada de esto marca un pago
como cobrado sin un evento firmado de un procesador.
"""

import hashlib
import hmac
import json
import time
from typing import Any, Callable, Dict, Optional

from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from comercial.suscripciones import ServicioSuscripciones
from identidad.servicio import ErrorIdentidad
from infra.db import engine as engine_por_defecto
from infra.db import get_session_factory, init_db
from infra.db_models import BillingEventRecord

TOLERANCIA_SEGUNDOS = 300
MAX_CUERPO = 64 * 1024


class FirmaInvalida(ErrorIdentidad):
    estado = 401
    codigo = "invalid_signature"


class EventoMalformado(ErrorIdentidad):
    estado = 400
    codigo = "invalid_event"


def firmar(secreto: str, cuerpo: bytes, momento: int) -> str:
    """La uso en pruebas y documento el formato que espero del procesador."""
    mac = hmac.new(secreto.encode(), f"{momento}.".encode() + cuerpo, hashlib.sha256).hexdigest()
    return f"t={momento},v1={mac}"


def verificar_firma(secreto: str, cuerpo: bytes, cabecera: Optional[str], ahora: float) -> None:
    if not cabecera or len(cuerpo) > MAX_CUERPO:
        raise FirmaInvalida("Missing signature.")
    partes = dict(p.split("=", 1) for p in cabecera.split(",") if "=" in p)
    try:
        momento = int(partes.get("t", ""))
    except ValueError:
        raise FirmaInvalida("Malformed signature.")
    if abs(ahora - momento) > TOLERANCIA_SEGUNDOS:
        raise FirmaInvalida("Signature timestamp outside the tolerance window.")
    esperada = firmar(secreto, cuerpo, momento).split("v1=", 1)[1]
    if not hmac.compare_digest(esperada, partes.get("v1", "")):
        raise FirmaInvalida("Signature mismatch.")


class ProcesadorWebhook:
    def __init__(self, secreto: str, proveedor: str = "processor", engine_: Optional[Engine] = None,
                 reloj: Callable[[], float] = time.time):
        self._secreto = secreto
        self.proveedor = proveedor
        self._engine = engine_ or engine_por_defecto
        init_db(self._engine)
        self._Session = get_session_factory(self._engine)
        self.reloj = reloj
        self.suscripciones = ServicioSuscripciones(self._engine, reloj)

    def procesar(self, cuerpo: bytes, cabecera: Optional[str]) -> Dict[str, Any]:
        verificar_firma(self._secreto, cuerpo, cabecera, self.reloj())
        try:
            evento = json.loads(cuerpo)
            event_id, tipo = str(evento["id"])[:100], str(evento["type"])[:64]
            datos = evento.get("data") or {}
            org = datos.get("organization_id")
        except (ValueError, KeyError, TypeError):
            raise EventoMalformado("Event must be JSON with id, type and data.")
        registro = BillingEventRecord(provider=self.proveedor, event_id=event_id, type=tipo, organization_id=org,
                                      payload_sha256=hashlib.sha256(cuerpo).hexdigest(), outcome="received",
                                      received_at=self.reloj())
        with self._Session() as s:
            s.add(registro)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                return {"status": "duplicate", "event_id": event_id}
            registro_id = registro.id
        try:
            resultado = self._aplicar(tipo, org, datos, event_id)
        except Exception:
            # Si no pude aplicar el efecto, borro el registro: el reintento del
            # procesador tiene que poder procesarlo de nuevo, no verlo como duplicado.
            with self._Session() as s:
                s.delete(s.get(BillingEventRecord, registro_id))
                s.commit()
            raise
        with self._Session() as s:
            fila = s.get(BillingEventRecord, registro_id)
            fila.outcome = resultado["status"][:32]
            s.commit()
        return {**resultado, "event_id": event_id}

    def _aplicar(self, tipo: str, org: Optional[str], datos: Dict[str, Any], event_id: str) -> Dict[str, Any]:
        if not org:
            return {"status": "ignored"}
        if tipo == "payment.succeeded":
            return self.suscripciones.confirmar_pago(org, str(datos.get("reference") or event_id), str(datos.get("amount_usd", "")),
                                                     f"webhook:{self.proveedor}", origen="webhook",
                                                     periodo_fin=datos.get("period_end"))
        if tipo == "payment.failed":
            return self.suscripciones.marcar_pago_fallido(org)
        if tipo == "subscription.canceled":
            return self.suscripciones.cancelar_por_procesador(org)
        return {"status": "ignored"}
