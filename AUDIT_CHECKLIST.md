# ✅ AUDIT CHECKLIST - ACCIONES INMEDIATAS
**Generado:** 20-Mar-2026 | **Prioridad:** CRÍTICA

---

## 🚨 24 HORAS - BLOQUEANTES

### [ ] 1. Eliminar Archivos Temporales
**Tiempo:** 5 minutos  
**Riesgo si no se hace:** Confusión en CI/CD, repositorio sucio

```bash
# Verificar contenidos antes de eliminar:
git show HEAD:tmp_sse.py
git show HEAD:tmp_sse2.py
git show HEAD:tmp_test_sse.py
git show HEAD:patch_main.py

# Eliminar:
git rm -f tmp_sse.py tmp_sse2.py tmp_test_sse.py patch_main.py
git commit -m "chore: remove dead test files (tmp_*.py, patch_main.py)"
git push
```

**Verificar en repositorio:**
- [ ] Archivos eliminados de main branch
- [ ] No quedan en .gitignore
- [ ] CI/CD pasa sin estos archivos

---

### [ ] 2. Fijar Red Equivocada en Swap
**Tiempo:** 15 minutos  
**Riesgo si no se hace:** ⚠️ PÉRDIDA DE FONDOS - Transacción falla o va a red equivocada

**Archivo:** `agents/agente_chainsignal.py:322`

**Current Code (MALO):**
```python
token_out = "0xdAC17F958D2ee523a2206206994597C13D831ec7"  # USD₮ MAINNET
```

**Fixed Code:**
```python
# Opción A: Si USDT existe en Sepolia
token_out = settings.USDT_ADDRESS_SEPOLIA  # Tomar de config

# Opción B: Si NO existe en Sepolia (unlikely)
token_out = "0x..."  # Actual USDT Sepolia address
```

**Pasos:**
1. [ ] Verificar dirección USDT en Sepolia en Etherscan
2. [ ] Actualizar code en agents/agente_chainsignal.py
3. [ ] Actualizar infra/config.py si no existe
4. [ ] Ejecutar test que verifica token correcto
5. [ ] Commit y push

**Verificación:**
```python
# Test para verificar:
def test_usdt_address_is_sepolia():
    from agents.agente_chainsignal import EstrategiaProteccionWallet
    # Verify address is NOT 0xdAC17...
    # Verify it's in SEPOLIA network instead of MAINNET
```

---

### [ ] 3. Remover Delay Artificial
**Tiempo:** 5 minutos  
**Riesgo si no se hace:** UX degradada, SSE stream lento

**Archivo:** `api/main.py:186`

**Current Code (MALO):**
```python
yield f'data: {json.dumps({"paso": "x402_validation", "estado": "starting", ...})}\n\n'
import time
time.sleep(1)  # <-- REMOVER
yield f'data: {json.dumps({"paso": "x402_validation", "estado": "completed", ...})}\n\n'
```

**Fixed Code:**
```python
yield f'data: {json.dumps({"paso": "x402_validation", "estado": "starting", ...})}\n\n'
# Log or perform actual validation here, not time.sleep()
yield f'data: {json.dumps({"paso": "x402_validation", "estado": "completed", ...})}\n\n'
```

**Verificar:**
- [ ] time.sleep() removido
- [ ] Línea 186 ahora es otra cosa
- [ ] SSE stream se acelera como esperado

---

## 📅 3-5 DÍAS - ALTA PRIORIDAD

### [ ] 4. Centralizar Constantes en Config
**Tiempo:** 2 horas  
**Riesgo si no se hace:** Mantenibilidad reducida, cambios requieren editar múltiples archivos

**Archivo:** `infra/config.py`

**Agregar después de línea 27:**
```python
# ====== AGENT OPERATION CONSTANTS ======
SAFE_WALLET_ADDRESS: str = os.getenv(
    "SAFE_WALLET_ADDRESS", 
    "0x000000000000000000000000000000000000dEaD"
)
SWAP_AMOUNT_WEI: int = int(os.getenv("SWAP_AMOUNT_WEI", "500000000000000"))
RESCUE_TRANSFER_AMOUNT_WEI: int = int(
    os.getenv("RESCUE_TRANSFER_AMOUNT_WEI", "1000000000000000")
)
MAX_AMOUNT_ETH_RATIO: float = float(
    os.getenv("MAX_AMOUNT_ETH_RATIO", "0.5")
)
GAS_LIMIT_HIGH: int = int(os.getenv("GAS_LIMIT_HIGH", "500000"))
GAS_LIMIT_DEFAULT: int = int(os.getenv("GAS_LIMIT_DEFAULT", "250000"))
ETHERSCAN_BASE_URL: str = os.getenv(
    "ETHERSCAN_BASE_URL", 
    "https://sepolia.etherscan.io"
)
```

**Actualizar archivos que referenican estos valores:**
- [ ] `api/main.py:232` → usar `settings.SAFE_WALLET_ADDRESS`
- [ ] `agents/agente_chainsignal.py:156` → usar `settings.SAFE_WALLET_ADDRESS`
- [ ] `api/main.py:247` → usar `settings.SWAP_AMOUNT_WEI`
- [ ] `agents/agente_chainsignal.py:176` → usar `settings.SWAP_AMOUNT_WEI`
- [ ] `api/main.py:309` → usar `settings.ETHERSCAN_BASE_URL`
- [ ] `decision_engine.py:35-36` → usar `settings.MAX_AMOUNT_ETH_RATIO`, etc.
- [ ] `strategy/estrategia_proteccion_wallet.py:11` → usar `settings.RESCUE_TRANSFER_AMOUNT_WEI`

**Verificar:**
- [ ] Todos los imports de `settings` están presentes
- [ ] No hay más hardcodes de estas direcciones/montos
- [ ] Tests pasan con valores por defecto
- [ ] Tests pasan con valores ENV personalizados (.env file)

---

### [ ] 5. Mejorar Logging x402
**Tiempo:** 1 hora  
**Riesgo si no se hace:** Difícil debuggear problemas de validación

**Archivo:** `services/servicio_x402.py`

**En `verificar_transaccion_onchain()` alrededor de línea 195:**

Agregar logging robusto:
```python
def verificar_transaccion_onchain(self, tx_hash: str) -> Tuple[bool, str]:
    """Verifica una transacción ERC-20 real en la blockchain."""
    if not self.w3:
        logger.error(f"x402: Web3 provider not available for {tx_hash}")
        return False, "On-chain validation failed: Provider not available."

    try:
        receipt = self.w3.eth.get_transaction_receipt(tx_hash)
        if not receipt:
            logger.warning(f"x402: Receipt not found for {tx_hash}")
            return False, "Transaction not found on-chain."
        
        if receipt['status'] != 1:
            logger.warning(f"x402: Transaction failed {tx_hash} status={receipt['status']}")
            return False, "Transaction failed or not found on-chain."

        usdc_address = settings.USDC_ADDRESS_SEPOLIA.lower()
        recipient_expected = settings.X402_PAYMENT_RECIPIENT.lower()
        amount_required = settings.X402_REPORT_PRICE_USDC * 1_000_000

        logger.debug(f"x402: Validating {tx_hash}")
        logger.debug(f"x402: Expected recipient={recipient_expected}, amount={amount_required}")
        logger.debug(f"x402: Found {len(receipt['logs'])} logs in transaction")

        for i, log in enumerate(receipt['logs']):
            if log['address'].lower() != usdc_address:
                logger.debug(f"x402: Log {i} mismatch address (not USDC)")
                continue
            
            topics = log['topics']
            if not topics or topics[0].hex() != _TRANSFER_EVENT_SIGNATURE:
                logger.debug(f"x402: Log {i} not a Transfer event")
                continue
            
            try:
                recipient_found = "0x" + topics[2].hex()[-40:].lower()
                logger.debug(f"x402: Log {i} Transfer to {recipient_found}")
                
                if recipient_found != recipient_expected:
                    logger.debug(f"x402: Log {i} recipient mismatch")
                    continue
                
                value = int(log['data'].hex(), 16)
                logger.debug(f"x402: Log {i} value={value} required={amount_required}")
                
                if value >= amount_required:
                    logger.success(f"✅ x402: Payment validated {value} USDC from tx {tx_hash}")
                    self._guardar_hash_usado(tx_hash)
                    return True, "Payment verified on-chain."
                else:
                    logger.warning(f"x402: Insufficient amount {value} < {amount_required}")
                    continue
                    
            except Exception as e:
                logger.error(f"x402: Error parsing log {i}: {e}")
                continue

        logger.error(f"❌ x402: No valid USDC transfer found in {tx_hash}")
        return False, f"No valid USDC transfer to {recipient_expected} found in transaction."

    except Exception as e:
        logger.error(f"❌ x402: Error verifying {tx_hash}: {e}", exc_info=True)
        return False, f"Verification error: {str(e)}"
```

**Verificar:**
- [ ] Logging granular para cada paso
- [ ] Errores se registran con contexto
- [ ] Tests que verifican logs en casos fallidos

---

## 🔄 1-2 SEMANAS - MEDIANO PLAZO

### [ ] 6. Consolidar Scoring Logic
**Tiempo:** 3 horas  
**Riesgo si no se hace:** Duplicación, cambios inconsistentes

**Opción A: Usar BehavioralScorer para todo**
- Remove `_calcular_score_riesgo()` from `agente_ia/agente.py`
- Remove `_calcular_score_actividad()` from `agente_ia/agente.py`
- Update `AgenteAnalisis.analizar()` to use `BehavioralScorer` instead

**Opción B: Mantener agente_ia pero harmonizar fórmulas**
- Documento en shared location qué fórmulas son "canónicas"
- Ambas clases usan las mismas fórmulas

**Recomendación:** Opción A (más limpio)

**Checklist:**
- [ ] `agente_ia/agente.py` no define más scoring
- [ ] `AgenteAnalisis.analizar()` usa `BehavioralScorer`
- [ ] Tests pasan con results idénticos

---

### [ ] 7. Documentar SSE Contract
**Tiempo:** 2 horas  
**Riesgo si no se hace:** UI rompe si estructura cambia

**Archivo:** `README.md` (sección nueva)

**Agregar:**
```markdown
## SSE Stream Format

The `/run-agent/{wallet}` endpoint streams Server-Sent Events (SSE) in format:

```
data: {json_payload}\n\n
```

### JSON Payload Structure

Each event has this structure:

```json
{
  "paso": "string",              // Step name (machine-readable)
  "estado": "string",            // Status: starting|completed|error
  "detalle": "string",           // Human-readable description
  "data": {                       // Optional: step-specific data
    "...specific_fields...": "..."
  }
}
```

### Step Names & Data Fields

| paso | estado | data fields |
|------|--------|-------------|
| analyzing_wallet | starting, completed | transaction_count, balance |
| calculating_scores | completed | risk, activity, defi_engagement, confidence |
| classifying_profile | completed | profile_type, confidence |
| generating_insight | completed | type, analyzed_wallet, risk_score, activity_score |
| evaluating_decision | completed | decision, confidence, contract_type, reasoning |
| x402_validation | starting, completed | (none) |
| strategy_execution | completed | actions, detail |
| financial_operation | starting, completed, error | destination, hash, success |
| swap_operation | starting, completed, error | hash, success |
| contract_generation | starting, completed | code |
| contract_compilation | starting, completed | (none) |
| contract_deployment | starting, completed | address, hash, metrics |
| contract_active | completed | address, hash, metrics, etherscan |
| decision_final | completed | decision, contract_type, execution, motivo |
```

**Checklist:**
- [ ] Documento en README.md o docs/
- [ ] Schema validado contra ejemplos de main.py
- [ ] OpenAPI spec si es posible (.openapi.json)

---

### [ ] 8. Unit Tests para x402
**Tiempo:** 4 horas  
**Archivo:** `tests/test_x402_validation.py` (crear)

**Tests mínimos:**
```python
def test_x402_valid_hash_format():
    """Valid 0x + 64 hex must pass format check"""
    
def test_x402_invalid_hash_format():
    """Invalid formats must be rejected"""
    
def test_x402_anti_replay_prevents_reuse():
    """Same hash can't be used twice"""
    
def test_x402_simulation_mode_accepts_valid_format():
    """In SIMULATION: any valid format accepted"""
    
def test_x402_production_requires_onchain():
    """In PRODUCTION: must verify on-chain"""
    
def test_x402_validates_exact_amount():
    """Payment must be exact or overpayment within 10%"""
    
def test_x402_rejects_underpayment():
    """Less than required must fail"""
    
def test_x402_recipient_validation():
    """Transfer must be to correct recipient"""
```

**Checklist:**
- [ ] tests/test_x402_validation.py creado
- [ ] 8+ tests implementados
- [ ] Todos pasan
- [ ] Coverage >= 80% para servicio_x402.py

---

## 📋 VERIFICACIÓN FINAL

**Ejecutar antes de commit:**

```bash
# 1. Verificar archivos eliminados
git status  # No debe mostrar tmp_*.py o patch_main.py

# 2. Verificar imports
grep -r "0x000.*dEaD\|0xdAC17\|500000000000000\|time.sleep(1)" \
    --include="*.py" api/ agents/ tools/ strategy/
# Debe estar vacío o solo en config.py, testing

# 3. Ejecutar tests
pytest tests/ -v --cov=services/servicio_x402

# 4. Linting
pylint api/main.py agents/agente_chainsignal.py services/servicio_x402.py

# 5. Type checking (si está configurado)
mypy --strict api/main.py
```

---

## 📞 PREGUNTAS FRECUENTES

**P: ¿Por qué eliminar código temporal?**  
R: No debería estar en repositorio. Crea confusión y complejidad innecesaria.

**P: ¿Qué pasa si cambio USDT address?**  
R: Verifica que exista en Sepolia y que WDK pueda swappearlo. Sino, el step falla.

**P: ¿Puedo aplazo las acciones de 3-5 días?**  
R: Las de 24 horas son BLOQUEANTES. Las de 3-5 días pueden esperar una semana máximo sin riesgo.

**P: ¿Necesito re-testing todo después?**  
R: Sí. Mínimo: SSE stream end-to-end, x402 flow, decisión engine con nuevas constantes.

---

**Estado:** LISTA PARA EJECUTAR ✅  
**Generado:** 20-Mar-2026 | **Prioridad:** CRÍTICA  
**Deadline sugerido:** 24h + 3-5 días según sección
