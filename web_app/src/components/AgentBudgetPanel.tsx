import { useEffect, useState } from "react";
import { BrowserProvider, parseEther } from "ethers";
import { Wallet, Loader2 } from "lucide-react";
import { API_BASE } from "@/hooks/useAgentSSE";

declare global {
  interface Window {
    ethereum?: unknown;
  }
}

export function AgentBudgetPanel({ wallet }: { wallet: string }) {
  const [budget, setBudget] = useState<any>(null);
  const [amount, setAmount] = useState("0.01");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const refreshBudget = async () => {
    if (!wallet) return;
    try {
      const res = await fetch(`${API_BASE}/agent/budget/${wallet}`);
      const data = await res.json();
      setBudget(data);
    } catch {
      setBudget(null);
    }
  };

  useEffect(() => {
    refreshBudget();
    if (!wallet) return;
    const id = window.setInterval(refreshBudget, 8000);
    return () => window.clearInterval(id);
  }, [wallet]);

  const fundWithMetamask = async () => {
    if (!wallet || !budget?.agent_wallet) return;
    setLoading(true);
    setMsg(null);
    try {
      if (!window.ethereum) throw new Error("MetaMask not available");
      const provider = new BrowserProvider(window.ethereum as any);
      const signer = await provider.getSigner();
      const tx = await signer.sendTransaction({
        to: budget.agent_wallet,
        value: parseEther(amount || "0"),
      });
      await tx.wait();
      const res = await fetch(`${API_BASE}/agent/budget`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ wallet, tx_hash: tx.hash }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || "Funding failed");
      setMsg(`Budget funded: +${data.funded_eth} ETH`);
      await refreshBudget();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Funding failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Wallet className="h-4 w-4" /> Agent Budget
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
        <div className="rounded border border-border bg-secondary/30 p-2"><div className="text-muted-foreground">Balance</div><div className="font-semibold">{budget?.effective_balance_eth ?? budget?.balance_eth ?? 0} ETH</div></div>
        <div className="rounded border border-border bg-secondary/30 p-2"><div className="text-muted-foreground">Spent</div><div className="font-semibold">{budget?.spent_eth ?? 0} ETH</div></div>
        <div className="rounded border border-border bg-secondary/30 p-2"><div className="text-muted-foreground">Mode</div><div className="font-semibold">{budget?.simulation_only ? "Simulation only" : "Live funds"}</div></div>
      </div>
      <div className="flex items-center gap-2">
        <input
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          className="bg-background border border-border rounded px-2 py-1 text-xs w-28"
          placeholder="0.01"
        />
        <button
          onClick={fundWithMetamask}
          disabled={loading || !wallet}
          className="text-xs px-3 py-1.5 rounded bg-primary text-primary-foreground disabled:opacity-50 flex items-center gap-1"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
          Fund Agent
        </button>
      </div>
      <div className="text-[11px] text-muted-foreground break-all">Agent wallet: {budget?.agent_wallet || "Resolving agent wallet from runtime config"}</div>
      {msg && <div className="text-[11px] text-muted-foreground">{msg}</div>}
    </div>
  );
}
