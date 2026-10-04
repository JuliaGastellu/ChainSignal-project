"""Motor y sesiones de base de datos para el estado durable de ChainSignal.

Planes de ejecución, historial y presupuestos vivían antes en JSON bajo
storage/ y no sobrevivían un archivo perdido o corrupto. Aquí conecto
SQLAlchemy para que ese estado sea durable y consultable.

Compose apunta DATABASE_URL al servicio Postgres `db`. Si la variable falta,
el desarrollo local cae en un SQLite temporal (_default_sqlite_url). Esa base
me sirve para pruebas unitarias, no para certificar concurrencia ni para
producción: esas propiedades las pruebo contra PostgreSQL.

El esquema se versiona con Alembic (migrations/). init_db aplica las
migraciones pendientes; ya no uso create_all. Todavía no resuelvo locking
distribuido, centralización de nonce ni reconciliación tras una caída.
"""
import os
import tempfile
import threading
import weakref
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

from infra.config import settings

Base = declarative_base()


def _default_sqlite_url() -> str:
    # No lo pongo bajo storage/ a propósito: este repositorio suele estar en
    # una carpeta sincronizada (OneDrive) y el cliente de sincronización
    # bloquea los archivos de journal de SQLite, lo que produce "disk I/O
    # error". Es solo un recurso de desarrollo local.
    # En Linux uso mi UID efectivo: la plataforma puede reemplazar el usuario
    # del contenedor y dejar el directorio de la imagen con otro propietario.
    nombre_directorio = f"chainsignal-{os.geteuid()}" if hasattr(os, "geteuid") else "chainsignal"
    db_path = Path(tempfile.gettempdir()) / nombre_directorio / "chainsignal.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"


def make_engine(database_url: Optional[str] = None) -> Engine:
    """Construyo un engine para la URL recibida, o settings.DATABASE_URL, o el
    SQLite local si no hay ninguna."""
    url = database_url or settings.DATABASE_URL or _default_sqlite_url()
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    elif url.startswith("postgresql"):
        # Una base que no responde no debe colgar un request ni un job (E08).
        connect_args = {"connect_timeout": settings.DB_CONNECT_TIMEOUT_SECONDS,
                        "options": f"-c statement_timeout={settings.DB_STATEMENT_TIMEOUT_MS}"}
    else:
        connect_args = {}
    nuevo = create_engine(url, connect_args=connect_args, future=True, pool_pre_ping=not url.startswith("sqlite"))
    if url.startswith("sqlite"):
        # SQLite no aplica claves foráneas salvo que lo pida en cada conexión.
        @event.listens_for(nuevo, "connect")
        def _activar_claves_foraneas(conexion_dbapi, _registro):
            cursor = conexion_dbapi.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return nuevo


# Engine y fábrica de sesiones por defecto para el código de producción. Las
# pruebas construyen su propio engine y lo pasan a cada servicio en lugar de
# mutar este global, así no comparten estado entre sí.
engine: Engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


_RAIZ = Path(__file__).resolve().parents[1]
# WeakSet y no id(engine): un id se reutiliza cuando el engine se libera, y un
# engine nuevo en la misma dirección se daba por migrado sin estarlo.
_migrados: "weakref.WeakSet[Engine]" = weakref.WeakSet()
_lock_migrados = threading.Lock()


class EsquemaDesactualizado(RuntimeError):
    """La base no está en la última migración y este proceso no migra."""


def _config_alembic():
    from alembic.config import Config

    config = Config(str(_RAIZ / "alembic.ini"))
    config.set_main_option("script_location", str(_RAIZ / "migrations"))
    return config


def revision_head() -> str:
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(_config_alembic()).get_current_head()


def revision_actual(engine_: Optional[Engine] = None) -> Optional[str]:
    from alembic.runtime.migration import MigrationContext

    with (engine_ or engine).connect() as conexion:
        return MigrationContext.configure(conexion).get_current_revision()


def init_db(engine_: Optional[Engine] = None) -> None:
    """Dejo el esquema en head antes de usar la base.

    Con DB_AUTO_MIGRATE (desarrollo y pruebas) aplico las migraciones
    pendientes; entre procesos, env.py serializa con un advisory lock de
    PostgreSQL. Sin DB_AUTO_MIGRATE (producción, varias réplicas) no migro:
    verifico que la base esté en head y, si no, me niego a arrancar. Las
    migraciones corren antes, como paso aparte (`alembic upgrade head`).

    Recuerdo qué engines ya preparé en este proceso para no repetir el trabajo.
    """
    from alembic import command

    target = engine_ or engine
    with _lock_migrados:
        if target in _migrados:
            return
        if settings.DB_AUTO_MIGRATE:
            config = _config_alembic()
            with target.begin() as conexion:
                config.attributes["connection"] = conexion
                command.upgrade(config, "head")
        else:
            actual, head = revision_actual(target), revision_head()
            if actual != head:
                raise EsquemaDesactualizado(f"Database schema is at {actual}, expected {head}; run the migration step first.")
        _migrados.add(target)


def get_session_factory(engine_: Optional[Engine] = None):
    target = engine_ or engine
    return sessionmaker(bind=target, autoflush=False, autocommit=False, future=True)
