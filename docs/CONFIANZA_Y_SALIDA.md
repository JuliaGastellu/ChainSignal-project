# Confianza, configuración y criterio de salida

Fecha: 4 de octubre de 2026. Base: commit `e186940` en la rama `JuliaGastellu`, más los cambios sin commitear que describo acá. No desplegué nada.

## Qué implementé

### Señales que no se mezclan

En Posiciones y en el detalle de cada cuenta muestro tres señales separadas, cada una con texto y símbolo (no dependen solo del color):

- **Alertas**: salen de los incidentes abiertos. Si una cuenta tiene un incidente de health factor abierto, lo dice ("Alerta abierta: health factor bajo el umbral") y la cuenta sube al principio de la lista.
- **Dato**: frescura y calidad de la lectura (actualizado, atrasado, parcial, no disponible, sintético). Un dato fresco no significa que la posición esté bien; un dato no disponible dice explícitamente que no indica que la cuenta esté sana.
- **Actividad**: descripción neutra de la cuenta ("Posición con deuda", "Solo depósitos", "Sin posiciones en Aave V3").

Separo el **umbral de alerta** (la política de la organización) del **umbral de liquidación del protocolo**, y aclaro que Aave permite liquidar con un health factor menor a 1.

### Entregas: simulada, aceptada por el destino y nada más

Cada entrega tiene un resultado: `simulated`, `accepted_by_destination`, `failed` o `pending`. El canal simulado dice que registró una simulación y que el mensaje no salió del sistema. Un webhook que responde 2xx queda como "Aceptada por el destino externo". No afirmo que una persona la haya leído. La demo y la práctica nunca cuentan como verificación operativa.

### Webhook externo seguro

`monitoreo/webhook_seguro.py`:

- solo `https` en el puerto 443 y sin credenciales en la URL;
- resuelvo el nombre y exijo que todas las IP sean públicas;
- me conecto a la IP ya validada, con SNI y verificación del certificado contra el nombre (evita rebinding de DNS);
- no sigo redirecciones ni reintento dentro de la misma llamada;
- firmo con HMAC-SHA256 (`X-ChainSignal-Signature: t=…,v1=…`) usando un secreto por canal que se muestra una sola vez;
- los errores se guardan como códigos y la interfaz los traduce.

Los destinos de prueba (`WEBHOOK_TEST_ALLOWED_TARGETS`, `WEBHOOK_CA_BUNDLE`) solo existen para el E2E y el ensayo, y la API se niega a arrancar con ellos si `APP_ENV=production`. Con `NOTIFICATIONS_WEBHOOKS_ENABLED=false` la API responde 409 `webhooks_disabled` y la interfaz explica el siguiente paso sin crear un sandbox en su lugar.

### Configuración

- **Políticas**: crear, editar como versión nueva (la evidencia de incidentes anteriores conserva su versión), pausar con confirmación y reactivar. Antes de guardar muestro cuándo abre, cuándo despeja y cuándo sube de severidad (`POST /orgs/{org}/policies/preview`).
- **Canales**: webhook externo con prueba y último resultado, y canal simulado.
- **Personas**: cambiar roles, quitar e invitar con un enlace de un solo uso (no envío correos). La API no deja la organización sin al menos una persona dueña.
- Las referencias de las explicaciones son enlaces legibles ("Lectura del bloque 26.116.392", "Política, versión 1") hacia la evidencia o la política, y la procedencia técnica queda en un detalle expandible.

### Resumen y preparación

- **Qué necesita atención**: incidentes ordenados por severidad y cuentas sin datos, cada uno con motivo, frescura y enlace a la acción.
- **Monitoreo preparado** se deriva del estado vigente, no de hitos pasados. En una organización real exige cuatro condiciones:
  - una cuenta observada;
  - una lectura válida ahora: la última lectura de esa cuenta en su cadena, protocolo y mercado es FRESH, la última evaluación no informó un problema, y el dato se confirmó dentro de dos intervalos (mínimo 15 minutos);
  - una política habilitada;
  - un webhook habilitado, con los envíos externos encendidos en la instancia, cuyo destino aceptó la prueba y cuya última entrega no falló.

  Una cuenta sana completa la preparación sin necesidad de un incidente. Cuando está completa, la lista se reduce a una línea.
- **Configuración completada y circuito vigente están separados.** `readiness.configured` dice si alguna vez se completó cada paso, y `readiness.issues` dice por qué una condición vigente no se cumple:
  - lectura: no disponible, parcial, atrasada, sin confirmar reciente o sin lectura;
  - política: pausada;
  - canal: envíos apagados, webhook deshabilitado, última entrega fallida o sin probar.

  Si la configuración está completa pero el circuito no funciona, el Resumen muestra "Monitoreo no disponible ahora", con el motivo y el siguiente paso, en lugar de "preparado". En la demo, la sección se llama "Demo del monitoreo".
- Un snapshot que fue FRESH al guardarlo no alcanza para afirmar frescura actual. Límite conocido: mientras el worker reintenta una falla transitoria, que dura como máximo los intentos configurados, sigo contando la última lectura fresca si está dentro de la ventana; agotados los intentos, la cuenta queda no disponible.
- **Práctica opcional**: abre una organización de datos sintéticos aislada, que no cuenta para la preparación ni para la analítica.
- Contadores secundarios, sin tendencias.
- En la demo, un aviso permanente dice que todo es simulado.

### Presentación

- Identidad oscura con acento turquesa.
- Portada con título corto ("Alertas con evidencia para tus posiciones en Aave"), beneficio, alcance de solo lectura, precio en validación y detalles técnicos plegados.
- No uso clientes, testimonios ni garantías.
- En pantallas angostas, los activos se muestran como tarjetas y la barra de secciones entra completa a 360 px.
- Colores de texto con contraste AA.

## Qué comprobé

| Suite | Resultado |
|---|---|
| Python (`pytest`, con PostgreSQL 16 desechable) | 460 aprobadas, 0 omitidas. Incluyen las transiciones de preparación: dato FRESH que pasa a no disponible y vuelve, dato que envejece, envíos apagados, webhook deshabilitado y entrega fallida después de una prueba aceptada, y política pausada. 4 deseleccionadas: son las `integration`, que usan servicios reales y no corro. |
| Vitest | 67 de 67. |
| `typecheck` y `build` | Sin errores. |
| `lint` | 0 errores y 7 advertencias de fast refresh. |
| Playwright (Chromium, entorno aislado con receptor HTTPS local) | 20 de 20. |
| Ensayo en staging local (`python -m operacion.ensayo_staging`) | 7 de 7 pasos; detalle en `docs/ensayos/ensayo-piloto.json`. |

Los 20 escenarios de Playwright cubren:

- activación completa con webhook aceptado por el destino;
- recorridos de dueña, operación y lectura;
- webhook fallido y destino privado rechazado;
- Resumen sano, sin datos y práctica aislada;
- 360, 390, 768 y 1440 px, comprobando el ancho efectivo del DOM (`clientWidth` y `scrollWidth`), desbordes y la barra de secciones;
- axe (WCAG 2 A/AA) sin violaciones serias ni críticas en portada, Resumen, Posiciones, Incidentes, Configuración y los dos detalles;
- navegación con teclado y foco visible;
- errores 429 y 403, servidor caído, sesión vencida y stream cortado;
- demo aislada y móvil.

El ensayo de staging levanta la topología del piloto con dos réplicas de la API y agrega:

- un frente TLS con certificado autofirmado de un día;
- un receptor HTTPS dentro de la red del compose.

Comprueba:

- migración aparte;
- flujo de producto por HTTPS;
- cookies `Secure`, `HttpOnly` y `SameSite=Lax`, HSTS y rechazo de un certificado no confiable;
- entrega aceptada, entrega fallida con `http_500`, destino privado rechazado, firma presente y secreto ausente de los logs;
- réplicas, reinicios, proveedor caído, y respaldo, pérdida del volumen y restauración con huellas iguales.

Capturas en `docs/capturas/`:

- `01`–`07`: activación e incidente;
- `08`–`11`: demo, error, móvil y portada;
- `12`–`14`: configuración por rol y webhook fallido;
- `15`–`16`: Resumen sano y sin datos;
- `ancho-360-*` y `ancho-1440-*`: móvil y escritorio.

## Qué no pude verificar

- **CI en GitHub**: la API pública no muestra ejecuciones de workflows para la rama `JuliaGastellu` y no tengo `gh` instalado. Queda pendiente confirmar que el workflow corre y pasa en GitHub.
- **Staging autorizado**: no tengo acceso a un staging real. Todo lo anterior lo ensayé en local. En el staging real falta repetir el ensayo con TLS de la plataforma, dominio propio, un destino webhook del equipo y un respaldo y restauración sobre el almacenamiento de la plataforma.
- **Recepción humana** de una notificación: por diseño no la afirmo.

## Límites conocidos

- Una red (Ethereum mainnet) y un mercado (Aave V3). Solo lectura: no firmo ni muevo fondos.
- Los límites de alta, demo y práctica viven en memoria por proceso. Con varias réplicas no se comparten.
- El webhook no reintenta dentro de la misma llamada; los reintentos los hace el outbox. No hay correo ni chat como canal.
- Las invitaciones no se envían: la dueña comparte el enlace por su cuenta.
- El precio (USD 150) sigue siendo una hipótesis. El cobro es asistido.

## Condiciones para publicar

1. Confirmar CI verde en GitHub para el commit que se publique.
2. Repetir `operacion.ensayo_staging` (o su equivalente) en el staging autorizado: TLS real, cookies y HSTS, readiness con API y worker separados, entrega a un webhook del equipo y respaldo y restauración.
3. Definir licencia, privacidad y soporte (pendientes desde E09).
4. Revisar y commitear estos cambios: hoy están sin commitear en el árbol de trabajo.
5. Recién entonces, desplegar. Me detuve antes de ese paso.
