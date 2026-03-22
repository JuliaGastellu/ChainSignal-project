import { useEffect, useState } from "react";
import { API_BASE } from "@/hooks/useAgentSSE";
import { Wallet, TrendingUp, Activity, Shield } from "lucide-react";

type AgentState = {
  status?: string;
  budget?: { total_balance_eth?: number };
  pnl?: { estimated_eth?: number };
  stats?: { total_value_moved?: number };
  last_action?: { type?: string; status?: string; strategy?: string };
};

export function AgentHeroSection() {
  const [state, setState] = useState<AgentState | null>(null);

  const load = async () => {
    try {
      const res = await fetch(`${API_BASE}/agent/state`);
      const data = await res.json();
      setState(data as AgentState);
    } catch {
      setState(null);
    }
  };

  useEffect(() => {
    load();
    const id = window.setInterval(load, 7000);
    return () => window.clearInterval(id);
  }, []);

  const balance = state?.budget?.total_balance_eth ?? 0;
  const pnl = state?.pnl?.estimated_eth ?? 0;
  const moved = state?.stats?.total_value_moved ?? 0;
  const lastAction = state?.last_action;
  const hasFunds = balance > 0;
  const statusLabel = hasFunds ? "ACTIVE" : "FUNDING_REQUIRED";
  const lastActionLabel = lastAction
    ? `${lastAction.type || "ACTION"} · ${lastAction.status || "DONE"}`
    : hasFunds
      ? "Preparing first action..."
      : "Fund agent to unlock first autonomous action";

  return (
    <div className="space-y-2">
      {balance <= 0 && (
        <div className="rounded-xl border border-yellow-500/30 bg-yellow-500/10 p-3 text-xs text-yellow-800">
          Fund the agent to activate autonomous execution.
        </div>
      )}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
      <div className="rounded-xl border border-border bg-card p-3">
        <div className="text-[11px] text-muted-foreground flex items-center gap-1"><Wallet className="h-3.5 w-3.5" /> Agent Balance</div>
        <div className="mt-1 font-semibold">{balance} ETH</div>
      </div>
      <div className="rounded-xl border border-border bg-card p-3">
        <div className="text-[11px] text-muted-foreground flex items-center gap-1"><Activity className="h-3.5 w-3.5" /> Last Action</div>
        <div className="mt-1 font-semibold">{lastActionLabel}</div>
      </div>
      <div className="rounded-xl border border-border bg-card p-3">
        <div className="text-[11px] text-muted-foreground flex items-center gap-1"><TrendingUp className="h-3.5 w-3.5" /> PnL (approx)</div>
        <div className="mt-1 font-semibold">{pnl} ETH</div>
      </div>
      <div className="rounded-xl border border-border bg-card p-3">
        <div className="text-[11px] text-muted-foreground flex items-center gap-1"><TrendingUp className="h-3.5 w-3.5" /> Capital Moved</div>
        <div className="mt-1 font-semibold">{moved} ETH</div>
      </div>
      <div className="rounded-xl border border-border bg-card p-3">
        <div className="text-[11px] text-muted-foreground flex items-center gap-1"><Shield className="h-3.5 w-3.5" /> Status</div>
        <div className="mt-1 font-semibold">{statusLabel}</div>
      </div>
    </div>
    </div>
  );
}
