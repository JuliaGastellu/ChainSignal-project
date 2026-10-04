# Mi experiencia comercial (E06)

Fecha: 4 de octubre de 2026.

Reemplacé la interfaz fragmentada (Index y OperationsCenter, con paneles de agente, funding, balance de la wallet compartida y PnL) por un producto con cuatro secciones: Resumen, Posiciones, Incidentes y Configuración. El alcance sigue siendo lectura de Aave V3 en Ethereum mainnet. La interfaz no firma, no mueve fondos ni pide acceso a una wallet.

## Recorrido

| Ruta | Qué muestra |
|---|---|
| `/` | Landing con el alcance real, botón de demo y alta. |
| `/registro` | Alta de organización y persona owner (`POST /auth/signup`, solo con `SIGNUP_ENABLED=true`). |
| `/login` | Inicio de sesión. |
| `/app` | Redirige a la primera organización de la persona. |
| `/app/:org/resumen` | Checklist de activación (dirección, primer snapshot, política, canal probado, incidente revisado), incidentes activos por severidad, cuentas por calidad de dato y última evaluación. |
| `/app/:org/posiciones` | Alta de dirección con red (solo Ethereum mainnet) y lista de cuentas con su estado. |
| `/app/:org/posiciones/:cuenta` | Health factor, umbral de alerta, colateral, deuda, bloque y hash, frescura, calidad, activos y límites de la lectura. Botones para obtener el snapshot y evaluar ahora. |
| `/app/:org/incidentes` | Activos y resueltos. |
| `/app/:org/incidentes/:id` | Condición, valor observado, umbral con histéresis, bloque de apertura, calidad, responsable, versión de la política, historial de evidencia y entregas. Tomar y resolver con nota. |
| `/app/:org/configuracion` | Políticas versionadas (health factor, cambio de deuda, dato atrasado), canales sandbox con prueba y personas con su rol. |

Los controles dependen del rol (viewer, operator, owner), pero la API vuelve a autorizar cada pedido. Una persona de solo lectura ve el incidente y no ve las acciones.

## Demo aislada

`POST /demo` crea una organización `is_demo` que vence sola (`DEMO_TTL_HOURS`), con un owner sin contraseña conocida, una cuenta con dirección sintética, dos políticas, un canal sandbox probado y un incidente abierto. Sus snapshots salen de un escenario codificado con el ABI real y quedan marcados `is_synthetic`. Una organización real que observa la misma dirección no los ve. El worker no programa ni toma jobs de demos: se evalúan en línea. El límite es de 20 demos por hora y por IP, en memoria.

## Cliente y estados

- `src/lib/api.ts`: cliente tipado. Envía la cookie, agrega CSRF solo en mutaciones y convierte toda respuesta no OK en `ApiError` (también la falta de red, con estado 0). Nunca trato una respuesta no OK como éxito.
- `src/lib/consultas.ts`: React Query, con claves por organización. No reintento 4xx. Reintento un 429 una vez solo si `Retry-After` es de 10 s o menos; si es mayor, muestro cuánto esperar. Reintento red y 5xx dos veces con backoff. Cada mutación invalida las consultas de su organización.
- `src/hooks/useEventosOrg.ts`: SSE con `onopen` y `onerror` (EventSource no tiene `onclose`). Un corte transitorio lo reconecta el navegador con `Last-Event-ID`. Si el servidor rechaza el stream, verifico la sesión y reabro con backoff desde el último cursor; con 401 me detengo. El encabezado muestra "En vivo", "Reconectando…" o "Sin actualizaciones en vivo".
- Estados que distingo: sin lectura todavía, sin posiciones en Aave V3 y sin deuda (no son errores), datos parciales, atrasados (STALE, o lectura más vieja que dos intervalos y al menos 15 min), no disponibles, servidor caído, 401 (lleva al login), 403, 404, 409, 422 y 429.

## Accesibilidad

Uso `lang="es"`, enlace "Saltar al contenido", foco visible global y etiquetas en todos los campos. Las tablas tienen encabezados con `scope`, los mensajes de estado usan `role="status"` y los errores `role="alert"`. Subí el contraste del texto secundario. La barra de secciones se desplaza en horizontal en pantallas angostas.

## Limpieza

Quité los componentes y hooks heredados, las dependencias `ethers` y `framer-motion` (ya no se usan), las variables públicas de montos de demo y los proxies a rutas eliminadas. Arreglé `EventSource.onclose` y el hook condicional al quitar esos archivos. La CSP del HTML solo permite el mismo origen. Arreglé los tres errores de lint que quedaban en `ui/` y en la configuración de Tailwind.

## Pruebas E2E

`npm run e2e` (Playwright 1.63, Chromium) levanta dos servidores:

- `scripts/entorno_e2e.py`: API y worker de lectura sobre un SQLite temporal, sin `.env` ni red. La lectura de Aave V3 se reproduce desde `tests/datos/aave_v3_prestatario_usdc_26116392.json` (`AAVE_REPLAY_FIXTURE`). Migra antes de arrancar.
- `vite preview` del build, con proxy a esa API.

Escenarios:

- `activacion.spec.ts`: alta, dirección y red, primer snapshot (health factor 1,2254 en el bloque 26.116.392), política con umbral 1,5, canal creado y probado, evaluación por el worker, incidente que aparece por el stream, tomar, resolver con nota, lista de resueltos y checklist completa.
- `demo.spec.ts`: datos sintéticos visibles, incidente tomado, y aislamiento entre demo y organización real en los dos sentidos (interfaz y API).
- `errores.spec.ts`: 429 con `Retry-After`, 403, servidor caído con reintento, sesión vencida, stream cortado y recuperado, navegación con teclado.
- `movil.spec.ts` (Pixel 7): sin elementos fuera del ancho en las cuatro secciones ni en los detalles.

Las capturas de `docs/capturas/` las genera esta suite y las revisé una por una.

Los E2E encontraron dos defectos que corregí:

- **500 intermitente al crear una demo.** Con SQLite, el worker y la evaluación en línea podían reclamar el mismo job. Lo detallo en [mi monitoreo](MONITOREO.md).
- **Hash de bloque fuera de pantalla en móvil.** La primera versión de la prueba móvil medía `scrollWidth` y no lo detectaba. Ahora mide cada elemento; comprobé que falla sin el arreglo y pasa con él.

## Lo que falta

- Los textos de `limitations` y `detail` vienen de la API en inglés y los muestro tal cual.
- No hay edición ni pausa de políticas, alta de webhooks, invitaciones ni gestión de roles desde la interfaz. La API las tiene, salvo webhooks reales, que siguen apagados.
- No hay correcciones de evidencia desde la interfaz. La API las acepta y la interfaz las muestra en el historial.
- Los límites de alta y demo viven en memoria de cada proceso.
- El preview usa SQLite. Las garantías de concurrencia siguen certificadas solo contra PostgreSQL.
- Quedan 7 advertencias de lint (react-refresh) en componentes `ui/` del scaffolding.
