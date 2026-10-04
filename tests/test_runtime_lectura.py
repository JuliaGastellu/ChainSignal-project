"""Pruebas del runtime comercial de solo lectura (E01).

Verifico en backend, no en la interfaz, que ninguna ruta, alias SSE, health,
reconexión o análisis llega a firmar, transferir, hacer swap ni desplegar,
aunque la decisión sea accionable, haya presupuesto precargado y
AGENT_DEMO_MODE esté activo. Pongo espías en todos los métodos de firma y
exijo cero llamadas. Nunca arranco el WDK real.
"""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from strategy.modelos_estrategia import DecisionEstrategia

RAIZ = Path(__file__).resolve().parents[1]
WALLET = "0x00000000000000000000000000000000000000a1"

# Todo método que crea identidad, firma o pide firmar. Si alguno se llama
# durante el runtime de lectura, la prueba falla.
METODOS_DE_FIRMA = [
    ("wallet_controller.wallet_agent", "WalletAgent", "create_agent_wallet"),
    ("wallet_controller.wallet_agent", "WalletAgent", "ejecutar_transaccion"),
    ("wallet_controller.wallet_agent", "WalletAgent", "deploy_contract"),
    ("wallet_controller.wallet_agent", "WalletAgent", "call_contract"),
    ("wallet_controller.wallet_agent", "WalletAgent", "execute_swap"),
    ("services.servicio_wdk", "ServicioWDK", "desplegar_contrato"),
    ("services.servicio_wdk", "ServicioWDK", "ejecutar_funcion"),
    ("services.servicio_wdk", "ServicioWDK", "transferir_activo"),
    ("services.servicio_wdk", "ServicioWDK", "ejecutar_swap"),
    ("services.servicio_wdk", "ServicioWDK", "obtener_direccion_wallet"),
    ("execution_guard.runner", "ExecutionRunner", "run"),
    ("agent_executor.executor", "AgentExecutor", "__init__"),
    ("agent_executor.executor", "AgentExecutor", "execute"),
    ("services.agent_budget_service", "AgentBudgetService", "verify_and_fund"),
    ("services.agent_budget_service", "AgentBudgetService", "consume"),
    ("experiments.testnet_ejecucion", "ExperimentoEjecucionTestnet", "__init__"),
    ("experiments.guardian_loop", "GuardianAgentLoop", "__init__"),
]


@pytest.fixture
def espias(monkeypatch):
    """Reemplazo cada método de firma por un espía que registra llamadas."""
    import importlib

    registro = {}
    for modulo, clase, metodo in METODOS_DE_FIRMA:
        cls = getattr(importlib.import_module(modulo), clase)
        espia = MagicMock(name=f"{clase}.{metodo}", side_effect=AssertionError(f"Se llamó {clase}.{metodo}"))
        monkeypatch.setattr(cls, metodo, espia)
        registro[f"{clase}.{metodo}"] = espia

    # Cualquier POST HTTP saliente (el WDK solo firma por POST) también es una falla.
    import httpx

    post = MagicMock(name="httpx.post", side_effect=AssertionError("Se hizo un httpx.post"))
    monkeypatch.setattr(httpx, "post", post)
    registro["httpx.post"] = post
    return registro


def _sin_llamadas(registro):
    llamados = {nombre: espia.call_count for nombre, espia in registro.items() if espia.call_count}
    assert llamados == {}, f"Se llamaron métodos de firma: {llamados}"


@pytest.fixture
def decision_accionable(monkeypatch):
    """Fuerzo el peor caso: decisión accionable con transferencia, swap y contrato,
    estrategia con force_execute, presupuesto precargado y modo demo activo."""
    import api.main as api_main
    from infra.config import settings
    from infra.db import SessionLocal, init_db, engine
    from infra.db_models import AgentBudgetRecord

    servicio = api_main._agent_service

    from ingestion_onchain.resultados import Calidad, CalidadDatos, Motivo

    metrics = SimpleNamespace(
        total_transacciones=500, balance_eth_actual=10.0, dias_observados=400, historial_completo=True,
        primera_actividad_observada_timestamp=1_600_000_000,
        frecuencia_transacciones_por_dia=3.0, porcentaje_interacciones_contratos=80.0,
        # Peor caso: datos FRESH, así la decisión accionable no se degrada por calidad.
        calidad_datos=CalidadDatos(Calidad.FRESH, Motivo.NINGUNO, {}),
    )
    profile = SimpleNamespace(type="defi_power_user", confidence="high", description="sintético", signals=["s1"])
    valor = lambda v: SimpleNamespace(value=v, interpretation="sintético")  # noqa: E731
    scores_obj = SimpleNamespace(risk_score=valor(95), activity_score=valor(90), defi_engagement=valor(80), web3_activity_index=valor(85))
    scores_dict = {"activity": 90, "risk": 95, "defi_engagement": 80, "confidence": 1.0}
    insight = SimpleNamespace(type="risk_guard", analyzed_wallet=WALLET, risk_score=95, activity_score=90, recommended_action="protect")

    async def _analyze(wallet_addr):
        return metrics, profile, scores_obj, scores_dict, {"factor": "sintético"}, insight

    estrategia = DecisionEstrategia(
        requires_contract=True, requires_funds_movement=True, requires_execution=True, requires_swap=True,
        token_in="ETH", token_out="0xdAC17F958D2ee523a2206206994597C13D831ec7",  # gitleaks:allow (dirección pública de un token)
        actions=["transfer", "swap", "deploy"], detail="Riesgo crítico sintético",
    )

    async def _decide(insight_obj, scores, metrics_):
        return {"decision": "EXECUTE_ADVANCED", "contract_type": "risk_guard", "recommended_action": "protect", "reasoning": "sintético"}, estrategia

    monkeypatch.setattr(servicio, "_analyze", _analyze)
    monkeypatch.setattr(servicio, "_decide", _decide)
    monkeypatch.setattr(servicio.strategy_engine, "select", lambda *a, **k: {"strategy": "RISK_SHIELD", "force_execute": True, "confidence": 0.99, "trigger_signals": ["SUSPICIOUS_PATTERN"]})
    monkeypatch.setattr(settings, "AGENT_DEMO_MODE", True)

    init_db(engine)
    with SessionLocal() as session:
        session.merge(AgentBudgetRecord(wallet=WALLET, agent_wallet="0x" + "b" * 40, balance_eth=5.0, spent_eth=0.0, last_funding_amount_eth=5.0))
        session.commit()
    return servicio


@pytest.fixture
def cliente(organizacion):
    """Cliente con sesión de owner: desde E02 el análisis exige sesión."""
    from tests.ayudantes_identidad import iniciar_sesion

    with iniciar_sesion(organizacion[1]) as c:
        yield c


def _eventos_sse(texto):
    return [json.loads(linea[6:]) for linea in texto.splitlines() if linea.startswith("data: ")]


RUTAS_SSE = [
    f"/run-agent/{WALLET}",
    f"/ejecutar-agente/{WALLET}",
    f"/events/sse/{WALLET}",
    f"/events/sse?wallet={WALLET}",
]


@pytest.mark.parametrize("ruta", RUTAS_SSE)
def test_sse_y_aliases_no_ejecutan_aunque_la_decision_sea_accionable(cliente, espias, decision_accionable, ruta):
    respuesta = cliente.get(ruta)

    assert respuesta.status_code == 200
    eventos = _eventos_sse(respuesta.text)
    final = [e for e in eventos if e.get("paso") == "decision_final"][-1]
    assert final["data"]["decision"] == "EXECUTE_ADVANCED"
    assert final["data"]["execution"] is False
    assert final["data"]["motivo"] == "read_only_runtime"
    pasos = {e.get("paso") for e in eventos}
    assert pasos.isdisjoint({"execution_safety", "execution_submitted", "contract_deployment", "x402_validation", "execution_value"})
    assert all(e["action_scope"]["agent_wallet"] == "disabled" for e in eventos)
    _sin_llamadas(espias)


@pytest.mark.parametrize("ruta", [
    "/health", f"/report/{WALLET}", f"/analyze/wallet/{WALLET}", "/analyze/block/100",
    # Rutas globales heredadas: desde E02 responden 410 sin leer estado.
    "/agent/status", "/agent/state", "/agent/history", "/agent/actions", "/agent-activity",
    f"/agent/budget/{WALLET}", f"/agent-budget/{WALLET}", f"/agent/state/{WALLET}",
    "/agent/learning", "/agent/radar", "/agent/watch", "/agent/stream",
])
def test_rutas_get_de_lectura_no_firman(cliente, espias, decision_accionable, ruta):
    respuesta = cliente.get(ruta)

    # /analyze/block responde 503 sin RPC configurado; nada de esto puede ser 5xx por firma.
    assert respuesta.status_code in {200, 410, 503}, respuesta.text
    _sin_llamadas(espias)


def test_rutas_de_organizacion_no_firman(cliente, organizacion, espias, decision_accionable):
    org_id = organizacion[0]
    cuenta = cliente.post(f"/orgs/{org_id}/accounts", json={"address": WALLET, "chain_id": 1}).json()
    for ruta in (f"/orgs/{org_id}/accounts", f"/orgs/{org_id}/accounts/{cuenta['id']}",
                 f"/orgs/{org_id}/accounts/{cuenta['id']}/analysis", f"/orgs/{org_id}/policies",
                 f"/orgs/{org_id}/events", f"/orgs/{org_id}/members", "/auth/session"):
        assert cliente.get(ruta).status_code == 200, ruta
    _sin_llamadas(espias)


def test_health_declara_modo_solo_lectura(cliente):
    datos = cliente.get("/health").json()
    assert datos["mode"] == "READ_ONLY"
    assert set(datos) == {"status", "service", "version", "mode"}


@pytest.mark.parametrize("metodo,ruta", [
    ("POST", "/agent/budget"), ("POST", "/fund-agent"), ("POST", "/agent/execute"),
    ("POST", "/agent/start"), ("POST", "/agent/stop"), ("GET", "/agent/address"),
])
@pytest.mark.parametrize("con_sesion", [False, True], ids=["anonimo", "con_sesion_owner"])
def test_rutas_economicas_responden_403_sin_efectos(cliente, espias, decision_accionable, metodo, ruta, con_sesion):
    from tests.ayudantes_identidad import cliente_anonimo

    cuerpo = {"wallet": WALLET, "tx_hash": "0x" + "c" * 64}
    quien = cliente if con_sesion else cliente_anonimo()
    respuesta = quien.request(metodo, ruta, json=cuerpo if metodo == "POST" else None)

    assert respuesta.status_code == 403
    assert respuesta.json()["error"] == "economic_route_disabled"
    _sin_llamadas(espias)


def test_doble_consulta_secuencial_y_concurrente_no_ejecuta(cliente, espias, decision_accionable):
    # Secuencial: la misma wallet dos veces seguidas.
    for _ in range(2):
        assert cliente.get(f"/run-agent/{WALLET}").status_code == 200

    # Concurrente: varias consultas a la vez sobre la misma wallet.
    resultados = []

    def consultar():
        resultados.append(cliente.get(f"/events/sse/{WALLET}"))

    hilos = [threading.Thread(target=consultar) for _ in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    assert all(r.status_code == 200 for r in resultados)
    finales = [[e for e in _eventos_sse(r.text) if e.get("paso") == "decision_final"][-1]["data"] for r in resultados]
    assert all(f["execution"] is False for f in finales)
    _sin_llamadas(espias)


def test_consultas_duplicadas_no_agotan_el_semaforo(decision_accionable):
    """Antes, ALREADY_RUNNING retenía el semáforo y tres duplicados dejaban el
    servicio en SYSTEM_BUSY para siempre."""
    import asyncio

    servicio = decision_accionable

    async def escenario():
        async with servicio._active_stream_wallets_lock:
            servicio._active_stream_wallets.add(WALLET)
        for _ in range(5):
            eventos = [e async for e in servicio._run_stream(WALLET, source="test")]
            assert eventos[-1]["data"]["decision"] == "ALREADY_RUNNING"
        async with servicio._active_stream_wallets_lock:
            servicio._active_stream_wallets.discard(WALLET)
        eventos = [e async for e in servicio._run_stream(WALLET, source="test")]
        return eventos[-1]["data"]["decision"]

    assert asyncio.run(escenario()) == "EXECUTE_ADVANCED"


def test_reconexion_sse_a_mitad_del_stream_no_ejecuta(cliente, espias, decision_accionable):
    # Abro el stream, leo un evento y corto como lo haría un navegador al perder conexión.
    with cliente.stream("GET", f"/run-agent/{WALLET}") as respuesta:
        for linea in respuesta.iter_lines():
            if linea.startswith("data: "):
                break

    # Reconecto y completo el stream.
    respuesta = cliente.get(f"/run-agent/{WALLET}")
    final = [e for e in _eventos_sse(respuesta.text) if e.get("paso") == "decision_final"][-1]
    assert final["data"]["execution"] is False
    _sin_llamadas(espias)


def test_stream_de_eventos_conectar_y_reconectar_no_firma(cliente, organizacion, espias, decision_accionable):
    """El stream de la organización es infinito, así que consumo su generador y
    lo cierro con aclose(), como hace el servidor al cortar. Conecto dos veces,
    la segunda desde el último cursor (reconexión con Last-Event-ID)."""
    from api.rutas_org import generar_stream_eventos
    from api.sesion import servicio_identidad

    org_id = organizacion[0]
    cliente.post(f"/orgs/{org_id}/accounts", json={"address": WALLET})
    sesion = servicio_identidad().sesion_por_token(cliente.cookies.get("cs_session"))
    ctx = servicio_identidad().contexto(sesion, org_id, "viewer")

    async def conectar(cursor):
        stream = generar_stream_eventos(sesion, ctx, cursor, intervalo=0)
        mensajes = [await stream.__anext__() for _ in range(3)]
        await stream.aclose()
        ids = [int(m.split("\n")[0][4:]) for m in mensajes if m.startswith("id: ")]
        return ids

    import asyncio

    primeros = asyncio.run(conectar(0))
    assert primeros
    tras_reconectar = asyncio.run(conectar(primeros[-1]))
    assert all(i > primeros[-1] for i in tras_reconectar)
    _sin_llamadas(espias)


def test_lifespan_no_arranca_loops(monkeypatch):
    import asyncio

    import api.main as api_main

    tareas_antes = set()
    creadas = []
    original = asyncio.create_task

    def espiar_tareas(coro, *a, **k):
        creadas.append(getattr(coro, "__qualname__", repr(coro)))
        return original(coro, *a, **k)

    monkeypatch.setattr(asyncio, "create_task", espiar_tareas)
    with TestClient(api_main.app):
        pass
    assert not any("loop" in nombre.lower() or "_run" in nombre for nombre in creadas), creadas
    assert not hasattr(api_main, "_agent_loop")
    assert not hasattr(api_main, "_guardian_loop")
    assert not hasattr(api_main, "_wallet_agent")


def test_servicio_de_analisis_no_tiene_capa_de_firma():
    from services.agent_service import AgentService

    servicio = AgentService()
    for atributo in ("wdk", "budget", "guard", "lock_manager", "run_pipeline_loop", "_execute_with_esl"):
        assert not hasattr(servicio, atributo), atributo


def test_api_arranca_sin_secretos_de_firma_ni_importa_la_capa_de_firma(tmp_path):
    """Importo la API en un proceso limpio sin seed, token WDK ni destino de rescate."""
    entorno = {k: v for k, v in os.environ.items() if k not in {
        "SAFE_WALLET_ADDRESS", "WDK_SERVICE_TOKEN", "AGENT_SEED_PHRASE", "CHAINSIGNAL_MODE", "WDK_URL",
    }}
    entorno.update({
        "CHAINSIGNAL_DISABLE_DOTENV": "1",
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'arranque.db').as_posix()}",
        "PYTHONPATH": str(RAIZ),
    })
    codigo = (
        "import sys, json\n"
        "import api.main as m\n"
        "prohibidos = ['wallet_controller.wallet_agent', 'services.servicio_wdk', 'execution_guard.runner',"
        " 'agent_executor.executor', 'experiments', 'experiments.testnet_ejecucion', 'experiments.guardian_loop']\n"
        "print(json.dumps({'modo': m.settings.CHAINSIGNAL_MODE, 'cargados': [p for p in prohibidos if p in sys.modules]}))\n"
    )
    salida = subprocess.run([sys.executable, "-c", codigo], cwd=tmp_path, env=entorno, capture_output=True, text=True, timeout=120)

    assert salida.returncode == 0, salida.stderr[-2000:]
    resultado = json.loads(salida.stdout.strip().splitlines()[-1])
    assert resultado == {"modo": "READ_ONLY", "cargados": []}


def test_worker_de_lectura_evalua_sin_firmar(espias, decision_accionable, cliente, organizacion):
    import asyncio

    from agent_loop import AutonomousAgentLoop
    from api.sesion import servicio_recursos

    org_id = organizacion[0]
    cuenta = cliente.post(f"/orgs/{org_id}/accounts", json={"address": WALLET, "priority": "high"}).json()
    monitor = AutonomousAgentLoop(decision_accionable, servicio_recursos())

    resultados = asyncio.run(monitor.run_once())

    assert resultados[cuenta["id"]]["status"] == "analyzed"
    estado = cliente.get(f"/orgs/{org_id}/accounts/{cuenta['id']}").json()
    assert estado["last_risk_score"] == 95
    assert estado["last_decision"] == "EXECUTE_ADVANCED"
    _sin_llamadas(espias)


def test_worker_se_niega_a_arrancar_fuera_de_read_only(modo_experimental):
    import asyncio

    import worker_lectura

    with pytest.raises(SystemExit):
        asyncio.run(worker_lectura.main())
