"""Punto de entrada manual del experimento de ejecución en Sepolia.

Uso:
    CHAINSIGNAL_MODE=TESTNET_EXPERIMENT python -m experiments.cli ejecutar <wallet> --confirmo-testnet

Límites que verifico antes de construir cualquier cliente de firma:
- CHAINSIGNAL_MODE=TESTNET_EXPERIMENT y APP_ENV distinto de production;
- la bandera --confirmo-testnet, para que nadie lo dispare por accidente;
- el guard rechaza el plan si el chain_id leído no es Sepolia.

Nunca lo corro con una seed que controle fondos reales.
"""

import argparse
import asyncio
import json
import sys

from infra.modo import EscrituraDeshabilitada, exigir_escritura_experimental


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="experiments.cli")
    sub = parser.add_subparsers(dest="comando", required=True)
    ejecutar = sub.add_parser("ejecutar", help="Analizo una wallet y ejecuto la decisión en Sepolia si corresponde.")
    ejecutar.add_argument("wallet")
    ejecutar.add_argument("--confirmo-testnet", action="store_true")
    args = parser.parse_args(argv)

    if not args.confirmo_testnet:
        print("Falta --confirmo-testnet: no ejecuto sin confirmación explícita.", file=sys.stderr)
        return 2
    try:
        exigir_escritura_experimental("cli_experimento")
    except EscrituraDeshabilitada as e:
        print(str(e), file=sys.stderr)
        return 3

    from experiments.testnet_ejecucion import ExperimentoEjecucionTestnet

    resultado = asyncio.run(ExperimentoEjecucionTestnet().run_pipeline_loop(args.wallet))
    print(json.dumps(resultado, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
