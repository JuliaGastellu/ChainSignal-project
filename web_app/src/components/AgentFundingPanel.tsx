import { useEffect, useMemo, useState } from "react";
import { BrowserProvider, parseEther } from "ethers";
import { API_BASE } from "@/hooks/useAgentSSE";
import { Wallet, Loader2, Copy, CheckCircle2, AlertCircle } from "lucide-react";

declare global {
  interface Window {
    ethereum?: any;
  }
}

type AgentState = {
  budget?: { agent_wallet?: string; total_balance_eth?: number };
};

type FundingStatus = "idle" | "pending_tx" | "awaiting_balance" | "confirmed" | "error";
const DEFAULT_FUND_AMOUNT = ((import.meta.env.VITE_DEFAULT_FUND_AMOUNT as string | undefined)?.trim() || "0.01");

export function AgentFundingPanel({
  targetWallet,
  onFundingActivated,
}: {
  targetWallet?: string;
  onFundingActivated?: () => void;
}) {
  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [agentWallet, setAgentWallet] = useState<string>("");
  const [amount, setAmount] = useState(DEFAULT_FUND_AMOUNT);
  const [status, setStatus] = useState<FundingStatus>("idle");
  const [message, setMessage] = useState<string>("Ready to fund autonomous agent.");
  const [txHash, setTxHash] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const [copied, setCopied] = useState(false);

  const loadState = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      const data = await res.json();
      setAgentState(data as AgentState);
    } catch {
      setAgentState(null);
    }
  };

  const loadAddress = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      const data = await res.json();
      setAgentWallet(data.agent_budget?.agent_wallet || "");
    } catch (err) {
      console.error("Failed to load agent address:", err);
    }
  };

  useEffect(() => {
    loadState();
    loadAddress();
    const id = window.setInterval(loadState, 8000);
    return () => window.clearInterval(id);
  }, []);

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
      setMessage("Agent address not loaded. Please wait and retry.");
      return;
    }

    if (!window.ethereum) {
      setMessage("MetaMask is not installed or not accessible.");
      return;
    }

    try {
      setMessage("Requesting MetaMask access...");

      // Request accounts
      await (window.ethereum as any).request({ method: "eth_requestAccounts" });

      // Switch to Sepolia
      try {
        await (window.ethereum as any).request({
          method: "wallet_switchEthereumChain",
          params: [{ chainId: "0xaa36a7" }],
        });
      } catch (switchError: any) {
        if (switchError.code === 4902) {
          await (window.ethereum as any).request({
            method: "wallet_addEthereumChain",
            params: [{
              chainId: "0xaa36a7",
              chainName: "Sepolia",
              nativeCurrency: { name: "ETH", symbol: "ETH", decimals: 18 },
              rpcUrls: ["https://rpc.sepolia.org"],
              blockExplorerUrls: ["https://sepolia.etherscan.io"],
            }],
          });
        }
      }

      // Get sender address
      const accounts = await (window.ethereum as any).request({ method: "eth_accounts" });
      const from = accounts[0];

      // Convert amount to hex wei
      const amountEth = parseFloat(amount) || 0.01;
      const amountWei = BigInt(Math.floor(amountEth * 1e18));
      const amountHex = "0x" + amountWei.toString(16);

      setMessage("Confirm transaction in MetaMask...");

      // Send transaction
      const txHash = await (window.ethereum as any).request({
        method: "eth_sendTransaction",
        params: [{
          from,
          to: agentWallet,
          value: amountHex,
        }],
      });

      setTxHash(txHash);
      setMessage(`Transaction submitted: ${txHash}`);
      setStatus("awaiting_balance");

      // Register with API
      try {
        await fetch(`${API_BASE}/agent/budget`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            wallet: agentWallet,
            tx_hash: txHash
          }),
        });
      } catch (err) {
        console.warn("Budget registration failed:", err);
      }

      // 60s aggressive polling
      const startBalance = balance;
      const startTime = Date.now();
      setPolling(true);

      const pollInterval = window.setInterval(async () => {
        const elapsed = Date.now() - startTime;
        if (elapsed > 60000) {
          window.clearInterval(pollInterval);
          setPolling(false);
          setStatus("idle");
          return;
        }

        try {
          const res = await fetch(`${API_BASE}/health`);
          const data = await res.json();
          const newBalance = Number(data.agent_budget?.total_balance_eth ?? 0);
          
          if (newBalance > startBalance) {
            setAgentState(data as AgentState);
            window.clearInterval(pollInterval);
            setPolling(false);
            setStatus("confirmed");
            setMessage("Funds received and confirmed!");
          }
        } catch (err) {
          console.error("Polling error:", err);
        }
      }, 3000);

    } catch (error: any) {
      if (error?.code === 4001) {
        setMessage("Transaction rejected by user.");
      } else {
        setMessage(`Error: ${error?.message || "Unknown error"}`);
      }
      setStatus("error");
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
            placeholder={DEFAULT_FUND_AMOUNT}
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
