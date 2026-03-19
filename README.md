# ChainSignal: Agente Económico Autónomo de Inteligencia On-Chain

ChainSignal es un agente autónomo determinista que analiza el comportamiento on-chain, genera decisiones estructuradas y ejecuta estrategias de mitigación directamente en la cadena mediante una billetera autocustodial a través de Tether WDK.

Utiliza el **Tether Wallet Development Kit (WDK)** para interactuar con la red Ethereum (Sepolia), integrando capacidades avanzadas de Account Abstraction (ERC-4337), swaps estratégicos vía Velora y orquestación de smart contracts mediante LLMs.

## Arquitectura del Proyecto

El sistema opera bajo una arquitectura de microservicios coordinada por un núcleo de inteligencia en Python:

1.  **Ingesta y Análisis**: Extracción de features on-chain y clasificación conductual de carteras.
2.  **Motor de Decisión**: Evaluación de riesgos y determinación de acciones de protección.
3.  **Orquestación de Agente**: Generación de lógica en Solidity y gestión de ciclo de vida de contratos.
4.  **Capa de Ejecución (WDK)**: Interfaz con la blockchain mediante un servicio especializado en Node.js.

## Stack Tecnológico

-   **Backend**: Python 3.x (FastAPI, Web3.py, HTTPX, OpenClaw opcional).
-   **Blockchain Gateway**: Node.js (Tether WDK Protocol, Ethers.js).
-   **Infraestructura Web3**: 
    -   **Tether WDK**: Gestión de wallets y transacciones.
    -   **ERC-4337**: Soporte nativo para Account Abstraction (transacciones sin gas/bundlers).
    -   **Velora**: Protocolo de swap para mitigación en USD₮.
-   **Seguridad**: Verificación de firmas y límites de capital dinámicos por confianza.

## Configuración del Entorno

1.  **Dependencias Python**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Dependencias WDK**:
    ```bash
    cd wdk_service
    npm install
    ```
3.  **Variables de Entorno** (`.env`):
    -   `ETHERSCAN_API_KEY`: Acceso a datos históricos.
    -   `SEPOLIA_RPC_URL`: Conectividad con la red.
    -   `AGENT_SEED_PHRASE`: Llave maestra del agente.
    -   `WDK_BUNDLER_URL` / `WDK_PAYMASTER_URL`: Configuración para ERC-4337.

## Modos de Operación

-   **Modo Producción (Live)**: Requiere el microservicio WDK activo en el puerto 3001. El agente ejecuta transacciones reales.
-   **Modo Simulación**: Activado automáticamente ante la ausencia del servicio WDK, permitiendo pruebas de flujo sin consumo de gas real.

## Ejecución del Sistema

### Mediante Docker (Recomendado)
```bash
docker-compose up --build
```

### Ejecución Manual
```bash
# Iniciar servicio WDK
cd wdk_service && node server.js

# Iniciar API de Inteligencia
python -m uvicorn api.main:app --host 0.0.0.0 --port 8001
```

## Estructura de Documentación

-   [ARCHITECTURE.md](ARCHITECTURE.md): Detalle técnico del pipeline de datos y flujos de decisión.
-   [test_wdk_swap.py](tests/test_wdk_swap.py): Script de validación para la lógica de intercambio y conectividad WDK.
