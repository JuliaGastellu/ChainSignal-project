# Mi runtime de lectura (E01)

Fecha: 3 de octubre de 2026. Actualicé el grafo y los requisitos de arranque el 4 de octubre, con E02: la API ya no usa una clave global y los recursos privados viven bajo `/orgs/{org_id}/` ([mi identidad](IDENTIDAD.md)).

El runtime comercial de ChainSignal es de solo lectura. Ninguna ruta de la API, alias SSE, health, reconexión, análisis ni el worker de monitoreo pueden firmar, transferir, hacer swap, desplegar contratos ni pedirle al WDK que lo haga. Lo verifico en backend con espías sobre todos los métodos de firma, no en la interfaz.

## Modo de runtime

`CHAINSIGNAL_MODE` admite dos valores (`infra/modo.py`):

| Modo | Para qué | Qué exige al arrancar |
|---|---|---|
| `READ_ONLY` (por defecto) | API y worker del producto | Ningún secreto de firma: no pide seed, `WDK_SERVICE_TOKEN` ni `SAFE_WALLET_ADDRESS`. Desde E02 tampoco hay clave global; cada persona inicia sesión. |
| `TESTNET_EXPERIMENT` | Experimentos manuales en Sepolia (`experiments/`) | `SAFE_WALLET_ADDRESS`, `WDK_SERVICE_TOKEN` y `APP_ENV` distinto de `production`. |

Un valor distinto de esos dos frena el arranque. Una dirección nula o de quema en `SAFE_WALLET_ADDRESS` también lo frena, en cualquier modo.

La API nunca habilita escritura, ni siquiera en `TESTNET_EXPERIMENT`: el modo solo destraba la capa de firma para los experimentos que corro a mano.

## Guarda única de escritura

`exigir_escritura_experimental()` lanza `EscrituraDeshabilitada` salvo en `TESTNET_EXPERIMENT` fuera de producción. La llamo al comienzo de cada punto que crea identidad, firma o pide firmar:

- `WalletAgent`: `create_agent_wallet`, `ejecutar_transaccion`, `deploy_contract`, `call_contract`, `execute_swap`.
- `ServicioWDK`: `desplegar_contrato`, `ejecutar_funcion`, `transferir_activo`, `ejecutar_swap`.
- `ExecutionRunner.run`, `AgentExecutor.__init__` y `AgentExecutor.execute`.
- Los constructores de `ExperimentoEjecucionTestnet` y `GuardianAgentLoop`, y `experiments/cli.py`.

`AGENT_DEMO_MODE` no cambia nada de esto.

## Grafo final de llamadas

```text
API (api/main.py) — sin WalletAgent, ServicioWDK, ExecutionRunner, AgentExecutor ni loops
│
├─ GET /health ─► status, service, version, mode (sin métricas ni datos)
├─ [sesión] GET /report/{w}, /analyze/wallet/{w}
│     └─► AgentService.run_pipeline_core ─► _run_report ─┐
├─ [sesión] GET /run-agent/{w}, /ejecutar-agente/{w},    │
│           GET /events/sse/{w}, /events/sse?wallet=     │
│     └─► AgentService.run_pipeline_stream ─► _run_stream ┤
│                                                         ▼
│        _analyze: ClienteEtherscan (HTTP GET) → ExtractorFeatures → ClasificadorWallet
│                  → BehavioralScorer → AgenteAnalisis
│        _decide:  DecisionEngine → EstrategiaProteccionWallet
│        señales:  WalletIntel/ProtocolIntel → SignalDetector → StrategyEngine
│        _apply_strategy_overlay → decision_final {execution: false, read_only: true}
│        (el stream además anota la señal en HistorialEvaluaciones, un JSON local que solo cuenta)
├─ [sesión] GET /analyze/block/{n} ─► Web3 RPC de lectura (block_number, chain_id, get_block)
├─ /auth/* ─► ServicioIdentidad (sesiones en la base)
├─ [sesión + membresía + rol] /orgs/{org}/members, /invitations, /accounts, /policies,
│     /events, /events/stream ─► ServicioIdentidad / ServicioRecursos (filtran por organization_id)
├─ [sesión + membresía] GET /orgs/{org}/accounts/{id}/analysis ─► AgentService.run_pipeline_core
├─ 410 legacy_route_gone (desde E02): /track-wallet, /agent/watch, /agent/radar, /agent/history,
│     /agent/actions, /agent-activity, /agent/state, /agent/budget/{w}, /agent/learning,
│     /agent/status, /agent/stream
└─ 403 economic_route_disabled, con o sin sesión, sin tocar nada:
      POST /agent/budget, POST /fund-agent, POST /agent/execute,
      POST /agent/start, POST /agent/stop, GET /agent/address

Worker (python -m worker_lectura) — se niega a arrancar fuera de READ_ONLY
└─► AutonomousAgentLoop.run_once ─► ServicioRecursos.cuentas_para_monitorear
      ─► AgentService.run_pipeline_core ─► ServicioRecursos.registrar_evaluacion
      (escribe solo si la cuenta sigue en su organización y emite account.analyzed en ella)

Experimentos (fuera del runtime; CHAINSIGNAL_MODE=TESTNET_EXPERIMENT, nunca production)
python -m experiments.cli ejecutar <w> --confirmo-testnet
└─► ExperimentoEjecucionTestnet.run_pipeline_loop ─► _execute_with_esl
      ├─► ExecutionGuard.validate_plan (política TESTNET_UNSIMULATED, exige chain_id Sepolia)
      ├─► ExecutionRunner.run ─► ServicioWDK ─► WalletAgent ─► WDK /wallet/send, /swap/execute
      └─► compilar/desplegar contrato ─► ServicioWDK ─► WalletAgent ─► WDK /contract/deploy
GuardianAgentLoop (experiments/guardian_loop.py) ─► AgentExecutor ─► WalletAgent
```

Verifico en un proceso limpio que importar `api.main` no carga `wallet_controller.wallet_agent`, `services.servicio_wdk`, `execution_guard.runner`, `agent_executor.executor` ni nada de `experiments`. Para eso dejé vacíos `services/__init__.py` y `tools/__init__.py`, que reexportaban `ServicioWDK`, y separé la lectura del historial en `agent_executor/historial.py`.

## Rutas experimentales que quedaron inaccesibles

| Ruta | Antes | Ahora |
|---|---|---|
| `GET /run-agent/{w}` y sus tres alias | Con decisión accionable y presupuesto, entraba en `_execute_with_esl` (transferencia, swap, despliegue) | Analiza y termina con `execution: false`, `motivo: read_only_runtime` |
| `POST /agent/execute` | `run_pipeline_loop`, que podía ejecutar | 403 |
| `POST /agent/start` y `/agent/stop` | Arrancaban el loop Guardian, que transfería o desplegaba vía `AgentExecutor` sin guard ni presupuesto | 403; el loop vive en `experiments/` |
| `POST /agent/budget` y `/fund-agent` | Verificaban un depósito y acreditaban presupuesto | 403 |
| `GET /agent/address` | Creaba o derivaba la wallet del agente | 403 |
| Lifespan de la API | Arrancaba el loop autónomo, que podía ejecutar, una vez por worker HTTP | No arranca loops; el monitoreo está en `worker_lectura.py` |

## Hallazgos que cierro

| Hallazgo | Evidencia de cierre |
|---|---|
| A01: un GET público entraba al pipeline que podía ejecutar | `AgentService` ya no tiene capa de firma. Las pruebas recorren las cuatro rutas SSE con decisión `EXECUTE_ADVANCED`, presupuesto precargado y modo demo, y exigen cero llamadas de firma. |
| A02: el loop Guardian invocaba `WalletAgent` sin guard ni presupuesto | Salió de la API. Su constructor y `AgentExecutor` exigen el modo experimental. `/agent/start` responde 403. |
| A03: la "simulación exitosa" dependía de `APP_ENV != production` | `ExecutionGuard` ya no mira `APP_ENV`. `STRICT` exige evidencia de un simulador, que hoy nada produce. `TESTNET_UNSIMULATED` solo vale en modo experimental y con `chain_id` de Sepolia. |
| A10: un hash se volvía `confirmed` y la falta de respuesta aparecía como `simulated` | `ServicioWDK` ya no fabrica éxitos ni saldos simulados. `AgentExecutor` registra `submitted` si hay hash y `failed` si no. |
| A22: los loops del lifespan se multiplicaban por worker HTTP | El lifespan no crea tareas. El monitoreo es un único proceso `worker` en Compose. |

## Cómo lo verifico

`tests/test_runtime_lectura.py` y `tests/test_guarda_escritura.py`:

- Pongo espías en los 17 métodos de firma, presupuesto y experimento, y en `httpx.post`. Si alguno se llama, la prueba falla.
- Fuerzo el peor caso: decisión `EXECUTE_ADVANCED` con transferencia, swap y contrato, estrategia con `force_execute`, presupuesto de 5 ETH precargado en la base y `AGENT_DEMO_MODE` activo.
- Recorro todas las rutas GET y los alias SSE, y las rutas económicas con y sin API key.
- Simulo doble consulta secuencial y concurrente, corte a mitad del stream y reconexión, y conexión y reconexión al stream de estado.
- Importo la API en un proceso limpio sin seed, token WDK ni destino de rescate.
- Compruebo que la guarda frena cada método de firma antes de cualquier POST, que el modo experimental nunca vale en producción, A10 y A03 en cualquier `APP_ENV`, y que el worker solo arranca en `READ_ONLY`.

Para comprobar que los espías detectan una regresión reintroduje a propósito una transferencia en el stream: cinco pruebas fallaron. Después restauré el archivo.

En E01 corrí la imagen Docker sin red y solo con la clave global que existía entonces: `/health` declaró `READ_ONLY`, `POST /agent/execute` y `/agent/start` respondieron 403 con clave válida, el stream de análisis respondió 200 y el worker arrancó.

## Lo que no hice en E01

- La interfaz todavía muestra botones de fondeo, inicio y detención: ahora reciben 403. Los retiro en E06; la restricción ya se cumple en backend.
- En E01 `/agent/stream` no tenía productores. Desde E02 responde 410 y el stream por organización (`/orgs/{org}/events/stream`) entrega eventos persistidos con cursor; incidentes y outbox siguen en E05 (A23).
- En E01 `tracking.json` y `watched_wallets.json` eran archivos sin organización. Desde E02 los reemplazan las cuentas observadas por organización (A17, ver [mi identidad](IDENTIDAD.md)).
- En el experimento siguen abiertos A04 (no espero receipts), A05, A06, A08, A09 y A21. Por eso queda fuera del producto.
- El análisis sigue usando Etherscan y RPC de Sepolia; la lectura de Aave V3 en mainnet es E04.
