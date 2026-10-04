"""Suscripciones y derechos de servicio (entitlements) del piloto (E09).

Estados:
- trialing: prueba de 14 días con límites de prueba;
- active: hay un pago confirmado que cubre el período actual;
- past_due: venció el período sin pago nuevo; sigo prestando servicio hasta
  el fin de la gracia (7 días);
- canceled: la organización canceló y llegó al fin del período pagado o de la prueba;
- expired: terminó la prueba o la gracia sin pago.

Calculo el estado efectivo con el reloj, sin depender de un proceso que lo
actualice: si nadie paga, el servicio se corta solo al vencer. Con servicio
inactivo la organización conserva su historial (lectura de incidentes,
snapshots y evidencia), pero no monitoreo ni altas nuevas.

Un pago solo se registra confirmado: lo carga una persona (cobro asistido, por
CLI) o llega por webhook firmado. No existe un camino que simule un cobro.
"""

import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, Optional

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from comercial.planes import DIAS_GRACIA, DIAS_PERIODO, LIMITES_DEMO, PLANES, PILOTO, Limites
from identidad.servicio import ContextoOrg, ErrorIdentidad, NoEncontrado, SolicitudInvalida
from infra.db import engine as engine_por_defecto
from infra.db import get_session_factory, init_db
from infra.db_models import MonitoredAccountRecord, OrganizationRecord, PaymentRecord, SubscriptionRecord

DIA = 86400.0
ESTADOS_CON_SERVICIO = {"trialing", "active", "past_due"}


class LimiteDelPlan(ErrorIdentidad):
    estado = 403
    codigo = "plan_limit"


class PlanInactivo(ErrorIdentidad):
    estado = 402
    codigo = "plan_inactive"


@dataclass(frozen=True)
class Derecho:
    """Qué servicio recibe hoy una organización."""

    estado: str
    con_servicio: bool
    limites: Limites
    es_demo: bool = False


def estado_efectivo(sub: SubscriptionRecord, ahora: float) -> str:
    if sub.status == "trialing":
        if sub.trial_ends_at is not None and ahora >= sub.trial_ends_at:
            return "canceled" if sub.cancel_at_period_end else "expired"
        return "trialing"
    if sub.status == "active":
        fin = sub.current_period_end or 0
        if ahora < fin:
            return "active"
        if sub.cancel_at_period_end:
            return "canceled"
        return "past_due" if ahora < fin + DIAS_GRACIA * DIA else "expired"
    if sub.status == "past_due":
        return "past_due" if sub.grace_ends_at is not None and ahora < sub.grace_ends_at else "expired"
    return sub.status


def fin_de_gracia(sub: SubscriptionRecord) -> Optional[float]:
    if sub.status == "past_due":
        return sub.grace_ends_at
    if sub.status == "active" and sub.current_period_end and not sub.cancel_at_period_end:
        return sub.current_period_end + DIAS_GRACIA * DIA
    return None


class ServicioSuscripciones:
    def __init__(self, engine_: Optional[Engine] = None, reloj: Callable[[], float] = time.time):
        self._engine = engine_ or engine_por_defecto
        init_db(self._engine)
        self._Session = get_session_factory(self._engine)
        self.reloj = reloj

    # --- creación y lectura --------------------------------------------------------

    @staticmethod
    def nueva_prueba(organization_id: str, ahora: float) -> SubscriptionRecord:
        return SubscriptionRecord(organization_id=organization_id, plan=PILOTO.id, status="trialing",
                                  trial_ends_at=ahora + PILOTO.dias_prueba * DIA, cancel_at_period_end=False,
                                  created_at=ahora, updated_at=ahora)

    def derecho_en_sesion(self, s, organization_id: str, bloquear: bool = False) -> Derecho:
        org = s.get(OrganizationRecord, organization_id)
        if org is None:
            raise NoEncontrado("Organization not found.")
        if org.is_demo:
            return Derecho("demo", True, LIMITES_DEMO, es_demo=True)
        consulta = select(SubscriptionRecord).where(SubscriptionRecord.organization_id == organization_id)
        if bloquear:
            consulta = consulta.with_for_update()
        sub = s.execute(consulta).scalar_one_or_none()
        if sub is None:
            # Sin suscripción no presto servicio: no invento una prueba implícita.
            return Derecho("none", False, PILOTO.limites_prueba)
        estado = estado_efectivo(sub, self.reloj())
        plan = PLANES[sub.plan]
        limites = plan.limites_prueba if estado == "trialing" else plan.limites
        return Derecho(estado, estado in ESTADOS_CON_SERVICIO, limites)

    def derecho(self, organization_id: str) -> Derecho:
        with self._Session() as s:
            return self.derecho_en_sesion(s, organization_id)

    def exigir_servicio(self, organization_id: str) -> Derecho:
        derecho = self.derecho(organization_id)
        if not derecho.con_servicio:
            raise PlanInactivo("The organization has no active plan: monitoring and new reads are paused. History stays available.")
        return derecho

    def exigir_alta_de_cuenta(self, s, organization_id: str, chain_id: int, intervalo: int) -> None:
        """Dentro de la transacción del alta: bloqueo la suscripción y cuento las cuentas, así dos altas simultáneas no superan el límite."""
        derecho = self.derecho_en_sesion(s, organization_id, bloquear=True)
        if not derecho.con_servicio:
            raise PlanInactivo("The organization has no active plan; it cannot add accounts.")
        if chain_id not in derecho.limites.redes:
            raise LimiteDelPlan("This plan covers Ethereum mainnet only.")
        cuentas = s.execute(select(func.count()).select_from(MonitoredAccountRecord).where(
            MonitoredAccountRecord.organization_id == organization_id)).scalar_one()
        if cuentas >= derecho.limites.max_cuentas:
            raise LimiteDelPlan(f"This plan allows up to {derecho.limites.max_cuentas} monitored accounts.")
        self.exigir_intervalo(derecho, intervalo)

    @staticmethod
    def exigir_intervalo(derecho: Derecho, intervalo: int) -> None:
        if intervalo < derecho.limites.intervalo_minimo_segundos:
            raise LimiteDelPlan(f"This plan evaluates at most every {derecho.limites.intervalo_minimo_segundos} seconds.")

    def presentar(self, organization_id: str) -> Dict[str, Any]:
        ahora = self.reloj()
        with self._Session() as s:
            derecho = self.derecho_en_sesion(s, organization_id)
            sub = s.get(SubscriptionRecord, organization_id)
            cuentas = s.execute(select(func.count()).select_from(MonitoredAccountRecord).where(
                MonitoredAccountRecord.organization_id == organization_id)).scalar_one()
            pagos = s.execute(select(PaymentRecord).where(PaymentRecord.organization_id == organization_id)
                              .order_by(PaymentRecord.period_end)).scalars().all()
        plan = PLANES[sub.plan] if sub else PILOTO
        return {
            "plan": {"id": plan.id, "name": plan.nombre, "guided_onboarding": plan.acompanamiento,
                     "reference_price_usd_per_month": plan.precio_referencia_usd,
                     "price_is_hypothesis": plan.precio_es_hipotesis, "billing": "assisted_invoice"},
            "status": derecho.estado,
            "service_active": derecho.con_servicio,
            "is_demo": derecho.es_demo,
            "trial_ends_at": sub.trial_ends_at if sub else None,
            "current_period_end": sub.current_period_end if sub else None,
            "grace_ends_at": fin_de_gracia(sub) if sub else None,
            "cancel_at_period_end": bool(sub.cancel_at_period_end) if sub else False,
            "canceled_at": sub.canceled_at if sub else None,
            "limits": derecho.limites.presentar(),
            "usage": {"accounts": cuentas},
            "confirmed_payments": [{"source": p.source, "period_start": p.period_start, "period_end": p.period_end,
                                    "amount_usd": p.amount_usd} for p in pagos],
            "server_time": ahora,
        }

    # --- cancelación ---------------------------------------------------------------

    def cancelar(self, ctx: ContextoOrg) -> Dict[str, Any]:
        """La organización deja de renovar; el servicio sigue hasta el fin de la prueba o del período pagado."""
        ctx.exigir_rol("owner")
        with self._Session() as s:
            sub = self._suscripcion(s, ctx.organization_id)
            if estado_efectivo(sub, self.reloj()) in ("canceled", "expired"):
                raise SolicitudInvalida("The subscription already ended.")
            sub.cancel_at_period_end, sub.canceled_at, sub.updated_at = True, self.reloj(), self.reloj()
            s.commit()
        self._analitica(ctx.organization_id, "subscription_canceled")
        return self.presentar(ctx.organization_id)

    def reanudar(self, ctx: ContextoOrg) -> Dict[str, Any]:
        ctx.exigir_rol("owner")
        with self._Session() as s:
            sub = self._suscripcion(s, ctx.organization_id)
            if estado_efectivo(sub, self.reloj()) in ("canceled", "expired"):
                raise SolicitudInvalida("The subscription already ended; a new confirmed payment is needed.")
            sub.cancel_at_period_end, sub.canceled_at, sub.updated_at = False, None, self.reloj()
            s.commit()
        self._analitica(ctx.organization_id, "subscription_resumed")
        return self.presentar(ctx.organization_id)

    # --- pagos confirmados ---------------------------------------------------------

    def confirmar_pago(self, organization_id: str, referencia: str, monto_usd: str, confirmado_por: str,
                       origen: str = "manual", periodo_fin: Optional[float] = None) -> Dict[str, Any]:
        """Registro un pago ya confirmado y extiendo el período. Idempotente por (origen, referencia)."""
        referencia, confirmado_por = (referencia or "").strip(), (confirmado_por or "").strip()
        if origen not in ("manual", "webhook") or not referencia or not confirmado_por:
            raise SolicitudInvalida("A confirmed payment needs a source, a reference and who confirmed it.")
        try:
            monto = Decimal(monto_usd)
        except (InvalidOperation, TypeError):
            raise SolicitudInvalida("amount_usd must be a number.")
        if monto <= 0:
            raise SolicitudInvalida("amount_usd must be positive.")
        ahora = self.reloj()
        with self._Session() as s:
            existente = s.execute(select(PaymentRecord).where(PaymentRecord.source == origen,
                                                              PaymentRecord.reference == referencia)).scalar_one_or_none()
            if existente is not None:
                if existente.organization_id != organization_id:
                    raise SolicitudInvalida("That payment reference belongs to another organization.")
                return {"status": "duplicate", "period_end": existente.period_end}
            sub = self._suscripcion(s, organization_id, bloquear=True)
            inicio = max(ahora, sub.current_period_end or 0) if estado_efectivo(sub, ahora) == "active" else ahora
            fin = periodo_fin if periodo_fin and periodo_fin > inicio else inicio + DIAS_PERIODO * DIA
            s.add(PaymentRecord(organization_id=organization_id, source=origen, reference=referencia[:100],
                                amount_usd=str(monto), period_start=inicio, period_end=fin,
                                confirmed_by=confirmado_por[:100], created_at=ahora))
            sub.status, sub.current_period_end, sub.grace_ends_at = "active", fin, None
            sub.cancel_at_period_end, sub.canceled_at, sub.updated_at = False, None, ahora
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                return {"status": "duplicate"}
        self._analitica(organization_id, "payment_confirmed", {"source": origen})
        return {"status": "confirmed", "period_end": fin}

    def marcar_pago_fallido(self, organization_id: str) -> Dict[str, Any]:
        ahora = self.reloj()
        with self._Session() as s:
            sub = self._suscripcion(s, organization_id, bloquear=True)
            if estado_efectivo(sub, ahora) in ("active", "past_due"):
                sub.status = "past_due"
                sub.grace_ends_at = sub.grace_ends_at or max(ahora, sub.current_period_end or ahora) + DIAS_GRACIA * DIA
                sub.updated_at = ahora
                s.commit()
                return {"status": "past_due", "grace_ends_at": sub.grace_ends_at}
            return {"status": "ignored"}

    def cancelar_por_procesador(self, organization_id: str) -> Dict[str, Any]:
        with self._Session() as s:
            sub = self._suscripcion(s, organization_id, bloquear=True)
            sub.cancel_at_period_end, sub.canceled_at, sub.updated_at = True, self.reloj(), self.reloj()
            s.commit()
        return {"status": "cancel_at_period_end"}

    # --- internos ------------------------------------------------------------------

    def _suscripcion(self, s, organization_id: str, bloquear: bool = False) -> SubscriptionRecord:
        consulta = select(SubscriptionRecord).where(SubscriptionRecord.organization_id == organization_id)
        if bloquear:
            consulta = consulta.with_for_update()
        sub = s.execute(consulta).scalar_one_or_none()
        if sub is None:
            raise NoEncontrado("This organization has no subscription (demo organizations do not have one).")
        return sub

    def _analitica(self, organization_id: str, nombre: str, propiedades: Optional[Dict[str, str]] = None) -> None:
        from comercial.analitica import registrar

        registrar(self._engine, organization_id, nombre, propiedades or {})
