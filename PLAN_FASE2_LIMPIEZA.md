# FASE 2: PLAN DE LIMPIEZA SEGURA
**Estado:** Plan de remediación estructurado  
**Basado en:** FASE 1 completada (18 hallazgos clasificados)  
**Metodología:** 6 bloques de trabajo con orden, riesgos y validación  
**RESTRICCIÓN:** SIN CAMBIOS TODAVÍA - Solo planificación

---

## RESUMEN: QÚANTO LIMPIAR Y EN QUÉ ORDEN

```
┌─ BLOQUE 1: Eliminación pura (10 min) ────────────────────┐
│ Risk: BAJO - Solo archivos que nunca se usan               │
│ - tmp_sse.py, tmp_sse2.py, tmp_test_sse.py (3 archivos)   │
│ - patch_main.py (1 archivo)                                │
│ - cache/cache_wallet.py (1 archivo + carpeta vacía)       │
│ - insight_engine/interpretador.py (1 archivo)              │
└─────────────────────────────────────────────────────────────┘
                    ↓ (Validar: tests pasan)
                    ↓
┌─ BLOQUE 2: Fix CRÍTICO (15 min) ───────────────────────┐
│ Risk: MEDIO - Cambio de configuración, requiere testing    │
│ - USDT Mainnet → Sepolia en 2 ubicaciones                 │
│ - time.sleep(1) remover                                    │
│ - Validación: WDK disponible                               │
└────────────────────────────────────────────────────────────┘
                    ↓ (Validar: SSE funciona)
                    ↓
┌─ BLOQUE 3: Centralización de configuración (30 min) ────┐
│ Risk: MEDIO - Refactoring de hardcodes                    │
│ - Monto swap: 3 ubicaciones → config.py (1)              │
│ - Wallet segura: 2 ubicaciones → config.py (1)           │
│ - USDT address: centralizar                              │
└──────────────────────────────────────────────────────────┘
                    ↓ (Validar: valores iguales)
                    ↓
┌─ BLOQUE 4: Consolidación de código duplicado (20 min) ──┐
│ Risk: BAJO - score_riesgo está en módulo muerto           │
│ - Eliminar score_riesgo de agente_ia/agente.py          │
│ - Verificar que behavioral_scoring es la fuente única    │
└───────────────────────────────────────────────────────────┘

TOTAL: ~75 minutos (con testing)
```

---

## BLOQUE 1: ELIMINACIÓN SEGURA (Archivos + Código Muerto)

### 1.1 Archivos a Eliminar

**Archivos:**
```
❌ tmp_sse.py
❌ tmp_sse2.py
❌ tmp_test_sse.py
❌ patch_main.py
❌ cache/ (directorio + archivo)
❌ insight_engine/interpretador.py (pero mantener __init__.py)
```

**Verificación PRE-ELIMINACIÓN:**

```bash
# Confirmar que NADA importa estos archivos
grep -r "import tmp_sse\|from tmp_sse\|import patch_main\|from patch_main" **/*.py
# Esperado: 0 resultados

grep -r "import cache\|from cache\|CacheWallet\|wallet_cache" **/*.py
# Esperado: 2 (solo definición en cache/cache_wallet.py)

grep -r "import insight_engine.interpretador\|from insight_engine\|InterpretadorInsight" **/*.py  
# Esperado: 1 (solo definición)

# Confirmar en git
git status
# Verificar que ninguno está staged o modificado
```

**Eliminación en orden:**

```powershell
# 1. Archivos raíz (tmp_*.py, patch_main.py)
Remove-Item -Path "tmp_sse.py"
Remove-Item -Path "tmp_sse2.py"
Remove-Item -Path "tmp_test_sse.py"
Remove-Item -Path "patch_main.py"

# 2. Directorio cache (si es enteramente código muerto)
# VERIFICAR PRIMERO: ¿hay otros archivos?
if ($(ls cache/ | wc -l) -eq 1) {
    Remove-Item -Recurse -Path "cache/"
}

# 3. Módulo insight_engine/interpretador.py (mantener carpeta)
Remove-Item -Path "insight_engine/interpretador.py"
```

**Validación POST-ELIMINACIÓN:**

```bash
# 1. Confirmar archivos no existen
ls tmp_sse.py 2>&1 | grep -i "not found"  # OK si falla
ls patch_main.py 2>&1 | grep -i "not found"  # OK si falla

# 2. Confirmar imports aún OK
python -c "from api.main import app; print('✓ api/main imports OK')"

# 3. Tests no rotos
pytest tests/ -x --tb=short

# 4. Confirmar no hay referencias
grep -r "tmp_sse\|patch_main\|CacheWallet" --include="*.py" .
# Esperado: 0 resultados (excepto en git history)
```

**Riesgo:** CERO (archivos no usados)  
**ROI:** Muy alto (limpieza inmediata y visible)

---

## BLOQUE 2: FIX CRÍTICO (USDT + time.sleep)

### 2.1 Problema: USDT Mainnet en Sepolia

**Ubicaciones a FIX:**
1. `agents/agente_chainsignal.py` línea 322
2. `strategy/estrategia_proteccion_wallet.py` línea 46

**Incorrecto (MAINNET):**
```python
token_out = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
```

**Correcto (SEPOLIA):**
```python
# OPCIÓN A: Hardcode Sepolia USDT
token_out = "0x1c7D4B196Cb0232491C26109653a6c6224a3383d"

# OPCIÓN B: Centralizar en config (RECOMENDADO)
token_out = settings.USDT_ADDRESS_SEPOLIA
```

### 2.2 Estrategia: Uso de Config Settings

**Modificación 1:** `infra/config.py` (ADD)
```python
@dataclass
class Settings(BaseSettings):
    # ... existing fields
    
    # ADD NEW
    USDT_ADDRESS_SEPOLIA: str = os.getenv(
        "USDT_ADDRESS_SEPOLIA",
        "0x1c7D4B196Cb0232491C26109653a6c6224a3383d"  # No usar Mainnet
    )
```

**Modificación 2:** `agents/agente_chainsignal.py` línea 322 (CHANGE)
```python
# Antes:
token_out = "0xdAC17F958D2ee523a2206206994597C13D831ec7"

# Después:
from infra.config import settings
token_out = settings.USDT_ADDRESS_SEPOLIA
```

**Modificación 3:** `strategy/estrategia_proteccion_wallet.py` línea 46 (CHANGE)
```python
# Antes:
token_out = "0xdAC17F958D2ee523a2206206994597C13D831ec7"

# Después:
from infra.config import settings
token_out = settings.USDT_ADDRESS_SEPOLIA
```

### 2.3 Problema: time.sleep Artificial

**Ubicación:** `api/main.py` línea 185-186

**Incorrecto:**
```python
import time
time.sleep(1)  # Sin propósito documentado
```

**Corrección:**
```python
# ELIMINAR completamente las 2 líneas
```

**Validación:**
```bash
# Verificar que no hay otros time.sleep en codebase
grep -r "time.sleep\|sleep(" **/*.py
# Esperado: 0 resultados (después de eliminación)
```

### 2.4 Validación del BLOQUE 2

**Paso 1: Tests unitarios**
```bash
pytest tests/test_agente_chainsignal.py -v -k "swap"
pytest tests/test_wdk_swap.py -v
```

**Paso 2: SSE stream funciona**
```bash
# Ejecutar en 2 terminales:
# Terminal 1:
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2:
curl -N http://localhost:8000/run-agent/0x123 | head -20
# Verificar: sin delay artificial, SSE fluido
```

**Paso 3: Verificar direcciones**
```python
from infra.config import settings
print(settings.USDT_ADDRESS_SEPOLIA)
# Esperar: 0x1c7D4B196Cb0232491C26109653a6c6224a3383d
```

**Riesgo:** MEDIO (cambio de dirección requiere WDK testnet)
**Blockers:** ¿WDK tiene USDT Sepolia disponible?

---

## BLOQUE 3: CENTRALIZACIÓN DE CONFIGURACIÓN

### 3.1 Monto Swap - 3 Ubicaciones → 1 Config

**Problema:** Valor `500000000000000` esparcido

**Ubicaciones:**
- `api/main.py:247` 
- `agents/agente_chainsignal.py:176`
- `agents/agente_chainsignal.py:323`

**Solución:**

**Paso 1:** Actualizar `infra/config.py`
```python
@dataclass
class Settings(BaseSettings):
    # ADD:
    SWAP_AMOUNT_WEI: int = int(os.getenv(
        "SWAP_AMOUNT_WEI",
        "500000000000000"  # 0.0005 ETH
    ))
```

**Paso 2:** Reemplazar en `api/main.py:247`
```python
# Antes:
monto_swap_wei = 500000000000000

# Después:
monto_swap_wei = settings.SWAP_AMOUNT_WEI
```

**Paso 3:** Reemplazar en `agents/agente_chainsignal.py` (2x)
```python
# Antes (línea 176):
monto_swap_wei = 500000000000000

# Después:
monto_swap_wei = settings.SWAP_AMOUNT_WEI

# Antes (línea 323):
monto_wei = 500_000_000_000_000

# Después:
monto_wei = settings.SWAP_AMOUNT_WEI
```

### 3.2 Wallet Segura - 2 Ubicaciones → 1 Config

**Problema:** Burn address `0x000...dEaD` en 2 lugares

**Ubicaciones:**
- `api/main.py:232`
- `agents/agente_chainsignal.py:156`

**Solución:**

**Paso 1:** Actualizar `infra/config.py`
```python
@dataclass
class Settings(BaseSettings):
    # ADD:
    SAFE_WALLET_ADDRESS: str = os.getenv(
        "SAFE_WALLET_ADDRESS",
        "0x000000000000000000000000000000000000dEaD"
    )
```

**Paso 2:** Reemplazar en `api/main.py:232`
```python
# Antes:
wallet_segura = "0x000000000000000000000000000000000000dEaD"

# Después:
wallet_segura = settings.SAFE_WALLET_ADDRESS
```

**Paso 3:** Reemplazar en `agents/agente_chainsignal.py:156`
```python
# Antes:
wallet_segura = "0x000000000000000000000000000000000000dEaD"

# Después:
wallet_segura = settings.SAFE_WALLET_ADDRESS
```

### 3.3 Validación del BLOQUE 3

```bash
# 1. Confirmar config carga
python -c "from infra.config import settings; \
  print(f'SWAP_AMOUNT: {settings.SWAP_AMOUNT_WEI}'); \
  print(f'SAFE_WALLET: {settings.SAFE_WALLET_ADDRESS}')"

# 2. Verificar que 500000000000000 SOLO está en tests/fixtures (OK)
grep -r "500000000000000" --include="*.py" . | grep -v "test"
# Esperado: 0 resultados en código productivo

# 3. Verificar que burn address SOLO está en config.py
grep -r "0x000.*dEaD" --include="*.py" . | grep -v config.py
# Esperado: 0 resultados

# 4. Tests
pytest tests/ -v
```

**Riesgo:** BAJO (cambio simple, valores idénticos)
**ROI:** Alto (centralización, mantenimiento futuro)

---

## BLOQUE 4: CONSOLIDACIÓN DE DUPLICACIÓN

### 4.1 Score Riesgo Duplicado

**Problema:** Misma función en 2 módulos
- `agente_ia/agente.py` línea 55-73 (MUERTA)
- `perfil_wallet/behavioral_scoring.py` (ACTIVA)

**Decisión:** Eliminar de `agente_ia/` (nunca se usa)

**Verificación:**
```bash
# 1. Confirmar que agente_ia no se importa
grep -r "import agente_ia\|from agente_ia" --include="*.py" .
# Esperado: 0 (excepto api/main.py que importa AgenteAnalisis, no funciones internas)

# 2. Confirmar que agente_ia/agente.py es muerto
grep -r "AgenteAnalisis\|agente_ia.agente" --include="*.py" tests/
# Esperado: comportamiento para entender si se usa
```

**Acción:** Eliminar `agente_ia/agente.py` líneas 55-73 (método completo)

**Riesgo:** CERO (módulo muerto)

---

## ORDEN RECOMENDADO DE EJECUCIÓN

```
FASE 2A: SEGURIDAD CRÍTICA (30 min)
├─ FIX: USDT Mainnet → Sepolia (+validación WDK)
├─ FIX: time.sleep(1) remover
└─ TEST: SSE stream funciona sin demora

FASE 2B: LIMPIEZA Y CENTRALIZACIÓN (60 min)
├─ ELIMINAR: tmp_*.py (3 archivos)
├─ ELIMINAR: patch_main.py
├─ ELIMINAR: cache/ (si totalmente muerto)
├─ ELIMINAR: insight_engine/interpretador.py
├─ CENTRALIZAR: monto swap (3→1)
├─ CENTRALIZAR: wallet segura (2→1)
├─ CONSOLIDAR: score riesgo (eliminar de agente_ia)
└─ TEST: tests verdes, imports OK

TOTAL: ~90 minutos (con testing)
```

---

## MATRIZ DE DEPENDENCIAS

```
BLOQUE 1 (Eliminar)
    ↓ (independiente, se puede hacer primero)
    
BLOQUE 2 (Fix USDT + time.sleep)
    ↓ (necesita BLOQUE 3 código limpio)
    
BLOQUE 3 (Centralizar config)
    ├─ Depende de: BLOQUE 2 (para no duplicar USDT)
    └─ Independiente: BLOQUE 1
    
BLOQUE 4 (Consolidar duplicación)
    └─ Depende de: BLOQUE 1 (agente_ia es muerto después)
```

**Orden seguro:** 1 → 3 → 2 → 4 (o 1 → 2 → 3 → 4)

---

## RIESGOS Y MITIGACIÓN

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|--------|-----------|
| WDK no tiene USDT Sepolia | MEDIA | ALTO | ✓ Verificar antes de cambiar |
| Config carga incorrectamente | BAJA | MEDIO | ✓ Test de config |
| Tests fallan | BAJA | BAJO | ✓ Run pytest completo |
| Datos en BD referencia direcciones | MUY BAJA | BAJO | ✓ Datos de prueba son frescos |
| Regresión SSE | MUY BAJA | MEDIO | ✓ E2E test del stream |

---

## VALIDACIÓN EXHAUSTIVA

### Pre-Limpieza:
- [ ] git stash (guardar cambios actuales)
- [ ] git checkout main (rama limpia)
- [ ] pytest tests/ --tb=short (baseline)
- [ ] grep para verificar referencias

### Post-Paso:
- [ ] pytest tests/ -x (no romper)
- [ ] Verificar imports
- [ ] grep "hardcode_eliminado"  → 0 resultados

### Post-Todos-los-Bloques:
- [ ] pytest tests/ -v (coverage)
- [ ] mypy api/ agents/ services/ (tipos OK)
- [ ] SSE stream test manual
- [ ] API health check

---

## ROLLBACK STRATEGY

Si algo falla:

```bash
# 1. Revert último commit
git reset --hard HEAD~1

# 2. Re-run tests
pytest tests/

# 3. Investigar qué salió mal
git diff HEAD~1 HEAD

# 4. Commit con fix
git add .
git commit -m "Fix: [problema]"
```

**Archivos críticos para backup:**
- `infra/config.py` (cambios necesarios)
- `api/main.py` (multiple changes)
- `agents/agente_chainsignal.py` (multiple changes)
- `strategy/estrategia_proteccion_wallet.py` (1 change)

---

## CHECKLIST GO/NO-GO

Antes de proceder a **FASE 3 (EJECUCIÓN):**

- [ ] **Hallazgos validados** - ¿FASE 1 está correcta?
- [ ] **Plan revisado** - ¿Team entiende el orden?
- [ ] **Ambiente listo** - ¿Testing setup funciona?
- [ ] **WDK disponible** - ¿Para validar swaps?
- [ ] **Config testing** - ¿Se puede cambiar USDT sin romper?
- [ ] **Backup de refs** - ¿Documentadas todas las ubicaciones?
- [ ] **Rollback ready** - ¿git stash preparado?

---

## PRÓXIMOS PASOS

✅ **FASE 1:** Auditoría completa  
✅ **FASE 2:** Plan estructurado  
⏳ **FASE 3:** Ejecución controlada (cuando se apruebe)  
⏳ **FASE 4:** Consolidación (refactoring)  
⏳ **FASE 5:** Validación  
⏳ **FASE 6:** Output final  

---

**Documento de planificación completado**  
**Status:** Listo para APROBACIÓN de stakeholders  
**Próximo:** FASE 3 (Ejecución) - requiere GO/NO-GO

