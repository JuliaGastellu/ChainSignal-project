import { useEffect, useState } from "react";
import { API_BASE } from "@/hooks/useAgentSSE";
import { History, ArrowRightLeft, Send, ShieldAlert, Eye } from "lucide-react";

type ActivityItem = {
  wallet?: string;
  timestamp?: number;
  type?: string;
  status?: string;
  tx_hash?: string;
  value_moved_eth?: number;
  reason?: string;
  strategy?: string;
  explorer?: string | null;
};

export function AgentActivityFeed() {
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [stats, setStats] = useState<{ total_executions?: number; total_value_moved?: number }>({});

  const fetchActivity = async () => {
    try {
      const res = await fetch(`${API_BASE}/agent-activity`);
      const data = await res.json();
      setItems(Array.isArray(data.recent_actions) ? data.recent_actions : []);
      setStats(data.stats || {});
    } catch {
      setItems([]);
    }
  };

  useEffect(() => {
    fetchActivity();
    const id = window.setInterval(fetchActivity, 8000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="bg-card border border-border rounded-xl p-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <History className="h-4 w-4" /> Agent Activity Feed
        </div>
        <div className="text-[11px] text-muted-foreground">
          Exec: {stats.total_executions || 0} · Moved: {stats.total_value_moved || 0} ETH
        </div>
      </div>
      <div className="mt-2 text-[11px] text-muted-foreground">
        Last action executed: {items[0] ? `${items[0].type || "ACTION"} (${items[0].status || "UNKNOWN"})` : "Agent has not executed yet (waiting for first trigger)"}
      </div>
      <div className="mt-3 space-y-2 max-h-72 overflow-auto pr-1">
        {items.length === 0 && <div className="text-xs text-muted-foreground">Agent has not executed yet (waiting for first trigger).</div>}
        {items.map((a, i) => (
          <div key={`${a.tx_hash || "action"}-${i}`} className="rounded border border-border bg-secondary/30 p-2">
            <div className="flex items-center justify-between text-xs">
              <div className="font-semibold flex items-center gap-1.5">
                {a.type === "SWAP" ? <ArrowRightLeft className="h-3.5 w-3.5 text-blue-500" /> : a.type === "TRANSFER" ? <Send className="h-3.5 w-3.5 text-green-500" /> : a.status === "FAILED" ? <ShieldAlert className="h-3.5 w-3.5 text-yellow-600" /> : <Eye className="h-3.5 w-3.5 text-primary" />}
                {a.type || "MONITORING"} · {a.status || "SKIPPED"}
              </div>
              <div className="text-muted-foreground">{a.timestamp ? new Date(a.timestamp * 1000).toLocaleString() : "Not triggered"}</div>
            </div>
            <div className="text-[11px] text-muted-foreground mt-1">{a.reason || "No data available yet"}</div>
            <div className="text-[11px] mt-1 text-muted-foreground">Strategy: {a.strategy || "EXPLORE"}</div>
            <div className="text-[11px] mt-1">Moved: {a.value_moved_eth || 0} ETH</div>
            {a.explorer && (
              <a href={a.explorer} target="_blank" rel="noreferrer" className="text-[11px] text-primary hover:underline">
                View tx
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
