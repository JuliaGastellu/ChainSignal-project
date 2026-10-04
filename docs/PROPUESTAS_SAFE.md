# Mis propuestas con firma humana (E10): spike, no etapa lista

Fecha: 4 de octubre de 2026.

## Por qué es un spike

E10 está condicionada a que el MVP pase sus puertas y a que haya demanda documentada. Hoy no se cumple ninguna de las dos:

- la puerta comercial está en 0 de 3 pilotos pagos y 0 de 2 renovaciones ([mi piloto](PILOTO.md));
- no hice entrevistas ni tengo pedidos registrados de esta función ([registro](piloto/REGISTRO_PILOTOS.md)).

Por eso entrego un spike revisable en `experiments/propuestas_safe/`, **fuera del runtime**:

- la API y el worker no lo importan (una prueba lo verifica en un proceso aparte);
- no hay rutas ni pantallas;
- el código no maneja claves, no firma y no envía transacciones ni propuestas reales.

Gasto autónomo, custodia compartida y módulos con gasto automático quedan fuera del alcance.

## Fuentes que verifiqué (2026-10-04)

| Qué | Fuente | Cómo lo comprobé |
|---|---|---|
| Safe 1.4.1 `0x41675C09…461a`, GnosisSafe 1.3.0 `0xd9Db270c…9552`, MultiSendCallOnly 1.4.1 `0x9641d764…02e2`, SafeProxyFactory 1.4.1 `0x4e1DCf7A…ec67` | `safe-global/safe-deployments` (JSON de cada versión) | `VERSION()` y código on-chain con un RPC público de lectura |
| API del Safe Transaction Service 6.11.0 | esquema OpenAPI del servicio | propuesta: `POST /api/v2/safes/{address}/multisig-transactions/` con `contractTransactionHash`, `sender` y `signature`; proposers: delegados en `/api/v2/delegates/`, autorizados con una firma EIP-712 de un owner |
| Pool de Aave V3, WETH, aWETH, USDC y su deuda variable en Ethereum | `bgd-labs/aave-address-book` (`AaveV3Ethereum.sol`) | mismas direcciones que uso desde E04; código on-chain |
| Hash EIP-712 de la SafeTx | contratos oficiales | `scripts/verificar_safe_onchain.py` compara mi hash con `getTransactionHash` (view) de los singletons 1.4.1 y 1.3.0 en 6 casos: coinciden todos (`docs/ensayos/safe-onchain.json`) |

## Diseño

**Acciones.** Uso una lista cerrada, siempre a nombre del propio Safe, que tiene que ser la cuenta monitoreada:

- aportar WETH como colateral;
- repagar deuda variable en USDC.

Los approvals son por el monto exacto, nunca infinitos. Los destinos permitidos son WETH, USDC y el Pool.

**Atomicidad.** Varias llamadas van en una sola SafeTx con delegatecall a MultiSendCallOnly, que no admite delegatecall internos: se ejecuta todo o nada. La marco `ATOMICO_MULTISEND`. No armo lotes secuenciales y no los llamaría atómicos. El estado `PARCIAL` existe solo para ellos.

**Vínculo de la aprobación.** La aprobación de una persona guarda una huella SHA-256 que cubre:

- organización, cadena, Safe y cuenta;
- versión de la política;
- acción y parámetros;
- nonce;
- SafeTx completa y safeTxHash;
- llamadas y efecto esperado;
- simulación exacta (bloque, hash, digest del estado previo, gas y fee);
- expiración (1 h).

Cambiar cualquiera de esos campos invalida la aprobación.

Antes de entregar valido además estas condiciones:

- misma red;
- mismo nonce del Safe;
- simulación de hace 25 bloques o menos;
- mismo digest de estado;
- sin vencer;
- safeTxHash recalculado igual al guardado.

**Antes de aprobar se muestra** (`guia.py`):

- pasos en lenguaje claro;
- fee estimada;
- approvals;
- cambios esperados simulados;
- riesgos;
- vencimiento;
- el safeTxHash que la persona tiene que ver en su wallet antes de firmar ("si no coincide, no firmes").

El cuerpo para el Transaction Service sale con `sender` y `signature` vacíos: los completa un owner o un proposer autorizado en su propia wallet.

**Estados** (`coordinador.py`):

| Estado | Significado |
|---|---|
| PROPUESTA | armada y simulada |
| APROBADA | aprobada para esa huella |
| INCIERTA | entrega empezada, resultado desconocido |
| ENVIADA | recibida, con su safeTxHash |
| CONFIRMADA | ejecutada, con el efecto esperado observado |
| FALLIDA | revertida, vencida, nonce usado por otra transacción o receipt exitoso sin el efecto |
| PARCIAL | solo para lotes secuenciales |

Las transiciones tienen una tabla y compare-and-set.

**Write-ahead y reconciliación:**

1. Persisto intención y payload, paso a INCIERTA y recién entonces entrego.
2. Ante un timeout queda INCIERTA y no reenvío.
3. Al reconciliar busco el safeTxHash en el servicio o en la cadena:
   - si aparece, sigo desde ahí (cubre el caso en que el proveedor transmite antes de devolver el hash);
   - si no aparece y el nonce del Safe avanzó, queda FALLIDA;
   - si no aparece y el nonce sigue libre, vuelve a APROBADA y recién ahí se puede entregar de nuevo.

## Pruebas

- **Mocks** (`tests/test_propuestas_safe.py`, 22 pruebas):
  - el hash coincide con los vectores del contrato;
  - el lote es atómico y el approval es exacto;
  - solo acciones y destinos permitidos, a nombre del Safe;
  - cambiar cualquier campo invalida la aprobación;
  - payload alterado sin recalcular el hash;
  - red, nonce, simulación vieja o con otro estado, y vencimiento;
  - una simulación fallida no se aprueba;
  - doble solicitud con la misma clave;
  - camino feliz con efecto;
  - receipt exitoso sin efecto;
  - ejecución revertida;
  - timeout sin entrega y prohibición de reenviar hasta reconciliar;
  - proveedor que transmite antes de devolver el hash, con una sola entrega;
  - nonce usado por otra transacción;
  - vencimiento al entregar;
  - transiciones inválidas;
  - guía y cuerpo sin firma;
  - el spike no usa APIs de firma ni entra al runtime.
  - Comprobé que la prueba de timeout falla si saco el bloqueo de reenvío y que la de simulación vieja falla si debilito el chequeo.
- **Fork aislado** (`scripts/ensayo_fork_safe.py`, anvil en Docker con un fork de mainnet; resultado en `docs/ensayos/safe-fork.json`):
  - despliego un Safe 1.4.1 con la ProxyFactory oficial;
  - simulo la SafeTx exacta con snapshot y revert;
  - el owner, una cuenta desbloqueada de anvil que hace de persona, ejecuta con la firma pre-aprobada de Safe;
  - reconcilio leyendo eventos y balances.

  | Escenario | Resultado |
  |---|---|
  | feliz | CONFIRMADA; aWETH +0,999999999999999998 por 1 WETH, fee simulada ≈ 0,000027 ETH |
  | receipt exitoso sin el efecto declarado | FALLIDA, "needs review" |
  | simulación vieja (30 bloques después) y payload alterado | rechazados antes de entregar |
  | otra transacción usa el nonce | FALLIDA |

**Un bug que encontró el fork.** En Safe 1.4.1, `ExecutionSuccess` indexa el `txHash`; en 1.3.0 va en `data`. Mi primera reconciliación solo miraba `data`, no encontraba la ejecución y marcaba una transacción exitosa como "nonce usado por otra transacción". Ahora acepto los dos formatos. Los mocks no lo habían detectado.

## Lo que falta para pensar en sacarlo del spike

1. Cumplir las puertas comerciales y documentar demanda real de propuestas con firma humana.
2. Un simulador para el producto. En el fork simulo ejecutando, pero en producción necesito un servicio de simulación o un nodo propio, con su costo.
3. Definir quién es el proposer. Proponer al Transaction Service requiere una firma de un owner o delegado; si ChainSignal fuera delegado tendría que custodiar esa clave. La alternativa sin clave es la guía manual que ya genera el spike.
4. Revisión independiente de seguridad del flujo, de la lista de acciones y de la reconciliación.
5. Persistir en la base del producto con migraciones, autorización por organización y rol, y auditoría.
6. Interfaz de aprobación con la información de la guía y pruebas de usabilidad con clientes.
7. Más acciones solo con evidencia de que se piden. Cada una con su efecto verificable.
