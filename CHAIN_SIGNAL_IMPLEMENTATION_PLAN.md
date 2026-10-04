# Mi plan de implementación

Fecha: 3 de octubre de 2026.

## Mi objetivo

Llego a un piloto cobrable de monitoreo DeFi con datos, alertas y seguimiento por organización. Uso la auditoría actual como diagnóstico y mi estrategia como alcance.

Trabajo por entregas pequeñas. Preservo cambios sin confirmar, no restauro trabajo previo y no ejecuto fondos ni publico despliegues durante esta planificación.

Escribo documentación, comentarios y docstrings en castellano natural, primera persona singular. No agrego nombres de asistentes, créditos automáticos o coautorías en archivos, metadatos o commits. No renombro APIs indiscriminadamente. La documentación actualizada cumple esa voz; dejo revisión exhaustiva del código heredado en E00.

## Mi definición de terminado

Exijo comportamiento verificable, pruebas relevantes, tipos/lint/build donde aplique, migraciones y documentación coherente. No acepto checks deshabilitados o resultados ficticios. Declaro checks bloqueados.

Uso PostgreSQL para certificar concurrencia/aislamiento; SQLite no demuestra esas propiedades. Vinculo hallazgos A01–A32 con entregas y evidencia de cierre.

## Mi orden

| Entrega | Resultado | Dependencias | Esfuerzo orientativo |
|---|---|---|---|
| E00 | Baseline reproducible y documentación pública | Ninguna | 2–4 días |
| E01 | Runtime de lectura | E00 | 2–4 días |
| E02 | Identidad y aislamiento | E01 | 4–7 días |
| E03 | Datos con cadena, calidad y checkpoints | E01 | 4–6 días |
| E04 | Posiciones Aave reales | E03 | 4–7 días |
| E05 | Worker, incidentes y outbox | E02/E04 | 5–8 días |
| E06 | Experiencia comercial | E02/E05 | 5–8 días |
| E07 | Explicaciones y evaluación | E04/E05 | 2–4 días |
| E08 | CI, staging y recuperación | E00–E06 | 4–6 días |
| E09 | Piloto pago y cuotas | E08/entrevistas | 1–2 semanas de observación |
| E10 | Propuestas con aprobación | E09/demanda/revisión | Estimo tras spike |

No trato la suma como compromiso calendario. Priorizo puertas de salida.

## E00. Mi baseline y publicación

Reviso dependencias/imports directos, runtime, tests, Docker, Compose, Render y documentación. Fijo versiones probadas; no actualizo todo por defecto. Mantengo un lockfile de frontend y elimino orquestación sin uso.

Agrego ejemplo de entorno sin secretos, corrijo CMD api.server y documento límites. Reviso comentarios/docstrings en mi voz sin cambiar contratos; sustituyo configuración de scaffolding no necesaria por estándar, preservando licencias requeridas.

Inventario logs/JSON operativos rastreados, preservo copias y preparo bajas revisables. Ignore no desversiona. No reescribo historial; ante credenciales reporto tipo/ubicación sin valores y dejo rotación explícita.

Mi salida: instalación limpia reproducible, documentación coherente y baseline de checks. La licencia raíz requiere decisión explícita antes de distribución comercial.

## E01. Mi lectura segura

Separo análisis de ejecución en API, AgentService y loops. READ_ONLY por defecto; runtime comercial sin transferencias, swap, deploy o funding. GET/SSE observa, no ejecuta. Reconexión no dispara otra operación.

Mi salida: API/worker arrancan sin seed/WDK/destino de rescate. Pruebo todos los GET y aliases con spies de firma: cero escrituras incluso con demo/presupuesto. POST heredado de ejecución indica función deshabilitada.

## E02. Mi identidad

Creo migraciones, sesiones, organizaciones, invitaciones y roles owner/operator/viewer. Protejo lecturas privadas, exports, jobs y streams. Para firma verifico nonce, dominio, cadena y expiración; considero EIP-1271.

Mi salida: dos organizaciones no cruzan datos por ID/filtro/cursor. Viewer no cambia política. 401 para sesión inválida; 403 para permiso insuficiente. Ningún secreto global llega al bundle.

## E03. Mis datos confiables

Centralizo cadena/proveedor/mercado y verifico eth_chainId. Distingo vacío, error, parcial y atrasado. Implemento paginación/checkpoints, retries acotados y cache TTL.

Mi salida: timeout no produce saldo cero o cuenta sana; red incorrecta detiene lectura. Pruebo símbolos repetidos, decimales, ventana, paginación, expiración y reorg.

## E04. Mi adaptador Aave V3

Leo cuenta y reservas a bloque consistente, con contratos/red verificados contra fuentes oficiales al implementar. Guardo colateral, deuda, health factor, activos, mercado y calidad.

Mi salida: comparo snapshot con lectura independiente a bloque fijo. Deuda cero no dispara liquidación; datos de oracle faltantes indican parcial. Replay offline y tests externos de lectura opt-in.

## E05. Mi monitoreo

Extraigo worker del lifespan. Uso jobs con leases/claims transaccionales. Versiono reglas/políticas para health factor, deuda y freshness. Modelo incidente, severidad, acknowledgement y resolución.

Deduplico con histéresis; escribo outbox con alerta; uso transporte falso en tests. Persisto eventos SSE con cursor, límites y permisos.

Mi salida: dos workers no duplican job/incidente; crash no pierde alerta ya persistida; reintentos limitados; reconnect no escribe. Verifico en PostgreSQL.

## E06. Mi interfaz

Consolido Index/OperationsCenter, cliente API tipado y tipos wallet. Corrijo hook condicional, estilos, EventSource.onclose y declaraciones Window.ethereum.

Creo landing, organización, dirección/red, snapshot, política/canal y centro de incidentes. Retiro funding y PnL sin respaldo. Explico vacío, parcial, atraso, proveedor caído, 401/403/429.

Mi salida: pasan tipos/lint/build y E2E de activación/revisión/reconnect, teclado y móvil. Demo sintética aislada.

## E07. Mi explicación

Renombro aprendizaje a historial y quito sesgo por éxitos. Explicación opcional con JSON limitado, IDs de evidencia, schema, fallback, costo y timeout. Sin credenciales de firma.

Mi salida: ninguna explicación agrega cifras o causas inexistentes; fallo del modelo no bloquea incidentes. Evalúo 50 casos curados de normalidad, alertas, datos ausentes y contenido malicioso. Reporto muestra y errores.

## E08. Mi operación

CI con instalación, tests, tipos, lint, build, migraciones, secrets/dependencias. Topología React/API/worker/Postgres, secretos mínimos, TLS y readiness. Staging sin fondos.

Pruebo backup/restore y rollback. Uso como metas internas iniciales cobertura 99%, detección p95 menor a 60 segundos desde snapshot y RPO 1 hora/RTO 4 horas; no vendo SLA antes de medir.

Mi salida: deployment repetible, restore ensayado, métricas y runbooks de proveedor caído, lag, acceso y rollback. Publicación real requiere alcance autorizado.

## E09. Mi piloto

Instrumento activación y revisión sin captar información innecesaria. Limito cuentas/frecuencia y verifico entitlements en backend. Comienzo con cobro asistido.

Si automatizo billing verifico firma/idempotencia de webhooks, cancelación, vencimiento y gracia. Mi salida: 3 pilotos pagos y 2 renovaciones antes de ampliar integración. Si no hay pago, reviso propuesta.

## E10. Mis propuestas futuras

Solo con demanda preparo guía o propuesta Safe para una posición que el cliente controla. Vinculo payload, cadena, nonce, política, simulación y expiración; aprobación humana.

Distingo CREATED, SIMULATED, PROPOSED, SUBMITTED, RECONCILING, CONFIRMED, FAILED, EXPIRED y UNKNOWN. No convierto timeout en retry automático ni receipt exitoso en mitigación sin cambio esperado.

Mi salida: cero broadcast por GET/texto/reconnect; cambio de payload invalida aprobación; recupero incertidumbre sin reenviar a ciegas. Excluyo custodia compartida y gasto autónomo.

## Mis puertas

G0: baseline/lectura. G1: aislamiento y snapshots. G2: incidentes confiables. G3: experiencia/operación. G4: pago y recurrencia. G5: propuestas verificadas.

No amplío permisos económicos por haber terminado una pantalla.
