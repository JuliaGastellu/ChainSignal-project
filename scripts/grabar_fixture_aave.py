"""Grabo una lectura pública de Aave V3 para reproducirla offline en las pruebas.

Es una integración opt-in: consulta un RPC de Ethereum mainnet de solo lectura
(sin claves de firma) y guarda cada eth_call y bloque leído:

    python -m scripts.grabar_fixture_aave --rpc https://... --usuario 0x... --bloque 26116000 \
        --salida tests/datos/aave_v3_ejemplo.json

No firma ni envía transacciones. Si el RPC no tiene el estado de ese bloque
(nodo sin archive), la lectura falla con archive_unavailable y no grabo nada.
"""

import argparse
import json
import sys
from pathlib import Path

from infra.red import ETHEREUM
from ingestion_onchain.proveedores import RpcLectura
from protocolos.aave_v3 import FUENTE_DIRECCIONES, AdaptadorAaveV3
from protocolos.replay import LectorGrabador, verificar_independiente


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="scripts.grabar_fixture_aave")
    parser.add_argument("--rpc", required=True)
    parser.add_argument("--usuario", required=True)
    parser.add_argument("--bloque", type=int, default=None, help="Bloque explícito; por defecto cabeza - 12 confirmaciones.")
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args(argv)

    grabador = LectorGrabador(RpcLectura(ETHEREUM, args.rpc))
    snapshot = AdaptadorAaveV3(grabador).leer_posicion(args.usuario, args.bloque)
    if snapshot.bloque is None:
        print(json.dumps(snapshot.presentar()["data_quality"]), file=sys.stderr)
        return 1
    verificacion = verificar_independiente(grabador, snapshot)
    grabador.guardar(args.salida, {
        "source": "public Ethereum mainnet RPC (read-only)",
        "addresses": FUENTE_DIRECCIONES,
        "user": snapshot.usuario,
        "block": snapshot.bloque.numero,
        "expected": snapshot.presentar()["raw"],
        "independent_check": verificacion,
    })
    print(json.dumps({"status": snapshot.estado, "quality": snapshot.calidad.value, "reconciled": snapshot.conciliacion,
                      "independent_check": verificacion}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
