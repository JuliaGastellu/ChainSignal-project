import { WalletInput } from "@/components/WalletInput";
import { AgentTimeline } from "@/components/AgentTimeline";
import { ResultsPanel } from "@/components/ResultsPanel";
import { useAgentSSE } from "@/hooks/useAgentSSE";
import { motion, AnimatePresence } from "framer-motion";
import { Bot, AlertCircle, RotateCcw, Shield, FileText, Monitor } from "lucide-react";
import { useState } from "react";

const Index = () => {
  const { events, results, status, error, execute, reset } = useAgentSSE();
  const [wallet, setWallet] = useState("");
  const [health, setHealth] = useState<string | null>(null);
  const [report, setReport] = useState<any>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [paymentHash, setPaymentHash] = useState("");

  const isLoading = status === "connecting" || status === "streaming";

  const checkHealth = async () => {
    try {
      const res = await fetch("/health");
      const data = await res.json();
      setHealth(JSON.stringify(data, null, 2));
    } catch {
      setHealth("Could not connect to API.");
    }
  };

  const getReport = async () => {
    setReport(null);
    setReportError(null);
    if (!wallet) {
      setReportError("Please enter a wallet address first.");
      return;
    }
    try {
      const headers: Record<string, string> = {};
      if (paymentHash.trim()) {
        headers["X-Payment"] = paymentHash.trim();
      }
      const res = await fetch(`/report/${wallet}`, {
        headers,
      });
      const data = await res.json();
      if (!res.ok) {
        setReportError(`Error ${res.status}: ${data.message || data.error || "403"}`);
      } else {
        setReport(data);
      }
    } catch {
      setReportError("Could not retrieve report.");
    }
  };

  const handleWalletSubmit = (value: string) => {
    setWallet(value);
    execute(value);
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="border-b border-border">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
              <Bot className="h-4 w-4 text-primary" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-foreground leading-none">On-Chain Agent</h1>
              <p className="text-xs text-muted-foreground mt-0.5">Autonomous Financial Analysis</p>
            </div>
          </div>
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
      </header>

      <main className="flex-1 max-w-4xl w-full mx-auto px-6 py-10 space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground"><Monitor className="h-4 w-4" /> API Endpoints</div>
              <span className="text-xs text-muted-foreground uppercase tracking-wider">REST</span>
            </div>
            <div className="space-y-2 text-xs text-muted-foreground">
              <div className="flex items-center justify-between gap-2 p-2 rounded-md bg-secondary/40">
                <div><span className="font-semibold text-foreground">GET /health</span><br/>Check health</div>
                <button onClick={checkHealth} className="text-xs px-2 py-1 rounded bg-primary/10 text-primary">Fetch</button>
              </div>
              <div className="flex items-center justify-between gap-2 p-2 rounded-md bg-secondary/40">
                <div><span className="font-semibold text-foreground">GET /run-agent/{'{wallet}'}</span><br/>Stream agent analysis</div>
                <button onClick={() => handleWalletSubmit(wallet || "0x0000000000000000000000000000000000000000")} className="text-xs px-2 py-1 rounded bg-primary/10 text-primary">Run Stream</button>
              </div>
              <div className="flex items-center justify-between gap-2 p-2 rounded-md bg-secondary/40">
                <div><span className="font-semibold text-foreground">GET /report/{'{wallet_address}'}</span><br/>Protected x402 report</div>
                <button onClick={getReport} className="text-xs px-2 py-1 rounded bg-primary/10 text-primary">Get Report</button>
              </div>
            </div>
            <div className="mt-3 space-y-2 text-xs text-muted-foreground">
              <div>
                <label className="text-[11px] uppercase tracking-wide text-muted-foreground">Current Wallet</label>
                <input
                  value={wallet}
                  onChange={(e) => setWallet(e.target.value)}
                  placeholder="0x..."
                  className="w-full mt-1 border border-border rounded px-2 py-1 text-xs bg-background"
                />
              </div>
              <div>
                <label className="text-[11px] uppercase tracking-wide text-muted-foreground">X-Payment (optional)</label>
                <input
                  value={paymentHash}
                  onChange={(e) => setPaymentHash(e.target.value)}
                  placeholder="0x..."
                  className="w-full mt-1 border border-border rounded px-2 py-1 text-xs bg-background"
                />
              </div>
            </div>
          </div>

          <div className="bg-card border border-border rounded-xl p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground mb-2"><Shield className="h-4 w-4" /> Health & Report</div>
            <div className="text-xs text-muted-foreground">
              <p className="font-medium text-foreground">Health:</p>
              <pre className="mt-1 p-2 bg-secondary/40 border border-border rounded text-[11px] whitespace-pre-wrap break-all">{health || "Click Fetch to see status."}</pre>
            </div>
            <div className="mt-3 text-xs text-muted-foreground">
              <p className="font-medium text-foreground">Report:</p>
              {reportError && <div className="mt-1 text-destructive text-[11px]">{reportError}</div>}
              {report && <pre className="mt-1 p-2 bg-secondary/40 border border-border rounded text-[11px] whitespace-pre-wrap break-all">{JSON.stringify(report, null, 2)}</pre>}
            </div>
          </div>
        </div>

        <div className="bg-card border border-border rounded-xl p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm font-semibold text-foreground"><FileText className="h-4 w-4 inline-block mr-1" /> Run agent</div>
            <span className="text-xs text-muted-foreground">SSE stream</span>
          </div>
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

        <AgentTimeline events={events} isStreaming={status === "streaming"} />
        {results && <ResultsPanel results={results} />}
      </main>

      <footer className="border-t border-border py-4">
        <p className="text-center text-xs text-muted-foreground">Autonomous Agent v1.0 — Real-time on-chain analysis</p>
      </footer>
    </div>
  );
};

export default Index;

