# Mi worker y centro de incidentes (E05)

Fecha: 4 de octubre de 2026.

El monitoreo de posiciones corre en workers independientes de la API, con jobs durables en PostgreSQL. Las reglas son versionadas y los incidentes guardan evidencia inmutable. Alerta, outbox y evento se escriben en la misma transacción. No envío mensajes reales: el canal de prueba (`sandbox`) guarda las entregas en la base y el webhook está apagado salvo configuración explícita.

## Worker

`python -m worker_lectura` arranca `monitoreo/worker.py` (servicio `worker` en Compose). Puedo correr varios a la vez. Cada paso hace tres cosas:

1. **Programar.** Encola un job `evaluate_account` por cada cuenta vencida. Un índice único parcial sobre `dedupe_key` (solo jobs `pending` o `running`) impide dos jobs activos por cuenta, aunque varios workers programen a la vez.
2. **Evaluar.** Elige un job con `FOR UPDATE SKIP LOCKED` y lo reclama con un `UPDATE` condicional (compare-and-set sobre estado e intentos) que suma un intento y fija `lease_owner` y `lease_expires_at`. En SQLite `SKIP LOCKED` no existe y esa condición es la que impide que dos procesos tomen el mismo job. Un lease vencido vuelve a poder tomarse; sin intentos restantes, el job queda en `dead`. El worker no toma jobs de organizaciones demo: esas se evalúan en línea con datos sintéticos.
3. **Entregar.** Despacha el outbox con el mismo esquema de lease.

**Fencing.** El job se marca terminado dentro de la misma transacción que escribe los efectos (incidentes, alertas, outbox, eventos), y solo si sigue siendo mío: mismo `lease_owner`, mismo intento, todavía `running`. Un worker que despierta tarde con el lease vencido no confirma nada (`LeasePerdido`). Un crash después del commit no deja nada por rehacer; un crash antes del commit se rehace y la evaluación es idempotente.

**Reintentos.** Un 429, un timeout o un error del proveedor reprograman el job con backoff exponencial y jitter. Al agotar los intentos evalúo igual con datos `UNAVAILABLE`, para que la regla de dato atrasado pueda dispararse.

## Reglas versionadas

Cada creación o cambio de regla escribe una versión inmutable en `alert_policy_versions`. Cada incidente guarda la versión que lo abrió. Una política con incidentes no se borra: se deshabilita.

| Tipo | Abre si | Cierra |
|---|---|---|
| `health_factor_below` | el health factor (con datos `FRESH`) cae bajo `threshold` | tras `clear_after` evaluaciones seguidas por encima de `clear_above` (histéresis); la banda intermedia reinicia el conteo |
| `debt_change` | la deuda cambió al menos `change_pct` % respecto de la línea base | lo resuelve una persona; la línea base se reinicia |
| `stale_data` | la última lectura `FRESH` es más vieja que `max_age_seconds` | con la primera lectura fresca |

Separo severidad, calidad del dato y probabilidad:

- **Severidad:** la declara la política (`low` a `critical`) y sube un nivel al escalar.
- **Calidad del dato:** viene del snapshot.
- **Probabilidad:** no la calculo. Ningún incidente ni regla expone una "confianza" que pueda leerse como probabilidad calibrada.

Con datos no frescos, el health factor no se evalúa: ni abre ni cuenta como despeje.

## Incidentes

- **Estados:** `open`, `acknowledged` y `resolved`. Un índice único parcial garantiza un solo episodio abierto por política y cuenta; si la condición sigue en cada poll, actualizo `last_observed` pero no emito otra alerta.
- **Escalamiento:** si un incidente abierto no se reconoce en `escalate_after_seconds`, subo el nivel y la severidad y emito una alerta `escalated`. Un incidente reconocido no escala.
- **Evidencia:** `incident_evidence` es de solo agregado; en PostgreSQL un trigger rechaza `UPDATE` y `DELETE`. Una corrección es otra fila con `corrects_evidence_id`: manual (`POST /incidents/{id}/corrections`) o automática cuando un reorg cambia el hash del bloque de apertura. En ese caso conservo la evidencia original y agrego la canónica.
- **Snapshots:** desde la migración `0005` la unicidad incluye `block_hash`. Solo reutilizo un snapshot si su bloque sigue teniendo el mismo hash.

## Alertas, outbox y canales

- Cada alerta escribe una fila de outbox por canal habilitado (`idempotency_key = alert:{alerta}:{canal}`) y un evento de la organización, en la misma transacción que el cambio de incidente.
- La entrega es at-least-once, nunca exactly-once. Si un worker envía y muere antes de marcar la fila, otro la reenvía con la misma `idempotency_key`; la prueba lo muestra explícitamente.
- Un 429 o un 5xx se reintentan con backoff hasta `dead`; un 4xx deja la fila en `failed`.
- **`sandbox`:** guarda la entrega en `notification_deliveries` y nunca sale del sistema. Una prueba exitosa marca el canal como verificado.
- **`webhook`:** exige HTTPS. La API muestra solo el host de la URL. No envía mientras `NOTIFICATIONS_WEBHOOKS_ENABLED` sea `false` (por defecto).

## Eventos y SSE

Los eventos del ciclo de vida (`incident.opened`, `escalated`, `acknowledged`, `resolved`, `evidence_corrected`, `account.evaluated`, `channel.*`) son filas durables en `org_events`.

- El stream `/orgs/{org}/events/stream` lee por cursor (`cursor` o `Last-Event-ID`) desde la base, en lotes de 100.
- No hay cola en memoria: un cliente lento solo frena su propio stream, y un corte no pierde eventos, porque al reconectar sigue desde el último id recibido.
- Reanudar el stream no dispara análisis ni escritura.
- Limito los streams abiertos por organización (`MAX_EVENT_STREAMS_PER_ORG`; al pasarlo, 429) y revalido sesión y membresía en cada vuelta.

## API

| Ruta | Rol |
|---|---|
| `GET /orgs/{org}/incidents?status=open|acknowledged|resolved|active` | viewer |
| `GET /orgs/{org}/incidents/{id}` (con evidencia, alertas y entregas) | viewer |
| `POST /orgs/{org}/incidents/{id}/acknowledge` | operator |
| `POST /orgs/{org}/incidents/{id}/resolve` (`note` obligatoria) | operator |
| `POST /orgs/{org}/incidents/{id}/corrections` | operator |
| `GET /orgs/{org}/policies/{id}/versions` | viewer |
| `GET`/`POST /orgs/{org}/channels` | viewer / owner |
| `POST /orgs/{org}/channels/{id}/test`, `GET .../deliveries` | operator / viewer |

## Cómo lo verifico

Los escenarios (`tests/escenarios_monitoreo.py`) corren igual sobre SQLite y sobre PostgreSQL. Cubren:

- abrir una sola vez sin repetir alertas;
- cerrar con histéresis y abrir un episodio nuevo;
- escalar sin reconocimiento;
- 429 con reintentos que termina en dato atrasado;
- recuperar un lease vencido con fencing del worker zombie;
- crash después del commit con replay;
- entrega at-least-once con la misma clave;
- reintentos de entrega;
- corrección por reorg;
- canal sandbox verificado.

Solo en PostgreSQL (`tests/test_monitoreo_postgres.py`):

- **Dos workers sobre 8 cuentas en riesgo:** exactamente un episodio, una alerta y una fila de outbox por cuenta, y cada job evaluado una sola vez.
- **Concurrencia:** cuatro schedulers simultáneos crean un job por cuenta, y dos despachadores entregan cada fila una vez.
- **Trigger:** rechaza `UPDATE` y `DELETE` sobre la evidencia.
- **Índice:** impide un segundo episodio abierto.

Comprobé que las pruebas detectan regresiones:

- sin `SKIP LOCKED` en la cola de jobs, la prueba de dos workers ve 9 evaluaciones en lugar de 8;
- sin `SKIP LOCKED` en el outbox, ve 25 envíos en lugar de 20.

Para el outbox tuve que ensanchar la ventana de carrera en la prueba, porque sin eso la mutación no se notaba.

En E06 los E2E mostraron un 500 intermitente al crear una demo: el worker y la evaluación en línea reclamaban el mismo job sobre SQLite, porque el reclamo no verificaba que la fila siguiera disponible. Lo corregí con el reclamo condicional y excluyendo las demos del worker. `test_reclamo_condicional_no_toma_un_job_que_otro_proceso_tomo` simula la carrera escribiendo desde otra conexión antes del reclamo, y falla si quito la condición; `test_el_worker_no_toma_jobs_de_demos` falla si quito el filtro.

`tests/test_incidentes_api.py` cubre:

- roles y ciclo de vida;
- corrección trazable;
- otra organización;
- canales;
- webhook apagado;
- límite de streams;
- reanudación del SSE sin análisis ni escritura.

## Lo que no hice en E05

- No envío webhooks reales y no hay email ni chat.
- Los eventos no tienen retención ni compactación.
- El límite de streams es por proceso; con varias réplicas de la API hace falta un contador compartido.
- El worker evalúa una cuenta por vez dentro de cada paso; no tiene concurrencia interna.
