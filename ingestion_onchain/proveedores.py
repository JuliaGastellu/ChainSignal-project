"""Proveedores de lectura on-chain: Etherscan (API v2) y RPC JSON.

Cada proveedor:
- verifica eth_chainId contra la red configurada en la primera llamada y lanza
  RedIncorrecta si no coincide, sin devolver datos;
- clasifica cada falla en un Motivo (timeout, 429, respuesta inválida, error
  del proveedor) y reintenta solo lo reintentable, con un número acotado de
  intentos y backoff exponencial con jitter completo;
- nunca convierte una falla en cero o en lista vacía.

El transporte HTTP es inyectable para probar todo sin red.
"""

import json
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import requests

from infra.red import Red, verificar_chain_id
from ingestion_onchain.modelos import Token, Transaccion, TransferenciaToken
from ingestion_onchain.resultados import BloqueRef, ErrorProveedor, Motivo

URL_ETHERSCAN = "https://api.etherscan.io/v2/api"


@dataclass
class RespuestaHttp:
    estado: int
    texto: str


class TransporteRequests:
    """Transporte por defecto. Traduce excepciones de red a ErrorProveedor."""

    def __init__(self, timeout: float):
        self.timeout = timeout
        self.sesion = requests.Session()
        # Algunos proveedores rechazan el User-Agent genérico de requests.
        self.sesion.headers["User-Agent"] = "chainsignal-reader/0.3"

    def _enviar(self, metodo: str, url: str, **kwargs) -> RespuestaHttp:
        try:
            r = self.sesion.request(metodo, url, timeout=self.timeout, **kwargs)
            return RespuestaHttp(r.status_code, r.text)
        except requests.Timeout as e:
            raise ErrorProveedor(Motivo.TIMEOUT, type(e).__name__, reintentable=True)
        except requests.RequestException as e:
            raise ErrorProveedor(Motivo.ERROR_PROVEEDOR, type(e).__name__, reintentable=True)

    def get(self, url: str, params: Dict[str, Any]) -> RespuestaHttp:
        return self._enviar("GET", url, params=params)

    def post_json(self, url: str, cuerpo: Dict[str, Any]) -> RespuestaHttp:
        return self._enviar("POST", url, json=cuerpo)


@dataclass
class PoliticaReintentos:
    intentos: int = 3
    base: float = 0.5
    tope: float = 4.0
    dormir: Callable[[float], None] = time.sleep
    azar: Callable[[], float] = random.random
    esperas: List[float] = field(default_factory=list)

    def ejecutar(self, funcion: Callable[[], Any]) -> Any:
        for intento in range(self.intentos):
            try:
                return funcion()
            except ErrorProveedor as error:
                if not error.reintentable or intento == self.intentos - 1:
                    raise
                # Jitter completo: espero un valor aleatorio entre 0 y el backoff.
                espera = self.azar() * min(self.tope, self.base * (2**intento))
                self.esperas.append(espera)
                self.dormir(espera)
        raise AssertionError("inalcanzable")


def _clasificar_http(respuesta: RespuestaHttp) -> Any:
    if respuesta.estado == 429:
        raise ErrorProveedor(Motivo.RATE_LIMITED, "HTTP 429", reintentable=True)
    if respuesta.estado >= 500:
        raise ErrorProveedor(Motivo.ERROR_PROVEEDOR, f"HTTP {respuesta.estado}", reintentable=True)
    if respuesta.estado != 200:
        raise ErrorProveedor(Motivo.ERROR_PROVEEDOR, f"HTTP {respuesta.estado}")
    try:
        return json.loads(respuesta.texto)
    except (ValueError, TypeError):
        raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, "body is not JSON")


def _hex_a_int(valor: Any, campo: str) -> int:
    if not isinstance(valor, str) or not valor.startswith("0x"):
        raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, f"{campo} is not a hex quantity")
    try:
        return int(valor, 16)
    except ValueError:
        raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, f"{campo} is not a hex quantity")


def _bloque_desde_rpc(resultado: Any, numero_esperado: Optional[int] = None) -> BloqueRef:
    if not isinstance(resultado, dict) or "hash" not in resultado or "number" not in resultado:
        raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, "block object missing fields")
    numero = _hex_a_int(resultado["number"], "block.number")
    if numero_esperado is not None and numero != numero_esperado:
        raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, "provider returned a different block")
    hash_bloque = resultado["hash"]
    if not isinstance(hash_bloque, str) or len(hash_bloque) != 66:
        raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, "block.hash is invalid")
    return BloqueRef(numero, hash_bloque.lower(), _hex_a_int(resultado.get("timestamp"), "block.timestamp"))


class ClienteEtherscan:
    """Lectura de historial vía Etherscan API v2, fijada a una red."""

    nombre = "etherscan"

    def __init__(self, red: Red, clave_api: str, transporte=None, reintentos: Optional[PoliticaReintentos] = None,
                 url: str = URL_ETHERSCAN, timeout: float = 15.0):
        self.red = red
        self.clave_api = clave_api
        self.transporte = transporte or TransporteRequests(timeout)
        self.reintentos = reintentos or PoliticaReintentos()
        self.url = url
        self._red_verificada = False

    # --- bajo nivel -----------------------------------------------------------

    def _una_peticion(self, params: Dict[str, Any]) -> Any:
        cuerpo = _clasificar_http(self.transporte.get(self.url, {**params, "chainid": self.red.chain_id, "apikey": self.clave_api}))
        if not isinstance(cuerpo, dict):
            raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, "body is not an object")
        if params.get("module") == "proxy":
            if "error" in cuerpo:
                mensaje = str((cuerpo.get("error") or {}).get("message", ""))
                limite = "rate limit" in mensaje.lower()
                raise ErrorProveedor(Motivo.RATE_LIMITED if limite else Motivo.ERROR_PROVEEDOR, mensaje[:120], reintentable=limite)
            if "result" not in cuerpo:
                raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, "proxy response without result")
            resultado = cuerpo["result"]
            if isinstance(resultado, str) and "rate limit" in resultado.lower():
                raise ErrorProveedor(Motivo.RATE_LIMITED, "rate limit", reintentable=True)
            return resultado
        estado, mensaje, resultado = cuerpo.get("status"), str(cuerpo.get("message", "")), cuerpo.get("result")
        if estado == "1":
            return resultado
        if estado == "0" and mensaje.startswith("No transactions found") and resultado in ([], None, ""):
            return []  # cuenta sin actividad en la ventana: es un dato, no una falla
        texto = f"{mensaje} {resultado if isinstance(resultado, str) else ''}".lower()
        if "rate limit" in texto:
            raise ErrorProveedor(Motivo.RATE_LIMITED, "rate limit", reintentable=True)
        if "invalid api key" in texto or "missing/invalid api key" in texto:
            raise ErrorProveedor(Motivo.NO_CONFIGURADO, "invalid or missing API key")
        if estado not in ("0", "1"):
            raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, "unexpected status field")
        raise ErrorProveedor(Motivo.ERROR_PROVEEDOR, mensaje[:120] or "provider error")

    def _pedir(self, params: Dict[str, Any]) -> Any:
        if not self.clave_api:
            raise ErrorProveedor(Motivo.NO_CONFIGURADO, "ETHERSCAN_API_KEY is not configured")
        if not self._red_verificada and params.get("action") != "eth_chainId":
            self.verificar_red()
        return self.reintentos.ejecutar(lambda: self._una_peticion(params))

    # --- red y bloques ----------------------------------------------------------

    def verificar_red(self) -> None:
        resultado = self.reintentos.ejecutar(lambda: self._una_peticion({"module": "proxy", "action": "eth_chainId"}))
        verificar_chain_id(self.red.chain_id, resultado, self.nombre)
        self._red_verificada = True

    def bloque_actual(self) -> int:
        return _hex_a_int(self._pedir({"module": "proxy", "action": "eth_blockNumber"}), "eth_blockNumber")

    def bloque(self, numero: int) -> BloqueRef:
        resultado = self._pedir({"module": "proxy", "action": "eth_getBlockByNumber", "tag": hex(numero), "boolean": "false"})
        return _bloque_desde_rpc(resultado, numero)

    def balance_ultimo(self, direccion: str) -> int:
        """Balance con tag latest: Etherscan no lo fija a un bloque."""
        resultado = self._pedir({"module": "account", "action": "balance", "address": direccion, "tag": "latest"})
        try:
            return int(resultado)
        except (TypeError, ValueError):
            raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, "balance is not an integer")

    # --- historial ----------------------------------------------------------------

    def pagina(self, direccion: str, flujo: str, desde: int, hasta: int, pagina: int, tamanio: int, orden: str) -> List[Any]:
        accion = {"transactions": "txlist", "tokens": "tokentx"}[flujo]
        filas = self._pedir({
            "module": "account", "action": accion, "address": direccion,
            "startblock": desde, "endblock": hasta, "page": pagina, "offset": tamanio, "sort": orden,
        })
        if not isinstance(filas, list):
            raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, "history result is not a list")
        return [self._parsear(flujo, fila) for fila in filas]

    def _parsear(self, flujo: str, fila: Any):
        try:
            if flujo == "transactions":
                entrada = fila.get("input", "0x") or "0x"
                if int(fila.get("value") or 0) < 0 or int(fila.get("gasUsed") or 0) < 0:
                    raise ValueError("negative quantity")
                return Transaccion(
                    hash=fila["hash"].lower(), bloque=int(fila["blockNumber"]), timestamp=int(fila["timeStamp"]),
                    origen=(fila.get("from") or "").lower(), destino=(fila.get("to") or "").lower(),
                    valor_wei=int(fila.get("value") or 0), gas_utilizado=int(fila.get("gasUsed") or 0),
                    es_error=fila.get("isError", "0") == "1", es_contrato=entrada != "0x",
                    hash_bloque=(fila.get("blockHash") or "").lower(),
                )
            decimales = int(fila["tokenDecimal"])
            if not 0 <= decimales <= 255:
                raise ValueError("decimals out of range")
            if int(fila["value"]) < 0:
                raise ValueError("negative quantity")
            return TransferenciaToken(
                hash=fila["hash"].lower(), bloque=int(fila["blockNumber"]), timestamp=int(fila["timeStamp"]),
                origen=(fila.get("from") or "").lower(), destino=(fila.get("to") or "").lower(),
                token=Token(self.red.chain_id, fila["contractAddress"].lower(), decimales, str(fila.get("tokenSymbol") or "")[:32]),
                cantidad_raw=int(fila["value"]), hash_bloque=(fila.get("blockHash") or "").lower(),
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, f"malformed {flujo} row")


class RpcLectura:
    """Cliente JSON-RPC de solo lectura (eth_call, bloques, balances), fijado a una red."""

    nombre = "rpc"

    def __init__(self, red: Red, url: str, transporte=None, reintentos: Optional[PoliticaReintentos] = None, timeout: float = 15.0):
        self.red = red
        self.url = url
        self.transporte = transporte or TransporteRequests(timeout)
        self.reintentos = reintentos or PoliticaReintentos()
        self._red_verificada = False
        self._id = 0

    def _una_llamada(self, metodo: str, params: list) -> Any:
        self._id += 1
        respuesta = self.transporte.post_json(self.url, {"jsonrpc": "2.0", "id": self._id, "method": metodo, "params": params})
        if respuesta.estado != 200:
            # Algunos nodos responden 4xx con un error JSON-RPC que explica la causa
            # (por ejemplo, falta de archive). Lo leo antes de clasificar por HTTP.
            try:
                cuerpo_error = json.loads(respuesta.texto)
            except (ValueError, TypeError):
                cuerpo_error = None
            if isinstance(cuerpo_error, dict) and cuerpo_error.get("error") and respuesta.estado not in (429,) and respuesta.estado < 500:
                respuesta = RespuestaHttp(200, respuesta.texto)
        cuerpo = _clasificar_http(respuesta)
        if not isinstance(cuerpo, dict):
            raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, "body is not an object")
        if "error" in cuerpo and cuerpo["error"]:
            error = cuerpo["error"] if isinstance(cuerpo["error"], dict) else {"message": str(cuerpo["error"])}
            mensaje = str(error.get("message", ""))
            texto = mensaje.lower()
            if error.get("code") in (-32005, 429) or "rate limit" in texto or "too many requests" in texto:
                raise ErrorProveedor(Motivo.RATE_LIMITED, mensaje[:120], reintentable=True)
            if any(marca in texto for marca in ("missing trie node", "header not found", "historical state", "pruned", "archive")):
                raise ErrorProveedor(Motivo.SIN_ARCHIVO, mensaje[:120])
            raise ErrorProveedor(Motivo.ERROR_PROVEEDOR, mensaje[:120] or "rpc error")
        if "result" not in cuerpo:
            raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, "rpc response without result")
        return cuerpo["result"]

    def llamar(self, metodo: str, params: list) -> Any:
        if not self.url:
            raise ErrorProveedor(Motivo.NO_CONFIGURADO, "RPC URL is not configured")
        if not self._red_verificada and metodo != "eth_chainId":
            self.verificar_red()
        return self.reintentos.ejecutar(lambda: self._una_llamada(metodo, params))

    def verificar_red(self) -> None:
        if not self.url:
            raise ErrorProveedor(Motivo.NO_CONFIGURADO, "RPC URL is not configured")
        resultado = self.reintentos.ejecutar(lambda: self._una_llamada("eth_chainId", []))
        verificar_chain_id(self.red.chain_id, resultado, self.nombre)
        self._red_verificada = True

    def bloque_actual(self) -> int:
        return _hex_a_int(self.llamar("eth_blockNumber", []), "eth_blockNumber")

    def bloque(self, numero: int) -> BloqueRef:
        return _bloque_desde_rpc(self.llamar("eth_getBlockByNumber", [hex(numero), False]), numero)

    def balance(self, direccion: str, numero: int) -> int:
        return _hex_a_int(self.llamar("eth_getBalance", [direccion, hex(numero)]), "eth_getBalance")

    def eth_call(self, destino: str, datos: str, numero: int) -> str:
        resultado = self.llamar("eth_call", [{"to": destino, "data": datos}, hex(numero)])
        if not isinstance(resultado, str) or not resultado.startswith("0x"):
            raise ErrorProveedor(Motivo.RESPUESTA_INVALIDA, "eth_call result is not hex data")
        return resultado
