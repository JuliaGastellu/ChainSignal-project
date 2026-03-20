# ChainSignal Autonomous On-Chain Agent

ChainSignal is an autonomous deterministic agent that analyzes on-chain wallet behavior, generates structured mitigation insights, and executes protective operations through the Tether Wallet Development Kit (WDK).

## Architecture Overview

The system is organized as follows:

1. Data ingestion and feature extraction from Etherscan.
2. Behavioral profiling and risk scoring.
3. Deterministic decision engine that outputs explicit actions.
4. Agent orchestration for contract generation/execution.
5. Execution gateway through WDK and ERC-4337.

## Technology Stack

- Python 3.x (FastAPI, Web3.py, HTTPX)
- Node.js (WDK gateway service)
- Tether WDK for wallet orchestration and ERC-4337
- SSE frontend for real-time progress updates

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
cd wdk_service && npm install
```

Set required environment variables:

- APP_ENV (production/local)
- ETHERSCAN_API_KEY
- SEPOLIA_RPC_URL
- AGENT_SEED_PHRASE
- WDK_BUNDLER_URL
- WDK_PAYMASTER_URL

## Run

Production:

```bash
docker-compose up --build
```

Local run:

```bash
cd wdk_service && node server.js
python -m uvicorn api.main:app --host 0.0.0.0 --port 8001
```

## API Documentation

- https://chainsignal-project.onrender.com/docs

## x402 Payment System (Protected Reports)

The endpoint `GET /report/{wallet_address}` is protected by the x402 protocol. To access a report:

1. Call the endpoint. It will return `402 Payment Required` with a challenge.
2. Pay the required amount (1.00 USDC) on **Sepolia Testnet**.
3. Re-call the endpoint with the transaction hash in the `X-Payment` header.

**Sepolia Testnet Info:**
- **USDC Contract**: `0x1C7D4b196cB0232491C26109653A6c6224a3383D`
- **Network**: Sepolia (Chain ID: 11155111)

**How to pay with MetaMask:**
- The UI provides a "Pay with MetaMask" button when a 402 is received.
- It executes a standard ERC20 `transfer` to the agent's recipient address.

**Manual usage (curl):**
```bash
curl -H "X-Payment: <tx_hash>" https://chainsignal-project.onrender.com/report/0x...
```

## API and UI

The FastAPI backend provides:

- `GET /` for landing page
- `GET /ejecutar-agente/{wallet}` as SSE for agent execution updates
- API docs at `https://chainsignal-project.onrender.com/docs`

The UI is served via FastAPI from `web_app/app.py` and uses SSE to display real-time progress.

## Operational Modes

- Production mode (`APP_ENV=production`) executes real blockchain operations and **verifies x402 payments on-chain**.
- Simulation mode runs deterministic flows without real on-chain transactions and accepts any valid-looking hash for x402.

## Production Mode Requirements

- [ ] APP_ENV=production
- [ ] WDK active and reachable
- [ ] Bundler configured
- [ ] Paymaster configured

## Decision System

The deterministic decision engine returns explicit outputs:

- `DATOS_INSUFICIENTES` (insufficient data)
- `MONITOR`
- `EXECUTE_BASIC`
- `EXECUTE_ADVANCED`

## Safety Guarantees

- Invalid wallet inputs are rejected.
- Execution only occurs when risk and confidence thresholds are met.
- Simulation mode is explicitly indicated.

## References

- ARCHITECTURE.md
- AGENT_DESIGN.md
