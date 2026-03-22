import { useEffect, useState } from "react";
import { API_BASE } from "@/hooks/useAgentSSE";
import { Wallet, TrendingUp, Activity, Shield } from "lucide-react";

type AgentState = {
  status?: string;
  budget?: { total_balance_eth?: number };
  pnl?: { estimated_eth?: number };
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
  const lastAction = state?.last_action;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <div className="rounded-xl border border-border bg-card p-3">
        <div className="text-[11px] text-muted-foreground flex items-center gap-1"><Wallet className="h-3.5 w-3.5" /> Agent Balance</div>
        <div className="mt-1 font-semibold">{balance} ETH</div>
      </div>
      <div className="rounded-xl border border-border bg-card p-3">
        <div className="text-[11px] text-muted-foreground flex items-center gap-1"><Activity className="h-3.5 w-3.5" /> Last Action</div>
        <div className="mt-1 font-semibold">{lastAction ? `${lastAction.type || "ACTION"} · ${lastAction.status || "DONE"}` : "First autonomous action is being prepared"}</div>
      </div>
      <div className="rounded-xl border border-border bg-card p-3">
        <div className="text-[11px] text-muted-foreground flex items-center gap-1"><TrendingUp className="h-3.5 w-3.5" /> PnL (approx)</div>
        <div className="mt-1 font-semibold">{pnl} ETH</div>
      </div>
      <div className="rounded-xl border border-border bg-card p-3">
        <div className="text-[11px] text-muted-foreground flex items-center gap-1"><Shield className="h-3.5 w-3.5" /> Status</div>
        <div className="mt-1 font-semibold">{state?.status === "active" ? "Autonomous active" : "Autonomous standby with safeguards"}</div>
      </div>
    </div>
  );
}

