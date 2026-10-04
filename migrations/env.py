"""Entorno de Alembic de ChainSignal.

Uso la conexión que me pasa infra.db.init_db cuando existe; si corro
`alembic upgrade head` a mano, construyo el engine desde DATABASE_URL.
En PostgreSQL tomo un advisory lock transaccional para que la API y el worker
no migren a la vez al arrancar juntos.
"""

from alembic import context
from sqlalchemy import text

import infra.db_models  # noqa: F401  (registra los modelos)
from infra.db import Base, make_engine

target_metadata = Base.metadata
_LOCK_MIGRACIONES = 724_242_001


def _migrar(conexion) -> None:
    if conexion.dialect.name == "postgresql":
        conexion.execute(text("SELECT pg_advisory_xact_lock(:clave)"), {"clave": _LOCK_MIGRACIONES})
    context.configure(
        connection=conexion,
        target_metadata=target_metadata,
        render_as_batch=conexion.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conexion = context.config.attributes.get("connection")
    if conexion is not None:
        _migrar(conexion)
        return
    engine = make_engine()
    with engine.begin() as conexion_nueva:
        _migrar(conexion_nueva)


if context.is_offline_mode():
    raise SystemExit("No uso migraciones offline: corro alembic contra una base real.")
run_migrations_online()
