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
  message?: string;
  hint?: string;
  network_latest_block?: number;
  chain_id?: number;
};

export function BlockAnalysisPanel() {
  const [block, setBlock] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BlockAnalysis | null>(null);
  const [latestBlock, setLatestBlock] = useState<number | null>(null);
  const [chainId, setChainId] = useState<number | null>(null);

  const run = async () => {
    if (!block.trim()) return;
    if (!/^\d+$/.test(block.trim())) {
      setError("Use decimal block number only (e.g. 19350000).");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/analyze/block/${block.trim()}`);
      const data = await res.json();
      if (typeof data.network_latest_block === "number") setLatestBlock(data.network_latest_block);
      if (typeof data.chain_id === "number") setChainId(data.chain_id);
      if (!res.ok) {
        const latest = typeof data.network_latest_block === "number" ? ` Latest: ${data.network_latest_block}.` : "";
        const chain = typeof data.chain_id === "number" ? ` Chain: ${data.chain_id}.` : "";
        const hint = typeof data.hint === "string" ? ` ${data.hint}` : "";
        setError(`${data.message || "Block analysis failed"}${latest}${chain}${hint}`);
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
    <div className="bg-card border border-border rounded-xl p-4 space-y-3 min-h-[220px] h-full flex flex-col">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Layers className="h-4 w-4" /> Block-Level Analysis
        </div>
        {(chainId !== null || latestBlock !== null) && (
          <span className="text-[11px] px-2 py-1 rounded-full border border-border bg-secondary/40 text-muted-foreground">
            {chainId !== null ? `Chain ${chainId}` : "Chain ?"} · {latestBlock !== null ? `Latest ${latestBlock}` : "Latest ?"}
          </span>
        )}
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
        {latestBlock !== null && (
          <button
            onClick={() => setBlock(String(latestBlock))}
            className="text-xs px-2 py-1.5 rounded border border-border bg-secondary/40 text-muted-foreground hover:text-foreground"
          >
            Use latest
          </button>
        )}
      </div>
      {error && <div className="text-xs text-destructive">{error}</div>}
      {result ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs mt-auto">
          <div className="rounded border border-border bg-secondary/30 p-2"><div className="text-muted-foreground">Tx Count</div><div className="font-semibold">{result.metrics?.tx_count ?? "sin datos"}</div></div>
          <div className="rounded border border-border bg-secondary/30 p-2"><div className="text-muted-foreground">Value ETH</div><div className="font-semibold">{result.metrics?.total_value_eth ?? "sin datos"}</div></div>
          <div className="rounded border border-border bg-secondary/30 p-2"><div className="text-muted-foreground">Avg Gas</div><div className="font-semibold">{result.metrics?.avg_gas_price_wei ?? "sin datos"}</div></div>
          <div className="rounded border border-border bg-secondary/30 p-2"><div className="text-muted-foreground">Suggested</div><div className="font-semibold">{result.recommended_action || "monitor"}</div></div>
          <div className="col-span-full rounded border border-border bg-secondary/30 p-2 text-muted-foreground">
            {result.reasoning || "sin datos"}
          </div>
        </div>
      ) : (
        <div className="mt-auto text-xs text-muted-foreground rounded border border-dashed border-border p-3">
          Analizá un bloque para detectar densidad de valor, congestión y acción sugerida para el Agent Wallet.
        </div>
      )}
    </div>
  );
}
