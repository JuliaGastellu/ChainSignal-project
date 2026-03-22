import { useEffect, useState } from "react";
import { API_BASE } from "@/hooks/useAgentSSE";
import { Radar } from "lucide-react";

type RadarWallet = {
  wallet: string;
  priority: string;
  last_risk_score?: number;
  last_evaluation?: string | null;
};

export function WalletRadarPanel() {
  const [items, setItems] = useState<RadarWallet[]>([]);

  const fetchRadar = async () => {
    try {
      const res = await fetch(`${API_BASE}/agent/radar`);
      const data = await res.json();
      setItems(Array.isArray(data.wallets) ? data.wallets : []);
    } catch {
      setItems([]);
    }
  };

  useEffect(() => {
    fetchRadar();
    const id = window.setInterval(fetchRadar, 9000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Radar className="h-4 w-4" /> Wallet Radar
      </div>
      <div className="mt-3 space-y-2 max-h-48 overflow-auto pr-1">
        {items.length === 0 && <div className="text-xs text-muted-foreground">No tracked wallets yet.</div>}
        {items.map((w) => (
          <div key={w.wallet} className="rounded border border-border bg-secondary/30 p-2 text-xs">
            <div className="font-mono truncate">{w.wallet}</div>
            <div className="text-muted-foreground mt-1">
              Priority: {w.priority} · Risk: {w.last_risk_score ?? 0}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

