"""Pruebas offline de la ingesta tipada (E03).

Cubro red incorrecta, 429, timeouts, respuestas inválidas, páginas faltantes,
tope de páginas, ventana de 10.000 filas, checkpoint incremental, caché TTL,
caché vencido con proveedor caído, reorg, filas no confirmadas, cuenta sin
actividad, símbolos repetidos y valores extremos. Nada sale a la red.
"""

import json

import pytest
import requests

from infra.db import make_engine
from infra.red import ETHEREUM, SEPOLIA
from ingestion_onchain import ingesta as modulo_ingesta
from ingestion_onchain.ingesta import ServicioIngesta
from ingestion_onchain.proveedores import ClienteEtherscan, PoliticaReintentos, RespuestaHttp, RpcLectura, TransporteRequests
from ingestion_onchain.resultados import Calidad, ErrorProveedor, Motivo
from tests.proveedor_simulado import DIRECCION, OTRA, CadenaSimulada, TransporteSimulado, error, es


class Reloj:
    def __init__(self, ahora: float = 1_800_000_000.0):
        self.ahora = ahora

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    from infra.config import settings

    monkeypatch.setattr(settings, "INGESTION_PAGE_SIZE", 3)
    monkeypatch.setattr(settings, "INGESTION_MAX_PAGES", 20)
    monkeypatch.setattr(settings, "INGESTION_CONFIRMATIONS", 12)
    monkeypatch.setattr(settings, "INGESTION_REORG_DEPTH", 64)
    monkeypatch.setattr(settings, "INGESTION_CACHE_TTL_SECONDS", 60)

    cadena = CadenaSimulada()
    transporte = TransporteSimulado(cadena)
    esperas = []
    reintentos = PoliticaReintentos(intentos=3, dormir=esperas.append, azar=lambda: 0.5)
    reloj = Reloj()
    engine = make_engine(f"sqlite:///{(tmp_path / 'ingesta.db').as_posix()}")

    def construir(con_rpc: bool = False, red_rpc=ETHEREUM):
        historial = ClienteEtherscan(ETHEREUM, "clave-sintetica", transporte, reintentos, url="https://simulado")
        rpc = RpcLectura(red_rpc, "https://rpc-simulado", transporte, reintentos) if con_rpc else None
        return ServicioIngesta(ETHEREUM, historial, rpc, engine, reloj)

    class E:
        pass

    e = E()
    e.cadena, e.transporte, e.esperas, e.reloj, e.construir, e.engine = cadena, transporte, esperas, reloj, construir, engine
    return e


def _sembrar(cadena: CadenaSimulada, bloques):
    for b in bloques:
        cadena.agregar_tx(b)


def _pedidos_de(transporte, accion):
    return [p for p in transporte.pedidos if p.get("action") == accion]


# --- red ------------------------------------------------------------------------


def test_red_incorrecta_del_proveedor_de_historial_no_devuelve_datos(entorno):
    entorno.cadena.chain_id = SEPOLIA.chain_id
    _sembrar(entorno.cadena, [10, 20])
    datos = entorno.construir().obtener_datos_wallet(DIRECCION)

    assert datos.calidad.calidad is Calidad.UNAVAILABLE
    assert datos.calidad.motivo is Motivo.RED_INCORRECTA
    assert datos.transacciones == []
    assert not _pedidos_de(entorno.transporte, "txlist")


def test_rpc_de_otra_red_deja_el_balance_no_disponible(entorno):
    _sembrar(entorno.cadena, [10])
    entorno.transporte.fallar(es("eth_chainId") , RespuestaHttp(200, json.dumps({"jsonrpc": "2.0", "id": 1, "result": hex(SEPOLIA.chain_id)})), veces=-1)
    # La falla anterior también afectaría a Etherscan; la limito al RPC.
    entorno.transporte.fallas[-1][0] = lambda p: p.get("rpc") == "eth_chainId"
    datos = entorno.construir(con_rpc=True).obtener_datos_wallet(DIRECCION)

    assert datos.balance_wei is None
    assert datos.calidad.componentes["balance"].motivo is Motivo.RED_INCORRECTA
    assert datos.calidad.calidad is Calidad.PARTIAL


def test_proveedores_de_redes_distintas_no_se_combinan(entorno):
    historial = ClienteEtherscan(ETHEREUM, "k", entorno.transporte)
    with pytest.raises(ValueError):
        ServicioIngesta(ETHEREUM, historial, RpcLectura(SEPOLIA, "https://x", entorno.transporte), entorno.engine)


def test_settings_rechaza_testnet_en_el_runtime_de_lectura():
    from infra.config import Settings

    with pytest.raises(RuntimeError):
        Settings(CHAIN_ID=SEPOLIA.chain_id, CHAINSIGNAL_MODE="READ_ONLY").validate()


# --- fallas del proveedor --------------------------------------------------------


def test_429_se_reintenta_con_backoff_y_jitter_y_luego_funciona(entorno):
    _sembrar(entorno.cadena, [10, 20])
    entorno.transporte.fallar(es("txlist"), RespuestaHttp(429, "Too Many Requests"), veces=2)
    datos = entorno.construir().obtener_datos_wallet(DIRECCION)

    assert datos.calidad.componentes["transactions"].calidad is Calidad.FRESH
    assert len(datos.transacciones) == 2
    # Dos esperas: 0.5 * min(4, 0.5*2^0) y 0.5 * min(4, 0.5*2^1).
    assert entorno.esperas == [0.25, 0.5]


def test_429_persistente_termina_en_unavailable_sin_dormir_de_mas(entorno):
    _sembrar(entorno.cadena, [10])
    entorno.transporte.fallar(es("txlist"), RespuestaHttp(429, "Too Many Requests"), veces=-1)
    datos = entorno.construir().obtener_datos_wallet(DIRECCION)

    assert datos.calidad.calidad is Calidad.UNAVAILABLE
    assert datos.calidad.motivo is Motivo.RATE_LIMITED
    assert len(_pedidos_de(entorno.transporte, "txlist")) == 3
    assert len(entorno.esperas) == 2


def test_rate_limit_en_el_cuerpo_tambien_cuenta_como_429(entorno):
    cuerpo = RespuestaHttp(200, json.dumps({"status": "0", "message": "NOTOK", "result": "Max rate limit reached"}))
    entorno.transporte.fallar(es("txlist"), cuerpo, veces=-1)
    datos = entorno.construir().obtener_datos_wallet(DIRECCION)
    assert datos.calidad.motivo is Motivo.RATE_LIMITED


def test_timeout_termina_en_unavailable_y_no_en_cuenta_vacia(entorno):
    entorno.transporte.fallar(es("txlist"), error(Motivo.TIMEOUT, reintentable=True), veces=-1)
    datos = entorno.construir().obtener_datos_wallet(DIRECCION)

    assert datos.calidad.calidad is Calidad.UNAVAILABLE
    assert datos.calidad.motivo is Motivo.TIMEOUT
    assert datos.calidad.a_dict()["no_activity"] is False


@pytest.mark.parametrize("respuesta", [
    RespuestaHttp(200, "<html>bad gateway</html>"),
    RespuestaHttp(200, json.dumps({"status": "1", "message": "OK", "result": "no es lista"})),
    RespuestaHttp(200, json.dumps({"status": "1", "message": "OK", "result": [{"hash": "0x1"}]})),
    RespuestaHttp(200, json.dumps({"status": "1", "message": "OK", "result": [{"hash": "0x1", "blockNumber": "5", "timeStamp": "1", "value": "-3"}]})),
], ids=["no_json", "no_lista", "fila_incompleta", "valor_negativo"])
def test_respuesta_invalida_no_se_reintenta(entorno, respuesta):
    entorno.transporte.fallar(es("txlist"), respuesta, veces=-1)
    datos = entorno.construir().obtener_datos_wallet(DIRECCION)
    assert datos.calidad.calidad is Calidad.UNAVAILABLE
    assert datos.calidad.motivo is Motivo.RESPUESTA_INVALIDA
    assert len(_pedidos_de(entorno.transporte, "txlist")) == 1


def test_transporte_traduce_timeout_de_requests(monkeypatch):
    transporte = TransporteRequests(timeout=0.01)

    def explotar(*args, **kwargs):
        raise requests.Timeout("lento")

    monkeypatch.setattr(transporte.sesion, "request", explotar)
    with pytest.raises(ErrorProveedor) as info:
        transporte.get("https://x", {})
    assert info.value.motivo is Motivo.TIMEOUT and info.value.reintentable


def test_cuenta_sin_actividad_es_fresh_y_distinta_de_una_falla(entorno):
    datos = entorno.construir().obtener_datos_wallet(DIRECCION)
    calidad = datos.calidad.a_dict()

    assert datos.calidad.calidad is Calidad.FRESH
    assert calidad["no_activity"] is True
    assert calidad["complete_history"] is True
    assert datos.transacciones == []


# --- paginación ---------------------------------------------------------------------


def test_pagina_faltante_en_el_primer_sync_queda_partial(entorno):
    _sembrar(entorno.cadena, [100, 200, 300, 400, 500, 600, 700])
    entorno.transporte.fallar(lambda p: p.get("action") == "txlist" and p.get("page") == 2, RespuestaHttp(503, "down"), veces=-1)
    datos = entorno.construir().obtener_datos_wallet(DIRECCION)
    tx = datos.calidad.componentes["transactions"]

    assert tx.calidad is Calidad.PARTIAL
    assert tx.motivo is Motivo.PAGINACION_INCOMPLETA
    assert tx.procedencia.historial_completo is False
    # La primera página trae 700, 600 y 500; descarto el bloque más bajo por si quedó a medias.
    assert sorted(t.bloque for t in datos.transacciones) == [600, 700]
    assert tx.procedencia.desde_bloque == 501
    assert datos.calidad.permite_recomendacion_accionable is False


def test_tope_de_paginas_declara_historial_incompleto_sin_inventar_edad(entorno, monkeypatch):
    from infra.config import settings
    from generacion_features.extractor import ExtractorFeatures

    monkeypatch.setattr(settings, "INGESTION_MAX_PAGES", 2)
    _sembrar(entorno.cadena, [100, 200, 300, 400, 500, 600, 700, 800])
    datos = entorno.construir().obtener_datos_wallet(DIRECCION)
    tx = datos.calidad.componentes["transactions"]

    assert tx.calidad is Calidad.FRESH
    assert tx.procedencia.historial_completo is False
    assert "truncated" in tx.detalle
    features = ExtractorFeatures().extraer(datos)
    assert features.historial_completo is False
    assert features.primera_actividad_observada_timestamp == entorno.cadena.timestamp_de(400)


def test_ventana_de_diez_mil_filas_continua_sin_duplicar(entorno, monkeypatch):
    monkeypatch.setattr(modulo_ingesta, "_FILAS_MAXIMAS_POR_CONSULTA", 6)  # 2 páginas de 3 por consulta
    bloques = [10, 20, 30, 40, 40, 50, 60, 70, 80, 90]
    _sembrar(entorno.cadena, bloques)
    datos = entorno.construir().obtener_datos_wallet(DIRECCION)

    assert datos.calidad.componentes["transactions"].procedencia.historial_completo is True
    assert sorted(t.bloque for t in datos.transacciones) == sorted(bloques)
    assert len({t.hash for t in datos.transacciones}) == len(bloques)


# --- checkpoint, caché y reorg ------------------------------------------------------


def test_sync_incremental_desde_el_checkpoint_sin_duplicar(entorno):
    _sembrar(entorno.cadena, [100, 200, 300])
    servicio = entorno.construir()
    servicio.obtener_datos_wallet(DIRECCION)

    entorno.cadena.cabeza = 1_100
    entorno.cadena.agregar_tx(1_050)
    entorno.reloj.avanzar(120)
    entorno.transporte.pedidos.clear()
    datos = servicio.obtener_datos_wallet(DIRECCION)

    consultas = _pedidos_de(entorno.transporte, "txlist")
    assert consultas and all(p["sort"] == "asc" and p["startblock"] == 1_000 - 12 + 1 for p in consultas)
    assert sorted(t.bloque for t in datos.transacciones) == [100, 200, 300, 1_050]


def test_cache_dentro_del_ttl_no_consulta_al_proveedor(entorno):
    _sembrar(entorno.cadena, [100])
    servicio = entorno.construir()
    servicio.obtener_datos_wallet(DIRECCION)
    entorno.transporte.pedidos.clear()
    entorno.reloj.avanzar(30)

    datos = servicio.obtener_datos_wallet(DIRECCION)
    tx = datos.calidad.componentes["transactions"]
    assert tx.calidad is Calidad.FRESH and "cache" in tx.detalle
    assert not _pedidos_de(entorno.transporte, "txlist")


def test_cache_vencido_con_proveedor_caido_devuelve_stale_con_su_antiguedad(entorno):
    _sembrar(entorno.cadena, [100, 200])
    servicio = entorno.construir()
    primera = servicio.obtener_datos_wallet(DIRECCION)
    sincronizado = primera.calidad.componentes["transactions"].procedencia.obtenido_en

    entorno.reloj.avanzar(3_600)
    entorno.transporte.fallar(lambda p: True, error(Motivo.TIMEOUT, reintentable=True), veces=-1)
    datos = servicio.obtener_datos_wallet(DIRECCION)
    tx = datos.calidad.componentes["transactions"]

    assert tx.calidad is Calidad.STALE
    assert tx.motivo is Motivo.TIMEOUT
    assert tx.procedencia.obtenido_en == sincronizado
    assert sorted(t.bloque for t in datos.transacciones) == [100, 200]
    assert datos.calidad.permite_recomendacion_accionable is False


def test_reorg_en_el_checkpoint_retrocede_y_reemplaza_filas(entorno):
    _sembrar(entorno.cadena, [100, 950, 980])
    servicio = entorno.construir()
    servicio.obtener_datos_wallet(DIRECCION)

    entorno.cadena.reorganizar(desde_bloque=960)  # cambia el hash del bloque confirmado (988)
    entorno.cadena.agregar_tx(970)
    entorno.reloj.avanzar(120)
    datos = servicio.obtener_datos_wallet(DIRECCION)
    tx = datos.calidad.componentes["transactions"]

    assert tx.procedencia.reorg_detectado is True
    assert sorted(t.bloque for t in datos.transacciones) == [100, 950, 970]
    assert all(t.hash_bloque == entorno.cadena.hash_de(t.bloque) for t in datos.transacciones)


def test_filas_no_confirmadas_se_vuelven_a_pedir(entorno):
    _sembrar(entorno.cadena, [995])  # dentro de las 12 confirmaciones
    servicio = entorno.construir()
    servicio.obtener_datos_wallet(DIRECCION)

    entorno.cadena.filas["txlist"].clear()
    entorno.cadena.agregar_tx(996)  # la transacción "se movió" de bloque
    entorno.reloj.avanzar(120)
    datos = servicio.obtener_datos_wallet(DIRECCION)
    assert [t.bloque for t in datos.transacciones] == [996]


# --- tokens y montos ------------------------------------------------------------------


def test_simbolos_repetidos_son_tokens_distintos_por_contrato(entorno):
    from generacion_features.extractor import ExtractorFeatures

    entorno.cadena.agregar_tx(50)
    entorno.cadena.agregar_token(60, "0x" + "1" * 40, "USDC", 6, 1_000_000)
    entorno.cadena.agregar_token(61, "0x" + "2" * 40, "USDC", 18, 10**18)
    datos = entorno.construir().obtener_datos_wallet(DIRECCION)
    features = ExtractorFeatures().extraer(datos)

    assert features.tokens_unicos_utilizados == 2
    assert features.diversidad_tokens == 1.0
    cantidades = sorted(t.cantidad for t in datos.transferencias_token)
    assert [str(c) for c in cantidades] == ["1", "1"]


def test_valores_extremos_sin_perder_precision(entorno):
    from generacion_features.extractor import ExtractorFeatures

    maximo = 2**256 - 1
    entorno.cadena.agregar_tx(40, valor_wei=maximo)
    entorno.cadena.agregar_token(41, "0x" + "3" * 40, "BIG", 0, maximo)
    entorno.cadena.agregar_token(42, "0x" + "4" * 40, "TINY", 77, 1)
    datos = entorno.construir().obtener_datos_wallet(DIRECCION)

    assert datos.transacciones[0].valor_wei == maximo
    grande = next(t for t in datos.transferencias_token if t.token.simbolo == "BIG")
    chica = next(t for t in datos.transferencias_token if t.token.simbolo == "TINY")
    assert grande.cantidad == maximo
    assert str(chica.cantidad) == "1E-77"
    features = ExtractorFeatures().extraer(datos)
    assert features.volumen_total_transferido_eth > 1e58


def test_decimales_fuera_de_rango_son_respuesta_invalida(entorno):
    entorno.cadena.agregar_tx(40)
    entorno.cadena.agregar_token(41, "0x" + "5" * 40, "BAD", 999, 1)
    datos = entorno.construir().obtener_datos_wallet(DIRECCION)
    tokens = datos.calidad.componentes["tokens"]
    assert tokens.calidad is Calidad.UNAVAILABLE and tokens.motivo is Motivo.RESPUESTA_INVALIDA
    assert datos.calidad.calidad is Calidad.PARTIAL


# --- balance ----------------------------------------------------------------------------


def test_balance_fijado_al_bloque_de_referencia_con_rpc(entorno):
    _sembrar(entorno.cadena, [10])
    datos = entorno.construir(con_rpc=True).obtener_datos_wallet(DIRECCION)
    balance = datos.calidad.componentes["balance"]

    assert datos.balance_wei == entorno.cadena.balance
    assert balance.procedencia.referencia.numero == entorno.cadena.cabeza
    pedidos = [p for p in entorno.transporte.pedidos if p.get("rpc") == "eth_getBalance"]
    assert pedidos[0]["params"][1] == hex(entorno.cadena.cabeza)


def test_balance_no_disponible_queda_en_none_y_no_en_cero(entorno):
    _sembrar(entorno.cadena, [10])
    entorno.transporte.fallar(es("balance"), RespuestaHttp(500, "err"), veces=-1)
    datos = entorno.construir().obtener_datos_wallet(DIRECCION)
    assert datos.balance_wei is None and datos.balance_eth is None
    assert datos.calidad.calidad is Calidad.PARTIAL
