from typing import Any, Dict, List


class StrategyEngine:
    def select(
        self,
        signals: List[Dict[str, Any]],
        decision: Dict[str, Any],
        wallet_intel: Dict[str, Any],
        learning_summary: Dict[str, Any] | None = None,
        demo_mode: bool = False,
    ) -> Dict[str, Any]:
        signal_types = {str(s.get("type", "")) for s in signals}
        risk = int(wallet_intel.get("risk", 0) or 0)
        confidence = float(wallet_intel.get("confidence", 0.0) or 0.0)
        strategy_success = (learning_summary or {}).get("strategy_success", {}) if learning_summary else {}
        if strategy_success:
            best_strategy = max(strategy_success.items(), key=lambda x: int(x[1]))[0]
            if best_strategy in {"COPY_TRADE", "LIQUIDITY_FOLLOW", "ARBITRAGE_SCOUT"} and confidence >= 0.45:
                return {"strategy": best_strategy, "reason": "Learning bias selected historically successful strategy.", "force_execute": True}
        if demo_mode and confidence < 0.5:
            confidence = 0.5

        if "SUSPICIOUS_PATTERN" in signal_types or risk >= 70:
            return {"strategy": "RISK_SHIELD", "reason": "High risk pattern detected.", "force_execute": True}
        if "WHALE_ACCUMULATION" in signal_types and confidence >= 0.5:
            return {"strategy": "COPY_TRADE", "reason": "Whale-style accumulation pattern detected.", "force_execute": True}
        if "LIQUIDITY_SHIFT" in signal_types:
            return {"strategy": "LIQUIDITY_FOLLOW", "reason": "Liquidity migration signal detected.", "force_execute": True}
        if "CONTRACT_SPIKE" in signal_types:
            return {"strategy": "ARBITRAGE_SCOUT", "reason": "Contract activity spike suggests market imbalance.", "force_execute": True}
        return {"strategy": "EXPLORE", "reason": "No dominant signal, running low-risk exploration.", "force_execute": True}
