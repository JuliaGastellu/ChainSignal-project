"""Verifico on-chain, solo con lecturas, lo que el spike E10 da por cierto.

    python scripts/verificar_safe_onchain.py [--rpc URL]

- VERSION() de los singletons Safe 1.4.1 y GnosisSafe 1.3.0 de safe-deployments;
- que MultiSendCallOnly 1.4.1, el Pool de Aave V3, WETH y USDC tengan código;
- que mi safe_tx_hash coincida con getTransactionHash del contrato oficial para
  varias SafeTx (simple, MultiSend, con nonce alto). getTransactionHash es una
  función view: uso eth_call contra el singleton, sin firmar ni enviar nada.

Uso un RPC público de lectura. Guardo el resultado en docs/ensayos/safe-onchain.json.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from experiments.propuestas_safe.safe_tx import (  # noqa: E402
    AAVE_V3_POOL, GET_TRANSACTION_HASH, MULTISEND_CALL_ONLY_1_4_1, SAFE_SINGLETON_1_3_0, SAFE_SINGLETON_1_4_1, USDC, VERSION,
    WETH, aportar_colateral_weth, armar_safe_tx, repagar_usdc, safe_tx_hash,
)


def rpc(url: str, metodo: str, params: list):
    respuesta = requests.post(url, json={"jsonrpc": "2.0", "id": 1, "method": metodo, "params": params}, timeout=20,
                              headers={"User-Agent": "chainsignal-reader/0.3"})
    datos = respuesta.json()
    if "error" in datos:
        raise RuntimeError(datos["error"])
    return datos["result"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", default="https://ethereum-rpc.publicnode.com")
    args = parser.parse_args()
    if int(rpc(args.rpc, "eth_chainId", []), 16) != 1:
        raise SystemExit("El RPC no es Ethereum mainnet.")
    bloque = rpc(args.rpc, "eth_blockNumber", [])
    resultado = {"verified_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "block": int(bloque, 16), "versions": {}, "code": {}, "hashes": []}

    for nombre, direccion in (("Safe 1.4.1", SAFE_SINGLETON_1_4_1), ("GnosisSafe 1.3.0", SAFE_SINGLETON_1_3_0)):
        crudo = rpc(args.rpc, "eth_call", [{"to": direccion, "data": VERSION.codificar()}, bloque])
        resultado["versions"][nombre] = VERSION.decodificar(crudo)[0]
    for nombre, direccion in (("MultiSendCallOnly 1.4.1", MULTISEND_CALL_ONLY_1_4_1), ("Aave V3 Pool", AAVE_V3_POOL),
                              ("WETH", WETH), ("USDC", USDC)):
        resultado["code"][nombre] = len(rpc(args.rpc, "eth_getCode", [direccion, bloque])) > 2

    safe_ficticio = "0x000000000000000000000000000000000000c0de"
    casos = [
        ("supply WETH por MultiSend", armar_safe_tx(aportar_colateral_weth(safe_ficticio, 10**18)[0], 7)),
        ("repay USDC por MultiSend", armar_safe_tx(repagar_usdc(safe_ficticio, 2_500 * 10**6)[0], 123456)),
        ("una sola llamada", armar_safe_tx(aportar_colateral_weth(safe_ficticio, 5)[0][:1], 0)),
    ]
    for singleton in (SAFE_SINGLETON_1_4_1, SAFE_SINGLETON_1_3_0):
        for nombre, tx in casos:
            datos = GET_TRANSACTION_HASH.codificar(tx.to, tx.value, bytes.fromhex(tx.data[2:]), tx.operation, tx.safe_tx_gas,
                                                   tx.base_gas, tx.gas_price, tx.gas_token, tx.refund_receiver, tx.nonce)
            del_contrato = "0x" + GET_TRANSACTION_HASH.decodificar(rpc(args.rpc, "eth_call", [{"to": singleton, "data": datos}, bloque]))[0].hex()
            mio = safe_tx_hash(1, singleton, tx)
            resultado["hashes"].append({"singleton": singleton, "case": nombre, "nonce": tx.nonce, "contract_hash": del_contrato,
                                        "match": mio == del_contrato})

    resultado["all_ok"] = (resultado["versions"] == {"Safe 1.4.1": "1.4.1", "GnosisSafe 1.3.0": "1.3.0"}
                           and all(resultado["code"].values()) and all(h["match"] for h in resultado["hashes"]))
    destino = RAIZ / "docs" / "ensayos" / "safe-onchain.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
    return 0 if resultado["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
