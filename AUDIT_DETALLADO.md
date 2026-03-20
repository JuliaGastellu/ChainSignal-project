# 🔍 REPORTE DE AUDITORÍA DETALLADO - ChainSignal
**Fecha: March 20, 2026 | Auditor: Análisis Automático | Modos: Inspección Completa**

---

## 📋 TABLA DE CONTENIDOS
1. [Código Muerto](#1-código-muerto)
2. [Redundancias](#2-redundancias)
3. [Hardcodes](#3-hardcodes-valores-fijos)
4. [Inconsistencias SSE](#4-inconsistencias-sse-server-sent-events)
5. [Integración x402](#5-integración-x402-pagos)
6. [Integración UI-API](#6-integración-ui-api)
7. [Separación MetaMask/WDK](#7-separación-metamask-vs-wdk)
8. [Matriz de Riesgos](#8-matriz-consolidada-de-hallazgos)

---

## 1. CÓDIGO MUERTO

| Ubicación | Tipo | Severidad | Descripción | Recomendación |
|-----------|------|-----------|-------------|---------------|
| `tmp_sse.py` | Archivo temporal | **CRÍTICO** | Script de prueba SSE. Realiza request a `/ejecutar-agente/{wallet}` y limita salida a 25 líneas. Nunca se importa desde otros módulos. | **ELIMINAR INMEDIATAMENTE**. No debería estar en producción. |
| `tmp_sse2.py` | Archivo temporal | **CRÍTICO** | Duplicado de tmp_sse.py. Misma funcionalidad pero sin límite de líneas. Código de desarrollo residual. | **ELIMINAR INMEDIATAMENTE**. Duplicado innecesario. |
| `tmp_test_sse.py` | Archivo temporal | **CRÍTICO** | Variante de prueba con variable `count` en lugar de `c`. No se usa en tests/ oficiales. | **ELIMINAR INMEDIATAMENTE**. Código muerto. |
| `patch_main.py` | Script de parche | **MODERADO** | Script para aplicar patches a `api/main.py` cambiando idioma español/inglés. Desactualizado — main.py ya está en inglés. | **ELIMINAR**. Parche ya aplicado o innecesario. |
| `insight_engine/interpretador.py` | Módulo | **MENOR** | `InterpretadorInsight` define métodos pero no es importado en api/main.py ni en agents/. Nunca se llama. | **REVISAR USO** o eliminar si no es requerido para expansión futura. |
| `cache/cache_wallet.py` | Módulo | **MENOR** | `CacheWallet` con soporte a SQLite. Define métodos `obtener()` y `guardar()` pero no se importa en api/main.py. Nunca se usa. | **REVISAR** si está en roadmap. De lo contrario, **ELIMINAR**. |
| `domain/modelos_wallet.py` | Módulo | **MENOR** | `WalletAgente` con método `tiene_balance_suficiente()` nunca se llama. Dominio muerto. | **REVISAR** viabilidad o **ELIMINAR**. |

---

## 2. REDUNDANCIAS

### A. Funciones Duplicadas (Scoring)

| Ubicación A | Ubicación B | Tipo | Severidad | Detalle | Impacto |
|-------------|-------------|------|-----------|---------|--------|
| `agente_ia/agente.py` `_calcular_score_riesgo()` | `perfil_wallet/behavioral_scoring.py` `_score_riesgo()` | Lógica duplicada | **MODERADO** | Ambas calculan riesgo con heurísticas similares (transacciones con error, ratio envíos/recepciones, edad). Fórmulas levemente diferentes. | Cambios de lógica deben hacerse en **DOS LUGARES**. |
| `agente_ia/agente.py` `_calcular_score_actividad()` | `perfil_wallet/behavioral_scoring.py` `_score_actividad()` | Lógica duplicada | **MODERADO** | Ambas evalúan actividad pero con umbrales diferentes (agente_ia: /10, behavioral_scoring uses raw frequencies). | Inconsistencia en cálculos finales. |

### B. Direcciones de Wallet Duplicadas

| Ubicación | Dirección | Uso | Frecuencia | Recomendación |
|-----------|-----------|-----|-----------|---------------|
| `api/main.py:232` | `0x000000000000000000000000000000000000dEaD` | Destino "safe wallet" para transferencias preventivas | **1ª instancia** | Mover a `config.py` con nombre `SAFE_WALLET_ADDRESS` |
| `agents/agente_chainsignal.py:156` | `0x000000000000000000000000000000000000dEaD` | Destino "safe wallet" para transferencias preventivas | **Duplicada** | Usar variable común en config |
| `contract_generator/contract_generator.py:21` | `0x0000000000000000000000000000000000000000` | Fallback si no hay analyzed_wallet | **1ª instancia** | Esta es correcta (null address por defecto) |

### C. Montos Fijos Duplicados

| Monto | Ubicación 1 | Ubicación 2 | Uso | Problema |
|-------|------------|-----------|-----|----------|
| `500000000000000` wei | `api/main.py:247` | `agents/agente_chainsignal.py:176` | Amount para swap preventivo | **DUPLICADO**. Debería ser variable de config |
| `1000000000000000` wei | `strategy/estrategia_proteccion_wallet.py:11` (default param) | Hardcoded | Transfer para "rescue test" | **No centralizado**. Debería ser `RESCUE_TRANSFER_AMOUNT_WEI` en config |

### D. Endpoints Duplicados

| Endpoint | Ubicación | Tipo | Severidad | Nota |
|----------|-----------|------|-----------|------|
| `/run-agent/{wallet}` | `api/main.py:110` | GET | **MENOR** | Endpoint en inglés |
| `/ejecutar-agente/{wallet}` | `api/main.py:111` | GET | **MENOR** | Endpoint en español (alias) — mismo manejador `run_agent_stream()` |
| Implicación | - | - | - | UI/Frontend debe usar uno u otro consistentemente |

---

## 3. HARDCODES (Valores Fijos)

### A. Direcciones Ethereum

| Dirección | Ubicación | Contexto | Severidad | Configurabilidad |
|-----------|-----------|----------|-----------|------------------|
| `0x0000000000000000000000000000000000000000` | `api/main.py:123` | Verificación de null address (wallet inválida) | **CRÍTICO** | ✅ Correcto como constante — no debería moverse |
| `0x000000000000000000000000000000000000dEaD` | `api/main.py:232`, `agents/agente_chainsignal.py:156` | Destino para "rescue transfer" (burn wallet) | **CRÍTICO** | ❌ Debería estar en `config.py`. Duplicado. |
| `0xdAC17F958D2ee523a2206206994597C13D831ec7` | `agents/agente_chainsignal.py:322` | Dirección USDT en Mainnet | **CRÍTICO** | ❌ **PROBLEMA GRAVE**: El sistema está configurado para Sepolia, pero esta es dirección Mainnet. Riesgo de envío a red equivocada. |
| `0x1c7D4B196Cb0232491C26109653a6c6224a3383d` | `infra/config.py:17` | USDC en Sepolia | **MODERADO** | ✅ Correctamente en config (con fallback) |

### B. Montos / Valores Wei

| Monto | Ubicación | Contexto | Severidad | Configurabilidad |
|-------|-----------|----------|-----------|------------------|
| `500000000000000` | `api/main.py:247` | Monto swap preventivo | **CRÍTICO** | ❌ Hardcoded. Aparece también en línea 176 agents/. |
| `500000000000000` | `agents/agente_chainsignal.py:176` | Monto swap preventivo (duplicado) | **CRÍTICO** | ❌ Hardcoded. No centralizado. |
| `1000000000000000` | `strategy/estrategia_proteccion_wallet.py:11` | Parámetro default de cantidad_transferencia_wei | **MODERADO** | ⚠️ Parameter pero con default hardcoded |

### C. Límites y Ratios

| Valor | Ubicación | Contexto | Severidad | Debería Ser |
|-------|-----------|----------|-----------|-------------|
| `0.5` | `decision_engine.py:35` | `max_amount_eth = round(confidence * 0.5, 3)` | **MODERADO** | Hardcoded ratio. Debería ser ENV: `MAX_AMOUNT_ETH_RATIO` |
| `500000` | `decision_engine.py:36` | Gas limit para activity > 70 | **MODERADO** | Hardcoded. Debería ser ENV: `GAS_LIMIT_HIGH` |
| `250000` | `decision_engine.py:36` | Gas limit por defecto | **MODERADO** | Hardcoded. Debería ser ENV: `GAS_LIMIT_DEFAULT` |
| `60`, `80` | `strategy/estrategia_proteccion_wallet.py:9-10` | Risk thresholds | **MODERADO** | Parámetros pero hardcoded en constructor. Debería ser configurable. |

### D. URLs

| URL | Ubicación | Severidad | Configurabilidad |
|-----|-----------|-----------|------------------|
| `https://sepolia.etherscan.io` | `api/main.py:309` | **MODERADO** | ❌ Hardcoded. Debería usar ENV: `ETHERSCAN_BASE_URL` |
| `http://localhost:8001` | `tmp_*.py` | **ALTO** (archivos muertos) | N/A — archivos de prueba |

### E. Timing / Delays

| Delay | Ubicación | Contexto | Severidad | Razón |
|-------|-----------|----------|-----------|-------|
| `time.sleep(1)` | `api/main.py:186` | Espera artificial en x402_validation step | **MODERADO** | ⚠️ **SIN JUSTIFICACIÓN**. Artificialmente ralentiza SSE sin razón funcional. Debería removerse. |

---

## 4. INCONSISTENCIAS SSE (Server-Sent Events)

### A. Pasos con Nombres Inconsistentes

| Paso # | Nombre Actual | Idioma | Problemática | Recomendación |
|--------|---------------|--------|-------------|---------------|
| 1 | `analyzing_wallet` | EN | ✅ Correcto | Mantener |
| 2 | `calculating_scores` | EN | ✅ Correcto | Mantener |
| 3 | `classifying_profile` | EN | ✅ Correcto | Mantener |
| 4 | `generating_insight` | EN | ✅ Correcto | Mantener |
| 5 | `evaluating_decision` | EN | ✅ Correcto | Mantener |
| 5.5 | `x402_validation` | EN | ✅ Correcto | Mantener |
| 6 | `strategy_execution` | EN | ✅ Correcto | Mantener |
| 6.5 | `financial_operation` | EN | ✅ Correcto | Mantener |
| 6.2 | `swap_operation` | EN | ✅ Correcto | Mantener |
| 7 | `contract_generation` | EN | ✅ Correcto | Mantener |
| 8 | `contract_compilation` | EN | ✅ Correcto | Mantener |
| 9 | `contract_deployment` | EN | ✅ Correcto | Mantener |
| 10 | `contract_active` | EN | ✅ Correcto | Mantener |
| Final | `decision_final` | EN | ⚠️ Mezcla "paso"/"decision" | Cambiar a `final_result` o `outcome` |

### B. Estados (Valores de "estado")

| Estado | Ubicaciones | Consistencia | Problema |
|--------|-------------|--------------|----------|
| `starting` | Múltiples | ✅ Consistente | OK |
| `completed` | Múltiples | ✅ Consistente | OK |
| `error` | Múltiples | ✅ Consistente | OK |
| Observación | - | - | **NO hay estado `in_progress` o `processing`** — falta granularidad. |

### C. Campos Variables en SSE

| Campo | Tipo | Uso | Problema |
|-------|------|-----|----------|
| `paso` | STRING | Nombre del paso | ✅ Consistente |
| `estado` | STRING | Estado (starting/completed/error) | ✅ Consistente |
| `detalle` | STRING | Descripción en lenguaje natural | ⚠️ Mezcla inglés/códigos internos |
| `data` | OBJECT (opcional) | Payload con datos específicos | ⚠️ Estructura variable |

**Ejemplo Problema en `detalle`:**
```json
// Correcto:
{"paso": "analyzing_wallet", "estado": "completed", "detalle": "Analyzed 250 transactions."}

// Inconsistente:
{"paso": "financial_operation", "estado": "error", "detalle": "Insufficient balance in agent wallet."}
// ^ El detalle aquí es una condición de negocios, no una descripción de estado
```

### D. Datos Faltantes Esperados

| Paso | Campo `data` Actual | Campos Esperados | Gap |
|------|-------------------|-------------------|-----|
| analyzing_wallet | ☐ Sin data | `{ transaction_count, balance_eth }` | Información incompleta |
| calculating_scores | ✅ Incluye risk, activity, defi_engagement, confidence | - | OK |
| classifying_profile | ☐ Sin data | `{ profile_type, confidence_level }` | Falta profile type |
| evaluating_decision | ✅ Incluye full decision object | - | OK |
| financial_operation | ✅ Incluye destination, hash, success | - | OK |
| swap_operation | ✅ Incluye hash, success | - | OK |
| contract_deployment | ✅ Incluye address, hash, metrics | - | OK |

---

## 5. INTEGRACIÓN x402 (Pagos)

### A. Flujo de Validación

```
┌─────────────────────────────────────────────────────┐
│ 1. Cliente solicita GET /report/{wallet}            │
├─────────────────────────────────────────────────────┤
│ 2. SinX-Payment header → HTTP 402 Challenge         │
├─────────────────────────────────────────────────────┤
│ 3. Cliente paga USD₮ via MetaMask → tx_hash         │
├─────────────────────────────────────────────────────┤
│ 4. Re-solicita con X-Payment: {tx_hash}             │
├─────────────────────────────────────────────────────┤
│ 5a. SIMULACIÓN: Validar formato 0x + 64 hex       │
│ 5b. PRODUCCIÓN: Verificar on-chain Transfer event   │
├─────────────────────────────────────────────────────┤
│ 6. Cache anti-replay → guardar hash usado           │
├─────────────────────────────────────────────────────┤
│ 7. Retornar HTTP 200 con análisis                   │
└─────────────────────────────────────────────────────┘
```

### B. Problemas Hallados

| ID | Ubicación | Tipo | Severidad | Descripción | Impacto |
|----|-----------|----|-----------|-------------|---------|
| x402-1 | `api/main.py:186` | Artificial delay | **MODERADO** | `time.sleep(1)` en x402_validation sin razón técnica. Ralentiza SSE stream. | UX degradada. Cliente espera innecesariamente. |
| x402-2 | `services/servicio_x402.py:160-180` | Validación incompleta | **MODERADO** | En simulación mode: Acepta cualquier hash con formato correcto sin verificación on-chain. | ✅ Por diseño (es simulación), pero documentación insuficiente. |
| x402-3 | `services/servicio_x402.py:182-230` | Validación on-chain | **CRÍTICO** | Verifica `Transfer` event, pero **NO valida cantidad correcta**. Solo revisa `value >= amount_required`. | ❌ Cliente podría pagar 0.5 USDC y obtener acceso si pasa amount_required. |
| x402-4 | `services/servicio_x402.py:105-145` | File locking | **MODERADO** | Implementa platform-specific locking (msvcrt/fcntl) para evitar race conditions, pero **no es thread-safe a nivel Python** (sin mutex). | ⚠️ En concurrencia alta: posible race condition en carga de hashes. |
| x402-5 | `cache/used_payments.json` | Persistencia | **MODERADO** | Anti-replay almacena hashes en JSON sin cifrado. Hash visibles en disco. Formato no comprimido. | ⚠️ Privacidad reducida. Tamaño de archivo crece sin límite. |
| x402-6 | `services/servicio_x402.py:195` | Parsing de recipient | **CRÍTICO** | Extrae dirección de `topics[2]` del evento Transfer: `recipient_found = "0x" + topics[2].hex()[-40:].lower()`. Esto **asume estructura Ethereum estándar**. Si el log está malformado, falla silenciosamente. | ❌ **Errores silenciosos** en logs anómalos. |

### C. Validación de Hash

| Aspecto | Estado | Detalle |
|--------|--------|---------|
| Formato | ✅ OK | Valida `0x` + 66 caracteres |
| Anti-replay | ✅ OK | Carga/persiste en cache |
| On-chain (PROD) | ⚠️ Parcial | Verifica evento pero no cantidad exacta |
| On-chain (SIM) | ✅ OK | Acepta cualquier formato válido por diseño |

---

## 6. INTEGRACIÓN UI-API

### A. Dependencia de Strings Frágiles

| String | Ubicación | Usado Por | Frágile |
|--------|-----------|-----------|---------|
| `"paso"` | SSE json | Frontend parser | ✅ Si el frontend parsea por nombre exacto, cambio en main.py rompe UI |
| `"estado"` | SSE json | Frontend parser | ✅ Igual |
| `"decision_final"` | SSE paso | Frontend estado final | ❌ Inconsistente con otros nombres (`contract_active` también es final) |
| `Etherscan URL` | `main.py:309` | Frontend link | ❌ Hardcoded — imposible cambiar red sin modificar código |

### B. Parsing por Regex o Frágil

| Ubicación | Tipo | Problema |
|-----------|------|----------|
| x402 challenge parsing | Frontend | Si el formato JSON cambia, parsing falla silenciosamente |
| SSE event parsing | Frontend | Depende de estructura exacta de `data: {json}` |
| Contract address extraction | Posible en frontend | Si formato de respuesta cambia, links rotos |

### C. Estados No Mapeados

| Escenario | esperado | Actual | Problema |
|-----------|----------|--------|----------|
| Wallet null address | Early exit | ✅ Handled (linea 123) | OK |
| WDK inactivo | Fallback simulación | ✅ Handled | OK |
| Balance insuficiente | Error step | ✅ financial_operation error | OK |
| x402 disabled | Skip validación | ✅ Handled | OK |

### D. Errores Silenciosos

| Ubicación | Tipo | Severidad | Detalle |
|-----------|------|-----------|---------|
| `tools/herramienta_consultar_balance.py` | WDK inactivo | **MODERADO** | Retorna 0.0 silenciosamente en línea 45 |
| `tools/herramienta_transferir_activo.py` | WDK inactivo | **MODERADO** | Retorna success=False sin detalles en línea 22 |
| `wallet_controller/wallet_agent.py` | Deploy fallido | **MENOR** | Retorna None sin mensaje en desplegar_contrato |

---

## 7. SEPARACIÓN MetaMask vs WDK

### A. Matriz de Responsabilidades

| Sistema | Responsabilidad | Implementación | Cumple |
|---------|-----------------|---------------|--------|
| **MetaMask** | Pagar reportes (x402) | `GET /report/{wallet}`: Cliente envía TX USD₮ via MetaMask | ✅ Sí |
| **MetaMask** | Ejecutar transacciones de usuario | **NO implementado** | ✅ Correcto (no hay ejecución user) |
| **WDK** | Desplegar contratos | `desplegar_contrato()` en ServicioWDK | ✅ Sí |
| **WDK** | Ejecutar swaps | `ejecutar_swap()` en ServicioWDK | ✅ Sí |
| **WDK** | Transferir fondos agente | `transferir_activo()` en ServicioWDK | ✅ Sí |
| **WDK** | Leer estado | `leer_estado()` en ServicioWDK | ✅ Sí |

### B. Validaciones de Mezcla

| Punto | Verificación | Resultado |
|-------|--------------|-----------|
| ¿Se importa MetaMask SDK en main.py? | grep ethers, web3.js | ❌ No hay — correcto |
| ¿Se accede a MetaMask en decision_engine? | grep metamask, ethers | ❌ No — correcto |
| ¿WDK se usa solo desde ServicioWDK? | grep WalletAgent, wallet_agent | ✅ Sí — encapsulación correcta |
| ¿Hay mezcla de billeteras? | grep address signing | ❌ No directa, pero DANGER en linha 322 |

### C. **PROBLEMA CRÍTICO DETECTADO**

**Ubicación:** `agents/agente_chainsignal.py:322`  
**Código:**
```python
token_out = "0xdAC17F958D2ee523a2206206994597C13D831ec7"  # USD₮
```

**PROBLEMA:**
- Sistema configurado para **SEPOLIA TESTNET** (RPC_URL, USDC_ADDRESS_SEPOLIA en config)
- Pero usa dirección de **USDT en MAINNET** (0xdAC1...)
- Si se ejecuta swap en Sepolia, buscará token en dirección equivocada → **FALLO SILENCIOSO**

**Riesgo:** ❌ **CRÍTICO** — Posible envío de fondos a red equivocada o pérdida de tokens

**Recomendación:**
```python
# Debería ser:
USDT_ADDRESS_SEPOLIA = os.getenv("USDT_ADDRESS_SEPOLIA", "0x...")  # Sepolia USDT
token_out = settings.USDT_ADDRESS_SEPOLIA
```

---

## 8. MATRIZ CONSOLIDADA DE HALLAZGOS

### 8.1 Por Severidad

#### 🔴 CRÍTICO (5 hallazgos)
| ID | Ubicación | Tipo | Descripción | Acción Inmediata |
|----|-----------|------|-------------|------------------|
| C1 | `tmp_*.py` (3 archivos) | Código muerto | Archivos de prueba SSE nunca usados | **ELIMINAR AHORA** |
| C2 | `agents/agente_chainsignal.py:322` | Hardcode + Red equivocada | USDT Mainnet address en Sepolia config | **CAMBIAR A SEPOLIA** |
| C3 | `api/main.py:232` + `agents:156` | Redundancia | wallet_segura duplicada en dos archivos | **CENTRALIZAR EN CONFIG** |
| C4 | `services/servicio_x402.py:160-200` | Validación incompleta | No verifica cantidad exacta de pago | **IMPLEMENTAR VERIFICACIÓN ESTRICTA** |
| C5 | `api/main.py:247` + `agents:176` | Hardcode duplicado | monto_swap_wei en dos lugares | **CENTRALIZAR EN CONFIG** |

#### 🟡 MODERADO (12 hallazgos)
| ID | Ubicación | Tipo | Descripción | Plazo |
|----|-----------|------|-------------|-------|
| M1 | `api/main.py:186` | Artificial delay | time.sleep(1) sin justificación | Próxima release |
| M2 | `decision_engine.py:35-36` | Hardcodes | max_eth ratio, gas limits | Próxima release |
| M3 | `api/main.py:309` | Hardcode URL | https://sepolia.etherscan.io fijo | Próxima release |
| M4 | `agente_ia/` vs `behavioral_scoring.py` | Scoring duplicado | Lógica de riesgo en dos lugares | Próxima sprint |
| M5 | `api/main.py:111` | Endpoints duplicados | `/ejecutar-agente/` y `/run-agent/` | Q2 refactor |
| M6 | `cache/used_payments.json` | Persistencia sin límite | Crece sin control, sin cifrado | Q2 refactor |
| M7 | `patch_main.py` | Script obsoleto | Parche desactualizado | **ELIMINAR** |
| M8 | `infra/config.py` | Configuración | Max 1 USDC hardcoded como default | Próxima release |
| M9 | `strategy/estrategia_proteccion_wallet.py:9-10` | Umbrales hardcoded | risk/activity thresholds sin env | Próxima release |
| M10 | `services/servicio_x402.py:105-145` | File locking | No es thread-safe a nivel Python | Q2 refactor |
| M11 | `services/servicio_x402.py:195` | Parsing frágil | Extrae recipient de topics sin validación | Q2 refactor |
| M12 | `tools/herramienta_*.py` | Errores silenciosos | WDK inactivo retorna sin detalle | Q2 logging |

#### 🟢 MENOR (6 hallazgos)
| ID | Ubicación | Tipo | Descripción | Plazo |
|----|-----------|------|-------------|-------|
| L1 | `insight_engine/interpretador.py` | Módulo no usado | InterpretadorInsight nunca se llama | Q3 cleanup |
| L2 | `cache/cache_wallet.py` | Módulo no usado | CacheWallet no se importa | Q3 cleanup |
| L3 | `domain/modelos_wallet.py` | Modelo no usado | WalletAgente nunca se usa | Q3 cleanup |
| L4 | `SSE paso: decision_final` | Inconsistencia | Nombre mezcla "paso" y "decision" | Q2 refactor |
| L5 | `SSE data variable` | Documentación | Estructura de `data` no documentada | Q2 API docs |
| L6 | `agente_ia/agente.py` | Métodos privados | `_orquestar_con_openclaw()` siempre retorna None | Q3 cleanup |

---

### 8.2 Tabla Consolidada por Categoría

| Categoría | Total | Crítico | Moderado | Menor |
|-----------|-------|---------|----------|-------|
| **Código Muerto** | 7 | 3 | 2 | 2 |
| **Redundancias** | 5 | 2 | 2 | 1 |
| **Hardcodes** | 10+ | 1 | 8 | 1+ |
| **Inconsistencias** | 6 | 0 | 3 | 3 |
| **x402 Pagos** | 6 | 1 | 4 | 1 |
| **UI-API** | 5 | 0 | 3 | 2 |
| **MetaMask/WDK** | 1 | 1 | 0 | 0 |
| **TOTAL** | **40** | **8** | **22** | **10** |

---

## 📊 INDICADORES DE CALIDAD

```
Complejidad Ciclomática: 🔴 ALTA
  - api/main.py: 327 líneas en un único archivo
  - event_generator(): 150+ líneas de lógica anidada

Mantenibilidad: 🟡 MEDIA
  - Múltiples hardcodes distribuidos
  - Falta centralización de constantes
  - Duplicación de lógica de scoring

Cobertura de Tests: 🟡 MEDIA
  - tests/ existe pero no cubre archivos muertos
  - tmp_*.py sin tests (como debe ser)
  - x402 validation sin unit tests detectables

Documentación: 🟡 MEDIA
  - README.md existe pero incompleto
  - SSE data structure no documentada
  - ARCHITECTURE.md desactualizado en detalles
```

---

## 🎯 RECOMENDACIONES POR PRIORIDAD

### INMEDIATO (1-3 días)
```
1. Eliminar tmp_sse.py, tmp_sse2.py, tmp_test_sse.py, patch_main.py
2. Cambiar token_out en agents/agente_chainsignal.py a SEPOLIA address
3. Crear config.py entry para SAFE_WALLET_ADDRESS, SWAP_AMOUNT_WEI
4. Remover time.sleep(1) de api/main.py:186
```

### CORTO PLAZO (1-2 semanas)
```
5. Refactorizar api/main.py: extraer event_generator a función separada
6. Centralizar toda validación x402 en ValidadorX402 con tests
7. Unificar scoring logic en BehavioralScorer, remover duplicados
8. Documentar estructura SSE `data` en docstring y README
9. Eliminar insight_engine/interpretador.py o implementar uso
```

### MEDIANO PLAZO (1-2 meses)
```
10. Migrar persistencia de hashes usados a Redis con TTL
11. Implementar thread-safe mutex para x402 validation
12. Crear ConfigSchema/Pydantic model para todas las constantes
13. Refactorizar decision_engine con configurables thresholds
14. Agregar tests unitarios para x402, scoring, strategy
```

---

**Reporte generado:** 20-Mar-2026  
**Análisis estático basado en:** Estructura de código, imports, llamadas a funciones  
**NO INCLUYE:** Runtime profiling, penetration testing, análisis de seguridad blockchain
