"""Recursos privados de una organización: cuentas observadas, políticas y eventos.

Cada operación recibe un ContextoOrg verificado y filtra por su
organization_id; nunca por un valor que mande el cliente. Las mutaciones exigen
rol operator u owner también aquí, no solo en la ruta. El worker usa funciones
de sistema que siempre escriben con el organization_id de la cuenta leída.

Una cuenta observada es una dirección pública que la organización quiere
seguir. Observarla no implica controlar sus fondos ni pertenecer a nada.
"""

import re
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from identidad import seguridad
from identidad.servicio import (
    Conflicto,
    ContextoOrg,
    NoEncontrado,
    SolicitudInvalida,
    registrar_evento,
)
from infra.db import engine as engine_por_defecto
from infra.db import get_session_factory, init_db
from infra.db_models import (
    AlertPolicyRecord,
    AlertPolicyVersionRecord,
    IncidentRecord,
    MonitoredAccountRecord,
    OrgEventRecord,
)

_PATRON_DIRECCION = re.compile(r"^0x[0-9a-fA-F]{40}$")
PRIORIDADES = ("high", "medium", "low")
LIMITE_MAXIMO = 200


def _validar_direccion(direccion: str) -> str:
    if not isinstance(direccion, str) or not _PATRON_DIRECCION.match(direccion.strip()):
        raise SolicitudInvalida("Address must be a 0x-prefixed 20-byte hex string.")
    return direccion.strip().lower()


def _validar_limite(limite: int, desplazamiento: int) -> None:
    if not (1 <= limite <= LIMITE_MAXIMO) or desplazamiento < 0:
        raise SolicitudInvalida(f"limit must be 1..{LIMITE_MAXIMO} and offset >= 0.")


def _cuenta_a_dict(c: MonitoredAccountRecord) -> Dict[str, Any]:
    return {
        "id": c.id, "chain_id": c.chain_id, "address": c.address, "label": c.label,
        "priority": c.priority, "interval_seconds": c.interval_seconds, "relationship": "observed",
        "created_at": c.created_at, "last_evaluation_at": c.last_evaluation_at,
        "last_risk_score": c.last_risk_score, "last_decision": c.last_decision,
        "last_data_quality": c.last_data_quality,
    }


def _politica_a_dict(p: AlertPolicyRecord) -> Dict[str, Any]:
    return {"id": p.id, "account_id": p.account_id, "name": p.name, "rule": p.rule, "version": p.current_version,
            "enabled": p.enabled, "created_at": p.created_at, "updated_at": p.updated_at}


def validar_regla(regla: Dict[str, Any]) -> Dict[str, Any]:
    """Valido y normalizo con monitoreo.reglas (tipos versionados de E05)."""
    from monitoreo.reglas import ReglaInvalida, normalizar_regla

    try:
        return normalizar_regla(regla)
    except ReglaInvalida as error:
        raise SolicitudInvalida(str(error))


class ServicioRecursos:
    def __init__(self, engine_: Optional[Engine] = None):
        self._engine = engine_ or engine_por_defecto
        init_db(self._engine)
        self._Session = get_session_factory(self._engine)

    # --- cuentas observadas ---------------------------------------------------

    def _cuenta(self, s, ctx: ContextoOrg, account_id: str) -> MonitoredAccountRecord:
        cuenta = s.execute(
            select(MonitoredAccountRecord).where(
                MonitoredAccountRecord.id == account_id,
                MonitoredAccountRecord.organization_id == ctx.organization_id,
            )
        ).scalar_one_or_none()
        if cuenta is None:
            raise NoEncontrado("Account not found.")
        return cuenta

    def listar_cuentas(self, ctx: ContextoOrg, limite: int = 50, desplazamiento: int = 0) -> List[Dict[str, Any]]:
        _validar_limite(limite, desplazamiento)
        with self._Session() as s:
            cuentas = s.execute(
                select(MonitoredAccountRecord)
                .where(MonitoredAccountRecord.organization_id == ctx.organization_id)
                .order_by(MonitoredAccountRecord.created_at, MonitoredAccountRecord.id)
                .limit(limite).offset(desplazamiento)
            ).scalars().all()
            return [_cuenta_a_dict(c) for c in cuentas]

    def obtener_cuenta(self, ctx: ContextoOrg, account_id: str) -> Dict[str, Any]:
        with self._Session() as s:
            return _cuenta_a_dict(self._cuenta(s, ctx, account_id))

    def crear_cuenta(self, ctx: ContextoOrg, direccion: str, chain_id: int = 1, etiqueta: Optional[str] = None,
                     prioridad: str = "medium", intervalo_segundos: int = 300) -> Dict[str, Any]:
        ctx.exigir_rol("operator")
        direccion = _validar_direccion(direccion)
        from infra.config import settings

        # No hay multichain: solo acepto cuentas de la red del producto.
        if chain_id != settings.CHAIN_ID:
            raise SolicitudInvalida(f"Only chain_id {settings.CHAIN_ID} is supported.")
        if prioridad not in PRIORIDADES:
            raise SolicitudInvalida("priority must be high, medium or low.")
        if not isinstance(chain_id, int) or chain_id <= 0:
            raise SolicitudInvalida("chain_id must be a positive integer.")
        cuenta = MonitoredAccountRecord(
            id=seguridad.nuevo_id(), organization_id=ctx.organization_id, chain_id=chain_id, address=direccion,
            label=(etiqueta or None), priority=prioridad, interval_seconds=max(30, int(intervalo_segundos)),
            created_by_user_id=ctx.user_id, created_at=time.time(),
        )
        from comercial.suscripciones import ServicioSuscripciones

        with self._Session() as s:
            # Límites del plan (E09), con la suscripción bloqueada durante el alta.
            ServicioSuscripciones(self._engine).exigir_alta_de_cuenta(s, ctx.organization_id, chain_id, cuenta.interval_seconds)
            s.add(cuenta)
            registrar_evento(s, ctx.organization_id, "account.created",
                             {"account_id": cuenta.id, "chain_id": chain_id, "address": direccion}, ctx.user_id)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                raise Conflicto("This address is already monitored on that chain.")
            resultado = _cuenta_a_dict(cuenta)
        from comercial.analitica import registrar

        registrar(self._engine, ctx.organization_id, "account_added", {"role": ctx.role})
        return resultado

    def actualizar_cuenta(self, ctx: ContextoOrg, account_id: str, cambios: Dict[str, Any]) -> Dict[str, Any]:
        ctx.exigir_rol("operator")
        with self._Session() as s:
            cuenta = self._cuenta(s, ctx, account_id)
            if "label" in cambios:
                cuenta.label = cambios["label"] or None
            if "priority" in cambios:
                if cambios["priority"] not in PRIORIDADES:
                    raise SolicitudInvalida("priority must be high, medium or low.")
                cuenta.priority = cambios["priority"]
            if "interval_seconds" in cambios:
                from comercial.suscripciones import ServicioSuscripciones

                nuevo = max(30, int(cambios["interval_seconds"]))
                servicio = ServicioSuscripciones(self._engine)
                servicio.exigir_intervalo(servicio.derecho_en_sesion(s, ctx.organization_id), nuevo)
                cuenta.interval_seconds = nuevo
            registrar_evento(s, ctx.organization_id, "account.updated", {"account_id": cuenta.id}, ctx.user_id)
            s.commit()
            return _cuenta_a_dict(cuenta)

    def eliminar_cuenta(self, ctx: ContextoOrg, account_id: str) -> None:
        ctx.exigir_rol("operator")
        with self._Session() as s:
            cuenta = self._cuenta(s, ctx, account_id)
            s.delete(cuenta)
            registrar_evento(s, ctx.organization_id, "account.deleted", {"account_id": account_id}, ctx.user_id)
            s.commit()

    # --- políticas de alerta --------------------------------------------------

    def _politica(self, s, ctx: ContextoOrg, policy_id: str) -> AlertPolicyRecord:
        politica = s.execute(
            select(AlertPolicyRecord).where(AlertPolicyRecord.id == policy_id, AlertPolicyRecord.organization_id == ctx.organization_id)
        ).scalar_one_or_none()
        if politica is None:
            raise NoEncontrado("Policy not found.")
        return politica

    def versiones_politica(self, ctx: ContextoOrg, policy_id: str) -> List[Dict[str, Any]]:
        with self._Session() as s:
            self._politica(s, ctx, policy_id)
            versiones = s.execute(select(AlertPolicyVersionRecord).where(
                AlertPolicyVersionRecord.policy_id == policy_id,
                AlertPolicyVersionRecord.organization_id == ctx.organization_id,
            ).order_by(AlertPolicyVersionRecord.version)).scalars().all()
            return [{"version": v.version, "rule": v.rule, "created_at": v.created_at} for v in versiones]

    def listar_politicas(self, ctx: ContextoOrg, limite: int = 50, desplazamiento: int = 0) -> List[Dict[str, Any]]:
        _validar_limite(limite, desplazamiento)
        with self._Session() as s:
            politicas = s.execute(
                select(AlertPolicyRecord).where(AlertPolicyRecord.organization_id == ctx.organization_id)
                .order_by(AlertPolicyRecord.created_at, AlertPolicyRecord.id).limit(limite).offset(desplazamiento)
            ).scalars().all()
            return [_politica_a_dict(p) for p in politicas]

    def crear_politica(self, ctx: ContextoOrg, nombre: str, regla: Dict[str, Any],
                       account_id: Optional[str] = None, habilitada: bool = True) -> Dict[str, Any]:
        ctx.exigir_rol("operator")
        nombre = (nombre or "").strip()
        if not nombre or len(nombre) > 200:
            raise SolicitudInvalida("name is required (max 200 characters).")
        regla = validar_regla(regla)
        ahora = time.time()
        with self._Session() as s:
            if account_id is not None:
                self._cuenta(s, ctx, account_id)  # 404 si la cuenta es de otra organización
            politica = AlertPolicyRecord(
                id=seguridad.nuevo_id(), organization_id=ctx.organization_id, account_id=account_id, name=nombre,
                rule=regla, enabled=bool(habilitada), created_by_user_id=ctx.user_id, created_at=ahora, updated_at=ahora,
                current_version=1,
            )
            s.add(politica)
            s.flush()
            s.add(AlertPolicyVersionRecord(organization_id=ctx.organization_id, policy_id=politica.id, version=1, rule=regla,
                                           created_at=ahora, created_by_user_id=ctx.user_id))
            registrar_evento(s, ctx.organization_id, "policy.created", {"policy_id": politica.id, "version": 1}, ctx.user_id)
            s.commit()
            resultado = _politica_a_dict(politica)
        from comercial.analitica import registrar

        registrar(self._engine, ctx.organization_id, "policy_created", {"rule_type": regla["type"], "role": ctx.role})
        return resultado

    def actualizar_politica(self, ctx: ContextoOrg, policy_id: str, cambios: Dict[str, Any]) -> Dict[str, Any]:
        ctx.exigir_rol("operator")
        with self._Session() as s:
            politica = self._politica(s, ctx, policy_id)
            if "name" in cambios:
                nombre = (cambios["name"] or "").strip()
                if not nombre or len(nombre) > 200:
                    raise SolicitudInvalida("name is required (max 200 characters).")
                politica.name = nombre
            if "rule" in cambios:
                # Nunca edito una versión: creo la siguiente. Los incidentes
                # abiertos siguen apuntando a la versión que los abrió.
                nueva = validar_regla(cambios["rule"])
                if nueva != politica.rule:
                    politica.current_version += 1
                    politica.rule = nueva
                    s.add(AlertPolicyVersionRecord(organization_id=ctx.organization_id, policy_id=politica.id,
                                                   version=politica.current_version, rule=nueva, created_at=time.time(),
                                                   created_by_user_id=ctx.user_id))
            if "enabled" in cambios:
                politica.enabled = bool(cambios["enabled"])
            if "account_id" in cambios:
                if cambios["account_id"] is not None:
                    self._cuenta(s, ctx, cambios["account_id"])
                politica.account_id = cambios["account_id"]
            politica.updated_at = time.time()
            registrar_evento(s, ctx.organization_id, "policy.updated", {"policy_id": politica.id, "version": politica.current_version}, ctx.user_id)
            s.commit()
            return _politica_a_dict(politica)

    def eliminar_politica(self, ctx: ContextoOrg, policy_id: str) -> None:
        ctx.exigir_rol("operator")
        with self._Session() as s:
            politica = self._politica(s, ctx, policy_id)
            con_incidentes = s.execute(select(IncidentRecord.id).where(IncidentRecord.policy_id == policy_id,
                                                                       IncidentRecord.organization_id == ctx.organization_id)).first()
            if con_incidentes is not None:
                raise Conflicto("This policy has incidents; disable it instead of deleting it.")
            s.delete(politica)
            registrar_evento(s, ctx.organization_id, "policy.deleted", {"policy_id": policy_id}, ctx.user_id)
            s.commit()

    # --- eventos ----------------------------------------------------------------

    def validar_cursor(self, ctx: ContextoOrg, cursor: int) -> int:
        """Un cursor válido es 0 o el id de un evento de esta organización.

        Respondo 404 igual para un cursor inexistente y para uno de otra
        organización, así no revelo qué ids existen fuera de la mía.
        """
        if cursor < 0:
            raise SolicitudInvalida("cursor must be >= 0.")
        if cursor == 0:
            return 0
        with self._Session() as s:
            existe = s.execute(
                select(OrgEventRecord.id).where(OrgEventRecord.id == cursor, OrgEventRecord.organization_id == ctx.organization_id)
            ).first()
        if existe is None:
            raise NoEncontrado("Cursor not found.")
        return cursor

    def eventos_desde(self, ctx: ContextoOrg, cursor: int, limite: int = 100) -> List[Dict[str, Any]]:
        if not (1 <= limite <= LIMITE_MAXIMO):
            raise SolicitudInvalida(f"limit must be 1..{LIMITE_MAXIMO}.")
        with self._Session() as s:
            eventos = s.execute(
                select(OrgEventRecord)
                .where(OrgEventRecord.organization_id == ctx.organization_id, OrgEventRecord.id > cursor)
                .order_by(OrgEventRecord.id).limit(limite)
            ).scalars().all()
            return [{"id": e.id, "type": e.type, "payload": e.payload, "created_at": e.created_at} for e in eventos]

    # --- funciones de sistema para el worker ------------------------------------

    def cuentas_para_monitorear(self) -> List[Dict[str, Any]]:
        """Devuelvo las cuentas con su organization_id; el worker no ve nada más."""
        with self._Session() as s:
            cuentas = s.execute(select(MonitoredAccountRecord).order_by(MonitoredAccountRecord.created_at)).scalars().all()
            return [{"organization_id": c.organization_id, **_cuenta_a_dict(c)} for c in cuentas]

    def registrar_evaluacion(self, organization_id: str, account_id: str, decision: Optional[str],
                             riesgo: Optional[int], estado: str, calidad: Optional[str] = None) -> bool:
        """Guardo el resultado solo si la cuenta sigue perteneciendo a esa organización."""
        with self._Session() as s:
            cuenta = s.execute(
                select(MonitoredAccountRecord).where(
                    MonitoredAccountRecord.id == account_id, MonitoredAccountRecord.organization_id == organization_id
                )
            ).scalar_one_or_none()
            if cuenta is None:
                return False
            cuenta.last_evaluation_at = time.time()
            cuenta.last_data_quality = calidad
            if estado == "analyzed":
                cuenta.last_decision = decision
                if riesgo is not None:
                    cuenta.last_risk_score = int(riesgo)
            registrar_evento(s, organization_id, "account.analyzed",
                             {"account_id": account_id, "status": estado, "decision": decision, "risk_score": riesgo,
                              "data_quality": calidad}, None)
            s.commit()
            return True
