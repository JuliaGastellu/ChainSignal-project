from dataclasses import dataclass
from typing import Any, Dict, Optional
import asyncio
import os
from openai import AsyncOpenAI
from loguru import logger


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
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = AsyncOpenAI(api_key=self.api_key) if self.api_key else None
        if not self.client:
            logger.warning("OPENAI_API_KEY not found. LLM reasoning will be disabled.")

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

    async def _llm_reasoning(
        self, 
        address: str, 
        scores: Dict[str, Any], 
        threat_score: float, 
        decision: str,
        event_bus: Optional[Any] = None
    ) -> Optional[str]:
        if not self.client:
            return None
            
        activity = scores.get("activity", 0)
        risk = scores.get("risk", 0)
        defi = scores.get("defi_engagement", 0)
        diversity = scores.get("diversity", 0)
        exploration = scores.get("exploration", 0)

        prompt = (
            "You are an autonomous on-chain financial guardian agent. You have just analyzed a wallet and computed the following:\n"
            f"Wallet: {address}\n"
            f"Activity score: {activity}/100\n"
            f"Risk score: {risk}/100\n"
            f"DeFi engagement: {defi}/100\n"
            f"Diversity: {diversity}/100\n"
            f"Exploration: {exploration}/100\n"
            f"Computed threat score: {threat_score:.2f} (scale 0-1)\n"
            f"Decision: {decision}\n"
            "Write a concise 2-3 sentence analysis explaining why you made this decision based on these specific scores. "
            "Reference the actual numbers. Be direct and technical. Do not use marketing language."
        )

        try:
            logger.info(f"Requesting OpenAI reasoning for {address}...")
            
            async def get_streaming_response():
                full_text = ""
                response = await self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                    timeout=10.0
                )
                async for chunk in response:
                    token = chunk.choices[0].delta.content or ""
                    if token:
                        full_text += token
                        if event_bus:
                            await event_bus.publish({"type": "reasoning_token", "token": token})
                return full_text

            # Execute with 10s timeout
            return await asyncio.wait_for(get_streaming_response(), timeout=10.0)

        except asyncio.TimeoutError:
            logger.error("OpenAI reasoning timed out (10s limit).")
            return None
        except Exception as e:
            logger.error(f"Error in OpenAI reasoning: {e}")
            return None

    async def decide(self, payload: Dict[str, Any], event_bus: Optional[Any] = None) -> Dict[str, Any]:
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

        reasoning = await self._llm_reasoning(address, scores, threat_score, decision, event_bus) or self._deterministic_reasoning(address, scores, threat_score, decision)
        return ReasoningDecision(cycle, address, round(threat_score, 4), round(confidence, 4), decision, reasoning, action).to_dict()
