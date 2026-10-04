# ChainSignal

Desarrollo ChainSignal para analizar actividad on-chain y construir monitoreo de posiciones DeFi con evidencia, alertas y seguimiento. Quiero ayudar a pequeños equipos a revisar sus posiciones sin custodiar sus fondos.

## Mi estado actual

Tengo un prototipo FastAPI, React/Vite, ingestión Etherscan, clasificación por reglas y circuitos experimentales testnet. Hay mejoras de seguridad y persistencia en el checkout, pero todavía no lo considero listo para recibir u operar capital de clientes.

Desde E01 la API y el worker corren en modo `READ_ONLY` por defecto: ninguna ruta puede firmar, transferir, hacer swap ni desplegar, y no necesitan seed, token WDK ni destino de rescate. Los experimentos de escritura en Sepolia quedan en experiments/, fuera del runtime. Describo el grafo de llamadas y las rutas deshabilitadas en [mi runtime de lectura](docs/RUNTIME_LECTURA.md). Desde E02 cada persona inicia sesión con una cookie HttpOnly y la API autoriza cada recurso privado por organización y rol (owner, operator, viewer); ya no existe la clave global. Lo detallo en [mi identidad](docs/IDENTIDAD.md). Desde E03 cada lectura on-chain informa su calidad (FRESH, STALE, PARTIAL o UNAVAILABLE), su bloque de referencia y su completitud, y no recomiendo acciones sin datos frescos ([mis datos](docs/DATOS.md)). Desde E04 leo posiciones de Aave V3 en Ethereum a un bloque explícito, las guardo como snapshots y las reconcilio con la fuente ([mis posiciones Aave](docs/POSICIONES_AAVE.md)). Desde E05 un worker independiente monitorea esas posiciones con jobs durables, reglas versionadas e incidentes con evidencia inmutable, y notifica por outbox sin enviar mensajes reales ([mi monitoreo](docs/MONITOREO.md)). Desde E06 la interfaz es un producto con cuatro secciones (Resumen, Posiciones, Incidentes y Configuración), alta de organización, demo sintética aislada y seguimiento de incidentes; lo verifico con E2E sobre un entorno aislado ([mi experiencia](docs/EXPERIENCIA.md)). Desde E07 cada incidente tiene una explicación por plantilla determinista, con referencias al snapshot, la regla y la evidencia; un modelo opcional (apagado por defecto) solo redacta esos hechos y se valida antes de mostrarse. Renombré el "aprendizaje" a historial y quité el sesgo que forzaba estrategias por cantidad de transacciones aceptadas ([mi evaluación](docs/EVALUACION_EXPLICACIONES.md)). Desde E08 el piloto tiene una topología revisable (nginx con React estático, API replicada, worker y PostgreSQL, con la migración como paso aparte), readiness, métricas operativas, CI y runbooks; ensayé en un staging local proveedor caído, reinicios, dos réplicas y restauración real de la base. No lo desplegué ([mi operación](docs/OPERACION.md)). Desde E09 hay un piloto comercial de lectura: prueba de 14 días, hasta 10 cuentas, límites aplicados en el backend, cancelación visible, cobro asistido (sin procesador real) y eventos de activación sin datos personales; el precio de USD 150 es una hipótesis y la puerta de 3 pilotos pagos y 2 renovaciones sigue en 0 ([mi piloto](docs/PILOTO.md)). E10 (propuestas Safe con firma humana) no está lista: como esas puertas no se cumplen, dejé un spike fuera del runtime, verificado con mocks, contra contratos oficiales y en un fork aislado ([mis propuestas Safe](docs/PROPUESTAS_SAFE.md)). Después separé en la interfaz alertas, frescura del dato y actividad de la cuenta; distingo entrega simulada de entrega aceptada por el destino; agregué webhook externo con protección SSRF y firma, edición versionada de políticas con vista previa, invitaciones y roles, y un Resumen que prioriza lo que necesita atención y dice si el monitoreo está preparado. Lo verifiqué en local, incluido un ensayo con HTTPS y un receptor controlado; CI en GitHub y staging autorizado siguen pendientes ([confianza y criterio de salida](docs/CONFIANZA_Y_SALIDA.md)).

## Mi evolución

Comienzo con lectura de Aave V3 en Ethereum, alertas y seguimiento por organización. Después evalúo propuestas simuladas con aprobación humana. Es mi objetivo, no funcionalidad ya implementada.

## Mi documentación

- [Mi baseline reproducible](docs/BASELINE.md): instalación, checks, resultados y bloqueos.
- [Mi runtime de lectura](docs/RUNTIME_LECTURA.md): modo READ_ONLY, grafo de llamadas y rutas deshabilitadas.
- [Mi identidad](docs/IDENTIDAD.md): organizaciones, roles, sesiones, migraciones y migración de configuración.
- [Mis datos](docs/DATOS.md): red única, resultados tipados, ingesta con checkpoints y features honestas.
- [Mis posiciones Aave](docs/POSICIONES_AAVE.md): adaptador Aave V3, snapshots, reconciliación y replay.
- [Mi monitoreo](docs/MONITOREO.md): worker, jobs con lease, reglas, incidentes, outbox y SSE.
- [Mi auditoría](CHAIN_SIGNAL_AUDIT.md).
- [Mi estrategia comercial](docs/ESTRATEGIA_PRODUCTO.md).
- [Mi plan de implementación](CHAIN_SIGNAL_IMPLEMENTATION_PLAN.md).
- [Mi arquitectura objetivo](CHAIN_SIGNAL_TARGET_ARCHITECTURE.md).
- [Mi guía del dashboard](docs/AUTONOMOUS_DASHBOARD.md).
- [Mi experiencia comercial](docs/EXPERIENCIA.md): recorrido de activación, demo, estados, E2E y capturas.
- [Mi explicación y evaluación](docs/EVALUACION_EXPLICACIONES.md): historial, explicación validada, 50 casos y plan de ML.
- [Mi operación](docs/OPERACION.md): topología del piloto, salud, métricas, CI, ensayo en staging y [runbooks](docs/runbooks/).
- [Mi piloto y monetización](docs/PILOTO.md): plan, límites, cobro asistido, analítica, tablero, [guía de entrevistas](docs/piloto/GUIA_ENTREVISTAS.md) y [registro](docs/piloto/REGISTRO_PILOTOS.md).
- [Mis propuestas Safe](docs/PROPUESTAS_SAFE.md): spike E10 fuera del runtime, fuentes verificadas, estados y ensayo en fork.
- [Confianza y criterio de salida](docs/CONFIANZA_Y_SALIDA.md): señales, entregas, webhook seguro, configuración, preparación, verificación, pendientes y condiciones para publicar.
- [Mi interfaz web](web_app/README.md).

## Mi código

Uso api/ para endpoints; ingestion_onchain/ y generacion_features/ para datos; perfil_wallet/, decision_engine/ y services/ para evaluación; infra/ para configuración/DB; web_app/src/ para React.

Mantengo los experimentos de escritura en experiments/, execution_guard/, wallet_controller/, agent_executor/, contract_generator/ y wdk_service/; todos exigen `CHAINSIGNAL_MODE=TESTNET_EXPERIMENT`. El monitoreo periódico corre en worker_lectura.py. La interfaz heredada en web_app/app.py quedó fuera del despliegue comercial (perfil `legado` del Compose de desarrollo). La topología del piloto está en [mi operación](docs/OPERACION.md).

## Cómo preparo desarrollo

Uso Python 3.11 y Node 20 o superior.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt -c constraints.txt
Copy-Item .env.example .env
Set-Location web_app
npm ci
```

`requirements.txt` lista solo dependencias directas con versión exacta y `constraints.txt` fija las transitivas que probé. `.env.example` no tiene secretos: en `READ_ONLY` no necesito ningún secreto para arrancar. WDK_SERVICE_TOKEN y SAFE_WALLET_ADDRESS solo los pide el experimento testnet. El esquema se aplica con migraciones de Alembic y creo la primera organización con `python -m identidad.cli crear-organizacion`. DATABASE_URL vacía cae en un SQLite temporal solo apto para desarrollo; Compose usa PostgreSQL.

No guardo secretos en Git ni en VITE_*. Antes de conectar RPC/WDK/fondos resuelvo la lectura de E01.

## Qué comprobé

Al 4 de octubre de 2026, en Python 3.11 sobre Windows:

- 460 pruebas Python aprobadas y 0 omitidas, offline y sin leer mi `.env`, incluidas las de concurrencia contra PostgreSQL 16 (`CHAINSIGNAL_TEST_POSTGRES_URL`). Sin PostgreSQL, esas quedan omitidas. Las 4 `integration` quedan deseleccionadas.
- Migraciones `0001`–`0009` de ida y vuelta en PostgreSQL y `alembic check` sin diferencias.
- Frontend: `typecheck` y `lint` sin errores (7 advertencias de fast refresh), 67 pruebas de Vitest, build correcto y 20 escenarios E2E con Playwright sobre un entorno aislado con un receptor HTTPS local, incluidos 4 anchos (360, 390, 768 y 1440 px) y axe.
- Evaluación de explicaciones: 50 casos, plantilla fiel y útil en los 50.
- Ensayo del piloto en staging local (`python -m operacion.ensayo_staging`): 7 de 7 pasos, con HTTPS, entrega externa controlada y restauración real de la base.
- Sin secretos en el historial ni en el árbol (gitleaks) y sin vulnerabilidades conocidas en dependencias Python ni altas en las de producción de la interfaz.

```powershell
python -m pytest
Set-Location web_app
npm run build
npm test
npm run lint
npm run typecheck
npm run e2e
```

Las integraciones manuales (Etherscan, WDK, descarga de solc) viven en tests/integration/ o llevan la marca `integration` y solo corren con `CHAINSIGNAL_RUN_INTEGRATION=1 pytest -m integration`. No las corro con claves de firma ni fondos.

## Cómo interpreto resultados

Mis scores son heurísticas, no probabilidades calibradas. Historial no es modelo entrenado; hash enviado no es confirmación; contrato de plantilla no protege por sí mismo una posición externa.

Preparé la baja revisable de los archivos operativos versionados, pero todavía no la apliqué. Debo elegir licencia raíz y definir privacidad/soporte antes de distribuir una versión cobrable.
