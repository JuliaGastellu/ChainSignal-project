# ChainSignal Autonomous On-Chain Agent

ChainSignal is an autonomous deterministic agent that analyzes on-chain wallet behavior, generates structured mitigation insights, and executes protective operations through the Tether Wallet Development Kit (WDK).

## Product Definition

ChainSignal is an autonomous capital intelligence agent:

- Wallet/Block input is an intelligence source.
- Agent Wallet is the only execution actor.
- The agent detects signals, selects strategy, executes safely, and learns from outcomes.

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

## Product Model: Target Wallet vs Agent Wallet

- **Target Wallet**: wallet under analysis (read-only).
- **Agent Wallet**: execution wallet controlled by the autonomous agent.
- **Funds source**: agent actions use the agent budget, not the target wallet funds.

The UI exposes this context explicitly through Wallet Context, Agent Summary, and Action Scope blocks.

## API and UI

The FastAPI backend provides:

- `GET /run-agent/{wallet}` / `GET /ejecutar-agente/{wallet}` SSE analysis+decision+execution stream
- `GET /events/sse/{wallet}` / `GET /events/sse?wallet=...` SSE aliases
- `GET /report/{wallet}` full free analysis snapshot
- `GET /analyze/wallet/{wallet}` wallet-level strategic analysis
- `GET /analyze/block/{block_number}` block-level strategic analysis
- `POST /agent/execute` trigger autonomous execution evaluation
- `POST /agent/budget` assign budget from verified MetaMask tx hash
- `GET /agent/budget/{wallet}` current budget for target wallet
- `GET /agent/actions` recent autonomous actions
- `GET /agent/state` global agent state and latest action
- `GET /agent/learning` learning outcomes and signal history summary
- `GET /agent/radar` tracked wallets radar for autonomous prioritization
- `POST /track-wallet` add/update autonomous loop tracking
- `GET /health` service and loop health

The UI is served via FastAPI from `web_app/app.py` and uses SSE to display real-time progress.

## SSE Event Payload Model

All SSE events include contextual fields to avoid ambiguity:

- `source`: `api` | `loop`
- `agent_wallet`
- `action_scope`: `{ target_wallet: "read_only", agent_wallet: "execution_enabled" }`
- `decision_context`: `{ target_wallet, executor_wallet, funds_source }`

Autonomous observability events:

- `signal_detected`
- `strategy_selected`
- `simulation_passed`
- `execution_submitted`
- `execution_value`
- `execution_verified`

Final event is always guaranteed as `decision_final` or `execution_final_status`.

## Operational Modes

- Production mode (`APP_ENV=production`) executes real blockchain operations through ESL/WDK.
- Simulation mode runs deterministic flows without real on-chain transactions.
- If budget is empty, the agent returns `SIMULATION_ONLY` (no funds at risk).
- Demo mode (`AGENT_DEMO_MODE=true`) lowers action thresholds and forces low-risk explore execution when budget is available.

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
- Execution only occurs when decision is actionable and budget is available.
- Simulation mode is explicitly indicated.
- ESL remains mandatory: idempotency, cooldown, nonce and exposure validation before execution.

## Dashboard Flow

Analyze & Monitor → Decision → ESL Validation → Autonomous Execution (if applicable) → Activity Feed

Autonomous lifecycle:

Observe → Analyze → Detect Signal → Select Strategy → Simulate → Execute → Verify → Learn

## Demo Instructions

1. Set `AGENT_DEMO_MODE=true`.
2. Use **Fund Agent Wallet** panel and approve MetaMask transaction.
3. Wait for status: `Funds received. Autonomous execution activated.`
4. Run wallet analysis or block-window analysis.
5. Verify timeline events: `signal_detected` → `strategy_selected` → `execution_submitted` → `execution_value` → `execution_verified`.
6. Confirm Hero and Activity Feed show updated balance and moved capital.

## Funding Flow

- Funding is signed only in MetaMask from the frontend.
- Backend verifies tx receipt and recipient via `POST /agent/budget`.
- Agent wallet is the sole execution wallet; analyzed wallet is intelligence input only.
- On balance increase, UI triggers autonomous execution for the selected target wallet.

## Panel Meanings

- Agent Hero: balance, last action, PnL, runtime status.
- Strategy Engine: chosen strategy, confidence, trigger signals.
- Agent Intelligence Feed: detected signal stream with severity/confidence.
- Wallet Radar: prioritized tracked wallets for loop execution.
- Agent Activity Feed: executed/skipped actions with strategy and moved value.

- Timeline: append-only and phase-colored.
- ResultsPanel + AnalysisDashboard: full analysis, free, no premium gate.
- SidePanel: autonomous status, safety semantics, treasury state.

## References

- ARCHITECTURE.md
- AGENT_DESIGN.md
- docs/AUTONOMOUS_DASHBOARD.md
