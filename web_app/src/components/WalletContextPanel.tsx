import { useEffect, useState } from "react";
import { API_BASE } from "@/hooks/useAgentSSE";
import { Wallet, Bot, Shield } from "lucide-react";

type BudgetInfo = {
  wallet?: string;
  agent_wallet?: string;
  balance_eth?: number;
  simulation_only?: boolean;
};

export function WalletContextPanel({ targetWallet }: { targetWallet: string }) {
  const [budget, setBudget] = useState<BudgetInfo | null>(null);

  useEffect(() => {
    if (!targetWallet) {
      setBudget(null);
      return;
    }
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(`${API_BASE}/agent/budget/${targetWallet}`);
        const data = (await res.json()) as BudgetInfo;
        if (!cancelled) setBudget(data);
      } catch {
        if (!cancelled) setBudget(null);
      }
    };
    load();
    const id = window.setInterval(load, 8000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [targetWallet]);

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3">
      <div className="text-sm font-semibold text-foreground">Wallet Context</div>
      <div className="rounded-lg border border-border bg-secondary/30 p-3 text-xs">
        <div className="text-muted-foreground flex items-center gap-1"><Wallet className="h-3.5 w-3.5" /> Target Wallet (Analyzed)</div>
        <div className="font-mono mt-1 break-all">{targetWallet || "Not selected yet"}</div>
      </div>
      <div className="rounded-lg border border-border bg-secondary/30 p-3 text-xs">
        <div className="text-muted-foreground flex items-center gap-1"><Bot className="h-3.5 w-3.5" /> Agent Wallet (Executor)</div>
        <div className="font-mono mt-1 break-all">{budget?.agent_wallet || "Agent wallet is resolving from runtime context"}</div>
      </div>
      <div className="rounded-lg border border-border bg-secondary/30 p-3 text-xs">
        <div className="text-muted-foreground flex items-center gap-1"><Shield className="h-3.5 w-3.5" /> Agent Balance Source</div>
        <div className="mt-1">
          {budget ? `${budget.balance_eth ?? 0} ETH ${budget.simulation_only ? "(Simulation only)" : "(Execution enabled)"}` : "Balance telemetry is syncing with treasury"}
        </div>
      </div>
      <div className="text-[11px] text-muted-foreground">
        Target Wallet is read-only analysis input. Agent Wallet is the execution wallet using funded budget.
      </div>
    </div>
  );
}
