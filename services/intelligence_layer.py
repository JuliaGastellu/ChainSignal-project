from typing import Any, Dict


class WalletIntelService:
    def analyze(self, wallet: str, metrics: Any, profile: Any, scores: Dict[str, Any]) -> Dict[str, Any]:
        total_tx = int(getattr(metrics, "total_transacciones", 0) or 0)
        volume_eth = float(getattr(metrics, "volumen_total_transferido_eth", 0.0) or 0.0)
        contract_pct = float(getattr(metrics, "porcentaje_interacciones_contratos", 0.0) or 0.0)
        return {
            "wallet": wallet,
            "profile": getattr(profile, "type", "unknown"),
            "signals": list(getattr(profile, "signals", []) or []),
            "tx_count": total_tx,
            "volume_eth": volume_eth,
            "contract_interactions_pct": contract_pct,
            "risk": int(scores.get("risk", 0) or 0),
            "activity": int(scores.get("activity", 0) or 0),
            "confidence": float(scores.get("confidence", 0.0) or 0.0),
        }


class BlockIntelService:
    def analyze(self, block_metrics: Dict[str, Any]) -> Dict[str, Any]:
        tx_count = int(block_metrics.get("tx_count", 0) or 0)
        total_value_eth = float(block_metrics.get("total_value_eth", 0.0) or 0.0)
        avg_gas = int(block_metrics.get("avg_gas_price_wei", 0) or 0)
        return {
            "tx_count": tx_count,
            "total_value_eth": total_value_eth,
            "avg_gas_price_wei": avg_gas,
            "high_congestion": tx_count > 250 or avg_gas > 1_000_000_000,
            "value_dense_block": total_value_eth > 10,
        }


class ProtocolIntelService:
    def analyze(self, metrics: Any, profile: Any) -> Dict[str, Any]:
        token_diversity = int(getattr(metrics, "tokens_unicos_utilizados", 0) or 0)
        failed_txs = int(getattr(metrics, "transacciones_con_error", 0) or 0)
        profile_type = str(getattr(profile, "type", "unknown") or "unknown")
        return {
            "token_diversity": token_diversity,
            "failed_txs": failed_txs,
            "protocol_spike": token_diversity >= 15,
            "failure_pressure": failed_txs >= 8,
            "profile": profile_type,
        }

