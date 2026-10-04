"""Proveedor Etherscan/RPC simulado para probar la ingesta sin red.

Mantengo una cadena sintética (bloques con hash y timestamp, transacciones y
transferencias por dirección) y respondo como la API v2 de Etherscan y como un
nodo JSON-RPC. Puedo inyectar fallas por predicado: HTTP 429, timeouts,
cuerpos inválidos o errores en una página concreta.
"""

import hashlib
import json
from typing import Callable, Dict, List, Optional

from ingestion_onchain.proveedores import RespuestaHttp
from ingestion_onchain.resultados import ErrorProveedor, Motivo

DIRECCION = "0x00000000000000000000000000000000000000a1"
OTRA = "0x00000000000000000000000000000000000000b2"


def _hash(n: int, sal: str) -> str:
    return "0x" + hashlib.sha256(f"{n}:{sal}".encode()).hexdigest()


class CadenaSimulada:
    def __init__(self, chain_id: int = 1, cabeza: int = 1_000):
        self.chain_id = chain_id
        self.cabeza = cabeza
        self.sales: Dict[int, str] = {}
        self.filas: Dict[str, List[dict]] = {"txlist": [], "tokentx": []}
        self.balance = 123 * 10**18

    def hash_de(self, n: int) -> str:
        return _hash(n, self.sales.get(n, "original"))

    def timestamp_de(self, n: int) -> int:
        return 1_700_000_000 + n * 12

    def agregar_tx(self, bloque: int, valor_wei: int = 10**18, hash_tx: Optional[str] = None, desde: str = DIRECCION,
                   hacia: str = OTRA, entrada: str = "0x"):
        self.filas["txlist"].append({
            "hash": hash_tx or _hash(len(self.filas["txlist"]), f"tx{bloque}"), "blockNumber": str(bloque),
            "blockHash": self.hash_de(bloque), "timeStamp": str(self.timestamp_de(bloque)), "from": desde, "to": hacia,
            "value": str(valor_wei), "gasUsed": "21000", "isError": "0", "input": entrada,
        })

    def agregar_token(self, bloque: int, contrato: str, simbolo: str, decimales: int, valor: int):
        self.filas["tokentx"].append({
            "hash": _hash(len(self.filas["tokentx"]), f"tok{bloque}"), "blockNumber": str(bloque),
            "blockHash": self.hash_de(bloque), "timeStamp": str(self.timestamp_de(bloque)), "from": OTRA, "to": DIRECCION,
            "contractAddress": contrato, "tokenSymbol": simbolo, "tokenDecimal": str(decimales), "value": str(valor),
        })

    def reorganizar(self, desde_bloque: int):
        """Cambio el hash de los bloques >= desde_bloque y descarto sus filas."""
        for n in range(desde_bloque, self.cabeza + 1):
            self.sales[n] = "reorg"
        for clave in self.filas:
            self.filas[clave] = [f for f in self.filas[clave] if int(f["blockNumber"]) < desde_bloque]


class TransporteSimulado:
    def __init__(self, cadena: CadenaSimulada):
        self.cadena = cadena
        self.pedidos: List[dict] = []
        self.fallas: List[tuple] = []

    def fallar(self, predicado: Callable[[dict], bool], respuesta, veces: int = 1):
        """respuesta: RespuestaHttp o ErrorProveedor; veces=-1 para siempre."""
        self.fallas.append([predicado, respuesta, veces])

    def _falla(self, params: dict):
        for falla in self.fallas:
            predicado, respuesta, veces = falla
            if veces != 0 and predicado(params):
                if veces > 0:
                    falla[2] -= 1
                if isinstance(respuesta, ErrorProveedor):
                    raise respuesta
                return respuesta
        return None

    @staticmethod
    def _json(cuerpo) -> RespuestaHttp:
        return RespuestaHttp(200, json.dumps(cuerpo))

    def get(self, url: str, params: dict) -> RespuestaHttp:
        self.pedidos.append(dict(params))
        falla = self._falla(params)
        if falla is not None:
            return falla
        c = self.cadena
        accion = params.get("action")
        if params.get("module") == "proxy":
            if accion == "eth_chainId":
                return self._json({"jsonrpc": "2.0", "id": 1, "result": hex(c.chain_id)})
            if accion == "eth_blockNumber":
                return self._json({"jsonrpc": "2.0", "id": 1, "result": hex(c.cabeza)})
            if accion == "eth_getBlockByNumber":
                n = int(params["tag"], 16)
                return self._json({"jsonrpc": "2.0", "id": 1, "result": {"number": hex(n), "hash": c.hash_de(n), "timestamp": hex(c.timestamp_de(n))}})
        if accion == "balance":
            return self._json({"status": "1", "message": "OK", "result": str(c.balance)})
        if accion in ("txlist", "tokentx"):
            desde, hasta = int(params["startblock"]), int(params["endblock"])
            filas = [f for f in c.filas[accion]
                     if f["to"] == params["address"] or f["from"] == params["address"]]
            filas = [f for f in filas if desde <= int(f["blockNumber"]) <= hasta]
            filas.sort(key=lambda f: int(f["blockNumber"]), reverse=params["sort"] == "desc")
            tamanio, pagina = int(params["offset"]), int(params["page"])
            lote = filas[(pagina - 1) * tamanio: pagina * tamanio]
            if not lote:
                return self._json({"status": "0", "message": "No transactions found", "result": []})
            return self._json({"status": "1", "message": "OK", "result": lote})
        return RespuestaHttp(400, "unsupported")

    def post_json(self, url: str, cuerpo: dict) -> RespuestaHttp:
        self.pedidos.append({"rpc": cuerpo["method"], **{"params": cuerpo["params"]}})
        falla = self._falla({"rpc": cuerpo["method"]})
        if falla is not None:
            return falla
        c = self.cadena
        metodo = cuerpo["method"]
        if metodo == "eth_chainId":
            resultado = hex(c.chain_id)
        elif metodo == "eth_blockNumber":
            resultado = hex(c.cabeza)
        elif metodo == "eth_getBalance":
            resultado = hex(c.balance)
        elif metodo == "eth_getBlockByNumber":
            n = int(cuerpo["params"][0], 16)
            resultado = {"number": hex(n), "hash": c.hash_de(n), "timestamp": hex(c.timestamp_de(n))}
        else:
            return self._json({"jsonrpc": "2.0", "id": cuerpo["id"], "error": {"code": -32601, "message": "method not found"}})
        return self._json({"jsonrpc": "2.0", "id": cuerpo["id"], "result": resultado})


def es(accion: str) -> Callable[[dict], bool]:
    return lambda p: p.get("action") == accion or p.get("rpc") == accion


def error(motivo: Motivo, reintentable: bool = False) -> ErrorProveedor:
    return ErrorProveedor(motivo, motivo.value, reintentable=reintentable)
