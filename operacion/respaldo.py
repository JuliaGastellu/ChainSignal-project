"""Respaldo y restauración de PostgreSQL (E08).

    python -m operacion.respaldo respaldar  --proyecto P --compose deploy/compose.piloto.yml --salida respaldo.dump
    python -m operacion.respaldo restaurar  --proyecto P --compose deploy/compose.piloto.yml --entrada respaldo.dump
    python -m operacion.respaldo huella     --proyecto P --compose deploy/compose.piloto.yml

Uso pg_dump en formato custom dentro del contenedor `db`, así no dependo de
tener las herramientas de PostgreSQL en la máquina que opera. La huella cuenta
filas y resume ids de las tablas principales para comparar origen y copia.

Restaurar exige una base vacía: no piso datos existentes. El paso de
`--clean` lo dejo afuera a propósito.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# Tablas del producto con columna id (las heredadas del experimento quedan afuera).
TABLAS_HUELLA = [
    "organizations", "users", "memberships", "invitations", "sessions", "monitored_accounts", "alert_policies",
    "alert_policy_versions", "policy_account_states", "position_snapshots", "position_snapshot_assets", "incidents",
    "incident_evidence", "alerts", "notification_channels", "outbox", "notification_deliveries", "jobs", "org_events",
    "incident_explanations",
]


def _compose(proyecto: str, archivos: List[str]) -> List[str]:
    base = ["docker", "compose", "-p", proyecto]
    for archivo in archivos:
        base += ["-f", archivo]
    return base


def _psql(proyecto: str, archivos: List[str], sql: str, env: Optional[Dict[str, str]] = None) -> str:
    salida = subprocess.run(_compose(proyecto, archivos) + ["exec", "-T", "db", "psql", "-U", "chainsignal", "-d", "chainsignal",
                                                            "-At", "-v", "ON_ERROR_STOP=1", "-c", sql],
                            env=env, check=True, capture_output=True, text=True)
    return salida.stdout.strip()


def respaldar(proyecto: str, archivos: List[str], destino: Path, env: Optional[Dict[str, str]] = None) -> Dict[str, float]:
    inicio = time.monotonic()
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("wb") as archivo:
        subprocess.run(_compose(proyecto, archivos) + ["exec", "-T", "db", "pg_dump", "-U", "chainsignal", "-d", "chainsignal",
                                                       "-Fc", "--no-owner"], env=env, check=True, stdout=archivo)
    return {"seconds": round(time.monotonic() - inicio, 2), "bytes": destino.stat().st_size,
            "sha256": hashlib.sha256(destino.read_bytes()).hexdigest()}


def restaurar(proyecto: str, archivos: List[str], origen: Path, env: Optional[Dict[str, str]] = None) -> Dict[str, float]:
    tablas = _psql(proyecto, archivos, "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'", env)
    if int(tablas or 0) > 0:
        raise SystemExit("La base destino no está vacía; no restauro encima de datos existentes.")
    inicio = time.monotonic()
    with origen.open("rb") as archivo:
        subprocess.run(_compose(proyecto, archivos) + ["exec", "-T", "db", "pg_restore", "-U", "chainsignal", "-d", "chainsignal",
                                                       "--no-owner", "--exit-on-error"], env=env, check=True, stdin=archivo)
    return {"seconds": round(time.monotonic() - inicio, 2)}


def huella(proyecto: str, archivos: List[str], env: Optional[Dict[str, str]] = None) -> Dict[str, object]:
    resultado: Dict[str, object] = {"alembic_version": _psql(proyecto, archivos, "SELECT version_num FROM alembic_version", env)}
    for tabla in TABLAS_HUELLA:
        fila = _psql(proyecto, archivos, f"SELECT count(*) || ':' || coalesce(md5(string_agg(id::text, ',' ORDER BY id::text)), '') FROM {tabla}", env)
        resultado[tabla] = fila
    return resultado


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("accion", choices=["respaldar", "restaurar", "huella"])
    parser.add_argument("--proyecto", required=True)
    parser.add_argument("--compose", action="append", required=True)
    parser.add_argument("--salida")
    parser.add_argument("--entrada")
    args = parser.parse_args(argv)
    env = dict(os.environ)
    if args.accion == "respaldar":
        print(json.dumps(respaldar(args.proyecto, args.compose, Path(args.salida), env)))
    elif args.accion == "restaurar":
        print(json.dumps(restaurar(args.proyecto, args.compose, Path(args.entrada), env)))
    else:
        print(json.dumps(huella(args.proyecto, args.compose, env), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
