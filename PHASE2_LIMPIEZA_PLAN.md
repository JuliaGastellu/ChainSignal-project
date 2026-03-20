# FASE 2: PLAN DE LIMPIEZA Y REMEDIACIÓN
**Objetivo:** Consolidar todos los hallazgos en plan de acción ejecutable  
**Precedencia:** Fase 1 (COMPLETADA) → Fase 2 (ACTUAL)  
**Estado:** Plan APROBACIÓN

---

## OVERVIEW: ESTRATEGIA DE LIMPIEZA

El siguiente plan organiza los 37 hallazgos en **6 categorías de trabajo**, cada una con:
- Riesgo de implementación (bajo/medio/alto)
- Archivos afectados
- Estrategia de validación
- Orden de ejecución recomendado

```
┌─────────────── FASE 2: PLAN ─────────────────┐
│ ✓ Definir qué eliminar/refactorizar          │
│ ✓ Impacto assessment para cada cambio        │
│ → Validación strategy (sin API breakage)     │
│                                              │
│ RESULT: Documento de GO/NO-GO                │
└──────────────────────────────────────────────┘
```

---

## TRABAJO 1: ELIMINACIÓN DE CÓDIGO MUERTO
**Riesgo:** BAJO 🟢  
**Impacto:** Limpieza pura, sin cambios funcionales  
**Tiempo Estimado:** 5 minutos  

### 1.1 Archivos a Eliminar

| Archivo | Líneas | Justificación | Impacto |
|---------|--------|---------------|--------|
| tmp_sse.py | ~11 | Nunca importado, test local obsoleto | NINGUNO |
| tmp_sse2.py | ~20 | Nunca importado, duplicado | NINGUNO |
| tmp_test_sse.py | ~15 | Nunca importado, test obsoleto | NINGUNO |
| patch_main.py | ~40 | Script one-off, no es módulo | NINGUNO |

### Validación:
```bash
# 1. Verificar que NADA importa estos archivos
find . -name "*.py" -exec grep -l "import tmp_\|from tmp_\|import patch" {} \;
# Esperado: 0 resultados

# 2. Verificar en tests
grep -r "tmp_\|patch_main" tests/
# Esperado: 0 resultados

# 3. Verificar en requerimientos
grep -r "tmp\|patch" requirements.txt
# Esperado: 0 resultados
```

### Acción:
```powershell
Remove-Item tmp_sse.py
Remove-Item tmp_sse2.py
Remove-Item tmp_test_sse.py
Remove-Item patch_main.py
```

---

## TRABAJO 2: REMEDIACIÓN CRÍTICA - DIRECCIÓN USDT
**Riesgo:** MEDIO 🟠  
**Impacto:** FIX funcional bloqueante  
**Tiempo Estimado:** 15 minutos  

### 2.1 El Problema

Código actualmente usa USDT de **Mainnet** en **Sepolia Testnet**:

```python
# ❌ INCORRECTO (Mainnet)
token_out = "0xdAC17F958D2ee523a2206206994597C13D831ec7"  

# ✓ CORRECTO (Sepolia)
token_out = "0x1c7D4B196Cb0232491C26109653a6c6224a3383d"
```

### 2.2 Ubicaciones a Corregir

| Archivo | Línea | Contexto |
|---------|-------|---------|
| [agents/agente_chainsignal.py](agents/agente_chainsignal.py#L322) | 322 | Decisión de swap para estrategia |
| [strategy/estrategia_proteccion_wallet.py](strategy/estrategia_proteccion_wallet.py#L46) | 46 | Cálculo de token_out en protección |

### 2.3 Solución Recomendada

**OPCIÓN A: Centralizar en config.py (RECOMENDADO)**

```python
# infra/config.py - ADD:
@dataclass
class Settings:
    SEPOLIA_RPC_URL: str = os.getenv("SEPOLIA_RPC_URL", "")
    USDC_ADDRESS: str = os.getenv("USDC_ADDRESS_SEPOLIA", "0x1c7D4B196Cb0232491C26109653a6c6224a3383d")
    USDT_ADDRESS: str = os.getenv("USDT_ADDRESS_SEPOLIA", "0x1c7D4B196Cb0232491C26109653a6c6224a3383d")  # ← ADD
    # ... resto
```

**OPCIÓN B: Hardcode directo (RÁPIDO, no recomendado)**

Solo reemplazar en 2 ubicaciones

### 2.4 Validación

**Antes:**
```bash
# Testnet trata de usar 0xdAC17... → ABI lookup falla
curl -X GET "https://api-sepolia.etherscan.io/api?module=contract&action=getsourcecode&address=0xdAC17F958D2ee523a2206206994597C13D831ec7"
# Esperado: notAContract error
```

**Después:**
```bash
# Testnet encuentra contracto ✓
curl -X GET "https://api-sepolia.etherscan.io/api?module=contract&action=getsourcecode&address=0x1c7D4B196Cb0232491C26109653a6c6224a3383d"
# Esperado: Contract source code found
```

**Tests:**
```bash
# Executar tests de swap
pytest tests/test_wdk_swap.py -v

# Verificar decisión de estrategia
pytest tests/test_agente_chainsignal.py::test_agente_decide_estrategia -v
```

### 2.5 Riesgo de Cambio
- ✓ Sin cambios a API contracts
- ✓ Sin cambios a SSE structure
- ✓ Sin impacto a x402 validation
- ⚠ Requiere WDK disponible para validar swap
- ⚠ Requiere USDT Sepolia en wallet de testeo

---

## TRABAJO 3: CONSOLIDAR HARDCODES DE MONTOS
**Riesgo:** MEDIO 🟠  
**Impacto:** Mantenibilidad y consistencia  
**Tiempo Estimado:** 20 minutos  

### 3.1 El Problema

El monto `500000000000000` (0.0005 ETH) aparece en **3 ubicaciones independientes**:

```python
# agents/agente_chainsignal.py:176
monto_swap_wei = 500000000000000

# agents/agente_chainsignal.py:323
monto_wei = 500_000_000_000_000  # ← Mismo valor, formato distinto

# api/main.py:247
monto_swap_wei = 500000000000000
```

**Riego:** Si cambio uno, otros 2 quedan desincronizados

### 3.2 Solución: Centralizar en Config

```python
# infra/config.py - ADD:
@dataclass
class Settings:
    # ... existing fields
    SWAP_AMOUNT_WEI: int = int(os.getenv("SWAP_AMOUNT_WEI", "500000000000000"))
    
    @property
    def SWAP_AMOUNT_FORMATTED(self) -> str:
        """Para debugging: 0.0005 ETH"""
        return f"0.{str(self.SWAP_AMOUNT_WEI).zfill(18)[-4:]}"
```

### 3.3 Reemplazos

| Archivo | Línea | De | A |
|---------|-------|----|----|
| agents/agente_chainsignal.py | 176 | `monto_swap_wei = 500000000000000` | `monto_swap_wei = settings.SWAP_AMOUNT_WEI` |
| agents/agente_chainsignal.py | 323 | `monto_wei = 500_000_000_000_000` | `monto_wei = settings.SWAP_AMOUNT_WEI` |
| api/main.py | 247 | `monto_swap_wei = 500000000000000` | `monto_swap_wei = settings.SWAP_AMOUNT_WEI` |

### 3.4 Validación

```bash
# 1. Verificar que monto se lee correctamente
pytest tests/ -k "swap" -v

# 2. SSE debe mostrar monto correcto en detalle
# (Revisar logs: "Swap amount: 0.0005 ETH")

# 3. Verificar que no hay otros hardcodes de 500000000000000
grep -r "500000000000000\|500_000_000_000_000" **/*.py
# Esperado: 0 resultados en código (maybe solo en tests/fixtures)
```

---

## TRABAJO 4: REMOVER DEMORA ARTIFICIAL
**Riesgo:** BAJO 🟢  
**Impacto:** Performance improvement  
**Tiempo Estimado:** 5 minutos  

### 4.1 El Problema

```python
# api/main.py:185-186
async def event_generator() -> AsyncGenerator[str, None]:
    import time
    time.sleep(1)  # ❌ INNECESARIO
```

Demora propósito desconocido, ralentiza SSE en 1 segundo.

### 4.2 Solución

**Simplemente eliminar:**

```python
async def event_generator() -> AsyncGenerator[str, None]:
    # Removed: import time; time.sleep(1)
    
    # Proceder directo a lógica...
```

### 4.3 Validación

```bash
# 1. Medir tiempo de SSE stream
time curl http://localhost:8000/run-agent/0x_wallet_address

# Antes: ~1+ segundo (demora visible)
# Después: Inmediato (< 100ms)

# 2. Verificar que no hay otras demoras
grep -r "sleep\|wait\|delay" **/*.py
# Esperado: 0 resultados (excepto en tests si los hay)
```

---

## TRABAJO 5: NORMALIZAR ESTADO Y PASO SSE
**Riesgo:** ALTO 🔴  
**Impacto:** Máxima, afecta API contract  
**Tiempo Estimado:** 45 minutos + testing  

### 5.1 El Problema

Backend y frontend hablan idiomas diferentes:

```python
# Backend produce variaciones:
"estado": "iniciando"      # Spanish
"estado": "completado"     # Spanish
"estado": "processing"     # English
"estado": "error"          # English
"estado": "running"        # English

# Frontend espera múltiples:
const isActive = estado === "iniciando" || estado === "processing" || estado === "running"
```

### 5.2 Solución: Standardizar a ENGLISH

**Nuevo Estándar SSE:**

```json
{
  "paso": "analyzing_wallet",          // English, snake_case
  "estado": "in_progress",             // English, standardized
  "detalle": "Analyzing wallet activity...",
  "data": {}
}
```

**Estados Estandarizados:**
- `pending` - Iniciado pero sin procesar
- `in_progress` - Procesando
- `completed` - Finalizado exitosamente
- `error` - Error durante procesamiento

**Pasos Estandarizados (English, snake_case):**
1. `analyzing_wallet` - Análisis inicial
2. `calculating_scores` - Cálculo de scores
3. `classifying_profile` - Clasificación de perfil
4. `evaluating_risk` - Evaluación de riesgo
5. `generating_strategy` - Generación de estrategia
6. ` executing_strategy` - Ejecución
7. `operation_swap` - Swap en ejecución
8. `operation_transfer` - Transfer en ejecución
9. `finalizing_report` - Generación de reporte

### 5.3 Archivos a Refactorizar

| Archivo | Cambios |
|---------|---------|
| api/main.py | ~15 yield statements con paso/estado |
| agents/agente_chainsignal.py | ~8 yield statements |
| web_app/src/components/AgentTimeline.tsx | Mapear nuevos estados |
| web_app/src/hooks/useAgentSSE.ts | Actualizar parser |

### 5.4 Migration Strategy

**OPCIÓN A: Breaking Change (LARGO PLAZO)**
- Cambiar todo a nuevo estándar
- Cliente web actualizado simultáneamente
- Versión API baja a 2.0

**OPCIÓN B: Compatibility Layer (RECOMENDADO - FASE 2)**
- Backend produce ENGLISH (nuevo estándar)
- Backend TAMBIÉN emite Spanish (legacy) durante transición
- Frontend actualizado gradualmente
- Deprecate en Fase 3

**OPCIÓN B Implementation:**

```python
# utils/sse_normalize.py - NEW
def emit_event(paso: str, estado: str, detalle: str = "", data: dict = None):
    """Emit SSE event con soporte English y Spanish (legacy)"""
    
    # Mapeo English → Spanish (para legacy)
    spanish_map = {
        "analyzing_wallet": "analizando_wallet",
        "in_progress": "en_progreso",
        "completed": "completado",
        # ...
    }
    
    return {
        "paso": paso,  # English (nuevo)
        "paso_legacy": spanish_map.get(paso),  # Spanish (viejo)
        "estado": estado,  # English (nuevo)
        "estado_legacy": spanish_map.get(estado),  # Spanish (viejo)
        "detalle": detalle,
        "data": data or {}
    }
```

### 5.5 Validación

```bash
# 1. SSE event format
curl -N http://localhost:8000/run-agent/0xtest | head -20
# Verificar: paso, estado, detalle fields correctos

# 2. Frontend rendering
# Abrir web_app, ejecutar agent, verificar timeline rendering

# 3. Backward compatibility
# Enviar request antiguo, verificar que campos legacy existen

# 4. Tests
pytest tests/test_api_main.py::test_sse_events -v
```

### 5.6 Riesgo

- ⚠ API contract change (requiere coord con clientes)
- ⚠ Frontend puede mostrar duplicados temporalmente
- ✓ Sin impacto a x402 or payment flow
- ✓ Puede hacerse gradualmente

---

## TRABAJO 6: CENTRALIZAR CONFIGURACIÓN
**Riesgo:** MEDIO 🟠  
**Impacto:** Mantenibilidad y seguridad  
**Tiempo Estimado:** 30 minutos  

### 6.1 Valores Actualmente Dispersos

| Valore | Ubicación Actual | Debería Estar |
|--------|------------------|---------------|
| USDT address | agents/, strategy/ | infra/config.py |
| USDC address | codebase | ✓ config.py (parcial) |
| Monto swap | agents/, api/ | config.py ← TRABAJO 3 |
| Wallet segura | agents/:156 | config.py |
| Umbral riesgo | strategy/estrategia_proteccion_wallet.py | config.py |
| RPC URLs | Services/ | ✓ config.py (parcial) |

### 6.2 Actualizar infra/config.py

```python
@dataclass
class Settings:
    # Existing
    SEPOLIA_RPC_URL: str = os.getenv("SEPOLIA_RPC_URL", "")
    X402_PAYMENT_RECIPIENT: str = os.getenv("X402_PAYMENT_RECIPIENT", "0x...")
    
    # ADD for tokens
    USDC_ADDRESS_SEPOLIA: str = os.getenv(
        "USDC_ADDRESS_SEPOLIA", 
        "0x1c7D4B196Cb0232491C26109653a6c6224a3383d"
    )
    USDT_ADDRESS_SEPOLIA: str = os.getenv(
        "USDT_ADDRESS_SEPOLIA",
        "0x1c7D4B196Cb0232491C26109653a6c6224a3383d"
    )
    
    # ADD for operations
    SWAP_AMOUNT_WEI: int = int(os.getenv("SWAP_AMOUNT_WEI", "500000000000000"))
    PROTECTION_WALLET_ADDRESS: str = os.getenv(
        "PROTECTION_WALLET_ADDRESS",
        "0x000000000000000000000000000000000000dEaD"  # Quema, evaluar
    )
    
    # ADD for strategy
    RISK_THRESHOLD: int = int(os.getenv("RISK_THRESHOLD", "60"))
    HIGH_ACTIVITY_THRESHOLD: int = int(os.getenv("HIGH_ACTIVITY_THRESHOLD", "80"))
```

### 6.3 Actualizar .env

```
# .env (create if not exists)
SEPOLIA_RPC_URL=https://sepolia.infura.io/v3/YOUR_KEY
USDC_ADDRESS_SEPOLIA=0x1c7D4B196Cb0232491C26109653a6c6224a3383d
USDT_ADDRESS_SEPOLIA=0x1c7D4B196Cb0232491C26109653a6c6224a3383d
SWAP_AMOUNT_WEI=500000000000000
PROTECTION_WALLET_ADDRESS=0x000000000000000000000000000000000000dEaD
RISK_THRESHOLD=60
HIGH_ACTIVITY_THRESHOLD=80
```

### 6.4 Validación

```bash
# 1. Config carga correctamente
python -c "from infra.config import settings; print(settings.USDT_ADDRESS_SEPOLIA)"

# 2. Todas las ubicaciones heredan de config
grep -r "USDT_ADDRESS\|USDC_ADDRESS\|PROTECTION_WALLET" **/*.py
# Esperado: solamente references a settings.CONSTANT_NAME

# 3. .env variables se aplican
RISK_THRESHOLD=80 python -c "from infra.config import settings; print(settings.RISK_THRESHOLD)"
# Esperado: 80
```

---

## ORDEN DE EJECUCIÓN RECOMENDADO

```
┌─ FASE 2A: Limpieza Pura (LOW RISK) ────────┐
│ 1. Eliminar archivos temporales (TRABAJO 1) │
│ 2. Quitar time.sleep (TRABAJO 4)            │
└────────────────────────────────────────────┘
        ↓ (Validar después)
        ↓ 
┌─ FASE 2B: Config & Fix Crítico (MEDIUM) ───┐
│ 3. Centralizar config (TRABAJO 6)           │
│ 4. Fix USDT address (TRABAJO 2)             │
│ 5. Consolidar montos (TRABAJO 3)            │
└────────────────────────────────────────────┘
        ↓ (Validación exhaustiva)
        ↓
┌─ FASE 2C: Refactor API (HIGH RISK) ────────┐
│ 6. Normalizar SSE estados/pasos (TRABAJO 5) │
│    (Incluyendo updateos Frontend)           │
└────────────────────────────────────────────┘
        ↓ (Testing completo)
        ↓
┌─ VERIFICACIÓN FINAL ──────────────────────┐
│ ✓ Todos los tests pasan                    │
│ ✓ SSE stream funciona end-to-end          │
│ ✓ Payments siguen funcionando (x402)      │
│ ✓ No hay regressions                      │
└──────────────────────────────────────────┘
```

---

## MATRIZ DE DEPENDENCIAS

```
TRABAJO 1 (tmp files)
    ↓ (No dependencias)
    
TRABAJO 4 (time.sleep)
    ↓ (No dependencias)
    
TRABAJO 6 (Config)
    ← necesario para →
    
TRABAJO 2 (USDT fix)
TRABAJO 3 (Montos)
    ↓ (ambos completados)
    
TRABAJO 5 (SSE normalization)
    ← depende de → config centralizada
```

---

## CHECKLIST DE GO/NO-GO

### ✓ SignOff para FASE 2 Aprobada:

- [ ] Todos los hallazgos clasificados
- [ ] Riesgos entendidos por equipo
- [ ] Tests base-line ejecutados
  ```bash
  pytest tests/ -v --tb=short > tests_baseline.log
  ```
- [ ] Plan compartido con stakeholders
- [ ] Orden de ejecución confirmado
- [ ] Rollback strategy identified

### ✗ NO-GO Conditions:

- ❌ Si hay tests fallando ahora (deben pasar primero)
- ❌ Si no hay acceso a WDK testnet
- ❌ Si USDT_SEPOLIA no está configurado en RPC
- ❌ Si no hay ambiente de testeo disponible

---

**Este documento aprobado permite proceder a FASE 3: Eliminación + Refactor**

