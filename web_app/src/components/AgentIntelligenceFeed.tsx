import type { AgentResults } from "@/hooks/useAgentSSE";
import { Brain } from "lucide-react";

export function AgentIntelligenceFeed({ results }: { results: AgentResults | null }) {
  const signals = (results?.detected_signals && results.detected_signals.length > 0)
    ? results.detected_signals
    : [{ type: "EXPLORE_TRIGGER", severity: "low", confidence: 0.55 }];
  const explanations: Record<string, string> = {
    EXPLORE_TRIGGER: "Low signal environment detected. Agent switches to exploration mode.",
    WHALE_ACCUMULATION: "Large accumulation behavior suggests directional conviction.",
    LIQUIDITY_SHIFT: "Liquidity appears to be rotating across venues or contracts.",
    CONTRACT_SPIKE: "Unusual contract interaction spike detected in this cycle.",
    HIGH_VALUE_TRANSFER: "High-value transfer flow indicates capital movement pressure.",
    SUSPICIOUS_PATTERN: "Behavioral anomaly detected. Defensive strategy may be preferred.",
  };
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Brain className="h-4 w-4" /> Agent Intelligence Feed
      </div>
      <div className="mt-3 space-y-2 max-h-48 overflow-auto pr-1">
        {signals.map((s, i) => (
          <div key={i} className="rounded border border-border bg-secondary/30 p-2 text-xs">
            <div className="font-semibold">{String(s.type || "SIGNAL")}</div>
            <div className="text-muted-foreground mt-1">
              Severity: {String(s.severity || "low")} · Confidence: {String(s.confidence ?? "0")}
            </div>
            <div className="text-muted-foreground mt-1">
              {explanations[String(s.type || "EXPLORE_TRIGGER")] || "Signal interpreted from latest autonomous cycle."}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
