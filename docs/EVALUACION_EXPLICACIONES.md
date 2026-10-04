# Mi explicación y evaluación (E07)

Fecha: 4 de octubre de 2026.

Quiero que la inteligencia del producto sea honesta y comprobable. El producto funciona sin modelo. Un modelo, si lo habilito, solo redacta hechos que ya están en un JSON estructurado; cualquier salida que no pueda comprobar cae a una plantilla determinista.

## Historial, no aprendizaje

`services/learning_store.py` se llamaba "aprendizaje", pero solo contaba señales y resultados. Peor: `StrategyEngine.select` elegía la estrategia con más resultados `success`, subía su confianza a 0,65 y la marcaba `force_execute=True`. Ese `success` era el estado de la transacción, es decir, que la red la aceptó. Aceptación no es rentabilidad ni acierto.

- Lo renombré a `services/historial_evaluaciones.py` (`HistorialEvaluaciones`). El resumen informa `accepted_transactions` y conteos por estado, y ya no tiene `strategy_success`.
- Quité el sesgo: `StrategyEngine.select` ya no recibe el historial y decide solo con las señales de la evaluación actual.
- `tests/test_historial_evaluaciones.py` comprueba que 50 transacciones aceptadas de una estrategia no cambian la selección.

Esto afecta al análisis heredado y al experimento testnet. El monitoreo comercial (E05) nunca usó el historial.

## Explicación opcional

Lo implementé en el paquete `explicacion/`:

| Módulo | Qué hace |
|---|---|
| `entrada.py` | Arma el JSON desde el incidente, la versión de la regla que lo abrió, el último snapshot con evidencia y la evidencia. Cada hecho lleva su referencia (`snapshot:<id>`, `rule_version:<n>`, `evidence:<id>`). Calcula si las cifras son consistentes entre sí: health factor contra colateral, deuda y umbral de liquidación, valor evaluado contra snapshot, conciliación, y "sin deuda" con deuda. Los textos que escribe una persona van en `untrusted_metadata`, sin caracteres de control y con 200 caracteres como máximo. Límites: 20 evidencias y 8 KB. |
| `plantilla.py` | Explicación determinista. Es el camino por defecto y el fallback de cualquier falla. No usa los metadatos no confiables y no recomienda operar. |
| `validacion.py` | Valida schema y largos, que cada enunciado cite referencias existentes y que cada cifra coincida (redondeada) con una de la entrada. Rechaza hex o URLs ajenos, consejos de operar, menciones de claves, pedidos de cambiar políticas, reaseguros sin respaldo, eco de metadatos, una comparación con el umbral que contradiga los datos y la omisión de que el dato no es firme. |
| `proveedor.py` | API compatible con chat completions vía `requests`. `temperature` 0, salida JSON y timeout de conexión y de lectura. El pedido nunca declara herramientas. |
| `servicio.py` | Antes de llamar estima el costo máximo (entrada más tope de salida) contra el presupuesto diario de la organización y después registra el costo real. Ante timeout, 429, error, JSON inválido o validación fallida, usa la plantilla y guarda el motivo. Solo escribe el registro de la explicación (`incident_explanations`, migración `0007`). |

Rutas:

- `GET /orgs/{org}/incidents/{id}/explanation` (viewer): la última explicación guardada o la plantilla, sin costo.
- `POST` a la misma ruta (operator): genera una.

La interfaz muestra la explicación en el detalle del incidente, con sus referencias y el motivo del fallback.

Configuración:

- Apagada por defecto (`EXPLANATION_MODEL_ENABLED=false`).
- Para habilitarla exijo base, modelo, precios por millón de tokens y presupuesto. En producción, además, https.
- La clave solo la lee la API. El worker no importa `explicacion/` y no hay credenciales de firma en ningún camino.

El texto no cambia nada. Ninguna salida se interpreta como acción. `tests/test_explicaciones.py` comprueba que una salida que pide cambiar la política no crea versiones ni toca el incidente.

## Evaluación

`python -m evaluacion_explicaciones.correr` escribe `evaluacion_explicaciones/resultados.json`. `tests/test_evaluacion_explicaciones.py` repite la corrida como prueba de regresión.

**Muestra.** 50 casos curados en `evaluacion_explicaciones/casos.py`, con lo que la explicación debe decir y lo que no puede decir:

| Categoría | Casos |
|---|---|
| normalidad | 8 |
| alarma | 8 |
| deuda cero | 6 |
| fuentes atrasadas | 7 |
| datos parciales | 7 |
| cifras contradictorias | 7 |
| metadatos maliciosos (inyección de instrucciones, URL, dirección de quema, JSON incrustado, controles Unicode, texto de 500 caracteres) | 7 |

**Plantilla:**

- Fidelidad factual: 50 de 50. El validador no encuentra cifras, referencias ni contenido sin respaldo.
- Utilidad: 50 de 50. Dice lo exigido y nada de lo prohibido.

**Validador ante salidas infieles.** Apliqué a cada caso mutaciones que imitan errores de un modelo:

| Mutación | Detectadas |
|---|---|
| cifra inventada | 50/50 |
| referencia inexistente | 50/50 |
| enunciado sin referencia | 50/50 |
| consejo de operar | 50/50 |
| pedido de cambiar la política | 50/50 |
| reaseguro sin respaldo | 46/46 |
| hex inventado | 50/50 |
| URL | 50/50 |
| schema roto | 50/50 |
| comparación con el umbral invertida | 20/20 |
| omite que el dato no es firme | 23/23 |
| eco de metadatos maliciosos | 7/7 |

**Paráfrasis fieles rechazadas por error:** 0 de 50 reordenadas y 0 de 3 con el health factor redondeado a dos decimales.

**Errores que encontré en el camino:**

- La primera versión del validador detectaba 0 de 20 comparaciones invertidas y 0 de 23 omisiones de calidad, porque solo miraba cifras y referencias. Agregué los dos chequeos semánticos.
- Ese cambio hizo que la plantilla fallara 4 casos de dato atrasado: no decía "atrasado" en el enunciado principal y mi lista de marcas no reconocía "no están actualizados". Corregí las dos cosas.

**Costo:**

- Real de esta evaluación: 0 USD.
- Con un modelo: pendiente. No llamé ningún modelo porque es un servicio pago fuera de este alcance. La columna "modelo" de `resultados.json` dice `evaluado: false`.

**Lo que esta evaluación no prueba:**

- Escribí los casos, las mutaciones y el validador yo misma. Las mutaciones semánticas usan las mismas marcas que el validador, así que el 23/23 de omisión es circular. Un modelo real puede equivocarse de formas que no anticipé: atribuir un hecho a la evidencia equivocada, describir mal el estado del incidente o decir algo correcto pero inútil.
- La utilidad la mido con frases exigidas, no con personas.
- Antes de habilitar un modelo hace falta correr estos 50 casos contra él, medir costo y latencia reales y revisar a mano una muestra de lo que el validador acepta.

## ML futuro (solo planteo; no entrené nada)

No entreno un modelo para decir que hay IA. Si lo hago, el plan es este:

- **Evento a predecir:** que el health factor de una cuenta cruce un umbral (por ejemplo 1,1) dentro de las próximas N horas, medido con snapshots `FRESH`. No uso la aceptación de una transacción como etiqueta de nada.
- **Etiquetas:** salen de snapshots posteriores al instante de predicción, nunca de incidentes abiertos con la política vigente, que dependen del umbral elegido.
- **Separación:** temporal (entreno en meses anteriores y evalúo en posteriores) y por cuenta (una cuenta no aparece en dos particiones), para no memorizar direcciones.
- **Leakage a evitar:**
  - features calculadas con bloques posteriores al instante de predicción;
  - precios del oráculo leídos después;
  - incidentes o resoluciones posteriores;
  - snapshots sintéticos de la demo (`is_synthetic`).
- **Baseline:** la regla actual (health factor bajo umbral) y una extrapolación lineal del health factor con los dos últimos snapshots. Un modelo solo vale si mejora a los dos.
- **Métricas:**
  - precisión y recall por evento (un cruce detectado una vez, no por snapshot);
  - anticipación media;
  - falsas alarmas por cuenta y por semana.
  - Las reporto por tamaño de posición y por activo.
- **Límites:**
  - pocos cruces reales, con clases muy desbalanceadas;
  - dependencia del oráculo y de la volatilidad de cada período;
  - cambios de parámetros de Aave;
  - el modelo no reemplaza la regla, solo podría adelantar un aviso con su probabilidad calibrada y evaluada.
