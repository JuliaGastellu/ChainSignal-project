import { Brain, Shield, Activity, Sparkles } from "lucide-react";
import type { AgentResults } from "@/hooks/useAgentSSE";

function normalizeConfidence(confidence?: number) {
  if (confidence === undefined || Number.isNaN(confidence)) return undefined;
  return confidence > 1 ? confidence : confidence * 100;
}

export function AgentSummaryCard({ results }: { results: AgentResults | null }) {
  const decision = results?.decision_code || results?.agent_decision || "Not triggered";
  const intent = results?.agent_intent || "Autonomous safety monitoring is active";
  const confidence = normalizeConfidence(results?.confidence);
  const risk = results?.risk_score;
  const reasoning = results?.reasoning || results?.why_not_acting || "Agent is evaluating signal quality and preserving safe execution posture.";
  const moved = results?.moved_value_eth;

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Brain className="h-4 w-4" /> Agent Summary
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span className="px-2 py-1 rounded-full border border-border bg-secondary/40 font-semibold">{decision}</span>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground">Intent</div>
          <div className="font-medium mt-1">{intent}</div>
        </div>
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground">Confidence</div>
          <div className="font-medium mt-1">{confidence === undefined ? "Calibrating" : `${Math.round(confidence)}%`}</div>
        </div>
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground flex items-center gap-1"><Shield className="h-3 w-3" /> Risk</div>
          <div className="font-medium mt-1">{risk === undefined ? "Calibrating" : risk}</div>
        </div>
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground flex items-center gap-1"><Activity className="h-3 w-3" /> Source</div>
          <div className="font-medium mt-1">{results?.source === "loop" ? "Autonomous Agent" : "User Triggered"}</div>
        </div>
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground">Last action executed</div>
          <div className="font-medium mt-1">{results?.selected_strategy || "Waiting for first trigger"}</div>
        </div>
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground">Capital moved</div>
          <div className="font-medium mt-1">{moved === undefined ? "0 ETH" : `${moved} ETH`}</div>
        </div>
      </div>
      <div className="rounded border border-border bg-secondary/30 p-2">
        <div className="text-muted-foreground text-xs flex items-center gap-1"><Sparkles className="h-3 w-3" /> Reasoning</div>
        <div className="text-xs mt-1">{reasoning}</div>
      </div>
    </div>
  );
}
