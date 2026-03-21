import { WalletInput } from "@/components/WalletInput";
import { AgentTimeline } from "@/components/AgentTimeline";
import { ResultsPanel } from "@/components/ResultsPanel";
import { useAgentSSE, API_BASE } from "@/hooks/useAgentSSE";
import { motion, AnimatePresence } from "framer-motion";
import { Bot, AlertCircle, RotateCcw, Shield, FileText, Monitor, Wallet, CheckCircle2, Loader2 } from "lucide-react";
import { useState, useEffect } from "react";
import { BrowserProvider, Contract } from "ethers";
import { PremiumReportPanel } from "@/components/PremiumReportPanel";
import { SidePanel } from "@/components/SidePanel";
import logo from "../../static/chainsignal_logo_v2.png";

declare global {
  interface Window {
    ethereum?: any;
  }
}

// Minimal ERC20 ABI for transfer
const ERC20_ABI = [
  "function transfer(address to, uint256 amount) public returns (bool)",
  "function decimals() public view returns (uint8)",
];

const Index = () => {
  const { events, results, status, error, execute, reset } = useAgentSSE();
  const [wallet, setWallet] = useState("");
  const [health, setHealth] = useState<string | null>(null);
  const [report, setReport] = useState<any>(null);
  const [reportError, setReportError] = useState<string | null>(null);
  const [paymentHash, setPaymentHash] = useState("");
  const [isPaying, setIsPaying] = useState(false);
  const [challenge, setChallenge] = useState<any>(null);

  const isLoading = status === "connecting" || status === "streaming";
  const isSimulation = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";

  const checkHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      const data = await res.json();
      setHealth(JSON.stringify(data, null, 2));
    } catch {
      setHealth("Could not connect to API.");
    }
  };

  const payWithMetaMask = async () => {
    if (!challenge) return;
    setIsPaying(true);
    setReportError(null);

    try {
      if (!window.ethereum) {
        throw new Error("MetaMask is not installed.");
      }

      const provider = new BrowserProvider(window.ethereum);
      const signer = await provider.getSigner();
      
      // Verify network
      const network = await provider.getNetwork();
      if (Number(network.chainId) !== challenge.chain_id) {
        try {
          await window.ethereum.request({
            method: 'wallet_switchEthereumChain',
            params: [{ chainId: `0x${challenge.chain_id.toString(16)}` }],
          });
        } catch (switchError: any) {
          throw new Error(`Please switch to ${challenge.chain} (Chain ID: ${challenge.chain_id})`);
        }
      }

      const usdcContract = new Contract(challenge.token_address, ERC20_ABI, signer);
      
      // Amount is already in base units (string from API)
      const tx = await usdcContract.transfer(challenge.recipient, challenge.amount);
      
      console.log("Transaction sent:", tx.hash);
      setPaymentHash(tx.hash);
      
      // Wait for confirmation (optional but recommended for better UX)
      // await tx.wait(1);
      
      // Auto-retry report with the new hash
      setTimeout(() => getReport(tx.hash), 1000);

    } catch (err: any) {
      console.error("Payment error:", err);
      setReportError(err.reason || err.message || "Payment failed");
    } finally {
      setIsPaying(false);
    }
  };

  const getReport = async (overrideHash?: string) => {
    setReport(null);
    setReportError(null);
    setChallenge(null);

    const activeHash = overrideHash || paymentHash;

    if (!wallet) {
      setReportError("Please enter a wallet address first.");
      return;
    }
    try {
      const headers: Record<string, string> = {};
      if (activeHash.trim()) {
        headers["X-Payment"] = activeHash.trim();
      }
      const res = await fetch(`${API_BASE}/report/${wallet}`, {
        headers,
      });
      const data = await res.json();
      
      if (res.status === 402) {
        setChallenge(data.challenge);
        setReportError(data.message || "Payment Required");
      } else if (!res.ok) {
        setReportError(`Error ${res.status}: ${data.message || data.error || "403"}`);
      } else {
        setReport(data);
      }
    } catch {
      setReportError("Could not retrieve report.");
    }
  };

  const handleWalletSubmit = (value: string) => {
    if (isLoading) return;
    setWallet(value);
    execute(value);
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="border-b border-border">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="h-9 w-9 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center shadow-sm">
              <Bot className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-foreground leading-none">ChainSignal</h1>
              <p className="text-xs text-muted-foreground mt-0.5">On-Chain Risk Analysis</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {isSimulation && (
              <span className="text-[10px] bg-yellow-500/10 text-yellow-500 border border-yellow-500/20 px-2 py-0.5 rounded-full font-medium">
                SIMULATION MODE
              </span>
            )}
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

      <main className="flex-1 max-w-4xl w-full mx-auto px-6 py-10 space-y-6">
        {challenge && (
          <motion.div 
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-4"
          >
            {challenge.simulation_mode && (
              <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <AlertCircle className="h-5 w-5 text-yellow-600 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-semibold text-yellow-700">
                      ⚠️ SIMULATION MODE
                    </p>
                    <p className="text-xs text-yellow-600 mt-1">
                      This is a test environment. Payments are <strong>NOT validated on-chain</strong>. Any valid transaction hash will be accepted.
                    </p>
                    <p className="text-xs text-yellow-600 mt-2">
                      In production, all payments must be valid USDC transfers verified on the Sepolia blockchain.
                    </p>
                  </div>
                </div>
              </div>
            )}
            <div 
              className="bg-primary/5 border border-primary/20 rounded-xl p-6 shadow-sm"
            >
              <div className="flex items-start gap-4">
                <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                  <Wallet className="h-5 w-5 text-primary" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-bold text-foreground">Payment Required (x402)</h3>
                  <p className="text-xs text-muted-foreground mt-1">
                    This report is protected. Please pay <strong>{challenge.formatted_amount}</strong> to access it.
                  </p>
                <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-[11px]">
                  <div className="space-y-1">
                    <p className="text-muted-foreground uppercase tracking-wider">Network</p>
                    <p className="font-mono text-foreground">{challenge.chain.toUpperCase()} (ID: {challenge.chain_id})</p>
                  </div>
                  <div className="space-y-1">
                    <p className="text-muted-foreground uppercase tracking-wider">Token</p>
                    <p className="font-mono text-foreground">{challenge.token} (USDC)</p>
                  </div>
                  <div className="md:col-span-2 space-y-1">
                    <p className="text-muted-foreground uppercase tracking-wider">Recipient</p>
                    <p className="font-mono text-foreground break-all">{challenge.recipient}</p>
                  </div>
                </div>
                <div className="mt-6 flex items-center gap-3">
                  <button 
                    onClick={payWithMetaMask}
                    disabled={isPaying}
                    className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-xs font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
                  >
                    {isPaying ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wallet className="h-3 w-3" />}
                    Pay with MetaMask
                  </button>
                  <p className="text-[10px] text-muted-foreground italic">
                    * Payments are verified on-chain. Only USDC on Sepolia is accepted.
                  </p>
                </div>
              </div>
            </div>
            </div>
          </motion.div>
        )}

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
                <button
                  onClick={() => handleWalletSubmit(wallet || "0x0000000000000000000000000000000000000000")}
                  disabled={isLoading}
                  className={`text-xs px-2 py-1 rounded ${
                    isLoading
                      ? "bg-muted text-muted-foreground cursor-not-allowed"
                      : "bg-primary/10 text-primary hover:bg-primary/15"
                  }`}
                >
                  {isLoading ? "Running..." : "Run Stream"}
                </button>
              </div>
              <div className="flex items-center justify-between gap-2 p-2 rounded-md bg-secondary/40">
                <div><span className="font-semibold text-foreground">GET /report/{'{wallet_address}'}</span><br/>Protected x402 report</div>
                <button onClick={() => getReport()} className="text-xs px-2 py-1 rounded bg-primary/10 text-primary">Get Report</button>
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
                <div className="relative">
                  <input
                    value={paymentHash}
                    onChange={(e) => setPaymentHash(e.target.value)}
                    placeholder="0x..."
                    className="w-full mt-1 border border-border rounded px-2 py-1 pr-8 text-xs bg-background"
                  />
                  {paymentHash && (
                    <CheckCircle2 className="absolute right-2 top-2.5 h-3 w-3 text-green-500" />
                  )}
                </div>
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
              {reportError && (
                <div className="mt-1 flex items-center gap-1.5 text-destructive text-[11px]">
                  <AlertCircle className="h-3 w-3" />
                  {reportError}
                </div>
              )}
              {report && (
                <div className="mt-1 animate-in">
                  <div className="mb-2 flex items-center gap-1.5 text-green-500 text-[10px] font-bold uppercase">
                    <CheckCircle2 className="h-3 w-3" /> Payment Verified
                  </div>
                  <PremiumReportPanel report={report} />
                </div>
              )}
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

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
          <div className="lg:col-span-2">
            <AgentTimeline events={events} isStreaming={status === "streaming"} />
          </div>
          <div className="lg:col-span-1">
            <SidePanel events={events} />
          </div>
        </div>

        {results && <ResultsPanel results={results} />}
      </main>

      <footer className="border-t border-border py-4">
        <div className="max-w-4xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-2">
          <p className="text-xs text-muted-foreground">Autonomous Agent v1.0 — Real-time on-chain analysis</p>
          <div className="flex items-center gap-4 text-[10px] text-muted-foreground uppercase tracking-widest font-medium">
            <span>Sepolia Testnet</span>
            <span>USDC Protected</span>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Index;

