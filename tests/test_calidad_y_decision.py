"""Features honestas y decisiones que respetan la calidad de los datos (E03)."""

import asyncio
from types import SimpleNamespace

import pytest

from generacion_features.extractor import ExtractorFeatures, entropia_normalizada
from ingestion_onchain.modelos import DatosWallet
from ingestion_onchain.resultados import (
    Calidad,
    CalidadDatos,
    Motivo,
    Procedencia,
    ResultadoIngesta,
    combinar,
)
from perfil_wallet.behavioral_scoring import BehavioralScorer
from tests.fixtures import WALLET_MOCK, crear_transaccion, crear_transferencia_token


def _calidad(calidad=Calidad.FRESH, completo=True, motivo=Motivo.NINGUNO):
    procedencia = Procedencia("etherscan", 1, "ethereum", historial_completo=completo)
    componentes = {
        "transactions": ResultadoIngesta(calidad, procedencia, motivo),
        "tokens": ResultadoIngesta(Calidad.FRESH, procedencia),
        "balance": ResultadoIngesta(Calidad.FRESH, procedencia),
    }
    return combinar(componentes)


def _datos(txs, completo=True, tokens=None, calidad=Calidad.FRESH):
    return DatosWallet(WALLET_MOCK, 1, 10**18, txs, tokens or [], _calidad(calidad, completo))


# --- entropía ---------------------------------------------------------------------


def test_entropia_normalizada_va_de_cero_a_uno():
    assert entropia_normalizada([]) == 0.0
    assert entropia_normalizada([7]) == 0.0
    assert entropia_normalizada([5, 5, 5, 5]) == 1.0
    sesgada = entropia_normalizada([97, 1, 1, 1])
    assert 0.0 < sesgada < 0.2


def test_diversidad_cuenta_contratos_y_no_simbolos():
    tokens = [crear_transferencia_token("USDC", contrato="0x" + "1" * 40),
              crear_transferencia_token("USDC", contrato="0x" + "2" * 40)]
    features = ExtractorFeatures().extraer(_datos([crear_transaccion()], tokens=tokens))
    assert features.tokens_unicos_utilizados == 2
    assert features.diversidad_tokens == 1.0


# --- edad observada -----------------------------------------------------------------


def _wallet_de_diez_dias(completo):
    txs = [crear_transaccion(f"0x{i}", timestamp=1_700_000_000 + i * 86_400) for i in range(10)]
    return ExtractorFeatures().extraer(_datos(txs, completo=completo))


def test_wallet_joven_solo_con_historial_completo():
    completa = _wallet_de_diez_dias(completo=True)
    truncada = _wallet_de_diez_dias(completo=False)
    scorer = BehavioralScorer()

    assert completa.dias_observados == 9 and truncada.dias_observados == 9
    assert any(f["factor"] == "Young Wallet" for f in scorer.get_risk_breakdown(completa))
    assert not any(f["factor"] == "Young Wallet" for f in scorer.get_risk_breakdown(truncada))
    assert scorer.calcular_scores(truncada).risk_score.value < scorer.calcular_scores(completa).risk_score.value


def test_balance_desconocido_no_se_trata_como_cero():
    datos = DatosWallet(WALLET_MOCK, 1, None, [crear_transaccion()], [], _calidad())
    features = ExtractorFeatures().extraer(datos)
    assert features.balance_eth_actual is None
    from perfil_wallet.clasificador import ClasificadorWallet

    ClasificadorWallet().clasificar(features)  # no falla ni asume 0 ETH


def test_reciente_se_mide_contra_el_bloque_de_referencia():
    from ingestion_onchain.resultados import BloqueRef

    referencia = BloqueRef(100, "0x" + "a" * 64, 1_700_000_000 + 40 * 86_400)
    procedencia = Procedencia("etherscan", 1, "ethereum", referencia=referencia, historial_completo=True)
    calidad = combinar({"transactions": ResultadoIngesta(Calidad.FRESH, procedencia)})
    txs = [crear_transaccion("0x1", timestamp=1_700_000_000), crear_transaccion("0x2", timestamp=1_700_000_000 + 39 * 86_400)]
    features = ExtractorFeatures().extraer(DatosWallet(WALLET_MOCK, 1, 1, txs, [], calidad))
    assert features.porcentaje_transacciones_recientes == 50.0


# --- decisiones -------------------------------------------------------------------------


class IngestaFija:
    def __init__(self, datos):
        self.datos = datos

    def obtener_datos_wallet(self, direccion):
        return self.datos


def _servicio(datos, monkeypatch, decision="EXECUTE_ADVANCED"):
    from services.agent_service import AgentService
    from strategy.modelos_estrategia import DecisionEstrategia

    servicio = AgentService()
    servicio._ingesta = IngestaFija(datos)

    async def _decide(insight, scores, metrics):
        return ({"decision": decision, "recommended_action": "protect", "reasoning": "sintético"},
                DecisionEstrategia(True, True, True, actions=["transfer"], detail="sintético"))

    monkeypatch.setattr(servicio, "_decide", _decide)
    monkeypatch.setattr(servicio.strategy_engine, "select", lambda *a, **k: {"strategy": "RISK_SHIELD", "force_execute": True})
    return servicio


def _no_disponible():
    procedencia = Procedencia("etherscan", 1, "ethereum")
    return DatosWallet(WALLET_MOCK, 1, None, [], [], combinar({
        "transactions": ResultadoIngesta(Calidad.UNAVAILABLE, procedencia, Motivo.RATE_LIMITED),
        "tokens": ResultadoIngesta(Calidad.UNAVAILABLE, procedencia, Motivo.RATE_LIMITED),
        "balance": ResultadoIngesta(Calidad.UNAVAILABLE, procedencia, Motivo.RATE_LIMITED),
    }))


def test_datos_no_disponibles_no_generan_recomendacion_ni_scores(monkeypatch):
    servicio = _servicio(_no_disponible(), monkeypatch)
    reporte = asyncio.run(servicio.run_pipeline_core(WALLET_MOCK))

    assert reporte["agent_decision"]["decision"] == "DATA_UNAVAILABLE"
    assert reporte["agent_decision"]["recommended_action"] == "retry_later"
    assert reporte["scores"] is None and reporte["profile"] is None
    assert reporte["data_quality"]["status"] == "UNAVAILABLE"
    assert reporte["data_quality"]["reason"] == "rate_limited"
    assert reporte["data_quality"]["no_activity"] is False


def test_stream_con_datos_no_disponibles_termina_sin_recomendacion(monkeypatch):
    import json

    servicio = _servicio(_no_disponible(), monkeypatch)

    async def recorrer():
        return [json.loads(e[6:]) async for e in servicio.run_pipeline_stream(WALLET_MOCK)]

    eventos = asyncio.run(recorrer())
    final = eventos[-1]
    assert final["paso"] == "decision_final"
    assert final["data"]["decision"] == "DATA_UNAVAILABLE"
    assert final["data"]["execution"] is False
    assert not any(e["paso"] in {"calculating_scores", "strategy_selected"} for e in eventos)


@pytest.mark.parametrize("calidad", [Calidad.STALE, Calidad.PARTIAL])
def test_datos_viejos_o_parciales_no_permiten_decision_accionable(monkeypatch, calidad):
    txs = [crear_transaccion(f"0x{i}", timestamp=1_700_000_000 + i * 86_400) for i in range(5)]
    servicio = _servicio(_datos(txs, calidad=calidad, completo=False), monkeypatch)
    reporte = asyncio.run(servicio.run_pipeline_core(WALLET_MOCK))

    assert reporte["agent_decision"]["decision"] == "MONITOR"
    assert reporte["data_quality"]["status"] == calidad.value
    assert reporte["data_quality"]["actionable_allowed"] is False


def test_datos_frescos_conservan_la_decision(monkeypatch):
    txs = [crear_transaccion(f"0x{i}", timestamp=1_700_000_000 + i * 86_400) for i in range(5)]
    servicio = _servicio(_datos(txs), monkeypatch)
    reporte = asyncio.run(servicio.run_pipeline_core(WALLET_MOCK))
    assert reporte["agent_decision"]["decision"] == "EXECUTE_ADVANCED"
    assert reporte["metrics"]["complete_history"] is True


# --- worker y cuentas -----------------------------------------------------------------------


def test_worker_registra_no_disponible_sin_pisar_la_ultima_decision(cliente_owner, organizacion, monkeypatch):
    from unittest.mock import AsyncMock

    from agent_loop import AutonomousAgentLoop
    from api.sesion import servicio_recursos

    org_id = organizacion[0]
    cuenta = cliente_owner.post(f"/orgs/{org_id}/accounts", json={"address": "0x" + "7" * 40}).json()
    servicio = AsyncMock()
    servicio.run_pipeline_core.return_value = {"agent_decision": {"decision": "MONITOR"}, "scores": {"risk": {"value": 12}},
                                               "data_quality": {"status": "FRESH"}}
    monitor = AutonomousAgentLoop(servicio, servicio_recursos())
    asyncio.run(monitor.run_once())

    servicio.run_pipeline_core.return_value = {"agent_decision": {"decision": "DATA_UNAVAILABLE"}, "scores": None,
                                               "data_quality": {"status": "UNAVAILABLE"}}
    resultado = asyncio.run(monitor.evaluate_wallet(cuenta["address"]))
    assert resultado == {"status": "unavailable", "decision": None, "risk_score": None, "data_quality": "UNAVAILABLE"}
    servicio_recursos().registrar_evaluacion(org_id, cuenta["id"], resultado["decision"], resultado["risk_score"],
                                             resultado["status"], resultado["data_quality"])
    estado = cliente_owner.get(f"/orgs/{org_id}/accounts/{cuenta['id']}").json()

    assert estado["last_data_quality"] == "UNAVAILABLE"
    assert estado["last_decision"] == "MONITOR" and estado["last_risk_score"] == 12


def test_no_se_puede_observar_una_cuenta_de_otra_red(cliente_owner, organizacion):
    respuesta = cliente_owner.post(f"/orgs/{organizacion[0]}/accounts", json={"address": "0x" + "8" * 40, "chain_id": 11155111})
    assert respuesta.status_code == 422
