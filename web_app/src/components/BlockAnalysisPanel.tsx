import { useState } from "react";
import { API_BASE } from "@/hooks/useAgentSSE";
import { Layers, Search } from "lucide-react";

type BlockAnalysis = {
  block_number?: number;
  metrics?: {
    tx_count?: number;
    total_value_eth?: number;
    avg_gas_price_wei?: number;
    high_value_transactions?: number;
  };
  recommended_action?: string;
  reasoning?: string;
};

export function BlockAnalysisPanel() {
  const [block, setBlock] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BlockAnalysis | null>(null);

  const run = async () => {
    if (!block.trim()) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/analyze/block/${block.trim()}`);
      const data = await res.json();
      if (!res.ok) {
        setError(data.message || "Block analysis failed");
      } else {
        setResult(data as BlockAnalysis);
      }
    } catch {
      setError("Block analysis failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Layers className="h-4 w-4" /> Block-Level Analysis
      </div>
      <div className="flex items-center gap-2">
        <input
          value={block}
          onChange={(e) => setBlock(e.target.value)}
          placeholder="Block number"
          className="bg-background border border-border rounded px-2 py-1.5 text-xs w-40"
        />
        <button
          onClick={run}
          disabled={loading || !block.trim()}
          className="text-xs px-3 py-1.5 rounded bg-primary text-primary-foreground disabled:opacity-50 flex items-center gap-1"
        >
          <Search className="h-3.5 w-3.5" />
          {loading ? "Running..." : "Analyze Block"}
        </button>
      </div>
      {error && <div className="text-xs text-destructive">{error}</div>}
      {result && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
          <div className="rounded border border-border bg-secondary/30 p-2"><div className="text-muted-foreground">Tx Count</div><div className="font-semibold">{result.metrics?.tx_count ?? "sin datos"}</div></div>
          <div className="rounded border border-border bg-secondary/30 p-2"><div className="text-muted-foreground">Value ETH</div><div className="font-semibold">{result.metrics?.total_value_eth ?? "sin datos"}</div></div>
          <div className="rounded border border-border bg-secondary/30 p-2"><div className="text-muted-foreground">Avg Gas</div><div className="font-semibold">{result.metrics?.avg_gas_price_wei ?? "sin datos"}</div></div>
          <div className="rounded border border-border bg-secondary/30 p-2"><div className="text-muted-foreground">Suggested</div><div className="font-semibold">{result.recommended_action || "monitor"}</div></div>
          <div className="col-span-full rounded border border-border bg-secondary/30 p-2 text-muted-foreground">
            {result.reasoning || "sin datos"}
          </div>
        </div>
      )}
    </div>
  );
}

