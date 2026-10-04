# Mi estrategia de producto y mercado

Fecha: 3 de octubre de 2026. Presento hipótesis a validar.

## El producto que quiero vender

Convierto ChainSignal en monitoreo de riesgo DeFi con evidencia, alertas y seguimiento para pequeños equipos. Mi promesa inicial es: “Te ayudo a detectar cambios relevantes en tus posiciones y a entender qué revisar, con datos verificables y sin recibir tus fondos”.

Comienzo con Aave V3 en Ethereum. No vendo un score universal de seguridad, ganancias predichas ni prevención garantizada de liquidaciones. Después evalúo propuestas simuladas con firma humana.

## Mi cliente y su problema

Busco equipos de 2 a 10 personas que administran tesorerías o posiciones DeFi propias, revisan Aave recurrentemente y necesitan compartir seguimiento. Mi comprador responde por la operación; mi usuario supervisa exposición y alertas.

Mi hipótesis: separar dashboards, alarmas y mensajes hace perder tiempo y seguimiento de quién revisó un cambio y qué hizo. Mi unidad de valor es un incidente documentado y resuelto, no una transacción ejecutada por el sistema.

Si las entrevistas muestran otra red predominante, cambio el primer mercado antes de construir multichain. No atiendo traders, compliance, whales y fondos institucionales simultáneamente.

## La competencia que contrasté

| Referencia | Capacidad existente | Decisión que tomo |
|---|---|---|
| [DeBank](https://debank.com/) | Seguimiento de portfolios EVM | No diferencio por mostrar balances |
| [Tenderly Monitor](https://tenderly.co/products/monitor) | Alertas, simulación y respuesta | Valido si mi flujo reduce configuración o mejora seguimiento |
| [DeFi Saver](https://defisaver.com/features/automation) | Automatización de posiciones | No afirmo ausencia de competidores ni novedad de protección |
| [Safe](https://docs.safe.global/core-api/transaction-service-overview) | Transacciones y firmas | Integro infraestructura existente cuando tenga sentido |

Infiero una oportunidad posible en políticas por equipo, responsables y expedientes exportables. No la presento como ventaja demostrada: necesito comparar pilotos contra herramientas actuales.

## Mi MVP

Incluyo organización, invitaciones, roles, cuentas de lectura, posiciones verificadas, política de alerta, centro de incidentes, acknowledgement/resolución, un canal de notificación e historial exportable.

Empiezo con health factor que cruza un umbral, cambio material de deuda y datos que dejan de actualizarse. La última alerta informa cobertura operativa. Agrego concentración cuando tenga valoración confiable.

[Aave explica](https://aave.com/help/borrowing/liquidations) elegibilidad de liquidación debajo de health factor 1 y aclara que no existe un nivel seguro universal. Defino alertas según contexto y política; no convierto un umbral en garantía.

Dejo fuera custodia compartida, funding, copy trading, arbitraje, generación de contratos por wallet, microtransferencias de “protección”, x402, token propio y modelos que autoricen capital.

## Mi experiencia moderna

Diseño navegación con Resumen, Posiciones, Incidentes y Configuración. Primero muestro qué revisar, calidad y hora del dato; después evidencia y seguimiento. Retiro PnL sin respaldo y eventos técnicos como centro de la experiencia.

Mi recorrido: landing clara → demo sintética → cuenta/organización → dirección y red → primer snapshot → política/canal probado → incidente → reconocimiento y cierre.

No pido una transacción para conocer el producto. Implemento teclado, contraste, viewport móvil, estados vacíos y recuperación. Distingo FRESH, STALE, PARTIAL y UNAVAILABLE; proveedor caído no significa cuenta segura.

Mantengo documentación en primera persona y escribo la UI para el cliente en castellano claro; no fuerzo la voz de autora en cada botón.

## Mi validación

Busco 15 entrevistas calificadas en dos semanas. Pregunto por última revisión, último incidente, herramientas pagadas, tiempo perdido, proceso y comprador. Evito preguntar solo si “usarían IA”.

Mis puertas propuestas: 8 describen el mismo problema recurrente, 5 aceptan prueba y 3 aceptan piloto pago o compromiso verificable. No son resultados obtenidos.

Hago piloto asistido con 3–5 organizaciones, datos reales de lectura y configuración acompañada. Si tras 15–20 entrevistas no encuentro repetición o pago, reviso segmento/propuesta. Si prefieren sus alarmas, analizo el diferencial antes de agregar protocolos.

## Mi precio y economía como hipótesis

Pruebo piloto a USD 150 por organización/mes, hasta 10 cuentas, una red/mercado y acompañamiento. Después comparo USD 39 individual y USD 149 equipo con límites explícitos. No son tarifas comprobadas del mercado.

Cobro capacidad de monitoreo, no porcentaje de capital o ganancias. Puedo iniciar cobro asistido y automatizar suscripción cuando haya renovación.

Ejemplo: 10 clientes a USD 149 generan USD 1490 mensuales. Con USD 300–500 de costo directo total tendría margen aproximado de 66%–80% antes de mi tiempo, impuestos, comisiones y adquisición. Es sensibilidad, no cotización.

Reservo como hipótesis USD 150–400 mensuales para infraestructura y proveedores del piloto pequeño; verifico precios y consumo antes de contratar. No necesito simulador pago para lectura.

Con 50 cuentas, 3 consultas cada 5 minutos estimo 43.200 llamadas diarias antes de batching/retries. Mido por cliente, cacheo datos comunes y adapto frecuencia; no prometo monitoreo ilimitado.

## Mi adquisición

Priorizo contactos de tesorería y equipos DeFi, demostraciones concretas y recomendaciones de pilotos. Sigo conversación calificada → demo → configuración → uso → pago.

Preparo landing con alcance, ejemplo de incidente, permisos, preguntas frecuentes, privacidad y contacto. Publico casos solo con consentimiento y datos autorizados. No envío mensajes ni publico campañas como parte de esta planificación.

## Mis métricas

| Métrica | Definición | Objetivo propuesto |
|---|---|---|
| Activación | Cuenta, snapshot, política y canal probado | 60% de invitadas |
| Primer valor | Alta hasta snapshot comprensible | Mediana menor a 10 minutos |
| Recurrencia | Organizaciones que revisan datos/incidentes en semana 4 | 3 de 5 pilotos |
| Utilidad de alertas | Alertas revisadas que cliente considera relevantes | 80%, informando muestra |
| Cobertura | Snapshots válidos/polls programados | 99% en alcance del piloto |
| Detección | Snapshot observado a alerta persistida | p95 menor a 60 segundos |
| Entrega | Persistencia a aceptación del proveedor del canal | p95 menor a 60 segundos |
| Integridad | Acceso cruzado o broadcast no autorizado | Cero |
| Pago | Pilotos y renovaciones | 3 pagos y 2 renovaciones antes de ampliar |

Separo latencia de detección del intervalo de polling. Separo actividad de demo/replay de producción. Ante pocos eventos hago replay etiquetado; no invento incidentes reales para mejorar métricas.

Mi métrica central es organizaciones activas que completan revisiones con evidencia. No afirmo pérdidas evitadas sin contrafactual defendible.

## Mi inteligencia y datos

Uso reglas deterministas para leer posiciones. La explicación opcional recibe JSON limitado, cita evidencia y tiene fallback; no cambia políticas ni escribe.

No necesito entrenar un modelo para leer health factor. Si reúno etiquetas suficientes evalúo ranking de alertas/anomalías con separación temporal y por cuenta, prevención de leakage, precisión/recall por evento y comparación con reglas. Sin etiquetas reporto utilidad revisada, no precisión predictiva.

Promuevo cambios solo si reducen ruido sin ocultar incidentes relevantes. Guardo dataset, versión, límites y rollback. No llamo aprendizaje al conteo de éxitos.

## Mis riesgos y mi calendario

Los riesgos principales son diferencial insuficiente, necesidad poco frecuente, ruido y costos de datos. Los trato con entrevistas, alcance corto, pilotos pagos y medición.

Antes de cobrar públicamente defino términos, privacidad, retención, soporte y responsabilidades con asesoramiento para las jurisdicciones de operación. No resuelvo aquí una clasificación regulatoria.

Estimo 8–12 semanas de trabajo enfocado para un piloto cobrable: 1–2 estabilización/entrevistas, 3–4 identidad/datos, 5–6 alertas, 7–8 experiencia/piloto, 9–12 conversión/operación. No lo presento como fecha garantizada.

Amplío red/protocolo cuando pago y retención lo justifiquen. Luego pruebo propuestas con firma humana. Automatizar fondos exige nueva decisión, evidencia y revisión independiente.
