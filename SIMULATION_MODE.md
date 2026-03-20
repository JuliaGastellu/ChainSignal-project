# ChainSignal - Simulation Mode

## Current Environment Status

**Active Configuration**:
```bash
APP_ENV = local
SEPOLIA_RPC_URL = https://sepolia.infura.io/v3/...
X402_ENABLED = true
```

**Result**: System is in **SIMULATION MODE** ⚠️

---

## What is Simulation Mode?

Simulation mode is a testing configuration where the ChainSignal system performs all functions but **does NOT validate payments on-chain**.

### In Simulation Mode

| Component | Status | Behavior |
|-----------|--------|----------|
| Wallet Analysis | ✅ Real | Fetches actual data from Etherscan |
| Behavioral Scoring | ✅ Real | Calculates real metrics |
| x402 Challenge | ✅ Real | Shows real token/recipient/amount |
| **Payment Validation** | ❌ **SIMULATED** | **ANY valid-format hash accepted** |
| Contract Deployment | ❌ Simulated | Returns fake addresses |
| Contract Execution | ❌ Simulated | Returns fake hashes |
| MetaMask Payment | ✅ Real | User signs real transaction |

---

## Critical Difference: Simulation vs Production

### Simulation Mode (`APP_ENV ≠ production`)

User payment flow:
```
1. Browser: "Can I access the report?"
   ↓
2. Backend: "No, send 1 USDC to 0x516D97bC82a962627Fd52115F32ce80F2f5da52a"
   ↓
3. MetaMask: User signs & sends REAL USDC (transaction IS on blockchain)
   ↓
4. Backend: "OK, I'll accept that hash"
   ✅ Grant access
   
   ⚠️ BUT: NO VALIDATION that the transaction actually happened
```

### Production Mode (`APP_ENV = production`)

User payment flow:
```
1. Browser: "Can I access the report?"
   ↓
2. Backend: "No, send 1 USDC to 0x516D97bC82a962627Fd52115F32ce80F2f5da52a"
   ↓
3. MetaMask: User signs & sends REAL USDC (transaction IS on blockchain)
   ↓
4. Backend: Calls RPC to verify
   - Get transaction receipt
   - Check USDC contract logs
   - Verify recipient is correct
   - Verify amount ≥ 1 USDC
   ↓
   ✅ If valid: Grant access
   ❌ If invalid: Deny access (401)
```

---

## What This Means

### In Simulation Mode

✅ **You CAN**:
- Test the full workflow
- See what a 402 challenge looks like
- Understand the payment flow
- Demo with any valid-format transaction hash

❌ **You CANNOT**:
- Guarantee payments actually happened
- Trust that access was truly paid for
- Use for real value transfer
- Ensure anti-fraud protection

### Example

These commands ALL WORK in simulation mode (but would fail in production):

```bash
# Real transaction hash from a different payment:
curl -H "X-Payment: 0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef" \
     http://localhost:8001/report/0x1111111111111111111111111111111111111111

Result: 200 OK ✅ (in simulation)
Result: 401 Unauthorized ❌ (in production if hash is wrong)

---

# Completely fake hash:
curl -H "X-Payment: 0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
     http://localhost:8001/report/0x1111111111111111111111111111111111111111

Result: 200 OK ✅ (in simulation - DANGER!)
Result: 401 Unauthorized ❌ (in production - correct)

---

# Hash too short (always rejected):
curl -H "X-Payment: 0xabcd" \
     http://localhost:8001/report/0x1111111111111111111111111111111111111111

Result: 401 Invalid hash format ❌ (both modes agree)
```

---

## UI Indicators

### Simulation Mode Warning

The ChainSignal UI will show a **yellow warning banner** when accessing a report in simulation mode:

```
⚠️ SIMULATION MODE

This is a test environment. Payments are NOT validated on-chain.
Any valid transaction hash will be accepted.

In production, all payments must be valid USDC transfers 
verified on the Sepolia blockchain.
```

### API Response Indicator

All `/report/{wallet}` endpoints include a flag:

```json
HTTP/1.1 402 Payment Required

{
  "error": "Payment required to access this resource.",
  "payment_required": true,
  "simulation_mode": true,  ← INDICATES SIMULATION
  "challenge": { ... }
}
```

---

## Transitioning to Production

### Step 1: Set Environment Variable

```bash
# Change from "local" to "production"
export APP_ENV=production

# Restart service
python -m uvicorn api.main:app --reload
```

### Step 2: Verify Configuration

Check that these are configured:

```bash
# Valid Sepolia RPC endpoint
echo $SEPOLIA_RPC_URL
# Should output: https://sepolia.infura.io/v3/...

# Payment recipient address
echo $X402_PAYMENT_RECIPIENT
# Should output: 0x516D97bC82a962627Fd52115F32ce80F2f5da52a

# USDC address on Sepolia
echo $USDC_ADDRESS_SEPOLIA
# Should output: 0x1C7D4b196cB0232491C26109653A6c6224a3383D

# Price in USDC (in units, not wei)
echo $X402_REPORT_PRICE_USDC
# Should output: 1
```

### Step 3: Fund the Recipient Address

The `X402_PAYMENT_RECIPIENT` address will receive payments. Make sure it has some Sepolia ETH for gas:

```bash
# Examples:
# - Request from Sepolia faucet (https://www.sepoliafaucet.io)
# - Transfer from another testnet wallet
# - Use Infura faucet (requires Infura account)
```

### Step 4: Test Real Payment Validation

1. Go to http://localhost:8001
2. Enter a wallet address
3. Click "Get Report"
4. Try payment with a REAL transaction hash from Sepolia
5. If hash is valid USDC transfer: ✅ Report loads
6. If hash is fake or invalid: ❌ 401 error

---

## Simulation Mode Features

### ✅ What Works

**Wallet Analysis**:
```bash
curl http://localhost:8001/run-agent/0x1234567890123456789012345678901234567890

# Returns real behavioral analysis
# - Transactions count
# - Risk score
- Activity level
# - DeFi engagement
```

**Report Generation** (after fake payment):
```bash
curl -H "X-Payment: 0xaaaa...aaaa" \
     http://localhost:8001/report/0x1234567890123456789012345678901234567890

# Returns analysis report
# - Wallet classification
# - Risk metrics
# - Behavioral insights
```

**Contract Code Generation**:
```bash
# During /run-agent flow, contracts are generated (code shown in SSE)
# Contract address returned: 0xSimulatedAddress...
# Perfect for reviewing generated Solidity code without deploying
```

---

## Known Limitations

### Race Condition Prevention

File-based payment tracking (`cache/used_payments.json`) is now protected with file locking to prevent:
- Two requests claiming the same hash
- File corruption from concurrent writes

✅ Protection is **enabled** in both simulation and production modes.

### RPC Connection

- RPC endpoint is configured and used in production
- In simulation mode, RPC connection exists but is never called for validation
- If RPC goes down in production, payment validation fails (secure by default)

---

## Security Models

### Simulation (Current)

```
Trust Model: OPEN
Access Control: Format validation only
Assumption: This is a test environment
Risk: High (anyone with valid hash format can access)
Use Case: Development, testing, demos
```

### Production (After APP_ENV=production)

```
Trust Model: CRYPTOGRAPHIC
Access Control: RPC-verified blockchain state
Assumption: Only real payments count
Risk: Low (only valid on-chain tx accepted)
Use Case: Live systems handling real value
```

---

## Debugging

### How to Tell What Mode You're In

**Method 1: Check Response**
```bash
curl http://localhost:8001/report/0x... | jq '.simulation_mode'

Output: true  → SIMULATION mode
Output: false → PRODUCTION mode
```

**Method 2: Check Environment**
```bash
echo $APP_ENV

Output: local        → SIMULATION mode
Output: production   → PRODUCTION mode
```

**Method 3: Look at UI**
- Yellow "SIMULATION MODE" banner visible → Simulation mode
- Banner not visible → Production mode

### Troubleshooting

**"Payment validation fails in production"**

Check:
1. `APP_ENV=production` is set
2. `SEPOLIA_RPC_URL` is a valid endpoint
3. Network connection to Infura/Alchemy is working
4. Payment hash is real (from Sepolia blockchain)

```bash
# Test RPC connection
curl https://sepolia.infura.io/v3/YOUR_KEY
```

**"Fake hash accepted when it shouldn't be"**

Check:
1. `APP_ENV` is actually "production" (not "prod" or other value)
2. Restart the service after changing APP_ENV
3. Look at backend logs for "SIMULATION MODE" messages

---

## Best Practices

### For Development

```bash
# Keep simulation mode for development
export APP_ENV=local

# Test with real tx hashes from Sepolia (optional, not required)
# Still works even if hash is fake
```

### For Staging

```bash
# Use production validation but with test wallets
export APP_ENV=production
export SEPOLIA_RPC_URL=https://sepolia.infura.io/v3/...

# Users must make real payments, but on testnet (costs ~$0.01 per report)
```

### For Production

```bash
# Full production mode with mainnet
export APP_ENV=production
export SEPOLIA_RPC_URL=https://mainnet.infura.io/v3/...  # Change to mainnet!
export USDC_ADDRESS_SEPOLIA=0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48  # Mainnet USDC

# Real payments on real network
```

---

## Summary

| Aspect | Simulation | Production |
|--------|-----------|-----------|
| **Payment Validation** | Any format ✅ | RPC-verified ✅ |
| **Cost** | Free | Testnet gas (~$0.01) |
| **User Payment** | Optional | Required |
| **Use Case** | Demo, dev | Staging, live |
| **Security** | Low | High |
| **Configuration** | `APP_ENV=local` | `APP_ENV=production` |

---

**Last Updated**: 2026-03-20  
**Status**: Implementation Complete  
**Next Steps**: Deploy to production when ready
