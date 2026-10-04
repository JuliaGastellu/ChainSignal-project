"""Rutas comerciales públicas (E09): contacto desde la landing y webhook de facturación.

- POST /contact guarda un pedido de contacto con consentimiento explícito. No
  envío respuestas automáticas: lo leo y contesto a mano.
- POST /billing/webhook procesa eventos firmados de un procesador de pagos.
  Sin BILLING_WEBHOOK_SECRET responde 404: hoy cobro de forma asistida.
"""

import time

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from api.limites import LimiteSimple
from api.sesion import verificar_origen
from identidad.servicio import ErrorIdentidad, SolicitudInvalida, normalizar_email
from infra.config import settings

comercial = APIRouter(tags=["commercial"])

_limite_contacto = LimiteSimple(maximo=5, ventana_segundos=3600)


class NoDisponible(ErrorIdentidad):
    estado = 404
    codigo = "not_found"


class DemasiadosContactos(ErrorIdentidad):
    estado = 429
    codigo = "rate_limited"


class ContactoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=320)
    organization: str | None = Field(default=None, max_length=200)
    message: str = Field(min_length=1, max_length=2000)
    consent: bool


@comercial.post("/contact", status_code=201)
def contacto(body: ContactoBody, request: Request):
    if not settings.CONTACT_ENABLED:
        raise NoDisponible("Contact form is not enabled.")
    verificar_origen(request)
    if not body.consent:
        raise SolicitudInvalida("Consent is required to store your contact details.")
    ip = request.client.host if request.client else "desconocida"
    if not _limite_contacto.permitir(ip):
        raise DemasiadosContactos("Too many contact requests from this address; try again later.")
    from infra.db import get_session_factory
    from infra.db_models import ContactRequestRecord

    with get_session_factory()() as s:
        s.add(ContactRequestRecord(email=normalizar_email(body.email), organization=(body.organization or "").strip() or None,
                                   message=body.message.strip(), consent=True, created_at=time.time()))
        s.commit()
    return {"status": "received"}


@comercial.post("/billing/webhook")
async def webhook_facturacion(request: Request):
    if not settings.BILLING_WEBHOOK_SECRET:
        raise NoDisponible("Billing webhooks are not enabled.")
    from comercial.facturacion import ProcesadorWebhook

    cuerpo = await request.body()
    return ProcesadorWebhook(settings.BILLING_WEBHOOK_SECRET, settings.BILLING_PROVIDER).procesar(
        cuerpo, request.headers.get("x-billing-signature"))
