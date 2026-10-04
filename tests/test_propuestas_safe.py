"""Spike E10 (fuera del runtime): propuestas Safe con firma humana, con mocks.

Cubro doble solicitud, simulación vieja, payload alterado, red y nonce
incorrectos, crash o timeout en la entrega (también cuando el proveedor
transmite antes de devolver el hash), reconciliación y receipt exitoso sin el
efecto esperado. Los hashes los comparo con los que devolvió el contrato
oficial (docs/ensayos/safe-onchain.json).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from eth_abi import decode

from experiments.propuestas_safe import coordinador as c
from experiments.propuestas_safe.guia import cuerpo_propuesta_servicio, guia_manual, resumen_para_aprobacion
from experiments.propuestas_safe.propuesta import (
    Contexto, PropuestaInvalida, Simulacion, aprobar, crear_intencion, reemplazar, validar_para_envio,
)
from experiments.propuestas_safe.safe_tx import (
    AAVE_V3_POOL, MULTISEND_CALL_ONLY_1_4_1, AccionNoPermitida, Llamada, aportar_colateral_weth, armar_safe_tx, repagar_usdc,
    safe_tx_hash,
)

RAIZ = Path(__file__).resolve().parents[1]
SAFE = "0x000000000000000000000000000000000000c0de"
AHORA = 1_800_000_000.0


def _simulacion(bloque=21_000_000, digest="estado-a", ok=True):
    return Simulacion(block_number=bloque, block_hash="0x" + "ab" * 32, ok=ok, state_digest=digest, gas_estimate=250_000,
                      fee_estimate_wei=3 * 10**15, expected_changes=[{"token": "aWETH", "delta": "+1"}],
                      approvals=[{"token": "WETH", "spender": AAVE_V3_POOL, "amount": str(10**18)}])


def _intencion(nonce=7, **kwargs):
    return crear_intencion("org-1", 1, SAFE, SAFE, "pol-1", 3, "aportar_colateral_weth", {"monto_wei": 10**18}, nonce,
                           kwargs.get("simulacion", _simulacion()), AHORA)


def _ctx(**cambios):
    base = dict(chain_id=1, nonce_safe=7, bloque_actual=21_000_005, state_digest_actual="estado-a", ahora=AHORA + 60)
    base.update(cambios)
    return Contexto(**base)


# --- hash y payload -------------------------------------------------------------


def test_hash_coincide_con_el_contrato_oficial():
    registro = json.loads((RAIZ / "docs" / "ensayos" / "safe-onchain.json").read_text(encoding="utf-8"))
    casos = {
        "supply WETH por MultiSend": armar_safe_tx(aportar_colateral_weth(SAFE, 10**18)[0], 7),
        "repay USDC por MultiSend": armar_safe_tx(repagar_usdc(SAFE, 2_500 * 10**6)[0], 123456),
        "una sola llamada": armar_safe_tx(aportar_colateral_weth(SAFE, 5)[0][:1], 0),
    }
    assert registro["all_ok"] is True and len(registro["hashes"]) == 6
    for fila in registro["hashes"]:
        assert safe_tx_hash(1, fila["singleton"], casos[fila["case"]]) == fila["contract_hash"]


def test_lote_es_una_sola_safetx_atomica_con_approval_exacto():
    intencion = _intencion()
    assert intencion.modo == "ATOMICO_MULTISEND"
    assert intencion.safe_tx.to == MULTISEND_CALL_ONLY_1_4_1 and intencion.safe_tx.operation == 1
    approve = intencion.llamadas[1]["data"]
    assert decode(["address", "uint256"], bytes.fromhex(approve[10:])) == (AAVE_V3_POOL.lower(), 10**18)


def test_solo_acciones_y_destinos_permitidos_a_nombre_del_safe():
    with pytest.raises(PropuestaInvalida):
        crear_intencion("org-1", 1, SAFE, "0x" + "1" * 40, "pol", 1, "aportar_colateral_weth", {"monto_wei": 1}, 0, _simulacion(), AHORA)
    with pytest.raises(PropuestaInvalida):
        crear_intencion("org-1", 1, SAFE, SAFE, "pol", 1, "transferir_todo", {}, 0, _simulacion(), AHORA)
    with pytest.raises(AccionNoPermitida):
        armar_safe_tx([Llamada("0x" + "9" * 40, 0, "0x", "destino ajeno")], 0)


# --- aprobación atada al payload -------------------------------------------------


def test_cambiar_cualquier_campo_invalida_la_aprobacion():
    intencion = _intencion()
    aprobacion = aprobar(intencion, "tesorera@cliente", AHORA)
    assert validar_para_envio(intencion, aprobacion, _ctx()) == []
    for cambio in ({"parametros": {"monto_wei": 2 * 10**18}}, {"policy_version": 4}, {"organization_id": "org-2"},
                   {"expira_en": AHORA + 99_999}, {"simulacion": _simulacion(digest="estado-b")}):
        alterada = reemplazar(intencion, **cambio)
        assert "approval_does_not_match_payload" in validar_para_envio(alterada, aprobacion, _ctx(state_digest_actual=alterada.simulacion.state_digest))


def test_payload_alterado_sin_recalcular_hash():
    intencion = _intencion()
    # Cambio un byte del data y no recalculo el safeTxHash guardado.
    tx_alterada = type(intencion.safe_tx)(**{**intencion.safe_tx.como_dict(), "data": intencion.safe_tx.data[:-2] + "01"})
    alterada = reemplazar(intencion, safe_tx=tx_alterada)
    errores = validar_para_envio(alterada, aprobar(alterada, "x", AHORA), _ctx())
    assert "safe_tx_hash_mismatch" in errores


@pytest.mark.parametrize("ctx, error", [
    (dict(chain_id=11155111), "wrong_chain"),
    (dict(nonce_safe=8), "wrong_nonce"),
    (dict(bloque_actual=21_000_100), "stale_simulation"),
    (dict(state_digest_actual="estado-cambiado"), "stale_simulation"),
    (dict(ahora=AHORA + 7200), "expired"),
])
def test_red_nonce_simulacion_y_vencimiento(ctx, error):
    intencion = _intencion()
    assert error in validar_para_envio(intencion, aprobar(intencion, "x", AHORA), _ctx(**ctx))


def test_simulacion_fallida_no_se_aprueba():
    with pytest.raises(PropuestaInvalida):
        aprobar(_intencion(simulacion=_simulacion(ok=False)), "x", AHORA)


# --- registro, entrega y reconciliación ---------------------------------------------


class ServicioFalso:
    """Simula el Safe Transaction Service y la cadena."""

    def __init__(self, falla_antes=False, falla_despues=False):
        self.recibidas = {}
        self.entregas = 0
        self.nonce = 7
        self.falla_antes, self.falla_despues = falla_antes, falla_despues
        self.ejecucion = {}
        self.con_efecto = True

    def entregar(self, intencion):
        self.entregas += 1
        if self.falla_antes:
            raise TimeoutError("sin respuesta")
        self.recibidas[intencion.safe_tx_hash] = {"executed": False}
        if self.falla_despues:
            raise TimeoutError("el proveedor transmitió pero no devolvió el hash")
        return intencion.safe_tx_hash

    def buscar(self, h):
        if h not in self.recibidas:
            return None
        return {**self.recibidas[h], **self.ejecucion.get(h, {})}

    def nonce_actual(self, safe):
        return self.nonce

    def efecto(self, efecto, tx_hash):
        return self.con_efecto


def _preparada(registro=None):
    registro = registro or c.Registro()
    intencion = _intencion()
    registro.crear(intencion, "org-1:inc-9:aportar")
    aprobacion = aprobar(intencion, "tesorera@cliente", AHORA)
    coord = c.Coordinador(registro)
    coord.aprobar(intencion, aprobacion)
    return registro, coord, intencion, aprobacion


def test_doble_solicitud_crea_una_sola_propuesta():
    registro = c.Registro()
    a, b = _intencion(), _intencion()
    assert registro.crear(a, "org-1:inc-9:aportar") == registro.crear(b, "org-1:inc-9:aportar") == a.id
    assert registro.db.execute("SELECT count(*) FROM propuestas").fetchone()[0] == 1


def test_entrega_feliz_y_confirmacion_con_efecto():
    registro, coord, intencion, aprobacion = _preparada()
    servicio = ServicioFalso()
    assert coord.entregar(intencion, aprobacion, _ctx(), servicio) == c.ENVIADA
    assert coord.reconciliar(intencion, servicio) == c.ENVIADA  # esperando firmas humanas
    servicio.ejecucion[intencion.safe_tx_hash] = {"executed": True, "success": True, "tx_hash": "0xabc"}
    assert coord.reconciliar(intencion, servicio) == c.CONFIRMADA
    assert registro.historia(intencion.id) == ["PROPUESTA", "APROBADA", "INCIERTA", "ENVIADA", "CONFIRMADA"]


def test_receipt_exitoso_sin_efecto_no_se_confirma():
    registro, coord, intencion, aprobacion = _preparada()
    servicio = ServicioFalso()
    coord.entregar(intencion, aprobacion, _ctx(), servicio)
    servicio.ejecucion[intencion.safe_tx_hash] = {"executed": True, "success": True, "tx_hash": "0xabc"}
    servicio.con_efecto = False
    assert coord.reconciliar(intencion, servicio) == c.FALLIDA
    assert "without the expected effect" in registro.detalle(intencion.id)


def test_ejecucion_revertida_es_fallida():
    _, coord, intencion, aprobacion = _preparada()
    servicio = ServicioFalso()
    coord.entregar(intencion, aprobacion, _ctx(), servicio)
    servicio.ejecucion[intencion.safe_tx_hash] = {"executed": True, "success": False, "tx_hash": "0xdef"}
    assert coord.reconciliar(intencion, servicio) == c.FALLIDA


def test_timeout_sin_llegar_queda_incierta_y_no_se_reenvia_hasta_reconciliar():
    registro, coord, intencion, aprobacion = _preparada()
    servicio = ServicioFalso(falla_antes=True)
    assert coord.entregar(intencion, aprobacion, _ctx(), servicio) == c.INCIERTA
    with pytest.raises(c.EnvioRechazado) as error:
        coord.entregar(intencion, aprobacion, _ctx(), servicio)
    assert error.value.errores == ["uncertain_reconcile_first"] and servicio.entregas == 1
    # Reconciliar: no llegó y el nonce sigue libre → se puede entregar de nuevo.
    assert coord.reconciliar(intencion, servicio) == c.APROBADA
    servicio.falla_antes = False
    assert coord.entregar(intencion, aprobacion, _ctx(), servicio) == c.ENVIADA


def test_proveedor_transmite_antes_de_devolver_el_hash():
    _, coord, intencion, aprobacion = _preparada()
    servicio = ServicioFalso(falla_despues=True)
    assert coord.entregar(intencion, aprobacion, _ctx(), servicio) == c.INCIERTA
    assert coord.reconciliar(intencion, servicio) == c.ENVIADA  # la encontré: no la vuelvo a entregar
    assert servicio.entregas == 1


def test_nonce_usado_por_otra_transaccion():
    _, coord, intencion, aprobacion = _preparada()
    servicio = ServicioFalso(falla_antes=True)
    coord.entregar(intencion, aprobacion, _ctx(), servicio)
    servicio.nonce = 8
    assert coord.reconciliar(intencion, servicio) == c.FALLIDA


def test_aprobacion_vencida_al_entregar():
    registro, coord, intencion, aprobacion = _preparada()
    with pytest.raises(c.EnvioRechazado):
        coord.entregar(intencion, aprobacion, _ctx(ahora=AHORA + 7200), ServicioFalso())
    assert registro.estado(intencion.id) == c.FALLIDA


def test_transiciones_invalidas_y_compare_and_set():
    registro, coord, intencion, aprobacion = _preparada()
    with pytest.raises(c.TransicionInvalida):
        registro.transicionar(intencion.id, c.APROBADA, c.CONFIRMADA)
    with pytest.raises(c.TransicionInvalida):
        registro.transicionar(intencion.id, c.PROPUESTA, c.APROBADA)  # ya no está en PROPUESTA


# --- presentación y aislamiento --------------------------------------------------------


def test_guia_y_cuerpo_sin_firma():
    intencion = _intencion()
    resumen = resumen_para_aprobacion(intencion)
    assert resumen["atomic"] is True and resumen["fee_estimate_eth"] == "0.003" and resumen["approvals"] and resumen["risks"]
    guia = guia_manual(intencion)
    assert intencion.safe_tx_hash in guia and "Si no coincide, no firmes." in guia
    cuerpo = cuerpo_propuesta_servicio(intencion)
    assert cuerpo["sender"] is None and cuerpo["signature"] is None
    assert cuerpo["contractTransactionHash"] == intencion.safe_tx_hash


def test_el_spike_no_firma_ni_entra_al_runtime():
    fuentes = "".join(p.read_text(encoding="utf-8") for p in (RAIZ / "experiments" / "propuestas_safe").glob("*.py"))
    for prohibido in ("eth_account", "sign_transaction", "signHash", "private_key", "send_raw_transaction", "requests.post"):
        assert prohibido not in fuentes, prohibido
    codigo = ("import sys, api.main, worker_lectura; "
              "print(any(m.startswith('experiments.propuestas_safe') for m in sys.modules))")
    salida = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True,
                            env={**__import__("os").environ, "CHAINSIGNAL_DISABLE_DOTENV": "1", "PYTHONPATH": str(RAIZ)})
    assert salida.stdout.strip().splitlines()[-1] == "False", salida.stderr[-500:]
