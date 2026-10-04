# Mi operación del piloto (E08)

Fecha: 4 de octubre de 2026.

Preparé el piloto para operarlo de forma verificable, sin desplegarlo. No contraté servicios, no publiqué nada y no migré datos reales. Todo lo que afirmo acá lo probé en un staging local aislado o en CI local; lo que no probé lo marco como pendiente.

## Topología

```
navegador ──TLS (plataforma)──▶ web: nginx + React estático ──▶ api × 2 (FastAPI, lectura)
                                                                     │
                                         worker (lectura) ──────────┤
                                         migrate (una vez) ──────────┴──▶ PostgreSQL 16
```

- **Imagen de API y worker** (`Dockerfile`): multi-etapa, sin compiladores en la imagen final y sin root (uid 10001). Arranca uvicorn sin `--reload`, con proxy headers, keep-alive de 5 s y apagado ordenado de 20 s.
- **Interfaz** (`web_app/Dockerfile`, `web_app/nginx.conf`):
  - React compilado servido por nginx, que hace de proxy de `/auth`, `/orgs`, `/demo`, `/invitations`, `/health` y `/ready` hacia la API, en el mismo origen;
  - timeouts de 5 s para conectar y 30 s para leer; el SSE va sin buffer y con lectura de 1 h;
  - reintenta en otra réplica ante 502/503;
  - cabeceras de seguridad (CSP, HSTS, nosniff, sin referrer);
  - `/metrics` no se publica.
- **`deploy/compose.piloto.yml`**:
  - `migrate` corre `alembic upgrade head` una vez y termina; la API y el worker esperan a que termine bien y arrancan con `DB_AUTO_MIGRATE=false`;
  - cada proceso recibe solo sus variables; los secretos llegan del entorno de quien despliega (`${VAR:?}`);
  - ningún proceso recibe seed, token WDK ni destino de rescate;
  - la clave del modelo de explicaciones solo la ve la API.
- **`render.yaml`**: mismo esquema en Render, con la API como servicio privado detrás del nginx de la interfaz, la migración en `preDeployCommand` y los secretos cargados en el panel. No lo apliqué.
- **Retiré del despliegue comercial** la interfaz heredada en Jinja y el `--reload`. En el Compose de desarrollo queda en el perfil `legado`, sin `--reload`, y ya no le paso el `.env` entero a ningún proceso de lectura.

## Configuración que exijo en producción

Con `APP_ENV=production`, la API y el worker no arrancan si:

- `DATABASE_URL` falta o no es PostgreSQL;
- `DB_AUTO_MIGRATE=true` (las réplicas no migran al arrancar);
- `CORS_ALLOWED_ORIGINS` tiene un origen que no es https;
- la cookie de sesión no es Secure;
- en modo lectura aparece `AGENT_SEED_PHRASE`, `WDK_SERVICE_TOKEN` o `SAFE_WALLET_ADDRESS`. El mensaje nombra la variable, nunca su valor.

Otros controles de base de datos:

- **Arranque:** la API y el worker verifican que el esquema esté en head; si no lo está, no arrancan (`EsquemaDesactualizado`).
- **PostgreSQL:** connect timeout de 5 s, `statement_timeout` de 15 s y `pool_pre_ping`.

## Salud

| Ruta o comando | Qué dice |
|---|---|
| `GET /health` | liveness: el proceso responde |
| `GET /ready` | readiness: la base responde y el esquema está en head; si no, 503 sin detalle |
| `python -m operacion.vida_worker` | liveness del worker: latió en los últimos 120 s (tabla `worker_heartbeats`, migración `0008`) |
| `GET /metrics` | métricas en formato Prometheus; 404 sin `METRICS_TOKEN`, 401 con un token incorrecto |

## Métricas

Las calcula `operacion/metricas.py` desde la base (`python -m operacion.metricas` da el JSON):

- **cobertura:** cuentas reales con una evaluación FRESH dentro de dos intervalos;
- **frescura:** antigüedad de la evaluación y calidad por cuenta;
- **jobs:** por estado, el pendiente más viejo y los errores de las últimas 24 h;
- **workers vivos;**
- **detección:** desde la lectura del snapshot hasta la apertura del incidente;
- **entrega:** desde la fila de outbox hasta el envío;
- **errores del proveedor:** snapshots no FRESH y errores de jobs;
- **costo:** el de las explicaciones con modelo. El costo del RPC queda pendiente: depende del plan del proveedor y no lo mido.

Metas internas, comparadas contra lo medido y que **no son un SLA comercial**: RPO 1 h, RTO 4 h, cobertura 99 % y detección p95 menor a 60 s desde el snapshot.

## Ensayo en staging aislado

Lo corrí completo cuatro veces mientras corregía; las cifras son de la última corrida, con el código final. `python -m operacion.ensayo_staging` levanta `compose.piloto.yml` + `compose.ensayo.yml` con dos réplicas de la API, sin RPC real (la lectura se reproduce desde la fixture grabada) y con secretos aleatorios de un solo uso. Al terminar baja todo y borra los volúmenes. El resultado queda en `docs/ensayos/ensayo-piloto.json`.

| Paso | Qué comprobé | Resultado medido |
|---|---|---|
| levantar | `migrate` termina con 0, esquema `0008`, 2 réplicas sanas, `/ready` | ok |
| flujo | alta, cuenta, snapshot FRESH (health factor 1,2254), política, canal probado e incidente abierto por el worker, todo a través de nginx | detección 0,34 s; entrega p95 0,04 s; cobertura 100 % |
| réplicas | 40 requests con la misma sesión | 20 y 20 por réplica |
| reinicio | reinicio de API y worker: la sesión sigue válida. Crash con un job tomado: el worker no lo toma antes de que venza el lease de 15 s y después lo completa una vez, sin duplicar el incidente | API lista en 3,1 s; job recuperado a los 15,6 s |
| proveedor caído | worker apuntado a un RPC que no responde: la cuenta queda UNAVAILABLE, la API sigue lista, el incidente abierto no se cierra por falta de datos y todo se recupera al volver el proveedor | UNAVAILABLE a los 71 s; recuperado en 2 s |
| respaldo y restauración | `pg_dump`, pérdida del contenedor y del volumen de la base, `pg_restore` en una base vacía, misma huella en 20 tablas (conteo y hash de ids), login con las mismas credenciales e incidente visible | dump 0,4 s (90 KB); restore 1,6 s; recuperación total 21,3 s |

Límites del ensayo:

- **Escala:** la base tenía 90 KB. El RTO medido (21 s) no dice nada sobre una base grande; antes de comprometer 4 h hay que medir con el volumen real.
- **Seguridad de red:** corrí en http dentro de 127.0.0.1, sin TLS, CORS https ni cookie Secure. Esas exigencias las cubren las pruebas de configuración, no el ensayo.
- **Lecturas:** con la fixture no hay latencia de red. La detección (0,34 s en la última corrida y 1,16 s en otra) no representa un RPC real.
- **Proveedor caído:** la métrica `not_fresh_24h` no registró nada, porque una lectura fallida no se guarda como snapshot. El error sí aparece en `jobs.errors_24h` y en la calidad de la cuenta.

## CI

`.github/workflows/ci.yml`. No despliega nada. Lo escribí y verifiqué cada paso localmente, pero todavía no corrió en GitHub.

| Job | Qué hace | Verificación local |
|---|---|---|
| backend | dependencias fijadas, `alembic upgrade`/`downgrade base`/`upgrade`/`check` en PostgreSQL 16, pytest con PostgreSQL y evaluación de explicaciones | migraciones ok, `alembic check` sin diferencias, 376 pruebas aprobadas |
| frontend | `npm ci`, tipos, lint, Vitest, build | 0 errores de tipos y de lint (7 advertencias en `ui/`), 39 pruebas, build ok |
| e2e | Playwright sobre el entorno aislado | 10 escenarios aprobados |
| imagenes | build de las dos imágenes; la imagen no lleva `.env` ni `storage/` y no corre como root | build ok en el ensayo |
| secretos | gitleaks sobre todo el historial, con salida redactada | ver abajo |
| dependencias | `pip-audit --strict` y `npm audit --omit=dev --audit-level=high` | ver abajo |

**Secretos.** gitleaks encontró 24 coincidencias en commits de marzo de 2026 y 3 en el árbol actual. Las revisé sin imprimir valores:

- **24 del historial y 2 del árbol:** direcciones públicas de contratos de tokens (formato `0x` + 40 hex) en variables `token_out` y `token_address`. Ignoro solo esas 24 ocurrencias exactas por huella (`.gitleaksignore`) y marco las 2 líneas actuales con `gitleaks:allow`. La regla sigue activa.
- **1 en `.env.example`:** la regla tomaba la línea siguiente a una variable vacía como si fuera su valor. Separé las líneas con un comentario.

Con eso, historial y árbol quedan sin hallazgos.

**Dependencias:**

- **Python:**
  - `pip-audit` encontró `pydantic-settings` 2.13.1 (GHSA-4xgf-cpjx-pc3j) y `requests` 2.32.5 (PYSEC-2026-2275);
  - los subí a 2.14.2 y 2.33.0;
  - la suite completa pasa y no quedan vulnerabilidades conocidas.
- **npm, producción:**
  - apliqué los arreglos compatibles y moví `tailwindcss-animate` a dependencias de desarrollo, porque solo se usa al compilar;
  - quedan 2 moderadas en `react-router` 6 cuyo arreglo exige migrar a v7;
  - la app solo navega a rutas internas y no usa SSR, así que lo dejo como pendiente aceptado; el umbral de CI (high) pasa sin apagar nada.
- **npm, desarrollo:** quedan 6 altas en la cadena de Vite 5 y Tailwind 3, que no llegan al bundle. Requieren migraciones mayores y quedan pendientes.

## Errores que encontré

- **`init_db` recordaba engines migrados por `id()`.** Python reutiliza la dirección de un objeto liberado, así que un engine nuevo podía darse por migrado sin tablas. Apareció como una falla intermitente de `reintenta_429_y_luego_marca_dato_atrasado` en la suite completa. Lo cambié por un `WeakSet`; `test_init_db_no_confunde_engines_que_reutilizan_direccion` reproduce el bug con el código anterior.
- **La API no preparaba la base al arrancar**, solo cuando la construía algún servicio, y `/ready` daba 503 en una base nueva. Ahora el arranque la prepara: en desarrollo migra y en producción verifica.
- **El primer ensayo de crash no lo probaba de verdad:** el worker terminaba el job antes de que lo matara. Lo rehíce con un job tomado por un worker muerto y lease vigente.
- **En nginx**, un `add_header` dentro de un `location` borraba las cabeceras de seguridad heredadas. Uso `expires`.
- **Mi primer `render.yaml`** separaba interfaz y API en orígenes distintos dentro de un sufijo público, y la cookie no habría viajado. Ahora comparten origen detrás de nginx.

## Runbooks

Los escribo cortos y en el orden en que los usaría. Están en `docs/runbooks/`:

- [Despliegue y rollback](runbooks/DESPLIEGUE.md)
- [Respaldo y restauración](runbooks/RESPALDO.md)
- [Proveedor RPC caído](runbooks/PROVEEDOR_CAIDO.md)
- [Worker parado o jobs acumulados](runbooks/WORKER.md)
- [Base de datos caída o lenta](runbooks/BASE_DE_DATOS.md)

## Pendiente

- Correr el CI en GitHub y el blueprint en Render. No lo hice: publicar está fuera del alcance.
- Medir RTO y RPO con un volumen real y programar el respaldo horario en la plataforma elegida.
- Medir el costo del RPC y la detección con un proveedor real.
- Contador compartido de streams SSE y límites de alta y demo entre réplicas (hoy son por proceso).
- Migrar `react-router` a v7 y la cadena de Vite y Tailwind.
- Alertas sobre las métricas. Hoy se exponen, pero nadie las vigila automáticamente.
