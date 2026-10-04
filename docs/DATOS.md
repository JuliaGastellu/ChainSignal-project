# Mis datos confiables (E03)

Fecha: 4 de octubre de 2026.

Cada lectura on-chain de ChainSignal dice de dónde viene, a qué bloque corresponde, cuán actual es y si está completa. Una falla del proveedor nunca termina como cero o lista vacía, y no recomiendo ninguna acción con datos que no sean frescos y completos.

## Una sola red

`infra/red.py` centraliza `chain_id`, nombre y explorador. El producto lee Ethereum mainnet (`CHAIN_ID=1`). La configuración rechaza una testnet en `READ_ONLY`; Sepolia queda registrada solo para `experiments/`, que ahora también ingieren en Sepolia en lugar de analizar mainnet y ejecutar en testnet.

- Etherscan (API v2) y el RPC opcional (`ETHEREUM_RPC_URL`) verifican `eth_chainId` antes de la primera lectura. Si no coincide, el componente queda `UNAVAILABLE` con motivo `wrong_network` y no devuelvo ningún dato de esa red.
- `ServicioIngesta` no acepta proveedores de redes distintas entre sí.
- Una organización solo puede observar cuentas de la red del producto (422 para otro `chain_id`).
- `/analyze/block` usa el RPC de mainnet y responde 503 `wrong_network` si el RPC apunta a otra cadena.
- Retiré `ETHERSCAN_TX_BASE_URL` y `ETHERSCAN_ADDRESS_BASE_URL`, que apuntaban a Sepolia: los enlaces salen de la red.

No agregué multichain. Hice consistente la red inicial.

## Resultados tipados

`ingestion_onchain/resultados.py`:

| Calidad | Significado |
|---|---|
| `FRESH` | Leí la ventana pedida completa hace menos de `INGESTION_CACHE_TTL_SECONDS`. |
| `STALE` | El proveedor falló y devuelvo lo último guardado, con su antigüedad. |
| `PARTIAL` | Leí parte de la ventana (faltó una página) o faltó un componente, por ejemplo el balance. |
| `UNAVAILABLE` | No tengo datos utilizables. |

Cada componente (`transactions`, `tokens`, `balance`) lleva:
- un motivo: `timeout`, `rate_limited`, `invalid_response`, `pagination_incomplete`, `provider_error`, `wrong_network`, `not_configured`, `component_missing` o `archive_unavailable`;
- su procedencia: proveedor, `chain_id`, bloque de referencia con número, hash y timestamp, momento de la lectura, ventana `desde_bloque`/`hasta_bloque`, páginas leídas, si el historial está completo y si detecté un reorg.

Una cuenta sin actividad es `FRESH` con `no_activity: true`; un timeout o un 429 son `UNAVAILABLE`. Si falta el historial de transacciones, el conjunto es `UNAVAILABLE`; si falta otro componente, es `PARTIAL`.

## Ingesta incremental

`ingestion_onchain/ingesta.py` guarda en la base las transacciones y transferencias, con montos enteros como texto, más un checkpoint por cuenta y flujo (migración `0003`).

- **Primer sync:** recorro de lo más nuevo hacia atrás. Si llego al tope `INGESTION_MAX_PAGES`, la ventana reciente queda completa y declaro `complete_history: false` en lugar de inventar una edad. Descarto el bloque más bajo de la ventana porque pudo quedar a medias.
- **Syncs siguientes:** verifico el hash del bloque confirmado. Si cambió, hubo reorg: retrocedo `INGESTION_REORG_DEPTH` bloques y vuelvo a pedir. Borro las filas sin confirmar (`INGESTION_CONFIRMATIONS`) y avanzo desde el checkpoint.
- **Límite de Etherscan:** cuando una consulta llega a 10.000 filas, sigo desde el bloque límite y lo vuelvo a pedir completo, sin duplicar.
- **Reintentos:** acotados (`INGESTION_MAX_RETRIES`), con backoff exponencial y jitter completo, solo para timeout, 429, 5xx y límite de tasa informado en el cuerpo. Una respuesta inválida no se reintenta.
- **Caché:** la base hace de caché. Dentro del TTL no consulto al proveedor; con el proveedor caído y datos guardados devuelvo `STALE`.
- **Concurrencia:** dos procesos que sincronizan la misma cuenta no duplican filas. Uso un advisory lock de PostgreSQL y verifico que el checkpoint no haya cambiado mientras consultaba.
- **Balance:** con RPC, lo fijo al bloque de referencia (`eth_getBalance`). Sin RPC uso el `latest` de Etherscan y lo marco como no fijado a un bloque. Si falla queda `None`, nunca cero.

## Features honestas

| Antes | Ahora |
|---|---|
| `primera_transaccion_timestamp` y `dias_activo` sobre las últimas 200 transacciones | `primera_actividad_observada_timestamp` y `dias_observados` sobre la ventana ingerida, con `historial_completo` |
| "Wallet joven" si `dias_activo < 30` | Solo si `historial_completo` y `dias_observados < 30`. Observar un año de actividad sí prueba al menos un año de vida |
| Tokens por símbolo | Tokens por `(chain_id, contrato)` con decimales; el símbolo es una etiqueta |
| Diversidad `-Σ p·√p` | Entropía de Shannon normalizada: 0 con un token, 1 con uso parejo |
| Montos en float | Enteros y `Decimal` con 120 dígitos de precisión; convierto a float solo al presentar |
| "Reciente" contra el reloj local | Contra el timestamp del bloque de referencia |
| Balance desconocido como 0 | `None`; el clasificador ignora las reglas de balance |

## Decisiones y API

- **Sin datos (`UNAVAILABLE`):** `/report`, `/analyze/wallet` y el análisis por cuenta devuelven `DATA_UNAVAILABLE`, con `recommended_action: retry_later`, sin scores ni perfil. El stream termina igual, sin pasos de scoring ni estrategia.
- **Datos `STALE` o `PARTIAL`:** ninguna decisión accionable sobrevive. Bajo a `MONITOR` con `data_quality_gate`.
- **`data_quality`:** cada reporte y evento del stream lo incluye, con estado, motivo, `actionable_allowed`, `no_activity`, `complete_history` y la procedencia por componente.
- **Worker:** guarda `last_data_quality` en la cuenta observada. Una lectura `UNAVAILABLE` no pisa la última decisión ni el último riesgo.
- **Interfaz:** `DataQualityBadge` muestra la calidad en el panel de resultados. `DATA_UNAVAILABLE` se presenta como "Datos no disponibles", con el aviso de que no indica una cuenta sana.

## Cómo lo verifico

Todo sin red, con un proveedor simulado (`tests/proveedor_simulado.py`):

- `tests/test_ingesta.py` (27 pruebas):
  - red incorrecta en Etherscan y en el RPC, y proveedores de redes distintas;
  - 429 con backoff y jitter, 429 persistente y límite de tasa en el cuerpo;
  - timeout, respuestas inválidas sin reintento y la traducción de timeouts de `requests`;
  - cuenta sin actividad, página faltante, tope de páginas y ventana de 10.000 filas;
  - checkpoint incremental, caché dentro del TTL y caché vencido con proveedor caído;
  - reorg, filas no confirmadas, símbolos repetidos, valores extremos (2²⁵⁶−1, 0 y 77 decimales) y decimales fuera de rango;
  - balance fijado al bloque de referencia y balance no disponible.
- `tests/test_calidad_y_decision.py`: entropía, edad observada, balance desconocido, "reciente" contra la referencia, recomendaciones bloqueadas con datos no disponibles, viejos o parciales, el worker y el rechazo de cuentas de otra red.
- `tests/test_ingesta_postgres.py`: dos procesos sincronizan la misma cuenta contra PostgreSQL sin duplicar. Sin el control de concurrencia la prueba falla.
- Vitest (`src/lib/calidad.test.ts`): la interfaz nunca describe como sana una cuenta sin datos y distingue sin actividad, falla, datos viejos, parciales e historial truncado.

Las pruebas encontraron tres defectos que corregí en el código:
- aceptaba valores negativos;
- `no_activity` miraba el balance;
- el contexto por defecto de `Decimal` (28 dígitos) redondeaba montos de 78 dígitos.

## Lo que no hice en E03

- No validé contra Etherscan ni un RPC reales: no tengo credenciales en este entorno. La prueba de integración manual sigue en `tests/integration/`.
- `diversidad_protocolos` sigue siendo una heurística (contratos distintos sobre 10) y no la uso para decidir liquidez ni riesgo de liquidación. Las posiciones reales llegan con el adaptador de Aave (E04).
- Las filas ingeridas no tienen política de retención.
