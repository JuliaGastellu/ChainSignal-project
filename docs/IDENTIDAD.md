# Mi identidad y aislamiento por organización (E02)

Fecha: 4 de octubre de 2026.

Desde E02 ChainSignal no usa una clave global. Cada persona inicia sesión, pertenece a una o más organizaciones con un rol y solo ve y modifica los recursos de esas organizaciones. Verifico la autorización en las rutas, en los servicios, en el worker, en los eventos y en la base de datos.

## Qué elegí y por qué

| Decisión | Elección | Motivo |
|---|---|---|
| Login | Email y contraseña con `hashlib.scrypt` (n=2^14, r=8, p=1) | Es lo más simple que cubre el piloto y no suma dependencias. No elegí firma de wallet: exigiría RPC mainnet para EIP-1271 y confundiría identidad con control de fondos. |
| Alta de personas | Primera organización por CLI; el resto entra por invitación | No hay registro abierto. |
| Sesión | Cookie `cs_session` HttpOnly, Secure, SameSite=Lax; en la base guardo solo el SHA-256 del token | JavaScript no puede leerla y un volcado de la base no la expone. |
| Expiración y revocación | Expiración absoluta (`SESSION_TTL_HOURS`, 12 h por defecto), logout, logout de todas las sesiones y revocación por CLI | Una sesión robada tiene vida limitada y puedo cortarla. |
| CSRF | Doble envío: cookie legible `cs_csrf` y header `X-CSRF-Token`, que deben coincidir entre sí y con el hash de la sesión. Si llega `Origin`, debe estar en `CORS_ALLOWED_ORIGINS` | SameSite=Lax no cubre todo; el token queda atado a la sesión. |
| CORS | Orígenes explícitos con credenciales; `*` frena el arranque | Las cookies no deben viajar a orígenes arbitrarios. |
| Migraciones | Alembic (`migrations/`) | `init_db` aplica `upgrade head`; en PostgreSQL un advisory lock evita que la API y el worker migren a la vez. |

Observar una dirección no es controlar fondos ni pertenecer a una organización. Una cuenta observada (`monitored_accounts`) es una dirección pública que la organización sigue: la API la devuelve con `relationship: "observed"` y no deriva de ella ningún permiso.

## Modelo de datos (migración `0002`)

| Tabla | Clave de aislamiento |
|---|---|
| `organizations` | — |
| `users` | email único; sin vínculo con wallets |
| `memberships` | `(organization_id, user_id)` único; rol con `CHECK` |
| `invitations` | `organization_id`; token guardado como hash; un solo uso, vencimiento y revocación |
| `sessions` | `user_id`; hashes de token y de CSRF |
| `monitored_accounts` | `organization_id`; único por `(organization_id, chain_id, address)` y por `(id, organization_id)` |
| `alert_policies` | `organization_id`; clave foránea compuesta `(account_id, organization_id)` → `monitored_accounts(id, organization_id)` |
| `org_events` | `organization_id`; el `id` es el cursor del stream SSE |

La clave foránea compuesta hace que la base rechace una política que apunte a una cuenta de otra organización, aunque el código tenga un error. Lo pruebo contra PostgreSQL insertando la fila sin pasar por el servicio.

Incidentes, snapshots, jobs persistentes y exports todavía no existen (E03–E05). Cuando los agregue, siguen el mismo patrón: `organization_id` obligatorio, unicidad `(id, organization_id)` y referencias compuestas.

## Roles

| Acción | viewer | operator | owner |
|---|---|---|---|
| Ver cuentas, políticas, eventos, miembros y análisis | sí | sí | sí |
| Crear, modificar o borrar cuentas y políticas | no | sí | sí |
| Invitar, revocar invitaciones, cambiar roles y quitar miembros | no | no | sí |

Una organización siempre conserva al menos un owner. Bloqueo las filas de los owners (`SELECT … FOR UPDATE`) para que dos degradaciones simultáneas no la dejen sin ninguno; lo verifico con una carrera forzada en PostgreSQL.

Un cambio de rol o la salida de la organización rigen desde la siguiente solicitud de una sesión ya abierta, porque verifico la membresía en la base en cada solicitud. El stream de eventos la verifica en cada vuelta y se cierra con `event: session_ended`.

## Rutas

| Ruta | Rol mínimo |
|---|---|
| `POST /auth/login`, `GET /auth/session`, `POST /auth/logout`, `POST /auth/logout-all` | sesión (salvo login) |
| `POST /invitations/accept` | token de invitación; con sesión iniciada, el email debe coincidir |
| `GET /orgs/{org}/members` | viewer |
| `PATCH`/`DELETE /orgs/{org}/members/{id}` | owner |
| `POST`/`GET /orgs/{org}/invitations`, `DELETE /orgs/{org}/invitations/{id}` | owner |
| `GET /orgs/{org}/accounts`, `GET /orgs/{org}/accounts/{id}`, `GET /orgs/{org}/accounts/{id}/analysis` | viewer |
| `POST`/`PATCH`/`DELETE` de cuentas | operator |
| `GET /orgs/{org}/policies` | viewer |
| `POST`/`PATCH`/`DELETE` de políticas | operator |
| `GET /orgs/{org}/events?cursor=`, `GET /orgs/{org}/events/stream` (`cursor` o `Last-Event-ID`) | viewer |
| `GET /report/{w}`, `/analyze/wallet/{w}`, `/analyze/block/{n}`, `/run-agent/{w}` y alias SSE | sesión |
| `GET /health` | público; solo `status`, `service`, `version` y `mode` |

Respuestas de error: sin sesión, 401; sin membresía o con rol insuficiente, 403; un recurso que no pertenece a la organización del path, 404, igual que si no existiera. Un cursor de otra organización también da 404, para no revelar qué ids existen fuera. Los cuerpos rechazan campos desconocidos, incluido `organization_id`, con 422. Los errores internos devuelven `{"error": "internal_error"}` sin detalle.

### Rutas heredadas

| Ruta | Ahora | Reemplazo |
|---|---|---|
| `POST /track-wallet`, `GET`/`POST /agent/watch`, `DELETE /agent/watch/{a}`, `GET /agent/radar` | 410 | `/orgs/{org}/accounts` |
| `GET /agent/history`, `/agent/actions`, `/agent-activity`, `/agent/state`, `/agent/state/{w}`, `/agent/budget/{w}`, `/agent-budget/{w}`, `/agent/learning`, `/agent/status` | 410 | Datos globales del experimento sin organización; no tienen reemplazo en el producto |
| `GET /agent/stream` | 410 | `/orgs/{org}/events/stream` |
| `POST /agent/budget`, `/fund-agent`, `/agent/execute`, `/agent/start`, `/agent/stop`, `GET /agent/address` | 403 (desde E01) | — |

## Migración de usuarios y configuración

No había usuarios antes de E02: la única credencial era `CHAINSIGNAL_API_KEY`, que ya no existe y puedo borrar de mi `.env`.

1. **Base de datos.** Al arrancar, la API y el worker aplican las migraciones. Una base creada antes con `create_all` sirve tal cual: la migración `0001` crea solo las tablas heredadas que falten y conserva sus datos. A mano: `alembic upgrade head`.
2. **Primera organización.** `python -m identidad.cli crear-organizacion --nombre "Mi equipo" --email yo@ejemplo.com`. La contraseña sale de `CHAINSIGNAL_BOOTSTRAP_PASSWORD` o la pido sin eco; nunca va como argumento. Mínimo 12 caracteres.
3. **Configuración de monitoreo.** `python -m identidad.cli importar-legado --organizacion <org_id> --chain-id <red>` convierte `tracking.json` y `watched_wallets.json` en cuentas observadas de esa organización. No modifica los archivos, omite direcciones inválidas o ya importadas y exige la red explícita: los archivos no la registraban y no la supongo. Desde E02 el worker ya no lee `tracking.json`.
4. **Resto del equipo.** El owner invita desde `POST /orgs/{org}/invitations`. El token aparece una sola vez y lo comparto por un canal propio: todavía no envío emails.
5. **Interfaz.** Sin `VITE_API_BASE`, el frontend usa el mismo origen y el proxy de Vite reenvía `/auth`, `/orgs`, `/invitations` y el análisis a la API. En producción sirvo interfaz y API bajo el mismo dominio con HTTPS. Si la API queda en otro origen, lo agrego a `CORS_ALLOWED_ORIGINS`.
6. **Producción.** `SESSION_COOKIE_SECURE` no puede ser `false` con `APP_ENV=production`: la configuración frena el arranque.
7. **Revocación.** `python -m identidad.cli revocar-sesiones --email persona@ejemplo.com` corta todas las sesiones de una persona.

## Cómo lo verifico

- `tests/test_api_auth.py`:
  - atributos de cookie y login fallido idéntico para cualquier causa;
  - 401 sin sesión o con cookie falsificada, revocada o vencida;
  - CSRF ausente o de otra sesión, `Origin` ajeno y CORS;
  - errores internos sin detalle, rutas heredadas en 410 y económicas en 403.
- `tests/test_aislamiento_organizaciones.py`, con dos organizaciones:
  - IDs ajenos bajo mi path (404) y paths de otra organización (403);
  - filtros manipulados en la query, `organization_id` en el cuerpo (422) y políticas que apuntan a cuentas ajenas;
  - un viewer que intenta mutar, un operator que intenta administrar, cambio de rol en una sesión abierta, último owner y membresías ajenas;
  - invitaciones de un solo uso, revocadas, vencidas, para otro email o para un email ya registrado;
  - eventos y cursores ajenos, tokens que no aparecen en eventos, y el stream cerrándose al revocar la sesión o al quitar a la persona;
  - el worker escribiendo cada resultado en su organización y la verificación de rol en el servicio aun sin pasar por la ruta.
- `tests/test_identidad_postgres.py`, solo contra PostgreSQL:
  - migraciones sobre una base vacía y sobre una base heredada;
  - la clave foránea compuesta;
  - la carrera entre dos owners con una pausa forzada: sin `FOR UPDATE` la prueba falla;
  - cuatro aceptaciones simultáneas del mismo token, de las que solo una crea membresía.
- `tests/test_identidad_cli.py`: arranque, importación heredada y revocación.
- Vitest: el cliente HTTP manda credenciales y CSRF solo en mutaciones y nunca `X-API-Key`; la guarda de sesión redirige al login con 401.

Para comprobar que las pruebas detectan regresiones, quité a propósito el filtro por organización en `listar_cuentas` y la verificación de rol del servicio: fallaron las pruebas correspondientes. Después restauré el código.

También probé la imagen Docker contra un PostgreSQL 16 desechable:

- las migraciones dejaron la base en `0002`;
- la CLI creó la organización;
- el login devolvió el rol owner;
- crear una cuenta sin CSRF dio 403 y con CSRF dio 201;
- las rutas heredadas dieron 410 y las económicas 403;
- después del logout, reusar la cookie dio 401.

## Lo que no hice en E02

- No tengo límite de intentos de login, recuperación de contraseña, MFA ni envío de emails de invitación. Antes del piloto agrego al menos el límite de intentos (A30).
- No guardo una auditoría separada de los eventos: `org_events` cumple ese papel por ahora y no tiene política de retención.
- El historial de evaluaciones (antes `LearningStore`, renombrado en E07) sigue siendo un JSON global del análisis. Ya no lo expongo (`/agent/learning` da 410), pero no está particionado por organización.
- El análisis de una dirección arbitraria (`/report`, `/run-agent`) exige sesión, pero no está atado a una organización. Usa datos públicos de la cadena y no lee recursos privados.
- La interfaz heredada sigue llamando a rutas que ahora dan 410. Solo agregué el login, la guarda de sesión y el cierre de sesión; el rediseño comercial es E06.
