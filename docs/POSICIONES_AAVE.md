# Mis posiciones Aave reales (E04)

Fecha: 4 de octubre de 2026.

ChainSignal lee posiciones de Aave V3 en Ethereum mainnet a un bloque explícito, las guarda como snapshots y puede reconciliarlas con la fuente a ese bloque. Es solo lectura: no firma ni envía nada, no entrena modelos y no deduce liquidez ni riesgo de liquidación a partir de contratos o transferencias.

## Fuentes

Consulté las fuentes oficiales el 4 de octubre de 2026; no usé direcciones de memoria.

| Qué | Fuente |
|---|---|
| Direcciones | `bgd-labs/aave-address-book`, `src/AaveV3Ethereum.sol` (biblioteca `AaveV3Ethereum`) |
| Firmas y salidas | `aave-dao/aave-v3-origin`: `IPool`, `IPoolAddressesProvider`, `IPoolDataProvider`, `AaveProtocolDataProvider`, `AaveOracle` |
| Escalas | `GenericLogic.calculateUserAccountData`: el health factor usa `wadDiv` (18 decimales) y vale `type(uint256).max` sin deuda; LTV y umbral son puntos básicos (10.000 = 100 %) |
| Unidad de la moneda base | No la supongo: leo `AaveOracle.BASE_CURRENCY_UNIT()` y `BASE_CURRENCY()` al mismo bloque |

Solo fijo el `PoolAddressesProvider` (`0x2f39d218133AFaB8F2B819B1066c7E434Ad94E9e`). Pool, oráculo y data provider los resuelvo on-chain al bloque leído y los comparo con el address book; si difieren, lo anoto en `limitations` y uso lo que dice la cadena.

## Diseño

- **`protocolos/modelos.py`:** define `ProtocoloLectura`, la interfaz que cumple cada adaptador, y `LectorContratos`, cualquier objeto que haga `eth_call`, lea bloques y conozca su red. El adaptador no sabe qué proveedor hay detrás: un RPC real, un grabador o un reproductor.
- **`protocolos/aave_v3.py`:** todas las llamadas usan el mismo bloque, que por defecto es la cabeza menos `INGESTION_CONFIRMATIONS`:
  1. Resuelve las direcciones con el `PoolAddressesProvider`.
  2. Lee `getUserAccountData` y `getUserEMode` del Pool.
  3. Lee `BASE_CURRENCY_UNIT` y `BASE_CURRENCY` del oráculo.
  4. Lista las reservas con `getAllReservesTokens` y lee `getUserReserveData` de cada una.
  5. Para los activos con saldo o deuda, lee `getReserveConfigurationData`, `getAssetsPrices` y `getSourceOfAsset`.
  6. Al final vuelve a leer el bloque y verifica que su hash no cambió.
- **Dinero:** guardo cada valor como el entero que devuelve el contrato y convierto con `Decimal` (120 dígitos) solo al presentar. Cada respuesta incluye un bloque `raw` con los enteros originales.
- **Reconciliación:** comparo `totalCollateralBase` y `totalDebtBase` con la suma por activo, usando la misma aritmética entera del Pool (`unidades × precio / 10^decimales`). Solo cuento como colateral los activos marcados por la cuenta y con umbral distinto de cero. La tolerancia por activo es `ceil(precio / 10^decimales) + 1` unidades base: el Pool y el data provider pueden redondear distinto en una unidad del activo.
- **Verificación independiente** (`protocolos/replay.py`): comparo cada saldo con `balanceOf` del aToken y de los tokens de deuda de la reserva, al mismo bloque. Son contratos distintos que tienen que coincidir.

## Casos explícitos

| Caso | Tratamiento |
|---|---|
| Deuda cero | `status: COLLATERAL_ONLY`, `health_factor: null`, `no_debt: true` y una limitación que explica que el Pool devuelve el uint256 máximo |
| Sin posición | `status: NO_POSITION`, sin activos |
| E-mode activo | `emode_category` y una limitación: LTV y umbral de la cuenta incluyen E-mode; los de cada activo son los de la reserva |
| Reserva ilegible | `PARTIAL` con `component_missing`, la lista `unread_reserves` y la reconciliación marcada como incompleta |
| Totales que no concilian | `PARTIAL` con `reconciliation_mismatch` |
| Reorg durante la lectura | `PARTIAL` con `reorg_during_read` |
| Nodo sin archive | `UNAVAILABLE` con `archive_unavailable`, incluido el caso de un HTTP 403 con error JSON-RPC |
| RPC no configurado o de otra red | `UNAVAILABLE` (`not_configured` o `wrong_network`), sin valores |
| Respuesta vacía (`0x`) | Error, nunca cero |

Nunca guardo una lectura `UNAVAILABLE` ni una sin bloque.

## Persistencia (migración `0004`)

- **`position_snapshots`:** una fila por red, protocolo, mercado, usuario y bloque. Guarda los totales enteros como texto, el health factor en WAD, la unidad y la moneda base, la categoría E-mode, los contratos resueltos, la reconciliación, las limitaciones, la calidad y `schema_version` (`position-snapshot/1`).
- **`position_snapshot_assets`:** una fila por activo, con saldos, deudas, uso como colateral, precio, fuente del oráculo, LTV y umbral.

Un snapshot de un bloque ya guardado se sirve desde la base sin volver a leer. La prueba compara campo por campo el snapshot reconstruido con el original.

## API

| Ruta | Rol |
|---|---|
| `GET /orgs/{org}/accounts/{id}/positions/aave-v3?block=N` | viewer: lee o reutiliza el snapshot al bloque N (por defecto, cabeza − 12) |
| `GET /orgs/{org}/accounts/{id}/positions/aave-v3/snapshots` | viewer: historial de snapshots de la cuenta |

Aplican las mismas reglas de organización de E02: 403 fuera de la organización y 404 si la cuenta no le pertenece. Los valores llegan como texto decimal en la moneda base y con su `raw`; `health_factor` es `null` sin deuda.

## Replay y evidencia

- **Lectura pública real.** `tests/datos/aave_v3_prestatario_usdc_26116392.json` es una lectura de mainnet al bloque 26.116.392, grabada con `scripts/grabar_fixture_aave.py` desde un RPC público de solo lectura, sin claves. La cuenta es una dirección pública que pidió USDC prestado (la elegí de los logs del token de deuda oficial). A ese bloque:
  - el colateral reportado (5.813.896.368.411) coincide exacto con la suma por activo;
  - la deuda (3.937.856.381.718) difiere en 1 unidad base, dentro de la tolerancia de 103;
  - el health factor es 1,225421528368654169;
  - `balanceOf` coincide con el data provider en los dos activos.

  La prueba reproduce todo sin red y exige que cada llamada use ese bloque.
- **Escenarios sintéticos.** `tests/fixture_aave.py` codifica con el ABI real deuda cero, sin posición, E-mode, totales alterados, reservas ilegibles, reorg, address book distinto, otra red y valores extremos (10⁷⁰ unidades base).
- **Integración opt-in.** `tests/integration/test_aave_v3_rpc.py` lee una posición en vivo y la verifica. La corrí una vez contra el RPC público: pasó, a un bloque más reciente.

El nodo público no sirve estado histórico sin un token: pedir el bloque 26.116.300 devolvió "Archive requests require a personal token". Por eso grabé a la cabeza menos 12 confirmaciones, y el adaptador ahora informa ese caso como `archive_unavailable` en lugar de un error genérico.

## Lo que no hice en E04

- No tengo acceso archive: no puedo reconstruir posiciones antiguas. Con un nodo archive, el mismo código lee cualquier bloque.
- Leo cada reserva con una llamada (unas 60 en el mercado principal), sin Multicall. Es suficiente para el piloto, pero es lento.
- Con E-mode activo no leo la configuración de la categoría: queda como limitación visible.
- La interfaz todavía no muestra posiciones; el rediseño comercial es E06. El monitoreo periódico de posiciones e incidentes es E05.
