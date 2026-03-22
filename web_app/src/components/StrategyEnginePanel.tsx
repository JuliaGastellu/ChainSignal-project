import type { AgentResults } from "@/hooks/useAgentSSE";
import { Zap } from "lucide-react";

export function StrategyEnginePanel({ results }: { results: AgentResults | null }) {
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Zap className="h-4 w-4" /> Strategy Engine
      </div>
      <div className="mt-3 text-xs space-y-2">
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground">Selected strategy</div>
          <div className="font-semibold mt-1">{results?.selected_strategy || "EXPLORE"}</div>
        </div>
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground">Reason</div>
          <div className="mt-1">{results?.strategy_reason || "Awaiting signal selection."}</div>
        </div>
      </div>
    </div>
  );
}

