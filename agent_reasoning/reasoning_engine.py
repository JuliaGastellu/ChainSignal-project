from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ReasoningDecision:
    cycle: int
    wallet: str
    threat_score: float
    confidence: float
    decision: str
    reasoning: str
    action: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle": self.cycle,
            "wallet": self.wallet,
            "threat_score": self.threat_score,
            "confidence": self.confidence,
            "decision": self.decision,
            "reasoning": self.reasoning,
            "action": self.action,
        }


class ReasoningEngine:
    def __init__(self):
        self._llm_available = False
        try:
            from openclaw import OpenClaw  # type: ignore

            self._llm_available = True
            self._OpenClaw = OpenClaw
        except Exception:
            self._OpenClaw = None

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0

    def _deterministic_reasoning(self, address: str, scores: Dict[str, Any], threat_score: float, decision: str) -> str:
        activity = int(self._to_float(scores.get("activity")))
        risk = int(self._to_float(scores.get("risk")))
        defi = int(self._to_float(scores.get("defi_engagement")))
        diversity = int(self._to_float(scores.get("diversity")))
        exploration = int(self._to_float(scores.get("exploration")))
        return (
            f"Wallet {address} evaluated with risk={risk}, activity={activity}, "
            f"defi_engagement={defi}, diversity={diversity}, exploration={exploration}. "
            f"Composite threat score={threat_score:.2f}. Decision={decision}."
        )

    def _llm_reasoning(self, address: str, scores: Dict[str, Any], threat_score: float, decision: str) -> Optional[str]:
        if not self._llm_available or self._OpenClaw is None:
            return None
        try:
            client = self._OpenClaw()
            prompt = (
                "Write a concise technical reasoning sentence in English for an autonomous wallet agent. "
                f"Wallet={address}, scores={scores}, threat_score={threat_score:.2f}, decision={decision}. "
                "Reference concrete score values."
            )
            response = client.run(prompt)  # type: ignore[attr-defined]
            text = str(response).strip()
            return text if text else None
        except Exception:
            return None

    def decide(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        address = str(payload.get("address", "")).lower()
        cycle = int(payload.get("cycle", 0) or 0)
        scores = payload.get("scores", {}) or {}
        balance_eth = self._to_float(payload.get("agent_balance_eth", 0.0))

        if balance_eth < 0.003:
            decision = "INSUFFICIENT_FUNDS"
            threat_score = 0.0
            confidence = 0.0
            action = {
                "type": None,
                "amount_eth": None,
                "to": None,
                "contract_type": None,
                "justification": "Agent balance is below minimum execution threshold.",
            }
            reasoning = f"Agent balance is {balance_eth:.6f} ETH, below 0.003 ETH. No action is allowed."
            return ReasoningDecision(cycle, address, threat_score, confidence, decision, reasoning, action).to_dict()

        risk = self._to_float(scores.get("risk", 0))
        activity = self._to_float(scores.get("activity", 0))
        exploration = self._to_float(scores.get("exploration", 0))
        composite = (risk * 0.5) + ((100 - activity) * 0.3) + (exploration * 0.2)
        threat_score = max(0.0, min(1.0, composite / 100.0))
        confidence = max(0.0, min(1.0, (risk + exploration + (100 - activity)) / 300.0))

        if threat_score < 0.35:
            decision = "MONITOR"
            action = {
                "type": None,
                "amount_eth": None,
                "to": None,
                "contract_type": None,
                "justification": "Signal strength is below autonomous action threshold.",
            }
        elif threat_score <= 0.65:
            decision = "ALERT"
            action = {
                "type": "transfer",
                "amount_eth": "0.001",
                "to": address,
                "contract_type": None,
                "justification": "Medium confidence alert triggers an on-chain micro-transfer marker.",
            }
        else:
            decision = "INTERVENE"
            action = {
                "type": "deploy_contract",
                "amount_eth": None,
                "to": address,
                "contract_type": "risk_guard",
                "justification": "High threat profile requires contract-based intervention.",
            }

        reasoning = self._llm_reasoning(address, scores, threat_score, decision) or self._deterministic_reasoning(address, scores, threat_score, decision)
        return ReasoningDecision(cycle, address, round(threat_score, 4), round(confidence, 4), decision, reasoning, action).to_dict()
