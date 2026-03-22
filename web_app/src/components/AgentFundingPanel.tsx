import { useEffect, useMemo, useState } from "react";
import { BrowserProvider, parseEther } from "ethers";
import { API_BASE } from "@/hooks/useAgentSSE";
import { Wallet, Loader2, Copy, CheckCircle2, AlertCircle } from "lucide-react";

declare global {
  interface Window {
    ethereum?: unknown;
  }
}

type AgentState = {
  budget?: { agent_wallet?: string; total_balance_eth?: number };
};

type FundingStatus = "idle" | "pending_tx" | "awaiting_balance" | "confirmed" | "error";

export function AgentFundingPanel({
  targetWallet,
  onFundingActivated,
}: {
  targetWallet?: string;
  onFundingActivated?: () => void;
}) {
  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [amount, setAmount] = useState("0.01");
  const [status, setStatus] = useState<FundingStatus>("idle");
  const [message, setMessage] = useState<string>("Ready to fund autonomous agent.");
  const [polling, setPolling] = useState(false);
  const [copied, setCopied] = useState(false);

  const loadState = async () => {
    try {
      const res = await fetch(`${API_BASE}/agent/state`);
      const data = await res.json();
      setAgentState(data as AgentState);
    } catch {
      setAgentState(null);
    }
  };

  useEffect(() => {
    loadState();
    const id = window.setInterval(loadState, 8000);
    return () => window.clearInterval(id);
  }, []);

  const agentWallet = agentState?.budget?.agent_wallet || "";
  const balance = Number(agentState?.budget?.total_balance_eth ?? 0);

  const statusText = useMemo(() => {
    if (status === "pending_tx") return "Transaction submitted. Waiting for confirmation...";
    if (status === "awaiting_balance") return "Transaction submitted. Waiting for funds...";
    if (status === "confirmed") return message;
    if (status === "error") return message;
    return message;
  }, [status, message]);

  const copyAgentWallet = async () => {
    if (!agentWallet) return;
    try {
      await navigator.clipboard.writeText(agentWallet);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  const handleFundAgent = async () => {
    if (!agentWallet) {
      setStatus("error");
      setMessage("Agent wallet is unavailable. Refresh state and try again.");
      return;
    }
    if (!window.ethereum) {
      setStatus("error");
      setMessage("MetaMask is not installed.");
      return;
    }

    setStatus("idle");
    setMessage("Open MetaMask to approve funding transaction.");

    try {
      const baselineBalance = balance;
      const provider = new BrowserProvider(window.ethereum as any);
      await provider.send("eth_requestAccounts", []);
      const signer = await provider.getSigner();
      const fromAddress = await signer.getAddress();

      const tx = await signer.sendTransaction({
        from: fromAddress,
        to: agentWallet,
        value: parseEther(amount || "0"),
      });

      setStatus("pending_tx");
      setMessage("Transaction submitted. Waiting for confirmation...");

      let fundingRegistered = false;
      const firstRegister = await fetch(`${API_BASE}/agent/budget`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ wallet: targetWallet || fromAddress, tx_hash: tx.hash }),
      });
      if (firstRegister.ok) fundingRegistered = true;
      setStatus("awaiting_balance");
      setMessage("Transaction submitted. Waiting for funds...");

      setPolling(true);
      let attempts = 0;
      const timer = window.setInterval(async () => {
        attempts += 1;
        try {
          if (!fundingRegistered) {
            const registerRes = await fetch(`${API_BASE}/agent/budget`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ wallet: targetWallet || fromAddress, tx_hash: tx.hash }),
            });
            if (registerRes.ok) fundingRegistered = true;
          }
          const res = await fetch(`${API_BASE}/agent/state`);
          const next = await res.json();
          const nextBalance = Number(next?.budget?.total_balance_eth ?? 0);
          setAgentState(next as AgentState);
          if (nextBalance > baselineBalance) {
            window.clearInterval(timer);
            setPolling(false);
            const fundedDelta = Math.max(0, nextBalance - baselineBalance);
            setStatus("confirmed");
            setMessage(`Funds received: +${fundedDelta.toFixed(6)} ETH · Autonomous execution activated.`);
            if (targetWallet) {
              await fetch(`${API_BASE}/agent/execute`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ wallet: targetWallet }),
              });
            }
            onFundingActivated?.();
          }
          if (attempts >= 20) {
            window.clearInterval(timer);
            setPolling(false);
            setStatus("awaiting_balance");
            setMessage("Funding transaction submitted. Balance sync may take a few more seconds.");
          }
        } catch {
          if (attempts >= 20) {
            window.clearInterval(timer);
            setPolling(false);
          }
        }
      }, 3000);
    } catch (error: any) {
      const code = error?.code;
      const rejected = code === 4001 || String(error?.message || "").toLowerCase().includes("rejected");
      setStatus("error");
      setMessage(rejected ? "Transaction rejected in MetaMask." : "Funding failed. Please retry.");
      setPolling(false);
    }
  };

  return (
    <div className="bg-card border border-border rounded-xl p-4 space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Wallet className="h-4 w-4" /> Fund Agent Wallet
      </div>
      <div className="rounded border border-border bg-secondary/30 p-2 text-xs">
        <div className="text-muted-foreground">Agent wallet (executor)</div>
        <div className="mt-1 flex items-center gap-2">
          <span className="font-mono truncate">{agentWallet || "Loading agent wallet..."}</span>
          <button
            onClick={copyAgentWallet}
            className="px-2 py-1 rounded border border-border bg-background text-[10px] flex items-center gap-1"
            type="button"
          >
            <Copy className="h-3 w-3" /> {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground">Current balance</div>
          <div className="font-semibold mt-1">{balance} ETH</div>
        </div>
        <div className="rounded border border-border bg-secondary/30 p-2">
          <div className="text-muted-foreground">Funding amount</div>
          <input
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="mt-1 bg-background border border-border rounded px-2 py-1 text-xs w-full"
            placeholder="0.01"
          />
        </div>
      </div>
      <button
        onClick={handleFundAgent}
        disabled={status === "pending_tx" || status === "awaiting_balance" || polling || !agentWallet}
        className="w-full text-xs px-3 py-2 rounded bg-primary text-primary-foreground disabled:opacity-50 flex items-center justify-center gap-2"
        type="button"
      >
        {status === "pending_tx" || status === "awaiting_balance" || polling ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
        Fund Agent
      </button>
      <div className={`text-[11px] flex items-center gap-1 ${status === "error" ? "text-destructive" : "text-muted-foreground"}`}>
        {status === "error" ? <AlertCircle className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
        {statusText}
      </div>
    </div>
  );
}
