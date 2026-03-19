# Diseño del Agente ChainSignal

Este documento describe el diseño del agente autónomo y la migración de lógica de LLM hacia un motor determinista + OpenClaw opcional.

## Principios de diseño

- Entrada estructurada (métricas, perfil)
- Salida estructurada (`InsightContrato`)
- Paso a paso determinista para transparencia y reproducibilidad
- Compatibilidad total con el pipeline de WDK y herramientas existentes
- Modo OpenClaw opcional cuando está disponible

## Modelo de insight estructurado

`InsightContrato` (domain/modelos_contrato.py):

- `tipo`: str (`risk_guard`, `signal_lock`, `treasury_manager`)
- `wallet_analizada`: str
- `score_riesgo`: int
- `score_actividad`: int
- `accion_recomendada`: str

## Flujo de análisis

1. Se extraen métricas on-chain (`ExtractorFeatures`) y se clasifica el perfil (`ClasificadorWallet`).
2. `AgenteAnalisis.analizar()` crea insight determinista:
   - Calcula risk/actividad con reglas heurísticas
   - Selecciona tipo de contrato
   - Sugiere acción
3. DecisionEngine evalúa si ejecutar (`EXECUTE_ADVANCED`, `EXECUTE_BASIC`, etc.).
4. Si se requiere operación avanzada, `AgenteChainSignal` orquesta generar/compilar/desplegar/leer usando herramientas WDK.

## OpenClaw

- Si `OPENCLAW_ENABLED=true` y OpenClaw está instalado, el agente inicializa client OpenClaw.
- El flujo determinista no depende de modelo externo y sigue funcionando sin OpenClaw.
- OpenClaw se usa como capa de orquestación potencial para registrar tasks futuros.

## Dependencias eliminadas

Se removió la dependencia a LLM local (LM Studio) en `agente_ia/agente.py`.
El sistema no depende de endpoints `/chat/completions`.

## Compatibilidad con tests y pipeline

- Se mantienen todos los endpoints y formatos de resultados.
- Se mantuvo la integración con `services/servicio_wdk.py` y `tools/*`.
- Las pruebas existentes pasan con la nueva lógica.
