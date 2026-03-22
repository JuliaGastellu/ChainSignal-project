from typing import Any, Dict, List


class StrategyEngine:
    def select(self, signals: List[Dict[str, Any]], decision: Dict[str, Any], wallet_intel: Dict[str, Any]) -> Dict[str, Any]:
        signal_types = {str(s.get("type", "")) for s in signals}
        risk = int(wallet_intel.get("risk", 0) or 0)
        confidence = float(wallet_intel.get("confidence", 0.0) or 0.0)

        if "SUSPICIOUS_PATTERN" in signal_types or risk >= 70:
            return {"strategy": "RISK_SHIELD", "reason": "High risk pattern detected.", "force_execute": True}
        if "WHALE_ACCUMULATION" in signal_types and confidence >= 0.5:
            return {"strategy": "COPY_TRADE", "reason": "Whale-style accumulation pattern detected.", "force_execute": True}
        if "LIQUIDITY_SHIFT" in signal_types:
            return {"strategy": "LIQUIDITY_FOLLOW", "reason": "Liquidity migration signal detected.", "force_execute": True}
        if "CONTRACT_SPIKE" in signal_types:
            return {"strategy": "ARBITRAGE_SCOUT", "reason": "Contract activity spike suggests market imbalance.", "force_execute": True}
        return {"strategy": "EXPLORE", "reason": "No dominant signal, running low-risk exploration.", "force_execute": True}

