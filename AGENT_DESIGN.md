# ChainSignal Agent Design

This document describes the ChainSignal autonomous agent design and the migration from LLM-driven logic to a deterministic core with optional OpenClaw orchestration.

## Design Principles

- Structured input (metrics, wallet profile)
- Structured output (`InsightContrato`)
- Deterministic step-by-step processing for transparency and reproducibility
- Full compatibility with the WDK pipeline and existing tools
- Optional OpenClaw mode when available

## Structured Insight Model

`InsightContrato` (domain/modelos_contrato.py):

- `tipo`: str (`risk_guard`, `signal_lock`, `treasury_manager`)
- `wallet_analizada`: str
- `score_riesgo`: int
- `score_actividad`: int
- `accion_recomendada`: str

## Analysis Flow

1. On-chain metrics are extracted (`ExtractorFeatures`) and wallet profile is classified (`ClasificadorWallet`).
2. `AgenteAnalisis.analizar()` creates a deterministic insight:
   - Computes risk/activity using heuristic rules
   - Selects contract type
   - Recommends action
3. `DecisionEngine` evaluates execution level (`EXECUTE_ADVANCED`, `EXECUTE_BASIC`, etc.).
4. If advanced operations are required, `AgenteChainSignal` orchestrates contract generation, compilation, deployment, and state reads using WDK tools.

## OpenClaw

- If `OPENCLAW_ENABLED=true` and OpenClaw is installed, the agent initializes an OpenClaw client.
- The deterministic core does not depend on external models and continues to operate without OpenClaw.
- OpenClaw is used as an orchestration layer to track future tasks.

## Removed Dependencies

The local LLM dependency (LM Studio) was removed from `agente_ia/agente.py`.
The system does not rely on `/chat/completions` endpoints.

## Test and Pipeline Compatibility

- API endpoints and result formats remain compatible.
- Integration with `services/servicio_wdk.py` and `tools/*` is preserved.
- Existing tests pass with the deterministic logic.
