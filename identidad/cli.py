"""Administración de identidad desde la terminal.

    python -m identidad.cli crear-organizacion --nombre "Mi equipo" --email yo@ejemplo.com
    python -m identidad.cli importar-legado --organizacion <org_id> --chain-id 1
    python -m identidad.cli revocar-sesiones --email persona@ejemplo.com

No hay registro abierto: creo la primera organización y su owner desde aquí, y
el resto de las personas entra por invitación. La contraseña la leo de
CHAINSIGNAL_BOOTSTRAP_PASSWORD o la pido sin eco; nunca la recibo como argumento
para que no quede en el historial del shell.
"""

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from sqlalchemy import select

from identidad.recursos import ServicioRecursos
from identidad.servicio import ContextoOrg, Conflicto, ErrorIdentidad, ServicioIdentidad, normalizar_email
from infra.db_models import MembershipRecord, UserRecord


def _leer_contrasena() -> str:
    contrasena = os.getenv("CHAINSIGNAL_BOOTSTRAP_PASSWORD")
    if contrasena:
        return contrasena
    primera = getpass.getpass("Contraseña del owner: ")
    if primera != getpass.getpass("Repetí la contraseña: "):
        raise SystemExit("Las contraseñas no coinciden.")
    return primera


def _contexto_de_owner(identidad: ServicioIdentidad, organizacion: str) -> ContextoOrg:
    """Uso el primer owner de la organización como autor de la importación."""
    with identidad._Session() as s:
        membresia = s.execute(
            select(MembershipRecord).where(MembershipRecord.organization_id == organizacion, MembershipRecord.role == "owner")
            .order_by(MembershipRecord.created_at)
        ).scalars().first()
    if membresia is None:
        raise SystemExit("La organización no existe o no tiene owner.")
    return ContextoOrg(organizacion, membresia.user_id, "owner", membresia.id)


def _direcciones_legado(tracking: Optional[Path], watch: Optional[Path]) -> List[dict]:
    """Leo tracking.json y watched_wallets.json heredados sin modificarlos."""
    cuentas = {}
    if tracking and tracking.exists():
        for direccion, cfg in json.loads(tracking.read_text(encoding="utf-8-sig")).items():
            cuentas[direccion.lower()] = {
                "address": direccion, "label": None,
                "priority": cfg.get("priority", "medium") if cfg.get("priority") in {"high", "medium", "low"} else "medium",
                "interval_seconds": int(cfg.get("interval_seconds", 300) or 300),
            }
    if watch and watch.exists():
        for item in json.loads(watch.read_text(encoding="utf-8-sig")).get("wallets", []):
            direccion = str(item.get("address", ""))
            actual = cuentas.setdefault(direccion.lower(), {"address": direccion, "priority": "medium", "interval_seconds": 300, "label": None})
            actual["label"] = item.get("label") or actual.get("label")
    return list(cuentas.values())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="identidad.cli")
    sub = parser.add_subparsers(dest="comando", required=True)

    crear = sub.add_parser("crear-organizacion", help="Creo una organización y su primer owner.")
    crear.add_argument("--nombre", required=True)
    crear.add_argument("--email", required=True)

    importar = sub.add_parser("importar-legado", help="Importo tracking.json y watched_wallets.json como cuentas observadas.")
    importar.add_argument("--organizacion", required=True)
    importar.add_argument("--chain-id", type=int, required=True, help="Red de las direcciones heredadas; no la supongo.")
    importar.add_argument("--tracking", type=Path, default=Path("tracking.json"))
    importar.add_argument("--watch", type=Path, default=Path("watched_wallets.json"))

    revocar = sub.add_parser("revocar-sesiones", help="Revoco todas las sesiones de una persona.")
    revocar.add_argument("--email", required=True)

    args = parser.parse_args(argv)
    identidad = ServicioIdentidad()

    try:
        if args.comando == "crear-organizacion":
            org_id, user_id = identidad.crear_organizacion_con_owner(args.nombre, args.email, _leer_contrasena())
            print(json.dumps({"organization_id": org_id, "owner_user_id": user_id}))
        elif args.comando == "importar-legado":
            ctx = _contexto_de_owner(identidad, args.organizacion)
            recursos = ServicioRecursos()
            importadas, omitidas = 0, []
            for cuenta in _direcciones_legado(args.tracking, args.watch):
                try:
                    recursos.crear_cuenta(ctx, cuenta["address"], args.chain_id, cuenta.get("label"),
                                          cuenta["priority"], cuenta["interval_seconds"])
                    importadas += 1
                except Conflicto:
                    omitidas.append({"address": cuenta["address"], "reason": "already_monitored"})
                except ErrorIdentidad as e:
                    omitidas.append({"address": cuenta["address"], "reason": e.codigo})
            print(json.dumps({"imported": importadas, "skipped": omitidas}, indent=2))
        elif args.comando == "revocar-sesiones":
            email = normalizar_email(args.email)
            with identidad._Session() as s:
                usuario = s.execute(select(UserRecord).where(UserRecord.email == email)).scalar_one_or_none()
            if usuario is None:
                raise SystemExit("No existe una persona con ese email.")
            print(json.dumps({"revoked_sessions": identidad.revocar_sesiones_de_usuario(usuario.id)}))
    except ErrorIdentidad as e:
        print(f"{e.codigo}: {e.mensaje}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
