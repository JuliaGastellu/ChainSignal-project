import type { AgentResults } from "@/hooks/useAgentSSE";
import { Zap } from "lucide-react";

export function StrategyEnginePanel({ results }: { results: AgentResults | null }) {
  const strategy = results?.selected_strategy || "EXPLORE";
  const confidence = results?.strategy_confidence !== undefined ? `${Math.round(results.strategy_confidence * 100)}%` : "55%";
  const reason = results?.strategy_reason || "Fallback exploration ensures autonomous action continuity.";
  const rawTriggers = results?.trigger_signals?.length ? results.trigger_signals : ["EXPLORE_TRIGGER"];
  const triggerMap: Record<string, string> = {
    EXPLORE_TRIGGER: "Low signal density environment",
    WHALE_ACCUMULATION: "Whale accumulation detected",
    LIQUIDITY_SHIFT: "Liquidity migration detected",
    CONTRACT_SPIKE: "Contract activity spike detected",
    SUSPICIOUS_PATTERN: "Suspicious behavioral pattern detected",
    HIGH_VALUE_TRANSFER: "High-value transfers detected",
  };
  const triggers = rawTriggers.map((t) => triggerMap[t] || t).join(" · ");
  const intendedAction =
    strategy === "RISK_SHIELD"
      ? "Deploy defensive safe action with strict ESL checks"
      : strategy === "COPY_TRADE"
        ? "Run controlled micro-transfer to follow signal direction"
        : strategy === "LIQUIDITY_FOLLOW"
          ? "Execute low-risk liquidity-following micro action"
          : strategy === "ARBITRAGE_SCOUT"
            ? "Scout imbalance with conservative execution size"
            : "Testing low-risk transfer (0.001 ETH)";
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Zap className="h-4 w-4" /> Strategy Engine
      </div>
      <div className="mt-3 text-xs space-y-2">
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground">Selected strategy</div>
          <div className="font-semibold mt-1">{strategy}</div>
        </div>
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground">Confidence</div>
          <div className="mt-1">{confidence}</div>
        </div>
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground">Trigger signals</div>
          <div className="mt-1">{triggers}</div>
        </div>
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground">Intended action</div>
          <div className="mt-1">{intendedAction}</div>
        </div>
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground">Reason</div>
          <div className="mt-1">{reason}</div>
        </div>
      </div>
    </div>
  );
}
