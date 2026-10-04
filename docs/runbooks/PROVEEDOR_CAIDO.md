# Proveedor RPC caído

**Síntomas:**

- en `/metrics`, crecen los errores de jobs `provider_error`, `timeout` o `rate_limited`;
- las cuentas pasan a UNAVAILABLE o STALE;
- baja `chainsignal_coverage_ratio`.

**Qué hace el sistema solo:**

- reintenta con backoff y, al agotar los intentos, evalúa con UNAVAILABLE;
- la regla de dato atrasado abre un incidente;
- un incidente de health factor abierto no se cierra por falta de datos;
- la API sigue lista.

Lo ensayé: la cuenta quedó UNAVAILABLE a los 71 s y volvió a FRESH 2 s después de que volvió el proveedor.

**Pasos:**

1. Confirmo que es el proveedor: pruebo el RPC desde fuera con `eth_blockNumber`. No pego la URL con su clave en ningún canal.
2. Si es un límite de tasa, bajo la carga: subo `interval_seconds` de las cuentas de prioridad baja o espero.
3. Si la caída es larga, cambio `ETHEREUM_RPC_URL` del worker y de la API por el proveedor alternativo y recreo esos servicios. La red tiene que ser Ethereum mainnet: la verificación de `chain_id` rechaza otra.
4. Aviso a las organizaciones con incidentes de dato atrasado que la causa es el proveedor, no sus cuentas.
5. Cuando vuelve, verifico que la cobertura regrese a 100 % y que los incidentes de dato atrasado se cierren solos con la primera lectura fresca.
