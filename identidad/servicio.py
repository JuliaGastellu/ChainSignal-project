"""Organizaciones, usuarios, membresías, invitaciones y sesiones.

La autorización vive aquí y no solo en las rutas: cada operación sobre una
organización recibe un ContextoOrg que solo construyo después de verificar en
la base que la sesión es válida y que la persona es miembro con el rol
necesario. Nunca tomo un organization_id del cliente sin esa verificación.
"""

import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from identidad import seguridad
from infra.config import settings
from infra.db import engine as engine_por_defecto
from infra.db import get_session_factory, init_db
from infra.db_models import (
    InvitationRecord,
    MembershipRecord,
    OrganizationRecord,
    OrgEventRecord,
    SessionRecord,
    UserRecord,
)

ORDEN_ROLES = {"viewer": 0, "operator": 1, "owner": 2}
_PATRON_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ErrorIdentidad(Exception):
    estado = 400
    codigo = "bad_request"

    def __init__(self, mensaje: str = ""):
        super().__init__(mensaje or self.codigo)
        self.mensaje = mensaje or self.codigo


class NoAutenticado(ErrorIdentidad):
    estado = 401
    codigo = "not_authenticated"


class Prohibido(ErrorIdentidad):
    estado = 403
    codigo = "forbidden"


class NoEncontrado(ErrorIdentidad):
    estado = 404
    codigo = "not_found"


class Conflicto(ErrorIdentidad):
    estado = 409
    codigo = "conflict"


class SolicitudInvalida(ErrorIdentidad):
    estado = 422
    codigo = "invalid_request"


@dataclass(frozen=True)
class SesionActiva:
    session_id: str
    user_id: str
    email: str
    expires_at: float
    csrf_hash: str


@dataclass(frozen=True)
class ContextoOrg:
    """Prueba de que verifiqué sesión, membresía y rol para una organización."""

    organization_id: str
    user_id: str
    role: str
    membership_id: str

    def exigir_rol(self, rol_minimo: str) -> None:
        if ORDEN_ROLES[self.role] < ORDEN_ROLES[rol_minimo]:
            raise Prohibido(f"This action requires role '{rol_minimo}' or higher.")


def normalizar_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not _PATRON_EMAIL.match(email) or len(email) > 320:
        raise SolicitudInvalida("Invalid email address.")
    return email


def _validar_rol(rol: str) -> str:
    if rol not in ORDEN_ROLES:
        raise SolicitudInvalida("Role must be owner, operator or viewer.")
    return rol


def _hash_de_contrasena(contrasena: Optional[str]) -> str:
    try:
        return seguridad.hashear_contrasena(contrasena or "")
    except seguridad.ContrasenaInvalida as e:
        raise SolicitudInvalida(str(e))


def registrar_evento(sesion_db, organization_id: str, tipo: str, payload: Dict[str, Any], actor_user_id: Optional[str]) -> None:
    """Agrego un evento a la organización dentro de la transacción en curso.

    El payload nunca incluye tokens, hashes ni contraseñas.
    """
    sesion_db.add(OrgEventRecord(
        organization_id=organization_id,
        type=tipo,
        payload=payload,
        actor_user_id=actor_user_id,
        created_at=time.time(),
    ))


class ServicioIdentidad:
    def __init__(self, engine_: Optional[Engine] = None):
        self._engine = engine_ or engine_por_defecto
        init_db(self._engine)
        self._Session = get_session_factory(self._engine)

    # --- organizaciones y usuarios -------------------------------------------

    def registrar(self, email: str, contrasena: str, nombre_organizacion: str) -> Tuple[str, str]:
        """Alta autoservicio (si SIGNUP_ENABLED): persona nueva y su organización.

        No uso un email ya registrado para crear otra cuenta: esa persona inicia
        sesión. El mensaje no confirma si el email existe.
        """
        email = normalizar_email(email)
        with self._Session() as s:
            if s.execute(select(UserRecord.id).where(UserRecord.email == email)).first() is not None:
                raise Conflicto("This email cannot be used to sign up. If you already have an account, log in.")
        return self.crear_organizacion_con_owner(nombre_organizacion, email, contrasena)

    def organizacion(self, organization_id: str) -> Dict[str, Any]:
        with self._Session() as s:
            org = s.get(OrganizationRecord, organization_id)
            if org is None:
                raise NoEncontrado("Organization not found.")
            return {"id": org.id, "name": org.name, "is_demo": bool(org.is_demo), "expires_at": org.expires_at}

    def crear_organizacion_con_owner(self, nombre: str, email: str, contrasena: str, es_demo: bool = False,
                                     vence_en: Optional[float] = None) -> Tuple[str, str]:
        """Creo una organización y su primer owner (CLI de arranque, alta o demo)."""
        nombre = (nombre or "").strip()
        if not nombre or len(nombre) > 200:
            raise SolicitudInvalida("Organization name is required (max 200 characters).")
        email = normalizar_email(email)
        ahora = time.time()
        with self._Session() as s:
            usuario = s.execute(select(UserRecord).where(UserRecord.email == email)).scalar_one_or_none()
            if usuario is None:
                usuario = UserRecord(id=seguridad.nuevo_id(), email=email, password_hash=_hash_de_contrasena(contrasena), created_at=ahora)
                s.add(usuario)
            org = OrganizationRecord(id=seguridad.nuevo_id(), name=nombre, created_at=ahora, is_demo=es_demo, expires_at=vence_en)
            s.add(org)
            s.flush()
            s.add(MembershipRecord(id=seguridad.nuevo_id(), organization_id=org.id, user_id=usuario.id, role="owner", created_at=ahora))
            if not es_demo:
                from comercial.suscripciones import ServicioSuscripciones

                # Toda organización real nace con una prueba de 14 días (E09).
                s.add(ServicioSuscripciones.nueva_prueba(org.id, ahora))
            registrar_evento(s, org.id, "organization.created", {"name": nombre}, usuario.id)
            s.commit()
            org_id, user_id = org.id, usuario.id
        from comercial.analitica import registrar

        registrar(self._engine, org_id, "org_created", {"role": "owner"})
        return org_id, user_id

    def autenticar(self, email: str, contrasena: str) -> str:
        """Devuelvo el user_id o NoAutenticado, con el mismo mensaje para email
        desconocido, contraseña errónea o usuario deshabilitado."""
        try:
            email = normalizar_email(email)
        except SolicitudInvalida:
            seguridad.verificar_contra_senuelo(contrasena or "")
            raise NoAutenticado("Invalid email or password.")
        with self._Session() as s:
            usuario = s.execute(select(UserRecord).where(UserRecord.email == email)).scalar_one_or_none()
        if usuario is None:
            seguridad.verificar_contra_senuelo(contrasena or "")
            raise NoAutenticado("Invalid email or password.")
        if not seguridad.verificar_contrasena(contrasena or "", usuario.password_hash) or usuario.disabled_at is not None:
            raise NoAutenticado("Invalid email or password.")
        return usuario.id

    # --- sesiones -------------------------------------------------------------

    def crear_sesion(self, user_id: str) -> Tuple[str, str, SesionActiva]:
        """Devuelvo (token de sesión, token CSRF, sesión). Solo persisto sus hashes."""
        token, csrf = seguridad.nuevo_token(), seguridad.nuevo_token()
        ahora = time.time()
        expira = ahora + settings.SESSION_TTL_HOURS * 3600
        with self._Session() as s:
            usuario = s.get(UserRecord, user_id)
            if usuario is None or usuario.disabled_at is not None:
                raise NoAutenticado()
            registro = SessionRecord(
                id=seguridad.nuevo_id(), user_id=user_id, token_hash=seguridad.hashear_token(token),
                csrf_hash=seguridad.hashear_token(csrf), created_at=ahora, expires_at=expira, last_seen_at=ahora,
            )
            s.add(registro)
            s.commit()
            return token, csrf, SesionActiva(registro.id, user_id, usuario.email, expira, registro.csrf_hash)

    def sesion_por_token(self, token: Optional[str]) -> SesionActiva:
        if not token:
            raise NoAutenticado()
        ahora = time.time()
        with self._Session() as s:
            fila = s.execute(
                select(SessionRecord, UserRecord)
                .join(UserRecord, UserRecord.id == SessionRecord.user_id)
                .where(SessionRecord.token_hash == seguridad.hashear_token(token))
            ).first()
            if fila is None:
                raise NoAutenticado()
            registro, usuario = fila
            if registro.revoked_at is not None or registro.expires_at <= ahora or usuario.disabled_at is not None:
                raise NoAutenticado()
            if not registro.last_seen_at or ahora - registro.last_seen_at > 60:
                registro.last_seen_at = ahora
                s.commit()
            return SesionActiva(registro.id, usuario.id, usuario.email, registro.expires_at, registro.csrf_hash)

    def sesion_sigue_valida(self, session_id: str) -> bool:
        with self._Session() as s:
            registro = s.get(SessionRecord, session_id)
            return bool(registro and registro.revoked_at is None and registro.expires_at > time.time())

    def revocar_sesion(self, session_id: str) -> None:
        with self._Session() as s:
            registro = s.get(SessionRecord, session_id)
            if registro is not None and registro.revoked_at is None:
                registro.revoked_at = time.time()
                s.commit()

    def revocar_sesiones_de_usuario(self, user_id: str) -> int:
        ahora = time.time()
        with self._Session() as s:
            registros = s.execute(select(SessionRecord).where(SessionRecord.user_id == user_id, SessionRecord.revoked_at.is_(None))).scalars().all()
            for registro in registros:
                registro.revoked_at = ahora
            s.commit()
            return len(registros)

    # --- membresías y contexto -----------------------------------------------

    def membresias(self, user_id: str) -> List[Dict[str, Any]]:
        with self._Session() as s:
            filas = s.execute(
                select(MembershipRecord, OrganizationRecord)
                .join(OrganizationRecord, OrganizationRecord.id == MembershipRecord.organization_id)
                .where(MembershipRecord.user_id == user_id)
                .order_by(OrganizationRecord.name)
            ).all()
            return [{"organization_id": o.id, "organization_name": o.name, "role": m.role, "membership_id": m.id} for m, o in filas]

    def contexto(self, sesion: SesionActiva, organization_id: str, rol_minimo: str = "viewer") -> ContextoOrg:
        """Verifico en la base que la sesión pertenece a un miembro de la organización."""
        if not self.sesion_sigue_valida(sesion.session_id):
            raise NoAutenticado()
        with self._Session() as s:
            membresia = s.execute(
                select(MembershipRecord).where(
                    MembershipRecord.organization_id == organization_id,
                    MembershipRecord.user_id == sesion.user_id,
                )
            ).scalar_one_or_none()
        if membresia is None:
            raise Prohibido("You are not a member of this organization.")
        with self._Session() as s:
            org = s.get(OrganizationRecord, organization_id)
            if org is not None and org.expires_at is not None and org.expires_at <= time.time():
                raise Prohibido("This demo organization has expired.")
        ctx = ContextoOrg(organization_id, sesion.user_id, membresia.role, membresia.id)
        ctx.exigir_rol(rol_minimo)
        return ctx

    def listar_miembros(self, ctx: ContextoOrg) -> List[Dict[str, Any]]:
        with self._Session() as s:
            filas = s.execute(
                select(MembershipRecord, UserRecord)
                .join(UserRecord, UserRecord.id == MembershipRecord.user_id)
                .where(MembershipRecord.organization_id == ctx.organization_id)
                .order_by(UserRecord.email)
            ).all()
            return [{"membership_id": m.id, "user_id": u.id, "email": u.email, "role": m.role, "created_at": m.created_at} for m, u in filas]

    def _membresia_de_org(self, s, ctx: ContextoOrg, membership_id: str, bloquear: bool = False) -> MembershipRecord:
        consulta = select(MembershipRecord).where(
            MembershipRecord.id == membership_id, MembershipRecord.organization_id == ctx.organization_id
        )
        if bloquear:
            consulta = consulta.with_for_update()
        membresia = s.execute(consulta).scalar_one_or_none()
        if membresia is None:
            raise NoEncontrado("Membership not found.")
        return membresia

    def _owners_bloqueados(self, s, organization_id: str) -> int:
        # Bloqueo las filas owner para que dos cambios simultáneos no dejen la
        # organización sin owner.
        filas = s.execute(
            select(MembershipRecord.id)
            .where(MembershipRecord.organization_id == organization_id, MembershipRecord.role == "owner")
            .with_for_update()
        ).all()
        return len(filas)

    def cambiar_rol(self, ctx: ContextoOrg, membership_id: str, nuevo_rol: str) -> Dict[str, Any]:
        ctx.exigir_rol("owner")
        nuevo_rol = _validar_rol(nuevo_rol)
        with self._Session() as s:
            owners = self._owners_bloqueados(s, ctx.organization_id)
            membresia = self._membresia_de_org(s, ctx, membership_id, bloquear=True)
            if membresia.role == "owner" and nuevo_rol != "owner" and owners <= 1:
                raise Conflicto("An organization must keep at least one owner.")
            anterior = membresia.role
            membresia.role = nuevo_rol
            registrar_evento(s, ctx.organization_id, "membership.role_changed",
                             {"membership_id": membresia.id, "from": anterior, "to": nuevo_rol}, ctx.user_id)
            s.commit()
            return {"membership_id": membresia.id, "user_id": membresia.user_id, "role": membresia.role}

    def quitar_miembro(self, ctx: ContextoOrg, membership_id: str) -> None:
        ctx.exigir_rol("owner")
        with self._Session() as s:
            owners = self._owners_bloqueados(s, ctx.organization_id)
            membresia = self._membresia_de_org(s, ctx, membership_id, bloquear=True)
            if membresia.role == "owner" and owners <= 1:
                raise Conflicto("An organization must keep at least one owner.")
            s.delete(membresia)
            registrar_evento(s, ctx.organization_id, "membership.removed", {"membership_id": membership_id}, ctx.user_id)
            s.commit()

    # --- invitaciones ---------------------------------------------------------

    @staticmethod
    def _invitacion_a_dict(inv: InvitationRecord) -> Dict[str, Any]:
        if inv.revoked_at:
            estado = "revoked"
        elif inv.accepted_at:
            estado = "accepted"
        elif inv.expires_at <= time.time():
            estado = "expired"
        else:
            estado = "pending"
        return {"id": inv.id, "email": inv.email, "role": inv.role, "status": estado,
                "created_at": inv.created_at, "expires_at": inv.expires_at}

    def invitar(self, ctx: ContextoOrg, email: str, rol: str) -> Tuple[Dict[str, Any], str]:
        """Creo una invitación y devuelvo su token una sola vez; no lo vuelvo a mostrar."""
        ctx.exigir_rol("owner")
        email = normalizar_email(email)
        rol = _validar_rol(rol)
        token = seguridad.nuevo_token()
        ahora = time.time()
        with self._Session() as s:
            ya_miembro = s.execute(
                select(MembershipRecord.id)
                .join(UserRecord, UserRecord.id == MembershipRecord.user_id)
                .where(MembershipRecord.organization_id == ctx.organization_id, UserRecord.email == email)
            ).first()
            if ya_miembro is not None:
                raise Conflicto("That person is already a member.")
            inv = InvitationRecord(
                id=seguridad.nuevo_id(), organization_id=ctx.organization_id, email=email, role=rol,
                token_hash=seguridad.hashear_token(token), invited_by_user_id=ctx.user_id,
                created_at=ahora, expires_at=ahora + settings.INVITATION_TTL_HOURS * 3600,
            )
            s.add(inv)
            registrar_evento(s, ctx.organization_id, "invitation.created", {"invitation_id": inv.id, "email": email, "role": rol}, ctx.user_id)
            s.commit()
            return self._invitacion_a_dict(inv), token

    def listar_invitaciones(self, ctx: ContextoOrg) -> List[Dict[str, Any]]:
        ctx.exigir_rol("owner")
        with self._Session() as s:
            invitaciones = s.execute(
                select(InvitationRecord).where(InvitationRecord.organization_id == ctx.organization_id).order_by(InvitationRecord.created_at.desc())
            ).scalars().all()
            return [self._invitacion_a_dict(i) for i in invitaciones]

    def revocar_invitacion(self, ctx: ContextoOrg, invitation_id: str) -> None:
        ctx.exigir_rol("owner")
        with self._Session() as s:
            inv = s.execute(
                select(InvitationRecord).where(InvitationRecord.id == invitation_id, InvitationRecord.organization_id == ctx.organization_id)
            ).scalar_one_or_none()
            if inv is None:
                raise NoEncontrado("Invitation not found.")
            if inv.accepted_at is None and inv.revoked_at is None:
                inv.revoked_at = time.time()
                registrar_evento(s, ctx.organization_id, "invitation.revoked", {"invitation_id": inv.id}, ctx.user_id)
                s.commit()

    def aceptar_invitacion(self, token: str, sesion: Optional[SesionActiva], contrasena: Optional[str]) -> Tuple[str, str, bool]:
        """Acepto una invitación de un solo uso. Devuelvo (user_id, organization_id, usuario_nuevo).

        Con sesión, el email de la sesión debe coincidir con el invitado. Sin
        sesión, creo el usuario si el email no existe; si existe, pido iniciar
        sesión primero. Bloqueo la fila para que dos aceptaciones simultáneas
        del mismo token no generen dos membresías.
        """
        if not token:
            raise NoEncontrado("Invitation not found.")
        ahora = time.time()
        with self._Session() as s:
            inv = s.execute(
                select(InvitationRecord).where(InvitationRecord.token_hash == seguridad.hashear_token(token)).with_for_update()
            ).scalar_one_or_none()
            if inv is None or inv.revoked_at is not None or inv.accepted_at is not None or inv.expires_at <= ahora:
                # Mismo error para inexistente, usada, revocada o vencida.
                raise NoEncontrado("Invitation not found or no longer valid.")

            usuario_nuevo = False
            if sesion is not None:
                if sesion.email != inv.email:
                    raise Prohibido("This invitation was issued to a different email.")
                user_id = sesion.user_id
            else:
                existente = s.execute(select(UserRecord).where(UserRecord.email == inv.email)).scalar_one_or_none()
                if existente is not None:
                    raise NoAutenticado("Log in with the invited email to accept this invitation.")
                usuario = UserRecord(id=seguridad.nuevo_id(), email=inv.email,
                                     password_hash=_hash_de_contrasena(contrasena), created_at=ahora)
                s.add(usuario)
                s.flush()
                user_id, usuario_nuevo = usuario.id, True

            ya_miembro = s.execute(
                select(MembershipRecord.id).where(MembershipRecord.organization_id == inv.organization_id, MembershipRecord.user_id == user_id)
            ).first()
            if ya_miembro is None:
                s.add(MembershipRecord(id=seguridad.nuevo_id(), organization_id=inv.organization_id, user_id=user_id, role=inv.role, created_at=ahora))
            inv.accepted_at = ahora
            inv.accepted_by_user_id = user_id
            registrar_evento(s, inv.organization_id, "invitation.accepted", {"invitation_id": inv.id, "role": inv.role}, user_id)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                raise Conflicto("The invitation could not be accepted; try again.")
            return user_id, inv.organization_id, usuario_nuevo

    def contar_owners(self, organization_id: str) -> int:
        with self._Session() as s:
            return s.execute(
                select(func.count()).select_from(MembershipRecord)
                .where(MembershipRecord.organization_id == organization_id, MembershipRecord.role == "owner")
            ).scalar_one()
