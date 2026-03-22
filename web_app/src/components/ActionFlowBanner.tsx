import { ArrowRight } from "lucide-react";

export function ActionFlowBanner() {
  return (
    <div className="bg-card border border-border rounded-xl p-3">
      <div className="text-xs text-muted-foreground">Autonomous Value Loop</div>
      <div className="mt-2 flex items-center gap-2 text-xs">
        <span className="px-2 py-1 rounded border border-border bg-secondary/40">Analyzed wallet/block</span>
        <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="px-2 py-1 rounded border border-border bg-secondary/40">Learned signals + strategy</span>
        <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="px-2 py-1 rounded border border-border bg-secondary/40">Acted with Agent Wallet</span>
      </div>
    </div>
  );
}

