from typing import Any, Dict, List


class SignalDetector:
    def detect(self, wallet_intel: Dict[str, Any], protocol_intel: Dict[str, Any], block_intel: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
        signals: List[Dict[str, Any]] = []
        if wallet_intel.get("volume_eth", 0) >= 20:
            signals.append({"type": "WHALE_ACCUMULATION", "severity": "high", "confidence": 0.78})
        if wallet_intel.get("contract_interactions_pct", 0) >= 60:
            signals.append({"type": "LIQUIDITY_SHIFT", "severity": "medium", "confidence": 0.7})
        if protocol_intel.get("protocol_spike"):
            signals.append({"type": "CONTRACT_SPIKE", "severity": "medium", "confidence": 0.66})
        if wallet_intel.get("tx_count", 0) >= 150:
            signals.append({"type": "HIGH_VALUE_TRANSFER", "severity": "low", "confidence": 0.62})
        if protocol_intel.get("failure_pressure"):
            signals.append({"type": "SUSPICIOUS_PATTERN", "severity": "high", "confidence": 0.74})
        if block_intel and (block_intel.get("high_congestion") or block_intel.get("value_dense_block")):
            signals.append({"type": "LIQUIDITY_SHIFT", "severity": "medium", "confidence": 0.64})
        if not signals:
            signals.append({"type": "EXPLORE_TRIGGER", "severity": "low", "confidence": 0.55})
        return signals

