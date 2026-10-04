"""Entorno aislado para las pruebas E2E de la interfaz (E06).

Levanto la API y un worker de lectura contra una base SQLite temporal, sin leer
mi .env, sin red y con la lectura de Aave V3 reproducida desde la fixture
grabada. No hay ninguna conexión a producción ni a un RPC real.

    python scripts/entorno_e2e.py [--puerto 8001]

Termina (y se lleva el worker) cuando recibe Ctrl+C o cuando Playwright corta.
"""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = RAIZ / "tests" / "datos" / "aave_v3_prestatario_usdc_26116392.json"


def entorno(directorio: Path, origen_web: str) -> dict:
    return {
        **os.environ,
        "PYTHONPATH": str(RAIZ),
        "CHAINSIGNAL_DISABLE_DOTENV": "1",
        "CHAINSIGNAL_MODE": "READ_ONLY",
        "APP_ENV": "e2e",
        "CHAIN_ID": "1",
        "ETHEREUM_RPC_URL": "",
        "DATABASE_URL": f"sqlite:///{(directorio / 'e2e.sqlite3').as_posix()}",
        "AAVE_REPLAY_FIXTURE": str(FIXTURE),
        "SIGNUP_ENABLED": "true",
        "DEMO_ENABLED": "true",
        "NOTIFICATIONS_WEBHOOKS_ENABLED": "false",
        "CORS_ALLOWED_ORIGINS": origen_web,
        # Playwright navega por http://127.0.0.1; fuera de producción permito la cookie sin Secure.
        "SESSION_COOKIE_SECURE": "false",
        "WORKER_POLL_SECONDS": "0.5",
        "EVENT_STREAM_POLL_SECONDS": "0.5",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--puerto", type=int, default=8001)
    parser.add_argument("--origen-web", default="http://127.0.0.1:4173")
    args = parser.parse_args()

    directorio = Path(tempfile.mkdtemp(prefix="chainsignal-e2e-"))
    variables = entorno(directorio, args.origen_web)
    # Migro antes de arrancar los procesos para que no compitan por crear el esquema.
    subprocess.run([sys.executable, "-c", "from infra.db import init_db, engine; init_db(engine)"],
                   cwd=directorio, env=variables, check=True)
    worker = subprocess.Popen([sys.executable, "-m", "worker_lectura"], cwd=directorio, env=variables)
    try:
        subprocess.run([sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(args.puerto),
                        "--log-level", "warning"], cwd=directorio, env=variables, check=False)
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=10)
        except subprocess.TimeoutExpired:
            worker.kill()


if __name__ == "__main__":
    main()
