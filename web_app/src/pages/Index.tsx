import { WalletInput } from "@/components/WalletInput";
import { AgentTimeline } from "@/components/AgentTimeline";
import { AnalysisDashboard } from "@/components/AnalysisDashboard";
import { AgentActivityFeed } from "@/components/AgentActivityFeed";
import { HealthStatusCards } from "@/components/HealthStatusCards";
import { AgentSummaryCard } from "@/components/AgentSummaryCard";
import { AgentTreasuryCard } from "@/components/AgentTreasuryCard";
import { useAgentSSE, API_BASE } from "@/hooks/useAgentSSE";
import { motion } from "framer-motion";
import { Bot, AlertCircle, RotateCcw, Monitor, Activity } from "lucide-react";
import { useState, useEffect } from "react";
import { SidePanel } from "@/components/SidePanel";

const Index = () => {
  const { events, results, status, error, execute, reset } = useAgentSSE();
  const [wallet, setWallet] = useState("");
  const [healthRaw, setHealthRaw] = useState<string | null>(null);
  const [healthObj, setHealthObj] = useState<Record<string, any> | null>(null);
  const isLoading = status === "connecting" || status === "streaming";

  const checkHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      const data = await res.json();
      setHealthObj(data);
      setHealthRaw(JSON.stringify(data, null, 2));
    } catch {
      setHealthObj(null);
      setHealthRaw("Could not connect to API.");
    }
  };

  useEffect(() => {
    checkHealth();
    const id = window.setInterval(checkHealth, 8000);
    return () => window.clearInterval(id);
  }, []);

  const handleWalletSubmit = async (value: string) => {
    if (isLoading) return;
    setWallet(value);
    execute(value);
    try {
      await fetch(`${API_BASE}/track-wallet`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ wallet: value, priority: "high", interval_seconds: 60 }),
      });
    } catch {
      return;
    }
  };

  const loopActive = healthObj?.agent_loop === "active";

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="border-b border-border">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="h-9 w-9 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center shadow-sm">
              <Bot className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-foreground leading-none">ChainSignal</h1>
              <p className="text-xs text-muted-foreground mt-0.5">Autonomous Financial Agent Dashboard</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className={`text-[10px] px-2 py-0.5 rounded-full border ${loopActive ? "bg-green-500/10 text-green-500 border-green-500/20" : "bg-secondary text-muted-foreground border-border"}`}>
              {loopActive ? "AGENT ACTIVE" : "AGENT IDLE"}
            </span>
            {status !== "idle" && (
              <button
                onClick={reset}
                className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors px-3 py-1.5 rounded-md border border-border hover:border-primary/30"
              >
                <RotateCcw className="h-3 w-3" />
                New Analysis
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-8 space-y-6">
        <div className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground"><Monitor className="h-4 w-4" /> Agent Status</div>
            <button onClick={checkHealth} className="text-xs px-2 py-1 rounded bg-primary/10 text-primary">Refresh</button>
          </div>
          <HealthStatusCards health={healthObj} />
        </div>

        <div className="bg-card border border-border rounded-xl p-4">
          <div className="text-sm font-semibold text-foreground mb-2"><Activity className="h-4 w-4 inline-block mr-1" /> Analyze & Monitor</div>
          <WalletInput onSubmit={handleWalletSubmit} isLoading={isLoading} />
          {status === "error" && error && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex items-center gap-2 mt-4 p-3 rounded-lg bg-destructive/5 border border-destructive/20"
            >
              <AlertCircle className="h-4 w-4 text-destructive" />
              <p className="text-sm text-destructive">{error}</p>
            </motion.div>
          )}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-10 gap-6 items-start">
          <div className="lg:col-span-7">
            <AgentTimeline events={events} isStreaming={status === "streaming"} />
            {results && <AnalysisDashboard results={results} />}
          </div>
          <div className="lg:col-span-3">
            <div className="space-y-4 lg:sticky lg:top-4 h-fit">
              <AgentSummaryCard results={results} />
              {wallet && <AgentTreasuryCard wallet={wallet} />}
              <SidePanel events={events} />
            </div>
          </div>
        </div>

        <AgentActivityFeed />
      </main>

      <footer className="border-t border-border py-4">
        <div className="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">Autonomous Agent v2.0 — Analyze, Fund, Monitor, Execute</p>
          <div className="flex items-center gap-4 text-[10px] text-muted-foreground uppercase tracking-widest font-medium">
            <span>Sepolia Testnet</span>
            <span>ESL Protected</span>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Index;

