import type { AgentResults } from "@/hooks/useAgentSSE";
import { Brain } from "lucide-react";

export function AgentIntelligenceFeed({ results }: { results: AgentResults | null }) {
  const signals = results?.detected_signals || [];
  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Brain className="h-4 w-4" /> Agent Intelligence Feed
      </div>
      <div className="mt-3 space-y-2 max-h-48 overflow-auto pr-1">
        {signals.length === 0 && <div className="text-xs text-muted-foreground">No signals detected yet.</div>}
        {signals.map((s, i) => (
          <div key={i} className="rounded border border-border bg-secondary/30 p-2 text-xs">
            <div className="font-semibold">{String(s.type || "SIGNAL")}</div>
            <div className="text-muted-foreground mt-1">
              Severity: {String(s.severity || "low")} · Confidence: {String(s.confidence ?? "0")}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

