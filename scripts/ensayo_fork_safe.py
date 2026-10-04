"""Ensayo del spike E10 en un fork aislado de Ethereum mainnet (anvil).

    python scripts/ensayo_fork_safe.py [--rpc URL]

Levanto anvil en Docker con un fork de mainnet (lecturas del RPC público,
ninguna transacción real). En el fork:

1. despliego un Safe 1.4.1 con la ProxyFactory oficial, con un owner y umbral 1;
   el owner es una cuenta desbloqueada de anvil y hace de "persona del cliente";
   mi código no maneja claves;
2. simulo la SafeTx exacta (snapshot, ejecución y revert) y armo la intención con esa simulación;
3. la persona aprueba la huella y "ejecuta" con la firma pre-aprobada de Safe
   (msg.sender == owner, v = 1), que no es una firma criptográfica;
4. reconcilio leyendo eventos ExecutionSuccess del Safe y el efecto en aWETH.

Escenarios:

- **feliz:** CONFIRMADA solo si el efecto esperado aparece;
- **receipt sin efecto:** receipt exitoso sin el efecto declarado, queda FALLIDA;
- **simulación vieja y payload alterado:** se rechazan antes de entregar;
- **nonce usado por otra transacción:** se detecta al reconciliar.

Guardo el resultado en docs/ensayos/safe-fork.json y bajo el contenedor.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from eth_abi import encode
from eth_utils import keccak, to_checksum_address

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from experiments.propuestas_safe import coordinador as c  # noqa: E402
from experiments.propuestas_safe.propuesta import Contexto, Simulacion, aprobar, crear_intencion, reemplazar, validar_para_envio  # noqa: E402
from experiments.propuestas_safe.safe_tx import (  # noqa: E402
    A_WETH, AAVE_V3_POOL, NONCE, SAFE_SINGLETON_1_4_1, USDC_DEUDA_VARIABLE, WETH,
)
from protocolos.abi import Funcion  # noqa: E402

FABRICA = "0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67"  # SafeProxyFactory 1.4.1 (safe-deployments)
URL = "http://127.0.0.1:8545"
CONTENEDOR = "cs-e10-anvil"
SETUP = Funcion("setup", ("address[]", "uint256", "address", "bytes", "address", "address", "uint256", "address"), ())
CREAR = Funcion("createProxyWithNonce", ("address", "bytes", "uint256"), ("address",))
EXEC = Funcion("execTransaction", ("address", "uint256", "bytes", "uint8", "uint256", "uint256", "uint256", "address", "address", "bytes"),
               ("bool",))
BALANCE = Funcion("balanceOf", ("address",), ("uint256",))
PROXY_CREATION = "0x" + keccak(text="ProxyCreation(address,address)").hex()
EXEC_OK = "0x" + keccak(text="ExecutionSuccess(bytes32,uint256)").hex()
EXEC_FALLO = "0x" + keccak(text="ExecutionFailure(bytes32,uint256)").hex()


def rpc(metodo: str, params: list, url: str = URL) -> Any:
    datos = requests.post(url, json={"jsonrpc": "2.0", "id": 1, "method": metodo, "params": params}, timeout=120).json()
    if "error" in datos:
        raise RuntimeError(f"{metodo}: {datos['error']}")
    return datos["result"]


def llamar(destino: str, funcion: Funcion, *args, bloque: str = "latest") -> Any:
    return funcion.decodificar(rpc("eth_call", [{"to": destino, "data": funcion.codificar(*args)}, bloque]))[0]


def enviar(desde: str, destino: str, data: str, valor: int = 0) -> Dict[str, Any]:
    h = rpc("eth_sendTransaction", [{"from": desde, "to": destino, "data": data, "value": hex(valor), "gas": hex(3_000_000)}])
    for _ in range(120):  # el fork trae estado remoto: la primera minería puede tardar
        recibo = rpc("eth_getTransactionReceipt", [h])
        if recibo:
            return recibo
        time.sleep(0.5)
    raise RuntimeError(f"no receipt for {h}")


class Fork:
    def __init__(self, owner: str):
        self.owner = owner

    def desplegar_safe(self) -> str:
        inicial = SETUP.codificar([self.owner], 1, "0x" + "00" * 20, b"", "0x" + "00" * 20, "0x" + "00" * 20, 0, "0x" + "00" * 20)
        recibo = enviar(self.owner, FABRICA, CREAR.codificar(SAFE_SINGLETON_1_4_1, bytes.fromhex(inicial[2:]), int(time.time())))
        log = next(lg for lg in recibo["logs"] if lg["topics"][0] == PROXY_CREATION)
        return to_checksum_address("0x" + log["topics"][1][-40:])

    def ejecutar(self, safe: str, tx) -> Dict[str, Any]:
        firma = bytes.fromhex(self.owner[2:].lower().rjust(64, "0")) + b"\x00" * 32 + b"\x01"  # pre-aprobada: v = 1
        data = EXEC.codificar(tx.to, tx.value, bytes.fromhex(tx.data[2:]), tx.operation, tx.safe_tx_gas, tx.base_gas, tx.gas_price,
                              tx.gas_token, tx.refund_receiver, firma)
        return enviar(self.owner, safe, data)

    def digest(self, safe: str) -> str:
        partes = [rpc("eth_getBalance", [safe, "latest"]), str(llamar(A_WETH, BALANCE, safe)), str(llamar(safe, NONCE))]
        return hashlib.sha256("|".join(partes).encode()).hexdigest()

    def simular(self, safe: str, tx, monto: int) -> Simulacion:
        bloque = rpc("eth_getBlockByNumber", ["latest", False])
        digest = self.digest(safe)
        antes = llamar(A_WETH, BALANCE, safe)
        foto = rpc("evm_snapshot", [])
        try:
            recibo = self.ejecutar(safe, tx)
            ok = int(recibo["status"], 16) == 1 and any(lg["topics"][0] == EXEC_OK for lg in recibo["logs"])
            delta = llamar(A_WETH, BALANCE, safe) - antes
            gas, precio = int(recibo["gasUsed"], 16), int(recibo["effectiveGasPrice"], 16)
        finally:
            rpc("evm_revert", [foto])
        return Simulacion(block_number=int(bloque["number"], 16), block_hash=bloque["hash"], ok=ok, state_digest=digest,
                          gas_estimate=gas, fee_estimate_wei=gas * precio,
                          expected_changes=[{"token": "aWETH", "delta": f"+{delta}"}, {"token": "ETH", "delta": f"-{monto}"}],
                          approvals=[{"token": "WETH", "spender": AAVE_V3_POOL, "amount": str(monto)}])


class ConsultaFork:
    def __init__(self, safe: str, desde_bloque: int):
        # El Safe nace dentro del fork: no busco antes, así no pido historia de archivo al RPC público.
        self.safe, self.desde = safe, hex(desde_bloque)

    def buscar(self, safe_tx_hash: str) -> Optional[Dict[str, Any]]:
        for lg in rpc("eth_getLogs", [{"address": self.safe, "fromBlock": self.desde, "toBlock": "latest", "topics": [[EXEC_OK, EXEC_FALLO]]}]):
            # Safe 1.4.1 indexa txHash (topics[1]); Safe 1.3.0 lo emite en data. Acepto los dos.
            emitido = lg["topics"][1] if len(lg["topics"]) > 1 else "0x" + lg["data"][2:66]
            if emitido.lower() == safe_tx_hash.lower():
                return {"executed": True, "success": lg["topics"][0] == EXEC_OK, "tx_hash": lg["transactionHash"]}
        return None

    def nonce_actual(self, safe: str) -> int:
        return llamar(safe, NONCE)

    def efecto(self, esperado: Dict[str, Any], tx_hash: str) -> bool:
        recibo = rpc("eth_getTransactionReceipt", [tx_hash])
        bloque = int(recibo["blockNumber"], 16)
        antes = llamar(esperado["token"], BALANCE, esperado["holder"], bloque=hex(bloque - 1))
        despues = llamar(esperado["token"], BALANCE, esperado["holder"], bloque=hex(bloque))
        cambio = despues - antes if esperado["direction"] == "increase" else antes - despues
        return cambio >= int(esperado["min_delta"])


class TransporteFork:
    """En el fork no hay Transaction Service: entregar es dejarle la propuesta a la persona."""

    def entregar(self, intencion) -> str:
        return intencion.safe_tx_hash


def contexto(fork: Fork, safe: str, intencion) -> Contexto:
    return Contexto(chain_id=int(rpc("eth_chainId", []), 16), nonce_safe=llamar(safe, NONCE),
                    bloque_actual=int(rpc("eth_blockNumber", []), 16), state_digest_actual=fork.digest(safe), ahora=time.time())


def propuesta(fork: Fork, safe: str, monto: int, efecto_falso: bool = False):
    nonce = llamar(safe, NONCE)
    base = crear_intencion("org-fork", 1, safe, safe, "pol-hf", 1, "aportar_colateral_weth", {"monto_wei": monto}, nonce,
                           Simulacion(0, "0x", True, "", 0, 0, [], []), time.time())
    intencion = reemplazar(base, simulacion=fork.simular(safe, base.safe_tx, monto))
    if efecto_falso:
        intencion = reemplazar(intencion, efecto_esperado={"token": USDC_DEUDA_VARIABLE, "holder": safe, "direction": "decrease",
                                                          "min_delta": "1"})
    return intencion


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rpc", default="https://ethereum-rpc.publicnode.com")
    args = parser.parse_args()
    cabeza = int(rpc("eth_blockNumber", [], args.rpc), 16)
    subprocess.run(["docker", "rm", "-f", CONTENEDOR], capture_output=True)
    subprocess.run(["docker", "run", "-d", "--rm", "--name", CONTENEDOR, "-p", "127.0.0.1:8545:8545", "--entrypoint", "anvil",
                    "ghcr.io/foundry-rs/foundry:stable", "--host", "0.0.0.0", "--fork-url", args.rpc,
                    "--fork-block-number", str(cabeza - 5), "--chain-id", "1"], check=True, capture_output=True)
    resultado: Dict[str, Any] = {"fork_block": cabeza - 5, "scenarios": {}}
    try:
        for _ in range(60):
            try:
                rpc("eth_chainId", [])
                break
            except Exception:
                time.sleep(1)
        owner = to_checksum_address(rpc("eth_accounts", [])[0])
        fork = Fork(owner)
        safe = fork.desplegar_safe()
        rpc("anvil_setBalance", [safe, hex(5 * 10**18)])
        resultado["safe"] = safe
        consulta, transporte = ConsultaFork(safe, cabeza - 4), TransporteFork()
        registro = c.Registro()
        coord = c.Coordinador(registro)

        # 1. Feliz.
        feliz = propuesta(fork, safe, 10**18)
        registro.crear(feliz, "fork:feliz")
        aprob = aprobar(feliz, "owner del fork", time.time())
        coord.aprobar(feliz, aprob)
        assert coord.entregar(feliz, aprob, contexto(fork, safe, feliz), transporte) == c.ENVIADA
        assert coord.reconciliar(feliz, consulta) == c.ENVIADA  # todavía nadie ejecutó
        fork.ejecutar(safe, feliz.safe_tx)
        estado = coord.reconciliar(feliz, consulta)
        resultado["scenarios"]["happy_path"] = {"state": estado, "detail": registro.detalle(feliz.id), "history": registro.historia(feliz.id),
                                                "simulated_changes": feliz.simulacion.expected_changes,
                                                "fee_estimate_wei": feliz.simulacion.fee_estimate_wei, "mode": feliz.modo,
                                                "ok": estado == c.CONFIRMADA}

        # 2. Receipt exitoso sin el efecto declarado.
        sin_efecto = propuesta(fork, safe, 10**17, efecto_falso=True)
        registro.crear(sin_efecto, "fork:sin-efecto")
        aprob = aprobar(sin_efecto, "owner del fork", time.time())
        coord.aprobar(sin_efecto, aprob)
        coord.entregar(sin_efecto, aprob, contexto(fork, safe, sin_efecto), transporte)
        recibo = fork.ejecutar(safe, sin_efecto.safe_tx)
        estado = coord.reconciliar(sin_efecto, consulta)
        resultado["scenarios"]["receipt_without_effect"] = {"receipt_status": int(recibo["status"], 16), "state": estado,
                                                            "detail": registro.detalle(sin_efecto.id), "ok": estado == c.FALLIDA}

        # 3. Simulación vieja y payload alterado, contra el estado real del fork.
        vieja = propuesta(fork, safe, 10**17)
        aprob = aprobar(vieja, "owner del fork", time.time())
        rpc("anvil_mine", [hex(30)])
        errores_vieja = validar_para_envio(vieja, aprob, contexto(fork, safe, vieja))
        alterada = reemplazar(vieja, parametros={"monto_wei": 2 * 10**17})
        errores_alterada = validar_para_envio(alterada, aprob, contexto(fork, safe, alterada))
        resultado["scenarios"]["stale_and_altered"] = {"stale_errors": errores_vieja, "altered_errors": errores_alterada,
                                                       "ok": "stale_simulation" in errores_vieja
                                                       and "approval_does_not_match_payload" in errores_alterada}

        # 4. Otra transacción usa el nonce: la propuesta pendiente falla al reconciliar.
        pendiente = propuesta(fork, safe, 10**17)
        registro.crear(pendiente, "fork:pendiente")
        aprob = aprobar(pendiente, "owner del fork", time.time())
        coord.aprobar(pendiente, aprob)

        class Caida:
            def entregar(self, intencion):
                raise TimeoutError("sin respuesta")

        coord.entregar(pendiente, aprob, contexto(fork, safe, pendiente), Caida())
        otra = propuesta(fork, safe, 5 * 10**16)  # mismo nonce, otro payload
        fork.ejecutar(safe, otra.safe_tx)
        estado = coord.reconciliar(pendiente, consulta)
        resultado["scenarios"]["nonce_used_by_other"] = {"state": estado, "detail": registro.detalle(pendiente.id),
                                                         "ok": estado == c.FALLIDA}
    finally:
        subprocess.run(["docker", "stop", CONTENEDOR], capture_output=True)
    resultado["all_ok"] = all(s["ok"] for s in resultado["scenarios"].values())
    destino = RAIZ / "docs" / "ensayos" / "safe-fork.json"
    destino.write_text(json.dumps(resultado, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    print(json.dumps(resultado, indent=2, ensure_ascii=False, default=str))
    return 0 if resultado["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
