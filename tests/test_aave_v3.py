"""Pruebas del adaptador de lectura Aave V3 (E04), sin red.

1. Replay de una lectura pública real de mainnet, grabada a un bloque fijo con
   scripts/grabar_fixture_aave.py: reconcilio los totales del Pool con la suma
   por activo y verifico los saldos contra balanceOf de cada token.
2. Escenarios sintéticos codificados con el ABI real: deuda cero, sin posición,
   E-mode, totales que no concilian, reserva ilegible, reorg durante la
   lectura, falta de archive, red incorrecta y address book distinto.
"""

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from infra.db import make_engine
from infra.red import ETHEREUM, SEPOLIA
from ingestion_onchain.proveedores import RespuestaHttp, RpcLectura
from ingestion_onchain.resultados import BloqueRef, Calidad, ErrorProveedor, Motivo
from protocolos.aave_v3 import ADDRESS_BOOK, GET_USER_ACCOUNT_DATA, GET_USER_RESERVE_DATA, AdaptadorAaveV3
from protocolos.abi import direccion
from protocolos.modelos import MAX_UINT256
from protocolos.replay import LectorReproduccion, _clave, verificar_independiente
from protocolos.servicio import ServicioPosiciones
from tests.fixture_aave import USUARIO, EscenarioAave, ReservaSintetica, escenario_activo

FIXTURE_REAL = Path(__file__).parent / "datos" / "aave_v3_prestatario_usdc_26116392.json"


def _leer(fixture: dict, usuario: str = USUARIO, bloque=None):
    lector = LectorReproduccion(fixture)
    bloque = bloque if bloque is not None else int(next(iter(fixture["blocks"])))
    return AdaptadorAaveV3(lector).leer_posicion(usuario, bloque), lector


# --- lectura pública real, reproducida offline ------------------------------------


@pytest.fixture(scope="module")
def real():
    return json.loads(FIXTURE_REAL.read_text(encoding="utf-8"))


def test_replay_publico_reconcilia_a_bloque_fijo(real):
    meta = real["meta"]
    snapshot, lector = _leer(real, meta["user"], meta["block"])

    assert snapshot.calidad is Calidad.FRESH and snapshot.estado == "ACTIVE"
    assert snapshot.bloque.numero == meta["block"] == 26116392
    assert snapshot.presentar()["raw"] == meta["expected"]
    assert snapshot.conciliacion["reconciled"] is True
    assert snapshot.health_factor() == Decimal(meta["expected"]["health_factor_wad"]) / Decimal(10**18)
    # Todas las llamadas fueron al mismo bloque explícito.
    assert all(c.endswith(f"|{meta['block']}") for c in lector.llamadas)
    # Las direcciones resueltas on-chain coinciden con el address book.
    assert snapshot.contratos["pool"] == direccion(ADDRESS_BOOK["POOL"])
    assert not any("differs from the address book" in l for l in snapshot.limitaciones)


def test_replay_publico_coincide_con_balanceof_independiente(real):
    meta = real["meta"]
    snapshot, lector = _leer(real, meta["user"], meta["block"])
    verificacion = verificar_independiente(lector, snapshot)
    assert verificacion == meta["independent_check"]
    assert verificacion["matches"] is True and verificacion["assets_checked"] == len(snapshot.activos) > 0


def test_replay_falla_ante_llamadas_no_grabadas(real):
    meta = real["meta"]
    otro_bloque, _ = _leer(real, meta["user"], meta["block"] - 1)
    assert otro_bloque.calidad is Calidad.UNAVAILABLE
    assert otro_bloque.colateral_base is None


# --- escenarios sintéticos ----------------------------------------------------------


def test_posicion_activa_con_valores_enteros_y_conciliacion():
    escenario = escenario_activo()
    snapshot, _ = _leer(escenario.fixture())
    vista = snapshot.presentar()

    assert snapshot.calidad is Calidad.FRESH and snapshot.estado == "ACTIVE"
    assert vista["collateral_base"] == "25000" and vista["debt_base"] == "15000"
    assert vista["health_factor"] == "1.375"
    assert {a["symbol"] for a in vista["assets"]} == {"WETH", "USDC"}  # DAI sin saldo no aparece
    weth = next(a for a in vista["assets"] if a["symbol"] == "WETH")
    assert weth["supplied"] == "10" and weth["raw"]["a_token_balance"] == str(10 * 10**18)
    assert snapshot.conciliacion["reconciled"] is True


def test_deuda_cero_no_presenta_health_factor_numerico():
    escenario = EscenarioAave(reservas=[ReservaSintetica("WETH", 18, 2_500 * 10**8, saldo=10**18)])
    snapshot, _ = _leer(escenario.fixture())
    vista = snapshot.presentar()

    assert snapshot.estado == "COLLATERAL_ONLY"
    assert snapshot.health_factor_wad == MAX_UINT256
    assert vista["health_factor"] is None and vista["no_debt"] is True
    assert any("No debt" in l for l in vista["limitations"])


def test_cuenta_sin_posicion():
    snapshot, _ = _leer(EscenarioAave(reservas=[ReservaSintetica("WETH", 18, 2_500 * 10**8)]).fixture())
    assert snapshot.calidad is Calidad.FRESH
    assert snapshot.estado == "NO_POSITION" and snapshot.activos == []
    assert snapshot.presentar()["health_factor"] is None


def test_emode_queda_explicito():
    escenario = escenario_activo()
    escenario.emode = 1
    snapshot, _ = _leer(escenario.fixture())
    assert snapshot.categoria_emode == 1
    assert any("E-mode category 1" in l for l in snapshot.limitaciones)


def test_totales_que_no_concilian_degradan_la_calidad():
    escenario = escenario_activo()
    escenario.ajuste_colateral = 5_000 * 10**8
    snapshot, _ = _leer(escenario.fixture())
    assert snapshot.calidad is Calidad.PARTIAL and snapshot.motivo is Motivo.NO_CONCILIA
    assert snapshot.conciliacion["collateral_ok"] is False


def test_reserva_ilegible_deja_la_lectura_parcial():
    escenario = escenario_activo()
    fixture = escenario.fixture()
    dai = escenario.reservas[2]  # sin saldo conocido: no sé si la cuenta tiene DAI
    clave = _clave(ADDRESS_BOOK["AAVE_PROTOCOL_DATA_PROVIDER"], GET_USER_RESERVE_DATA.codificar(dai.activo, USUARIO), escenario.bloque)
    del fixture["calls"][clave]
    snapshot, _ = _leer(fixture)
    assert snapshot.calidad is Calidad.PARTIAL and snapshot.motivo is Motivo.COMPONENTE_FALTANTE
    assert snapshot.reservas_sin_leer == [dai.activo]
    assert snapshot.conciliacion["reconciled"] is False


def test_sin_datos_de_cuenta_no_fabrico_resultados():
    escenario = escenario_activo()
    fixture = escenario.fixture()
    del fixture["calls"][_clave(ADDRESS_BOOK["POOL"], GET_USER_ACCOUNT_DATA.codificar(USUARIO), escenario.bloque)]
    snapshot, _ = _leer(fixture)
    assert snapshot.calidad is Calidad.UNAVAILABLE
    assert snapshot.colateral_base is None and snapshot.presentar()["health_factor"] is None


def test_reorg_durante_la_lectura():
    escenario = escenario_activo()
    lector = LectorReproduccion(escenario.fixture())
    original = lector.bloque
    llamadas = {"n": 0}

    def bloque_que_cambia(numero):
        llamadas["n"] += 1
        ref = original(numero)
        return ref if llamadas["n"] == 1 else BloqueRef(ref.numero, "0x" + "f" * 64, ref.timestamp)

    lector.bloque = bloque_que_cambia
    snapshot = AdaptadorAaveV3(lector).leer_posicion(USUARIO, escenario.bloque)
    assert snapshot.calidad is Calidad.PARTIAL and snapshot.motivo is Motivo.REORG_DURANTE_LECTURA


def test_address_book_distinto_queda_como_limitacion():
    escenario = escenario_activo()
    escenario.pool = "0x" + "9" * 40
    snapshot, _ = _leer(escenario.fixture())
    assert snapshot.contratos["pool"] == direccion("0x" + "9" * 40)
    assert any("POOL at block" in l for l in snapshot.limitaciones)


def test_lector_de_otra_red_no_lee():
    fixture = escenario_activo().fixture()
    fixture["chain_id"] = SEPOLIA.chain_id
    snapshot, lector = _leer(fixture)
    assert snapshot.calidad is Calidad.UNAVAILABLE and snapshot.motivo is Motivo.RED_INCORRECTA
    assert lector.llamadas == []


def test_valores_extremos_sin_perder_precision():
    escenario = EscenarioAave(reservas=[ReservaSintetica("BIG", 0, 10**30, saldo=10**40)])
    snapshot, _ = _leer(escenario.fixture())
    assert snapshot.colateral_base == 10**70
    assert snapshot.presentar()["collateral_base"] == str(10**62)


# --- proveedor RPC -------------------------------------------------------------------


class TransporteFijo:
    def __init__(self, respuesta: RespuestaHttp):
        self.respuesta = respuesta

    def post_json(self, url, cuerpo):
        if cuerpo["method"] == "eth_chainId":
            return RespuestaHttp(200, json.dumps({"jsonrpc": "2.0", "id": cuerpo["id"], "result": "0x1"}))
        return self.respuesta


@pytest.mark.parametrize("respuesta", [
    RespuestaHttp(403, json.dumps({"jsonrpc": "2.0", "id": 3, "error": {"code": -32602, "message": "Archive requests require a personal token."}})),
    RespuestaHttp(200, json.dumps({"jsonrpc": "2.0", "id": 3, "error": {"code": -32000, "message": "missing trie node abc"}})),
], ids=["403_archive", "missing_trie_node"])
def test_falta_de_archive_se_reporta_como_tal(respuesta):
    lector = RpcLectura(ETHEREUM, "https://rpc", TransporteFijo(respuesta))
    snapshot = AdaptadorAaveV3(lector).leer_posicion(USUARIO, 15_000_000)
    assert snapshot.calidad is Calidad.UNAVAILABLE and snapshot.motivo is Motivo.SIN_ARCHIVO


def test_rpc_no_configurado_no_fabrica_resultados():
    snapshot = AdaptadorAaveV3(RpcLectura(ETHEREUM, "")).leer_posicion(USUARIO)
    assert snapshot.calidad is Calidad.UNAVAILABLE and snapshot.motivo is Motivo.NO_CONFIGURADO


def test_eth_call_vacio_no_es_cero():
    from protocolos.abi import Funcion

    with pytest.raises(ErrorProveedor):
        Funcion("getUserEMode", ("address",), ("uint256",)).decodificar("0x")


# --- persistencia ----------------------------------------------------------------------


@pytest.fixture
def posiciones(tmp_path):
    return ServicioPosiciones(make_engine(f"sqlite:///{(tmp_path / 'posiciones.db').as_posix()}"))


def test_snapshot_persistido_se_reconstruye_igual(posiciones, real):
    meta = real["meta"]
    snapshot, _ = _leer(real, meta["user"], meta["block"])
    assert posiciones.guardar(snapshot) is True
    guardado = posiciones.obtener(1, "aave-v3", "AaveV3Ethereum", meta["user"], meta["block"])

    original, reconstruido = snapshot.presentar(), guardado.presentar()
    for clave in ("raw", "assets", "reconciliation", "contracts", "block", "health_factor", "status", "schema"):
        assert reconstruido[clave] == original[clave], clave
    assert posiciones.guardar(copy.deepcopy(snapshot)) is False  # el bloque ya existe


def test_mismo_bloque_se_sirve_desde_la_base_sin_volver_a_leer(posiciones):
    escenario = escenario_activo()
    lector = LectorReproduccion(escenario.fixture())
    adaptador = AdaptadorAaveV3(lector)
    primero = posiciones.leer_y_guardar(adaptador, USUARIO, escenario.bloque)
    llamadas = len(lector.llamadas)
    segundo = posiciones.leer_y_guardar(adaptador, USUARIO, escenario.bloque)
    assert len(lector.llamadas) == llamadas
    assert segundo.presentar()["raw"] == primero.presentar()["raw"]


def test_no_persisto_lecturas_no_disponibles(posiciones):
    snapshot = AdaptadorAaveV3(RpcLectura(ETHEREUM, "")).leer_posicion(USUARIO)
    assert posiciones.guardar(snapshot) is False


# --- API ---------------------------------------------------------------------------------


def test_api_de_posiciones_con_autorizacion(cliente_owner, organizacion, monkeypatch):
    import api.rutas_org as rutas
    from tests.ayudantes_identidad import crear_organizacion, iniciar_sesion

    escenario = escenario_activo()
    fixture = escenario.fixture()
    fixture["synthetic"] = False  # simulo una lectura grabada de la red, como en organizaciones reales
    monkeypatch.setattr(rutas, "construir_adaptador_aave", lambda: AdaptadorAaveV3(LectorReproduccion(fixture)))
    org_id = organizacion[0]
    cuenta = cliente_owner.post(f"/orgs/{org_id}/accounts", json={"address": USUARIO}).json()

    respuesta = cliente_owner.get(f"/orgs/{org_id}/accounts/{cuenta['id']}/positions/aave-v3", params={"block": escenario.bloque})
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["read_only"] is True and datos["block"]["number"] == escenario.bloque
    assert datos["health_factor"] == "1.375" and datos["data_quality"]["status"] == "FRESH"
    historial = cliente_owner.get(f"/orgs/{org_id}/accounts/{cuenta['id']}/positions/aave-v3/snapshots").json()["snapshots"]
    assert [s["block"]["number"] for s in historial] == [escenario.bloque]

    otra_org, email = crear_organizacion("Otra")
    ajeno = iniciar_sesion(email)
    assert ajeno.get(f"/orgs/{org_id}/accounts/{cuenta['id']}/positions/aave-v3").status_code == 403
    assert ajeno.get(f"/orgs/{otra_org}/accounts/{cuenta['id']}/positions/aave-v3").status_code == 404


def test_api_sin_rpc_responde_unavailable_y_no_inventa(cliente_owner, organizacion):
    org_id = organizacion[0]
    cuenta = cliente_owner.post(f"/orgs/{org_id}/accounts", json={"address": USUARIO}).json()
    datos = cliente_owner.get(f"/orgs/{org_id}/accounts/{cuenta['id']}/positions/aave-v3").json()
    assert datos["data_quality"] == {"status": "UNAVAILABLE", "reason": "not_configured", "detail": "RPC URL is not configured"}
    assert datos["health_factor"] is None and datos["collateral_base"] is None and datos["assets"] == []
