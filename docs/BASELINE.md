# Mi baseline reproducible (E00)

Fecha: 3 de octubre de 2026.

Aquí registro cómo instalo ChainSignal desde cero, qué comprobaciones reproduzco, qué resultados obtuve y qué queda bloqueado. No describo funciones nuevas: E00 solo deja el repositorio instalable, verificable y documentado.

## Mi runtime

| Pieza | Decisión | Por qué |
|---|---|---|
| Python | 3.11 (`.python-version`; imagen `python:3.11-slim-bookworm`, probé 3.11.4 local y 3.11.17 en Docker) | Dockerfile y Render ya usaban 3.11. web3 7.14.1, SQLAlchemy 2.0.54 y psycopg2-binary 2.9.13 instalan y pasan las pruebas en ambas. No certifico 3.14 aunque mi `.venv` antiguo la use. |
| SQLAlchemy | 2.0.54 | El código usa la API 2.0; no salto a 2.1 en un baseline. |
| OpenAI | 2.54.0 | El cliente usa `chat.completions`; evito la major 3 sin probar el camino LLM, que es opcional. |
| Node (frontend) | `engines: >=20`; probé Node 24.14 y npm 11.9 | Vite 5 lo requiere. |
| Node (WDK) | imagen `node:20-bookworm` | Sin cambios. |
| PostgreSQL | 16 | Igual que Compose. |

## Mis dependencias

- `requirements.txt`: solo dependencias directas de ejecución, con versión exacta. Cada una corresponde a un import directo.
- `requirements-dev.txt`: agrega pytest.
- `constraints.txt`: todas las transitivas que instalé y probé. Lo uso con `-c`; un paquete exclusivo de otra plataforma no se fuerza.
- `web_app/package-lock.json`: único lockfile del frontend. Quité `bun.lock` y `bun.lockb`.
- `wdk_service/package.json`: reemplacé `latest` por las versiones del lockfile y saqué `@tetherto/wdk`, que nadie importaba. El Dockerfile usa `npm ci --omit=dev`.

Saqué estas dependencias sin uso comprobado:

| Dependencia | Motivo |
|---|---|
| `openclaw` | Solo instanciaba un cliente y registraba un mensaje (no-op). Quité también `OPENCLAW_ENABLED`. |
| `python-multipart` | Ninguna ruta usa `Form` ni `UploadFile`. |
| Plugin de etiquetado de componentes del scaffolding inicial | Solo actuaba en modo desarrollo y no aporta al producto. |
| `@playwright/test` y su configuración | No hay pruebas end-to-end y la configuración importaba un paquete de scaffolding no declarado. |
| `@tetherto/wdk` | `server.js` solo importa los módulos de wallet, swap y ERC-4337. |
| `LLM_BASE_URL` y `extra_hosts` en Compose | Ningún código lee esa variable. |

Declaré `pydantic-settings`, `openai` y `pytest` (este último solo en desarrollo), que se importaban sin figurar en el manifiesto.

## Cómo instalo desde cero

Backend (PowerShell):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt -c constraints.txt
Copy-Item .env.example .env   # solo para correr la API; las pruebas no lo leen
```

Frontend:

```powershell
Set-Location web_app
npm ci
```

Imágenes locales (sin publicar):

```powershell
docker build -t chainsignal-api:local .
docker build -t chainsignal-wdk:local ./wdk_service
```

## Cómo reproduzco los checks

```powershell
# Python: pruebas unitarias offline
python -m pytest

# Python: carrera de reclamo contra un PostgreSQL desechable
docker run -d --rm --name cs-pg -e POSTGRES_USER=cs_test -e POSTGRES_PASSWORD=cs_test -e POSTGRES_DB=cs_test -p 127.0.0.1:55432:5432 postgres:16-alpine
$env:CHAINSIGNAL_TEST_POSTGRES_URL = "postgresql+psycopg2://cs_test:cs_test@127.0.0.1:55432/cs_test"
python -m pytest -m postgres
docker stop cs-pg

# Integraciones manuales (red, servicios reales y mi .env local)
$env:CHAINSIGNAL_RUN_INTEGRATION = "1"
python -m pytest -m integration

# Frontend, desde web_app/
npm run build
npm test
npm run lint
npm run typecheck

# WDK
node --check wdk_service/server.js
```

## Cómo aíslo las pruebas

`conftest.py` se carga antes de importar el proyecto y:

- define `CHAINSIGNAL_DISABLE_DOTENV=1`; `infra/config.py` y `wallet_controller/wallet_agent.py` respetan esa variable y no leen mi `.env`;
- pisa las variables con valores sintéticos (ninguna credencial real);
- cambia a un directorio temporal de sesión y a uno nuevo por prueba, así `tracking.json`, `watched_wallets.json`, `storage/` y `cache/` del repositorio no se tocan;
- bloquea DNS y conexiones fuera de loopback; una prueba que intenta salir a la red falla;
- evita que el lifespan de la API arranque el loop autónomo cuando una prueba usa `TestClient`.

Las integraciones manuales llevan la marca `integration`, están en `tests/integration/` y exigen doble opt-in: `-m integration` y `CHAINSIGNAL_RUN_INTEGRATION=1`. En ese modo no piso el entorno porque necesitan servicios reales. `tests/test_tools.py::test_compilar_risk_guard` también es integración: descarga `solc` si no está en caché. Lo descubrí al correr la suite en el contenedor limpio, donde la guarda de red la frenó.

## Resultados que obtuve

| Comprobación | Antes de E00 | Después de E00 |
|---|---|---|
| Instalación Python limpia (3.11, Windows) | La colección fallaba por SQLAlchemy ausente | `pip check` sin conflictos |
| Instalación Python limpia (imagen Linux) | `CMD api.server` inexistente | Imagen construida, `pip check` sin conflictos, `/health` responde 200 sin red |
| `pytest` unitario (Windows 3.11.4 y Linux 3.11.17) | 31 pruebas aisladas a mano | 94 aprobadas, 1 omitida (requiere PostgreSQL), 3 integraciones deseleccionadas |
| `pytest -m postgres` (PostgreSQL 16.15) | Sin prueba sobre PostgreSQL | 1 aprobada en 3 corridas |
| `pytest -m integration` sin opt-in | Se mezclaban con las unitarias | 3 omitidas con motivo explícito |
| `npm ci` en copia limpia | Tres lockfiles | Instala 500 paquetes desde `package-lock.json` |
| `npm run build` | Pasaba | Pasa; JS principal 346,40 kB |
| `npm test` | 1 prueba que comparaba true con true | 4 pruebas de comportamiento |
| `npm run lint` | 45 errores, 9 advertencias | Sin cambios: 45 errores, 9 advertencias |
| `npm run typecheck` | 6 errores | Sin cambios: 6 errores |
| `node --check wdk_service/server.js` | Pasaba | Pasa; la imagen WDK se construye con `npm ci` y carga sus módulos |
| `docker compose config` con `.env.example` | No verificado | Válido: servicios db, wdk, api y web |

Las pruebas de Vitest cubren `cn` y una guarda que falla si el código usa una variable `VITE_*` fuera de la lista aprobada o si la lista aprueba un nombre con apariencia de secreto. Verifiqué que la guarda falla al introducir `VITE_PRIVATE_KEY`.

Alineé las pruebas antiguas de reporte premium con el contrato vigente: `/report/{wallet}` es un análisis gratuito de solo lectura. Ya no espero un 402 ni un contrato desplegado; pruebo que no exige pago, que declara la wallet objetivo como `read_only` y que devuelve 500 cuando falla el pipeline.

La carrera de reclamo pasó de SQLite a PostgreSQL. Solo certifica el primer reclamo concurrente de un fingerprint nuevo; el re-reclamo de planes FAILED/ABORTED sigue sin comparación atómica (A06).

## Mi topología actual

Actualicé esta tabla en E01; el resto del documento registra el estado de E00.

| Servicio | Dónde | Qué hace | Límite |
|---|---|---|---|
| `db` | Compose | PostgreSQL 16 para planes, historial y presupuestos | Esquema por `create_all`, sin migraciones (A24) |
| `api` | Compose, Render, Dockerfile | FastAPI `api.main:app` en 8001, en `READ_ONLY` y sin loops en el lifespan | Sin identidad por organización (E02) |
| `worker` | Compose | `python -m worker_lectura`: monitoreo periódico de solo lectura | Estado en `tracking.json`, sin jobs persistentes (E05) |
| `wdk` | Compose, perfil `experimento`, solo red interna | Firma en Sepolia con un token compartido | Experimento fuera del producto; no arranca por defecto |
| `web` | Compose | Interfaz heredada en Jinja (`web_app/app.py`) con `--reload` en 8081 | No es la interfaz actual |
| React/Vite | `npm run dev` local, puerto 8081 con proxy a 8001 | Interfaz actual | Sin servicio en Compose ni en Render; choca en 8081 con `web` si corren juntos |

Render solo describe la API (A25).

## Artefactos operativos versionados

Encontré 16 archivos de estado local versionados: `backend_log.txt`, `cache/used_payments.json`, `contratos_deployados.json`, `executions.json`, `health.json`, `health_check.json`, `storage/agent_budget.json`, `storage/learning_store.json`, seis `storage/plans/*/plan.json`, `tracking.json` y `watched_wallets.json`.

- Preservé una copia en `ops_backup/2026-10-03/` con `SHA256SUMS`, verificada byte a byte contra el original. La carpeta está ignorada por git.
- Preparé `scripts/desversionar_estado_operativo.sh`. Por defecto simula; con `--aplicar` ejecuta `git rm --cached`, que conserva los archivos en disco. No lo apliqué: la baja queda para que la revise.
- Agregué reglas en `.gitignore` para que no vuelvan a versionarse. Ignorar no desversiona: hasta aplicar el script siguen en el índice.
- No borré datos ni reescribí historial. Lo ya publicado sigue en commits anteriores.
- Conservo `demo_data/` y `demo_profiles/` como datos de demostración; ningún módulo Python los referencia y decido su destino más adelante.

## Mi búsqueda de secretos

Busqué claves privadas PEM, asignaciones de clave privada, seeds, claves de OpenAI, AWS, GitHub, Infura, Alchemy, Etherscan, contraseñas y tokens genéricos en el árbol de trabajo y en todo el historial de git (`git log --all -p`). Decodifiqué `backend_log.txt` como UTF-16, su codificación real.

- Árbol de trabajo versionado o no ignorado: sin hallazgos.
- Historial: sin hallazgos.
- `.env`: nunca estuvo versionado. Mi `.env` local está ignorado y contiene variables de tipo seed (`AGENT_SEED_PHRASE`), claves de proveedores (`ETHERSCAN_API_KEY`, `OPENAI_API_KEY`), URL de RPC y tokens (`CHAINSIGNAL_API_KEY`, `WDK_SERVICE_TOKEN`). No leí sus valores. Como nunca se versionó, no exige rotación por el repositorio; sí la exige si se compartió por otro medio.

El escaneo es por patrones: no reemplaza una herramienta dedicada en CI (E08).

## Bloqueos y pendientes

- **Licencia:** no hay `LICENSE` en la raíz y `wdk_service/package.json` declara MIT. No elegí ni inventé una licencia. Necesito decidirla explícitamente antes de distribuir; también reviso las atribuciones de los componentes de UI copiados en `web_app/src/components/ui`.
- **Lint y tipos:** quedan 45 errores, 9 advertencias de lint y 6 errores de tipos. No los arreglé en E00.
- **Vulnerabilidades npm:** el frontend reporta 19 en dependencias de producción (1 baja, 2 moderadas, 16 altas) y 37 en total con desarrollo (incluye 1 crítica). El servicio WDK reporta 14 (1 baja, 6 moderadas, 7 altas). Python no tiene auditoría de dependencias todavía. No actualicé en masa: lo trato en E08.
- **`ckzg` en Windows:** la política de Control de aplicaciones de mi Windows bloquea la DLL de `ckzg` 2.1.8 recién descargada. Fijé 2.1.6, que carga y pasa las pruebas. En Linux no observé el problema.
- **`.git/index.lock`:** encontré un lock de 0 bytes con siete horas de antigüedad y ningún proceso git activo. No lo borré porque no lo creé yo; impide comandos que escriben el índice (por ejemplo, la simulación del script de bajas). Lo reviso antes de usar git.
- **Revisión de voz:** reescribí docstrings y comentarios multilínea del código y las pruebas que citaban IDs viejos de auditoría o estaban en inglés. No cambié mensajes de log, textos de API ni comentarios breves de una línea en código heredado que no toqué.
- **Hallazgos de producto abiertos:** A01–A24 y A30–A32 siguen como están en mi [auditoría](../CHAIN_SIGNAL_AUDIT.md). E00 cierra o reduce A25 (CMD), A26 (dependencias), A27 (pruebas Python y Vitest trivial) y A28 (inventario y bajas preparadas); A29 queda abierto por la licencia.

## Mi criterio de salida

Doy E00 por cumplida cuando, desde un clon limpio, puedo instalar con los comandos de arriba, obtener los mismos resultados de checks y leer aquí qué falta. Para pasar a E01 no necesito resolver lint, tipos ni vulnerabilidades, pero sí decidir la licencia antes de cualquier distribución comercial.
