"""Pruebas de la guarda única de escritura (infra/modo.py), A10 y A03.

En READ_ONLY cada método que firma o pide firmar debe fallar con
EscrituraDeshabilitada antes de cualquier llamada HTTP al WDK, aun con
AGENT_DEMO_MODE activo. El modo experimental nunca vale en producción.
"""

import asyncio
from unittest.mock import MagicMock

import httpx
import pytest

from domain.modelos_contrato import ContratoCompilado, ContratoDeplegado
from infra.db import init_db, make_engine
from infra.modo import EscrituraDeshabilitada, exigir_escritura_experimental


@pytest.fixture
def sin_post_http(monkeypatch):
    post = MagicMock(side_effect=AssertionError("httpx.post no debía llamarse"))
    monkeypatch.setattr(httpx, "post", post)
    return post


@pytest.fixture
def wallet_agent():
    from wallet_controller.wallet_agent import WalletAgent

    agente = WalletAgent()  # su health check apunta a 127.0.0.1:9 y falla rápido
    agente.wdk_active = True  # peor caso: el WDK parece disponible
    return agente


@pytest.mark.parametrize("operacion", [
    lambda a: a.create_agent_wallet(),
    lambda a: a.ejecutar_transaccion("0x" + "1" * 40, 1),
    lambda a: a.deploy_contract([], "0x00"),
    lambda a: a.call_contract("0x" + "1" * 40, [], "poke"),
    lambda a: a.execute_swap("ETH", "0x" + "2" * 40, 1),
], ids=["crear_wallet", "transferir", "desplegar", "llamar_contrato", "swap"])
def test_wallet_agent_no_firma_en_read_only(wallet_agent, sin_post_http, monkeypatch, operacion):
    from infra.config import settings

    monkeypatch.setattr(settings, "AGENT_DEMO_MODE", True)
    with pytest.raises(EscrituraDeshabilitada):
        operacion(wallet_agent)
    sin_post_http.assert_not_called()


@pytest.mark.parametrize("operacion", [
    lambda s: s.desplegar_contrato(ContratoCompilado(name="X", abi=[], bytecode="0x00", source_code="")),
    lambda s: s.ejecutar_funcion(ContratoDeplegado(name="X", address="0x" + "1" * 40, transaction_hash="0x", abi=[]), "poke"),
    lambda s: s.transferir_activo("0x" + "1" * 40, 1),
    lambda s: s.ejecutar_swap("ETH", "0x" + "2" * 40, 1),
], ids=["desplegar", "llamar_contrato", "transferir", "swap"])
def test_servicio_wdk_no_firma_en_read_only(sin_post_http, operacion):
    from services.servicio_wdk import ServicioWDK

    servicio = ServicioWDK()
    servicio._agente.wdk_active = True
    with pytest.raises(EscrituraDeshabilitada):
        operacion(servicio)
    sin_post_http.assert_not_called()


def test_runner_ejecutor_experimento_y_guardian_se_niegan_en_read_only(sin_post_http):
    from agent_executor.executor import AgentExecutor
    from execution_guard.runner import ExecutionRunner
    from experiments.guardian_loop import GuardianAgentLoop
    from experiments.testnet_ejecucion import ExperimentoEjecucionTestnet

    with pytest.raises(EscrituraDeshabilitada):
        ExecutionRunner(MagicMock()).run(MagicMock())
    with pytest.raises(EscrituraDeshabilitada):
        AgentExecutor()
    with pytest.raises(EscrituraDeshabilitada):
        ExperimentoEjecucionTestnet()
    with pytest.raises(EscrituraDeshabilitada):
        GuardianAgentLoop(MagicMock(), MagicMock())
    sin_post_http.assert_not_called()


def test_modo_experimental_nunca_escribe_en_produccion(modo_experimental, monkeypatch):
    from infra.config import settings

    monkeypatch.setattr(settings, "APP_ENV", "production")
    with pytest.raises(EscrituraDeshabilitada):
        exigir_escritura_experimental("transferir")


def test_cli_experimental_exige_confirmacion_y_modo(capsys):
    from experiments import cli

    assert cli.main(["ejecutar", "0x" + "1" * 40]) == 2
    assert cli.main(["ejecutar", "0x" + "1" * 40, "--confirmo-testnet"]) == 3


# --- A10: nunca convierto una falla del WDK en éxito simulado -----------------


def test_servicio_wdk_sin_hash_es_fallo_no_exito(modo_experimental):
    from services.servicio_wdk import ServicioWDK

    servicio = ServicioWDK()
    servicio._agente = MagicMock(wdk_active=True)
    servicio._agente.ejecutar_transaccion.return_value = None
    servicio._agente.execute_swap.return_value = None
    servicio._agente.deploy_contract.return_value = None

    assert servicio.transferir_activo("0x" + "1" * 40, 1).success is False
    assert servicio.ejecutar_swap("ETH", "0x" + "2" * 40, 1).success is False
    assert servicio.desplegar_contrato(ContratoCompilado(name="X", abi=[], bytecode="0x00", source_code="")) is None


def test_servicio_wdk_no_inventa_saldo_sin_wdk(modo_experimental):
    from services.servicio_wdk import ServicioWDK

    servicio = ServicioWDK()
    servicio._agente = MagicMock(wdk_active=False)
    assert servicio.consultar_balance() is None


@pytest.mark.parametrize("tx_hash,estado,error", [
    (None, "failed", "wdk_no_tx_hash"),
    ("0x" + "a" * 64, "submitted", None),
])
def test_executor_distingue_envio_de_confirmacion_y_falla(modo_experimental, tmp_path, tx_hash, estado, error):
    from agent_executor.executor import AgentExecutor

    engine = make_engine(f"sqlite:///{tmp_path / 'exec.db'}")
    init_db(engine)
    ejecutor = AgentExecutor(engine_=engine)
    ejecutor.wallet_agent = MagicMock()
    ejecutor.wallet_agent.get_address.return_value = "0x" + "3" * 40
    ejecutor.wallet_agent.get_balance.return_value = 1.0
    ejecutor.wallet_agent.ejecutar_transaccion.return_value = tx_hash

    resultado = asyncio.run(ejecutor.execute({"wallet": "0x" + "4" * 40, "cycle": 1, "action": {"type": "transfer", "amount_eth": 0.001}}))

    assert resultado["status"] == estado
    assert resultado["status"] not in {"confirmed", "simulated"}
    assert resultado["error"] == error


# --- A03: la política de simulación no depende de APP_ENV --------------------


def _plan(politica):
    from execution_guard.guard import ExecutionGuard

    guard = ExecutionGuard.__new__(ExecutionGuard)
    guard.persistence = MagicMock(load_plan=MagicMock(return_value=None), get_all_plans=MagicMock(return_value=[]))
    plan = guard.create_plan(
        wallet="0x" + "5" * 40,
        actions_data=[{"type": "TRANSFER", "params": {"to": "0x" + "6" * 40, "value_wei": 1}}],
        risk_score=90, block_number=1, nonce=0, balance=1.0, simulation_policy=politica,
    )
    return guard, plan


@pytest.mark.parametrize("app_env", ["local", "test", "staging", "production"])
def test_politica_estricta_sin_evidencia_se_rechaza_en_cualquier_entorno(monkeypatch, app_env):
    from execution_guard.guard import POLITICA_ESTRICTA
    from infra.config import settings

    monkeypatch.setattr(settings, "APP_ENV", app_env)
    guard, plan = _plan(POLITICA_ESTRICTA)
    valido, motivo = guard.validate_plan(plan, {"nonce": 0, "balance": 1.0, "current_risk_score": 90, "simulation_success": True})
    assert valido is False
    assert "evidence" in motivo


def test_politica_testnet_se_rechaza_en_read_only():
    from execution_guard.guard import POLITICA_TESTNET_SIN_SIMULACION

    guard, plan = _plan(POLITICA_TESTNET_SIN_SIMULACION)
    valido, _ = guard.validate_plan(plan, {"nonce": 0, "balance": 1.0, "current_risk_score": 90, "chain_id": 11155111})
    assert valido is False


def test_politica_testnet_exige_sepolia(modo_experimental):
    from execution_guard.guard import POLITICA_TESTNET_SIN_SIMULACION

    guard, plan = _plan(POLITICA_TESTNET_SIN_SIMULACION)
    estado = {"nonce": 0, "balance": 1.0, "current_risk_score": 90}
    assert guard.validate_plan(plan, {**estado, "chain_id": 1})[0] is False
    assert guard.validate_plan(plan, {**estado, "chain_id": 11155111})[0] is True
