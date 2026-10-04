# Mi piloto y monetización (E09)

Fecha: 4 de octubre de 2026.

Implementé el recorrido comercial de un piloto de lectura tal como lo planteo en [mi estrategia](ESTRATEGIA_PRODUCTO.md): hasta 10 cuentas, una red y un mercado (Aave V3 en Ethereum mainnet) y acompañamiento. **USD 150 por organización y mes es una hipótesis**, no una tarifa comprobada, y la interfaz lo dice así.

No hay clientes, pagos ni renovaciones reales todavía. No contacté a nadie y no inventé métricas. La puerta comercial (3 pilotos pagos y 2 renovaciones antes de ampliar) se mide solo con pagos confirmados y hoy vale 0 de 3 y 0 de 2.

## Plan y límites

| | Prueba | Piloto |
|---|---|---|
| Duración | 14 días desde el alta | períodos de 30 días por pago confirmado |
| Cuentas | hasta 10 | hasta 10 |
| Frecuencia | cada 60 s como máximo | cada 60 s como máximo |
| Alcance | Aave V3, Ethereum mainnet | Aave V3, Ethereum mainnet |
| Precio | sin cargo | USD 150 por mes (hipótesis) |

La prueba tiene el mismo alcance que el piloto: quiero evaluar el servicio que se pagaría.

**Dónde se aplican los límites** (`comercial/suscripciones.py`):

- Las altas de cuenta bloquean la suscripción mientras cuentan, así dos altas simultáneas no superan el límite. Lo certifiqué en PostgreSQL; la prueba falla si saco el bloqueo.
- La frecuencia se controla al crear y al editar una cuenta.
- El worker no programa organizaciones sin servicio.
- Las lecturas en vivo y "evaluar ahora" responden 402 `plan_inactive`.
- Sin servicio, la organización conserva su historial: incidentes, evidencia y snapshots.

**Estados**, calculados con el reloj (no necesito un proceso que los actualice):

- `trialing`: prueba vigente;
- `active`: período pago vigente;
- `past_due`: vencido sin pago, con servicio durante una gracia de 7 días;
- `canceled`: cancelado y llegado el fin del período;
- `expired`: prueba o gracia terminadas.

Las organizaciones reales existentes recibieron una prueba de 14 días con la migración `0009`. Las demos no tienen suscripción.

**Prueba y cancelación visibles:**

- En Configuración, la tarjeta del plan muestra estado, fechas, uso ("3 de 10"), límites, el precio como hipótesis, el cobro asistido y los pagos confirmados.
- Quien es dueña o dueño cancela con confirmación en dos pasos y puede deshacerlo antes del fin del período. El servicio sigue hasta el fin de la prueba o del período.
- Un aviso arriba de toda la app aparece en estos casos:
  - quedan 3 días o menos de prueba;
  - hay una cancelación programada;
  - hay un pago pendiente;
  - el servicio está pausado.

## Cobro asistido

1. Acuerdo el piloto con la organización y emito una factura fuera del sistema.
2. Cuando verifico el pago, lo registro:
   ```sh
   python -m comercial.cli confirmar-pago --org <id> --referencia <factura> --monto 150 --por "<quién verificó>"
   ```
   Eso crea un `payment_record` y extiende el período 30 días. La misma referencia no se registra dos veces.
3. `python -m comercial.cli estado --org <id>` muestra el estado.

No existe un camino que simule un cobro. Un pago aparece como confirmado solo si lo cargó una persona o si llegó por un webhook firmado.

## Interfaz para un procesador futuro

`POST /billing/webhook` (`comercial/facturacion.py`) está apagado: sin `BILLING_WEBHOOK_SECRET` responde 404.

- **Firma:** `X-Billing-Signature: t=<epoch>,v1=<hex>`, con HMAC-SHA256 sobre `"<t>.<cuerpo>"` y comparación en tiempo constante.
- **Replay:** rechaza firmas con más de 5 minutos de diferencia. Cada `event_id` se registra una vez y un reenvío devuelve `duplicate` sin repetir efectos.
- **Entitlement:**
  - `payment.succeeded` registra un pago confirmado de origen `webhook`;
  - `payment.failed` pasa a `past_due` con 7 días de gracia;
  - `subscription.canceled` cancela al fin del período.
- **Reintentos:** si aplicar el efecto falla, el evento no queda registrado, así el reintento del procesador lo procesa.

## Analítica

Los eventos viven en `product_events`. Solo acepto nombres de una lista cerrada y propiedades enumeradas (`role`, `rule_type`, `channel_kind`, `source`, `severity`); cualquier otra cosa se rechaza.

**No registro** correos, direcciones, balances, montos ni textos libres. Una prueba recorre el flujo y verifica que las propiedades no contengan `@` ni `0x`.

| Evento | Dónde |
|---|---|
| `org_created` | alta de organización (una vez) |
| `account_added` | alta de cuenta |
| `first_snapshot` | primer snapshot guardado, por la API o el worker (una vez) |
| `policy_created` | política nueva |
| `channel_tested` | prueba de canal entregada |
| `incident_reviewed` | detalle de incidente abierto (una vez por incidente) |
| `incident_acknowledged` | incidente tomado |
| `data_reviewed` | resumen abierto (una vez por día) |
| `subscription_canceled`, `subscription_resumed`, `payment_confirmed` | cambios del plan |

Las demos se marcan `is_demo` y el tablero las excluye. Registrar un evento nunca rompe el producto.

## Tablero

`python -m comercial.tablero [--html archivo]` calcula sobre la base real:

- embudo de activación;
- activación: cuenta, snapshot, política y canal probado;
- primer valor: mediana desde el alta hasta el primer snapshot;
- recurrencia en semana 4;
- organizaciones activas en la semana;
- estados de suscripción;
- puerta comercial, solo con `payment_records`.

La utilidad de las alertas queda como pendiente, porque requiere el juicio del cliente.

`--sintetico` genera el mismo tablero sobre una base temporal con 5 pilotos inventados. [`docs/piloto/tablero-sintetico.html`](piloto/tablero-sintetico.html) dice "DATOS SINTÉTICOS" en el título, en cada organización y en la puerta comercial. Esos datos no cuentan para ninguna decisión.

## Landing

Contiene:

- la promesa acotada;
- un ejemplo de incidente marcado como sintético;
- alcance y permisos (solo lectura, sin claves ni firmas);
- qué datos guardo;
- el piloto con el precio como hipótesis y el cobro con factura;
- preguntas frecuentes, incluido "¿Evita liquidaciones?" (no lo prometo) y "¿Tienen auditoría o certificación?" (no);
- contacto.

**El formulario de contacto** (`POST /contact`):

- exige consentimiento;
- guarda email, organización opcional y mensaje;
- tiene un límite de tasa;
- no envía respuestas automáticas: los pedidos los leo con `python -m comercial.cli contactos`.

## Verificación

- **Backend:** `tests/test_comercial.py` (22 pruebas) cubre plan visible, límites de cuentas y frecuencia, prueba vencida sin servicio pero con historial, cancelación y reanudación, pago confirmado idempotente con gracia y vencimiento, datos obligatorios del pago, demo sin suscripción, webhook firmado contra replay, firma inválida, firma vieja, pago fallido con gracia, falla reintentable, webhook apagado, analítica sin datos personales, eventos de una vez, recorrido instrumentado por API, rutas de suscripción con roles, 402 sin servicio, contacto con consentimiento y límite, y tablero real sin pagos inventados.
- **Concurrencia:** `tests/test_comercial_postgres.py` prueba que dos altas simultáneas no superan el límite.
- **Interfaz:** Vitest cubre la tarjeta del plan, la cancelación en dos pasos, los roles, el aviso global y la landing sin promesas indebidas, con contacto que exige consentimiento. El E2E cubre el plan dentro de la activación y la landing con el contacto que llega al backend.

## Validaciones humanas pendientes

Ninguna de estas está hecha. Las hago yo, con personas reales:

1. 15 entrevistas calificadas con la [guía](piloto/GUIA_ENTREVISTAS.md), y anotar cuántas describen el mismo problema recurrente (puerta: 8).
2. Confirmar que Aave V3 en Ethereum es el mercado que más se repite; si no, cambiar de mercado antes de construir más.
3. Validar el precio: si USD 150 por mes es aceptable, demasiado alto o irrelevante, y quién paga.
4. Conseguir 5 organizaciones que acepten la prueba y 3 que paguen un piloto. Registrarlas en el [registro de pilotos](piloto/REGISTRO_PILOTOS.md).
5. Medir activación, primer valor y recurrencia con esos pilotos reales, no con el tablero sintético.
6. Pedir a cada piloto que califique las alertas revisadas (utilidad objetivo: 80 %, informando la muestra).
7. Lograr 2 renovaciones pagas antes de ampliar red, protocolo o funciones.
8. Redactar términos del servicio y política de privacidad con asesoría: la landing describe qué guardo, pero no es un documento legal.
9. Definir cómo emito facturas y en qué moneda, y quién confirma pagos además de mí.
10. Decidir la retención de pedidos de contacto y eventos de producto y borrarlos según esa política.
