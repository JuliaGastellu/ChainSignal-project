from typing import Any, Dict, List

# La selección depende solo de las señales de esta evaluación. Antes un
# "sesgo de aprendizaje" elegía la estrategia con más transacciones aceptadas
# y forzaba su ejecución; aceptación no es rentabilidad, así que lo quité.
#
# NO_ACTION es un resultado de primera clase y nunca lleva force_execute=True.
# Antes la rama sin señal dominante devolvía force_execute=True siempre y,
# junto con el overlay viejo de agent_service.py, el sistema tenía un camino
# para forzar una transferencia real aunque no encontrara nada accionable.
NO_ACTION = "NO_ACTION"


class StrategyEngine:
    def select(
        self,
        signals: List[Dict[str, Any]],
        decision: Dict[str, Any],
        wallet_intel: Dict[str, Any],
        demo_mode: bool = False,
    ) -> Dict[str, Any]:
        # No uso demo_mode para nada que afecte selección, confianza o
        # ejecución: el modo demo no puede alterar la estrategia que elegiría
        # producción. Conservo el parámetro por compatibilidad con los llamados.
        signal_types = {str(s.get("type", "")) for s in signals}
        real_signal_types = signal_types - {"EXPLORE_TRIGGER", ""}
        risk = int(wallet_intel.get("risk", 0) or 0)
        confidence = float(wallet_intel.get("confidence", 0.0) or 0.0)

        # No se disparó ninguna señal real: solo está el fallback EXPLORE_TRIGGER
        # (o nada). Esto nunca autoriza mover capital.
        if not real_signal_types:
            return {
                "strategy": NO_ACTION,
                "reason": "No actionable signal detected; monitoring only.",
                "confidence": confidence,
                "trigger_signals": list(signal_types) or ["EXPLORE_TRIGGER"],
                "force_execute": False,
            }

        if "SUSPICIOUS_PATTERN" in signal_types or risk >= 70:
            return {"strategy": "RISK_SHIELD", "reason": "High risk pattern detected.", "confidence": max(0.7, confidence), "trigger_signals": list(signal_types), "force_execute": True}
        if "WHALE_ACCUMULATION" in signal_types and confidence >= 0.5:
            return {"strategy": "COPY_TRADE", "reason": "Whale-style accumulation pattern detected.", "confidence": max(0.65, confidence), "trigger_signals": list(signal_types), "force_execute": True}
        if "LIQUIDITY_SHIFT" in signal_types:
            return {"strategy": "LIQUIDITY_FOLLOW", "reason": "Liquidity migration signal detected.", "confidence": max(0.6, confidence), "trigger_signals": list(signal_types), "force_execute": True}
        if "CONTRACT_SPIKE" in signal_types:
            return {"strategy": "ARBITRAGE_SCOUT", "reason": "Contract activity spike suggests market imbalance.", "confidence": max(0.58, confidence), "trigger_signals": list(signal_types), "force_execute": True}

        # A real (non-EXPLORE_TRIGGER) signal fired but didn't match a named
        # strategy above (e.g. HIGH_VALUE_TRANSFER alone). Still no action.
        return {
            "strategy": NO_ACTION,
            "reason": "Signal detected but no strategy matched; monitoring only.",
            "confidence": confidence,
            "trigger_signals": list(signal_types),
            "force_execute": False,
        }
